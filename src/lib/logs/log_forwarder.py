#     Copyright 2024 Dynatrace LLC
#
#     Licensed under the Apache License, Version 2.0 (the "License");
#     you may not use this file except in compliance with the License.
#     You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#     Unless required by applicable law or agreed to in writing, software
#     distributed under the License is distributed on an "AS IS" BASIS,
#     WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#     See the License for the specific language governing permissions and
#     limitations under the License.

import asyncio
from asyncio import Queue
import time
from typing import List, Tuple

from lib.clientsession_provider import init_gcp_client_session, init_dt_client_session
from lib.context import LoggingContext, LogsProcessingContext, create_logs_context
from lib.credentials import create_token
from lib.instance_metadata import InstanceMetadata
from lib.logs.dynatrace_client import DynatraceClient
from lib.logs.gcp_client import GCPClient
from lib.logs.log_forwarder_variables import (
    LOGS_SUBSCRIPTION_ID,
    LOGS_SUBSCRIPTION_PROJECT,
    MAX_SFM_MESSAGES_PROCESSED,
    PROCESSING_WORKERS,
    REQUEST_BODY_MAX_SIZE,
    NUMBER_OF_CONCURRENT_MESSAGE_PULL_COROUTINES,
    NUMBER_OF_CONCURRENT_PUSH_COROUTINES,
)


from lib.logs.log_self_monitoring import create_sfm_loop, put_sfm_into_queue
from lib.logs.logs_processor import prepare_context_and_process_message, prepare_batches, LogBatch
from lib.utilities import chunks


def run_logs_wrapper(logging_context, instance_metadata):
    asyncio.run(run_logs(logging_context, instance_metadata))


async def run_logs(logging_context: LoggingContext, instance_metadata: InstanceMetadata):
    if not LOGS_SUBSCRIPTION_PROJECT or not LOGS_SUBSCRIPTION_ID:
        raise Exception(
            "Cannot start pubsub streaming pull - GCP_PROJECT or LOGS_SUBSCRIPTION_ID are not defined"
        )

    sfm_queue = Queue(MAX_SFM_MESSAGES_PROCESSED)
    tasks = []

    # initiate http client for both GCP and DT
    async with init_gcp_client_session() as gcp_session:
        token = await create_token(logging_context, gcp_session)
        if token is None:
            raise Exception("Cannot start pubsub streaming pull - 'Failed to fetch token")
        gcp_client = GCPClient(token)
    dynatrace_client = DynatraceClient()

    dt_semaphore = asyncio.Semaphore(NUMBER_OF_CONCURRENT_PUSH_COROUTINES)
    
    for i in range(0, PROCESSING_WORKERS):
        worker_task = asyncio.create_task(
            pull_and_push_logs_forever(f"Worker-{i}", sfm_queue, gcp_client, dynatrace_client,dt_semaphore)
        )
        tasks.append(worker_task)

    sfm_task = asyncio.create_task(create_sfm_loop(sfm_queue, logging_context, instance_metadata))
    tasks.append(sfm_task)

    await asyncio.gather(*tasks, return_exceptions=True)


async def pull_and_push_logs_forever(
    worker_name: str, sfm_queue: Queue, gcp_client: GCPClient, dynatrace_client: DynatraceClient, dt_semaphore: asyncio.Semaphore
):
    logging_context = LoggingContext(worker_name)
    logging_context.log(f"Starting processing")
    while True:
        try:
            log_batches, ack_ids = await perform_pull(sfm_queue, gcp_client, logging_context)

            ack_ids_to_send = await push_logs(log_batches, sfm_queue, dynatrace_client,logging_context,dt_semaphore)

            ack_ids_to_send.extend(ack_ids)
            await push_ack_ids(ack_ids_to_send, gcp_client, logging_context)
        except Exception as e:
            logging_context.exception("Failed to pull messages")
            # Backoff for 1 minute to avoid spamming requests and logs
            await asyncio.sleep(60)


async def perform_pull(
    sfm_queue: Queue,
    gcp_client: GCPClient,
    logging_context: LoggingContext,
) -> Tuple[List[LogBatch], List[str]]:
    async with init_gcp_client_session() as gcp_session:
        context = LogsProcessingContext(None, None, sfm_queue)
        context.self_monitoring.pooling_time_start = time.perf_counter()
       
        tasks_to_pull_messages = [
            gcp_client.pull_messages(logging_context, gcp_session)
            for _ in range(NUMBER_OF_CONCURRENT_MESSAGE_PULL_COROUTINES)
        ]
        responses = await asyncio.gather(*tasks_to_pull_messages, return_exceptions=True)

        context.self_monitoring.calculate_pooling_time()
        processed_messages = []
        ack_ids_to_send = []

        
        context.self_monitoring.processing_time_start = time.perf_counter()
        for response in responses:
            if not isinstance(response, Exception): 
                for received_message in response.get("receivedMessages", []):
                    message_job = prepare_context_and_process_message(sfm_queue, received_message)
                    if not message_job or message_job.bytes_size > REQUEST_BODY_MAX_SIZE - 2:
                        ack_ids_to_send.append(received_message.get("ackId"))
                        continue
                    processed_messages.append(message_job)
        context.self_monitoring.calculate_processing_time()
        put_sfm_into_queue(context)
        return prepare_batches(processed_messages) if processed_messages else [], ack_ids_to_send


async def push_logs(
    log_batches, sfm_queue: Queue, dynatrace_client: DynatraceClient, logging_context: LoggingContext,  dt_semaphore: asyncio.Semaphore
) -> List[str]:
    ack_ids_to_send = []
    context = create_logs_context(sfm_queue)
    logging_context.log(f"Number of log batches to push to Dynatrace: {len(log_batches)}")

    async def process_batch(batch: LogBatch):
        async with dt_semaphore:
            await dynatrace_client.send_logs(context, dt_session, batch, ack_ids_to_send)

    
    context.self_monitoring.sending_time_start = time.perf_counter()
    async with init_dt_client_session() as dt_session:
        exceptions = await asyncio.gather(
            *[process_batch(batch) for batch in log_batches], return_exceptions=True
        )
    context.self_monitoring.calculate_sending_time()
    put_sfm_into_queue(context)
    


    return ack_ids_to_send


async def push_ack_ids(ack_ids: List[str], gcp_client: GCPClient, logging_context: LoggingContext):
    # request size limit is 524288, but we are not able to easily control size of created protobuf
    # empiric test indicates that ack_ids have around 200-220 chars. We can safely assume that ack id is never longer
    # than 256 chars, we split ack ids into chunks with no more than 2048 ack_id's
    async with init_gcp_client_session() as gcp_session:
        chunk_size = 2048
        tasks_to_send_ack_ids = [
            gcp_client.push_ack_ids(chunk, gcp_session, logging_context)
            for chunk in chunks(ack_ids, chunk_size)
        ]
        exceptions = await asyncio.gather(*tasks_to_send_ack_ids, return_exceptions=True)

    logging_context.log("Log ingest payload pushed successfully")

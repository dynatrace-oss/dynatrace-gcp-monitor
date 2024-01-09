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
from typing import List

from lib.clientsession_provider import init_gcp_client_session
from lib.context import LoggingContext, create_logs_context
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
)
from lib.logs.log_self_monitoring import create_sfm_loop
from lib.logs.logs_processor import prepare_context_and_process_message, prepare_batches
from lib.utilities import chunks

from lib.logs.logs_processor import LogBatch

from src.lib.clientsession_provider import init_dt_client_session


def run_logs_wrapper(logging_context, instance_metadata):
    asyncio.run(run_logs(logging_context, instance_metadata))


async def run_logs(logging_context: LoggingContext, instance_metadata: InstanceMetadata):
    if not LOGS_SUBSCRIPTION_PROJECT or not LOGS_SUBSCRIPTION_ID:
        raise Exception(
            "Cannot start pubsub streaming pull - GCP_PROJECT or LOGS_SUBSCRIPTION_ID are not defined"
        )

    sfm_queue = Queue(MAX_SFM_MESSAGES_PROCESSED)
    tasks = []

    for i in range(0, PROCESSING_WORKERS):
        worker_task = asyncio.create_task(pull_and_push_logs_forever(f"Worker-{i}", sfm_queue))
        tasks.append(worker_task)

    sfm_task = asyncio.create_task(create_sfm_loop(sfm_queue, logging_context, instance_metadata))
    tasks.append(sfm_task)

    await asyncio.gather(*tasks, return_exceptions=True)


async def pull_and_push_logs_forever(
    worker_name: str,
    sfm_queue: Queue,
):
    logging_context = LoggingContext(worker_name)
    async with init_gcp_client_session() as gcp_session:
        gcp_client = GCPClient(await create_token(logging_context, gcp_session))

    dynatrace_client = DynatraceClient()
    logging_context.log(f"Starting processing")
    while True:
        try:
            log_batches, ack_ids = await perform_pull(sfm_queue, gcp_client, logging_context)
            await push_logs(log_batches, sfm_queue, dynatrace_client)
            await push_ack_ids(ack_ids, gcp_client, logging_context)
        except Exception as e:
            logging_context.exception("Failed to pull messages")
            # Backoff for 1 minute to avoid spamming requests and logs
            await asyncio.sleep(60)


async def perform_pull(
    sfm_queue: Queue,
    gcp_client: GCPClient,
    logging_context: LoggingContext,
):
    async with init_gcp_client_session() as gcp_session:
        tasks_to_pull_messages = [gcp_client.pull_messages(logging_context, gcp_session) for _ in range(16)]
        responses = await asyncio.gather(*tasks_to_pull_messages, return_exceptions=True)

        processed_messages = []
        ack_ids_to_send = []

        for response in responses:
            for received_message in response.get("receivedMessages", []):
                message_job = prepare_context_and_process_message(sfm_queue, received_message)

                ack_ids_to_send.append(received_message.get("ackId"))
                if not message_job or message_job.bytes_size > REQUEST_BODY_MAX_SIZE - 2:
                    continue
                processed_messages.append(message_job)

        return prepare_batches(processed_messages) if processed_messages else [], ack_ids_to_send



async def push_logs(
    log_batches,
    sfm_queue: Queue,
    dynatrace_client: DynatraceClient,
):
    semaphore = asyncio.Semaphore(5)
    context = create_logs_context(sfm_queue)

    async with init_dt_client_session() as dt_session:
        async def process_batch(batch: LogBatch):
            async with semaphore:
                await dynatrace_client.send_logs(context, batch, dt_session)

        await asyncio.gather(*[process_batch(batch) for batch in log_batches])

    # try:
    #     if len(log_batches):
    #         sent = False
    #         # display_payload_size = round((worker_state.finished_batch_bytes_size / 1024), 3)
    #         try:
    #             # context.log(
    #             #     worker_state.worker_name, f"Log ingest payload size: {display_payload_size} kB"
    #             # )
    #
    #
    #             await dynatrace_client.send_logs(
    #                 context, worker_state.jobs, worker_state.finished_batch
    #             )
    #             # context.log(worker_state.worker_name, "Log ingest payload pushed successfully")
    #             sent = True
    #         except Exception:
                # context.exception(worker_state.worker_name, "Failed to ingest logs")
            # if sent:
            #     context.self_monitoring.sent_logs_entries += len(worker_state.jobs)
            #     context.self_monitoring.log_ingest_payload_size += display_payload_size
            #     await send_batched_ack(gcp_client, worker_state.ack_ids, context)
    # except Exception:
    #     context.exception(worker_state.worker_name, "Failed to perform flush")
    # finally:
    #     # reset state event if we failed to flush, to AVOID getting stuck in processing the same messages
    #     # over and over again and letting their acknowledgement deadline expire
    #     worker_state.reset()


async def push_ack_ids(
     ack_ids: List[str], gcp_client: GCPClient, logging_context: LoggingContext
):
    # request size limit is 524288, but we are not able to easily control size of created protobuf
    # empiric test indicates that ack_ids have around 200-220 chars. We can safely assume that ack id is never longer
    # than 256 chars, we split ack ids into chunks with no more than 2048 ack_id's
    async with init_gcp_client_session() as gcp_session:
        chunk_size = 2048
        tasks_to_send_ack_ids = [gcp_client.push_ack_ids(chunk, gcp_session, logging_context) for chunk in chunks(ack_ids, chunk_size)]
        await asyncio.gather(*tasks_to_send_ack_ids, return_exceptions=True)

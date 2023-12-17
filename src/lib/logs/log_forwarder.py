#     Copyright 2020 Dynatrace LLC
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
from queue import Queue
from typing import List

import aiohttp
from google.api_core.exceptions import Forbidden

from lib.clientsession_provider import init_gcp_client_session
from lib.context import LoggingContext, create_logs_context
from lib.credentials import create_token
from lib.instance_metadata import InstanceMetadata
from lib.logs.dynatrace_client import send_logs
from lib.logs.gcp_client import send_ack_ids_to_pubsub, pull_messages_from_pubsub
from lib.logs.log_forwarder_variables import MAX_SFM_MESSAGES_PROCESSED, LOGS_SUBSCRIPTION_PROJECT, \
    LOGS_SUBSCRIPTION_ID, PROCESSING_WORKERS, REQUEST_BODY_MAX_SIZE
from lib.logs.log_self_monitoring import create_sfm_loop
from lib.logs.logs_processor import _prepare_context_and_process_message
from lib.logs.worker_state import WorkerState
from lib.utilities import chunks


def run_logs_wrapper(instance_metadata):
    # Starting point for each process to handle asyncio loops independently in parallel
    asyncio.run(run_logs(instance_metadata))


async def run_logs(instance_metadata: InstanceMetadata):
    if not LOGS_SUBSCRIPTION_PROJECT or not LOGS_SUBSCRIPTION_ID:
        raise Exception(
            "Cannot start pubsub streaming pull - GCP_PROJECT or LOGS_SUBSCRIPTION_ID are not defined")

    sfm_queue = Queue(MAX_SFM_MESSAGES_PROCESSED)
    tasks = []

    # Create worker tasks to process logs from PubSub queue and ingest them into DT
    for i in range(PROCESSING_WORKERS):
        worker_task = asyncio.create_task(pull_and_flush_logs_forever(f'worker-{i}', sfm_queue))
        tasks.append(worker_task)

    # Create timed task to log and send self monitoring metrics to GCP (if enabled)
    sfm_task = asyncio.create_task(create_sfm_loop(sfm_queue, instance_metadata))
    tasks.append(sfm_task)

    await asyncio.gather(*tasks, return_exceptions=True)


async def pull_and_flush_logs_forever(worker_name: str, sfm_queue: Queue):
    logging_context = LoggingContext(worker_name)
    worker_state = WorkerState(worker_name)
    logging_context.log(f"Starting processing")

    while True:
        try:
            await perform_pull(worker_state, sfm_queue, logging_context)
        except Exception as e:
            if isinstance(e, Forbidden):
                logging_context.error(f"{e}. Please check whether assigned service account "
                                      f"has permission to fetch Pub/Sub messages.")
            else:
                logging_context.exception("Failed to pull messages")
            # Backoff for 1 minute to avoid spamming requests and logs
            await asyncio.sleep(60)


async def perform_pull(worker_state: WorkerState, sfm_queue: Queue, logging_context: LoggingContext):
    async with init_gcp_client_session() as gcp_session:
        token = await create_token(logging_context, gcp_session)
        response = await pull_messages_from_pubsub(gcp_session, token, logging_context)

        if 'receivedMessages' in response:
            for received_message in response.get('receivedMessages'):
                message_job = _prepare_context_and_process_message(sfm_queue, received_message)

                if not message_job or message_job.bytes_size > REQUEST_BODY_MAX_SIZE - 2:
                    worker_state.ack_ids.append(received_message.get('ackId'))
                    continue

                if worker_state.should_flush(message_job):
                    await perform_flush(worker_state, sfm_queue, gcp_session, token, logging_context)

                worker_state.add_job(message_job, received_message.get('ackId'))

            # check if worker_state should flush because of time
            if worker_state.should_flush():
                await perform_flush(worker_state, sfm_queue, gcp_session, token, logging_context)


async def perform_flush(worker_state: WorkerState,
                        sfm_queue: Queue,
                        gcp_session: aiohttp.ClientSession,
                        token: str,
                        logging_context: LoggingContext):
    sfm_context = create_logs_context(sfm_queue)
    try:
        if worker_state.jobs:
            sent = False
            display_payload_size = round((worker_state.finished_batch_bytes_size / 1024), 3)
            async with aiohttp.ClientSession() as session:
                try:
                    logging_context.log(f'Log ingest payload size: {display_payload_size} kB')
                    await send_logs(session, sfm_context, worker_state.jobs, worker_state.finished_batch)
                    logging_context.log("Log ingest payload pushed successfully")
                    sent = True
                except Exception:
                    logging_context.exception("Failed to ingest logs")
                if sent:
                    sfm_context.self_monitoring.sent_logs_entries += len(worker_state.jobs)
                    sfm_context.self_monitoring.log_ingest_payload_size += display_payload_size
                    await send_batched_ack_ids(gcp_session, token, worker_state.ack_ids, logging_context)
        elif worker_state.ack_ids:
            # Send ACK IDs of messages that failed to be processed (e.g., exceeding the size limit)
            await send_batched_ack_ids(gcp_session, token, worker_state.ack_ids, logging_context)
    except Exception:
        logging_context.exception("Failed to perform flush")
    finally:
        # reset state event if we failed to flush, to AVOID getting stuck in processing the same messages
        # over and over again and letting their acknowledgement deadline expire
        worker_state.reset()


async def send_batched_ack_ids(gcp_session, token: str, ack_ids: List[str], logging_context: LoggingContext):
    # request size limit is 524288, but we are not able to easily control size of created protobuf
    # empiric test indicates that ack_ids have around 200-220 chars. We can safely assume that ack id is never longer
    # than 256 chars, we split ack ids into chunks with no more than 2048 ack_id's
    chunk_size = 2048
    if len(ack_ids) < chunk_size:
        await send_ack_ids_to_pubsub(gcp_session, token, ack_ids, logging_context)
    else:
        for chunk in chunks(ack_ids, chunk_size):
            await send_ack_ids_to_pubsub(gcp_session, token, chunk, logging_context)

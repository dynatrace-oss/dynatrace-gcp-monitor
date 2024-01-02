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
import time
from queue import Queue
from typing import List, NamedTuple, Dict

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

from src.lib.logs.dynatrace_client import send_logs2
from src.lib.logs.logs_processor import LogProcessingJob


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
        tasks_to_pull = []
        messages_to_process = []
        for _ in range(0, 16):
            tasks_to_pull.append(pull_messages_from_pubsub(gcp_session, token, logging_context, messages_to_process))
        start_time = time.time()
        await asyncio.gather(*tasks_to_pull, return_exceptions=True)


        processed_messages_to_send = []
        ack_ids_to_send = []

        for response in messages_to_process:
            if 'receivedMessages' in response:
                for received_message in response.get('receivedMessages'):
                    message_job = _prepare_context_and_process_message(sfm_queue, received_message)

                    if not message_job or message_job.bytes_size > REQUEST_BODY_MAX_SIZE - 2:
                        ack_ids_to_send.append(received_message.get('ackId'))
                        continue

                    processed_messages_to_send.append(message_job)
                    ack_ids_to_send.append(received_message.get('ackId'))

        if len(processed_messages_to_send) > 0:
            batches = prepare_serialized_batches(processed_messages_to_send, logging_context)
            sfm_context = create_logs_context(sfm_queue)
            send_tasks = []
            print(f"Number of batches: {len(batches)}")
            for batch in batches:
                print(f"Number of logs in a batch: {batch.number_of_logs_in_batch}")
                send_tasks.append(send_logs2(gcp_session, sfm_context, processed_messages_to_send, batch))

            await asyncio.gather(*send_tasks, return_exceptions=True)




        if len(ack_ids_to_send) > 0:
            await send_batched_ack_ids(gcp_session, token, ack_ids_to_send, logging_context )

        print(f"end time: {time.time() - start_time}")



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
    print(f"Ack_Ids length: {len(ack_ids)}")
    if len(ack_ids) < chunk_size:
        await send_ack_ids_to_pubsub(gcp_session, token, ack_ids, logging_context)
    else:
        tasks_to_send_ack_ids = []
        for chunk in chunks(ack_ids, chunk_size):
            tasks_to_send_ack_ids.append(send_ack_ids_to_pubsub(gcp_session, token, chunk, logging_context))
        await asyncio.gather(*tasks_to_send_ack_ids, return_exceptions=True)

class LogBatch(NamedTuple):
    serialized_batch: str
    number_of_logs_in_batch: int


# Heavily based on AWS log forwarder batching implementation
def prepare_serialized_batches(logs: List[LogProcessingJob], logging_context: LoggingContext) -> List[LogBatch]:
    request_body_max_size = 4718592
    request_max_events = 5000
    log_entry_max_size = request_body_max_size - 2  # account for braces

    batches: List[LogBatch] = []

    logs_for_next_batch: List[str] = []
    logs_for_next_batch_total_len = 0
    logs_for_next_batch_events_count = 0

    log_entries = 0
    for log_entry in logs:
        new_batch_len = logs_for_next_batch_total_len + 2 + len(logs_for_next_batch) - 1  # add bracket length (2) and commas for each entry but last one.

        next_entry_serialized = log_entry.payload

        next_entry_size = len(next_entry_serialized.encode("UTF-8"))
        if next_entry_size > log_entry_max_size:
            # shouldn't happen as we are already truncating the content field, but just for safety
            logging_context.info(f"Dropping entry, as its size is {next_entry_size}, bigger than max entry size: {log_entry_max_size}")

        batch_length_if_added_entry = new_batch_len + 1 + len(next_entry_serialized)  # +1 is for comma

        if batch_length_if_added_entry > request_body_max_size or logs_for_next_batch_events_count >= request_max_events:
            # would overflow limit, close batch and prepare new
            batch = LogBatch("[" + ",".join(logs_for_next_batch) + "]", log_entries)
            batches.append(batch)
            log_entries = 0

            logs_for_next_batch = []
            logs_for_next_batch_total_len = 0
            logs_for_next_batch_events_count = 0

        logs_for_next_batch.append(next_entry_serialized)
        log_entries += 1
        logs_for_next_batch_total_len += next_entry_size
        logs_for_next_batch_events_count += 1

    if len(logs_for_next_batch) >= 1:
        # finalize the last batch
        batch = LogBatch("[" + ",".join(logs_for_next_batch) + "]", log_entries)
        batches.append(batch)

    return batches
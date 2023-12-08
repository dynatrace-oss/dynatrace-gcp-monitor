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
import threading
import time
from queue import Queue
from typing import List

import aiohttp
from google.api_core.exceptions import Forbidden
from google.cloud import pubsub
from google.cloud.pubsub_v1 import SubscriberClient
from google.pubsub_v1 import PullRequest, PullResponse

from lib.context import LoggingContext, create_logs_context
from lib.instance_metadata import InstanceMetadata
from lib.logs.dynatrace_client import send_logs
from lib.logs.log_forwarder_variables import MAX_SFM_MESSAGES_PROCESSED, LOGS_SUBSCRIPTION_PROJECT, \
    LOGS_SUBSCRIPTION_ID, \
    PROCESSING_WORKERS, PROCESSING_WORKER_PULL_REQUEST_MAX_MESSAGES, REQUEST_BODY_MAX_SIZE
from lib.logs.log_self_monitoring import create_sfm_loop
from lib.logs.logs_processor import _prepare_context_and_process_message
from lib.logs.worker_state import LogsBatch, BatchManager
from lib.utilities import chunks


sfm_queue = Queue(MAX_SFM_MESSAGES_PROCESSED)
subscriber_client = pubsub.SubscriberClient()
subscription_path = subscriber_client.subscription_path(LOGS_SUBSCRIPTION_PROJECT, LOGS_SUBSCRIPTION_ID)
batch_manager = BatchManager()


def run_logs(logging_context: LoggingContext, instance_metadata: InstanceMetadata):
    if not LOGS_SUBSCRIPTION_PROJECT or not LOGS_SUBSCRIPTION_ID:
        raise Exception(
            "Cannot start pubsub streaming pull - GCP_PROJECT or LOGS_SUBSCRIPTION_ID are not defined")

    # Open worker threads to process logs from PubSub queue and ingest them into DT
    #for i in range(0, PROCESSING_WORKERS):
    #    threading.Thread(target=pull_and_flush_logs_forever,
    #                     args=(f"Worker-{i}", sfm_queue, subscriber_client, subscription_path,),
    #                     name=f"worker-{i}").start()

    # Open pulling thread
    threading.Thread(target=pull_forever, name="Puller").start()

    # Open pushing thread
    #threading.Thread(target=push_forever, name="Pusher").start()

    # Create loop with a timer to gather self monitoring metrics and send them to GCP (if enabled)
    create_sfm_loop(sfm_queue, logging_context, instance_metadata)


def pull_forever():
    logging_context = LoggingContext("Pusher")
    pull_request = PullRequest()
    pull_request.max_messages = PROCESSING_WORKER_PULL_REQUEST_MAX_MESSAGES
    pull_request.subscription = subscription_path
    logging_context.log(f"Starting pulling")

    while True:
        try:
            response: PullResponse = subscriber_client.pull(pull_request)
            print(f"Received messages: {len(response.received_messages)}")

            for received_message in response.received_messages:
                message_job = _prepare_context_and_process_message(sfm_queue, received_message)
                if not message_job or message_job.bytes_size > REQUEST_BODY_MAX_SIZE - 2:
                    batch_manager.add_ids(received_message.ack_id)
                else:
                    batch_manager.add_job(message_job, received_message.ack_id)

            if batch_manager.should_send():
                asyncio.run(push_asynchronously())

        except Exception as e:
            if isinstance(e, Forbidden):
                logging_context.error(
                    f"{e} Please check whether assigned service account has permission to fetch Pub/Sub messages.")
            else:
                logging_context.exception("Failed to pull messages")
            # Backoff for 1 minute to avoid spamming requests and logs
            time.sleep(60)


def push_forever():
    logging_context = LoggingContext("Pusher")
    logging_context.log(f"Starting pushing")
    while True:
        try:
            #logging_context.log(f"Pusher sleep 1s")
            #time.sleep(1)
            asyncio.run(push_asynchronously())
        except Exception:
            logging_context.exception("Failed to push messages")


async def push_asynchronously():
    context = create_logs_context(sfm_queue)
    semaphore = asyncio.Semaphore(5)
    async with aiohttp.ClientSession() as session:  # Create the session once
        async def process_batch(batch: LogsBatch):
            async with semaphore:
                try:
                    if batch.jobs:
                        sent = False
                        display_payload_size = round((batch.finished_batch_bytes_size / 1024), 3)
                        try:
                            context.log("Batch", f'Log ingest payload size: {display_payload_size} kB')
                            await send_logs(session, context, batch.jobs, batch.finished_batch)
                            context.log("Batch", "Log ingest payload pushed successfully")
                            sent = True
                        except Exception:
                            context.exception("Batch", "Failed to ingest logs")
                        if sent:
                            context.self_monitoring.sent_logs_entries += len(batch.jobs)
                            context.self_monitoring.log_ingest_payload_size += display_payload_size
                            send_ack_ids(batch.ack_ids)
                    elif batch.ack_ids:
                        # Send ACKs from too big messages, if any
                        send_ack_ids(batch.ack_ids)
                except Exception:
                    context.exception("Batch", "Failed to process batch")

        print(f"batch_queue.qsize(): {batch_manager.batch_queue.qsize()}")
        await asyncio.gather(*[process_batch(batch) for batch in batch_manager.get_ready_batches()])


def send_ack_ids(ack_ids: List[str]):
    # request size limit is 524288, but we are not able to easily control size of created protobuf
    # empiric test indicates that ack_ids have around 200-220 chars. We can safely assume that ack id is never longer
    # than 256 chars, we split ack ids into chunks with no more than 2048 ack_id's
    chunk_size = 2048
    if len(ack_ids) < chunk_size:
        subscriber_client.acknowledge(request={"subscription": subscription_path, "ack_ids": ack_ids})
    else:
        for chunk in chunks(ack_ids, chunk_size):
            subscriber_client.acknowledge(request={"subscription": subscription_path, "ack_ids": chunk})





### OLD CODE:
def pull_and_flush_logs_forever(worker_name: str,
                                sfm_queue: Queue,
                                subscriber_client: SubscriberClient,
                                subscription_path: str):
    logging_context = LoggingContext(worker_name)
    worker_state = LogsBatch(worker_name)
    pull_request = PullRequest()
    pull_request.max_messages = PROCESSING_WORKER_PULL_REQUEST_MAX_MESSAGES
    pull_request.subscription = subscription_path
    logging_context.log(f"Starting processing")
    while True:
        try:
            perform_pull(worker_state, sfm_queue, subscriber_client, subscription_path, pull_request)
        except Exception as e:
            if isinstance(e, Forbidden):
                logging_context.error(f"{e} Please check whether assigned service account has permission to fetch Pub/Sub messages.")
            else:
                logging_context.exception("Failed to pull messages")
            # Backoff for 1 minute to avoid spamming requests and logs
            time.sleep(60)


def perform_pull(worker_state: LogsBatch,
                 sfm_queue: Queue,
                 subscriber_client: SubscriberClient,
                 subscription_path: str,
                 pull_request: PullRequest):
    response: PullResponse = subscriber_client.pull(pull_request)

    for received_message in response.received_messages:
        # print(f"Received: {received_message.message.data}.")
        message_job = _prepare_context_and_process_message(sfm_queue, received_message)

        if not message_job or message_job.bytes_size > REQUEST_BODY_MAX_SIZE - 2:
            worker_state.ack_ids.append(received_message.ack_id)
            continue

        if worker_state.should_flush(message_job):
            perform_flush(worker_state, sfm_queue, subscriber_client, subscription_path)

        worker_state.add_job(message_job, received_message.ack_id)

    # check if worker_state should flush because of time
    if worker_state.should_flush():
        perform_flush(worker_state, sfm_queue, subscriber_client, subscription_path)


def perform_flush(worker_state: LogsBatch,
                  sfm_queue: Queue,
                  subscriber_client: SubscriberClient,
                  subscription_path: str):

    context = create_logs_context(sfm_queue)
    try:
        if worker_state.jobs:
            sent = False
            display_payload_size = round((worker_state.finished_batch_bytes_size / 1024), 3)
            try:
                context.log(worker_state.worker_name, f'Log ingest payload size: {display_payload_size} kB')
                send_logs(context, worker_state.jobs, worker_state.finished_batch)
                context.log(worker_state.worker_name, "Log ingest payload pushed successfully")
                sent = True
            except Exception:
                context.exception(worker_state.worker_name, "Failed to ingest logs")
            if sent:
                context.self_monitoring.sent_logs_entries += len(worker_state.jobs)
                context.self_monitoring.log_ingest_payload_size += display_payload_size
                send_batched_ack(subscriber_client, subscription_path, worker_state.ack_ids)
        elif worker_state.ack_ids:
            # Send ACKs if processing all messages has failed
            send_batched_ack(subscriber_client, subscription_path, worker_state.ack_ids)
    except Exception:
        context.exception(worker_state.worker_name, "Failed to perform flush")
    finally:
        # reset state event if we failed to flush, to AVOID getting stuck in processing the same messages
        # over and over again and letting their acknowledgement deadline expire
        worker_state.reset()


def send_batched_ack(subscriber_client: SubscriberClient, subscription_path: str, ack_ids: List[str]):
    # request size limit is 524288, but we are not able to easily control size of created protobuf
    # empiric test indicates that ack_ids have around 200-220 chars. We can safely assume that ack id is never longer
    # than 256 chars, we split ack ids into chunks with no more than 2048 ack_id's
    chunk_size = 2048
    if len(ack_ids) < chunk_size:
        subscriber_client.acknowledge(request={"subscription": subscription_path, "ack_ids": ack_ids})
    else:
        for chunk in chunks(ack_ids, chunk_size):
            subscriber_client.acknowledge(request={"subscription": subscription_path, "ack_ids": chunk})


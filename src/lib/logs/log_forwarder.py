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
from asyncio import AbstractEventLoop
from functools import partial
from queue import Queue
from typing import List

from google.cloud import pubsub
from google.cloud.pubsub_v1 import SubscriberClient
from google.pubsub_v1 import PullRequest, PullResponse

from lib.context import LoggingContext, LogsContext
from lib.credentials import get_dynatrace_api_key_from_env, get_dynatrace_log_ingest_url_from_env, \
    get_project_id_from_environment
from lib.instance_metadata import InstanceMetadata
from lib.logs.dynatrace_client import send_logs
from lib.logs.log_forwarder_variables import MAX_SFM_MESSAGES_PROCESSED, LOGS_SUBSCRIPTION_PROJECT, \
    LOGS_SUBSCRIPTION_ID, \
    PROCESSING_WORKERS, PROCESSING_WORKER_PULL_REQUEST_MAX_MESSAGES, REQUEST_BODY_MAX_SIZE
from lib.logs.log_self_monitoring import create_sfm_worker_loop
from lib.logs.logs_processor import _process_message
from lib.logs.worker_state import WorkerState
from lib.utilities import chunks


def create_logs_context(sfm_queue: Queue):
    dynatrace_api_key = get_dynatrace_api_key_from_env()
    dynatrace_url = get_dynatrace_log_ingest_url_from_env()
    project_id_owner = get_project_id_from_environment()

    return LogsContext(
        project_id_owner=project_id_owner,
        dynatrace_api_key=dynatrace_api_key,
        dynatrace_url=dynatrace_url,
        scheduled_execution_id=str(int(time.time()))[-8:],
        sfm_queue=sfm_queue
    )


def run_logs(logging_context: LoggingContext, instance_metadata: InstanceMetadata, asyncio_loop: AbstractEventLoop):
    if not LOGS_SUBSCRIPTION_PROJECT or not LOGS_SUBSCRIPTION_ID:
        raise Exception(
            "Cannot start pubsub streaming pull - GCP_PROJECT or LOGS_SUBSCRIPTION_ID are not defined")

    sfm_queue = Queue(MAX_SFM_MESSAGES_PROCESSED)
    asyncio.run_coroutine_threadsafe(create_sfm_worker_loop(sfm_queue, logging_context, instance_metadata),
                                     asyncio_loop)

    for i in range(0, PROCESSING_WORKERS):
        threading.Thread(target=partial(run_ack_logs, f"Worker-{i}", sfm_queue), name=f"worker-{i}").start()


def run_ack_logs(worker_name: str, sfm_queue: Queue):
    logging_context = LoggingContext(worker_name)
    subscriber_client = pubsub.SubscriberClient()
    subscription_path = subscriber_client.subscription_path(LOGS_SUBSCRIPTION_PROJECT, LOGS_SUBSCRIPTION_ID)
    logging_context.log(f"Starting processing")

    worker_state = WorkerState(worker_name)
    while True:
        try:
            perform_pull(worker_state, sfm_queue, subscriber_client, subscription_path)
        except Exception as e:
            logging_context.exception("Failed to pull messages")


def perform_pull(worker_state: WorkerState,
                 sfm_queue: Queue,
                 subscriber_client: SubscriberClient,
                 subscription_path: str):
    pull_request = PullRequest()
    pull_request.max_messages = PROCESSING_WORKER_PULL_REQUEST_MAX_MESSAGES
    pull_request.subscription = subscription_path
    response: PullResponse = subscriber_client.pull(pull_request)

    for received_message in response.received_messages:
        # print(f"Received: {received_message.message.data}.")
        message_job = _process_message(sfm_queue, received_message)

        if not message_job or message_job.bytes_size > REQUEST_BODY_MAX_SIZE - 2:
            worker_state.ack_ids.append(received_message.ack_id)
            continue

        if worker_state.should_flush(message_job):
            perform_flush(worker_state, sfm_queue, subscriber_client, subscription_path)

        worker_state.add_job(message_job, received_message.ack_id)

    # check if should flush because of time
    if worker_state.should_flush():
        perform_flush(worker_state, sfm_queue, subscriber_client, subscription_path)


def perform_flush(worker_state: WorkerState,
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
                send_batched_acks(subscriber_client, subscription_path, worker_state.ack_ids)
    except Exception:
        context.exception(worker_state.worker_name, "Failed to perform flush")
    finally:
        # reset state event if we failed to flush, to AVOID getting stuck in processing the same messages
        # over and over again and letting their acknowledgement deadline expire
        worker_state.reset()


def send_batched_acks(subscriber_client: SubscriberClient, subscription_path: str, acks_ids: List[str]):
    # request size limit is 524288, but we are not able to easily control size of created protobuf
    # empiric test indicates that ack_ids have around 200-220 chars. We can safely assume that ack id is never longer
    # than 256 chars, we split ack ids into chunks with no more than 2048 ack_id's
    chunk_size = 2048
    if len(acks_ids) < chunk_size:
        send_acks(subscriber_client, subscription_path, acks_ids)
    else:
        for chunk in chunks(acks_ids, chunk_size):
            send_acks(subscriber_client, subscription_path, chunk)


def send_acks(subscriber_client: SubscriberClient, subscription_path: str, acks_ids: List[str]):
    subscriber_client.acknowledge(
        request={"subscription": subscription_path, "ack_ids": acks_ids}
    )

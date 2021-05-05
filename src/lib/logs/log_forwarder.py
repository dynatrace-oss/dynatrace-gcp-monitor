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
from asyncio import AbstractEventLoop
from concurrent.futures.thread import ThreadPoolExecutor
from queue import Queue
from threading import Thread

from google.cloud import pubsub
from google.cloud.pubsub_v1.subscriber.scheduler import ThreadScheduler
from google.cloud.pubsub_v1.types import FlowControl

from lib.context import LoggingContext
from lib.instance_metadata import InstanceMetadata
from lib.logs.log_forwarder_variables import MAX_MESSAGES_PROCESSED, MAX_WORKERS, \
    SENDING_WORKER_EXECUTION_PERIOD_SECONDS, LOGS_SUBSCRIPTION_PROJECT, LOGS_SUBSCRIPTION_ID
from lib.logs.log_self_monitoring import create_sfm_worker_loop
from lib.logs.logs_processor import create_process_message_handler
from lib.logs.logs_sending_worker import create_log_sending_worker_loop


def run_logs(logging_context: LoggingContext, instance_metadata: InstanceMetadata, asyncio_loop: AbstractEventLoop):
    if not LOGS_SUBSCRIPTION_PROJECT or not LOGS_SUBSCRIPTION_ID:
        raise Exception("Cannot start pubsub streaming pull - LOGS_SUBSCRIPTION_PROJECT or LOGS_SUBSCRIPTION_ID are not defined")
    # Settings for job queue size and subscriber should be fine tuned, but we have to do performance tests first
    job_queue = Queue(MAX_MESSAGES_PROCESSED)
    sfm_queue = Queue(MAX_MESSAGES_PROCESSED)
    subscriber_client = pubsub.SubscriberClient()
    subscription_path = subscriber_client.subscription_path(LOGS_SUBSCRIPTION_PROJECT, LOGS_SUBSCRIPTION_ID)
    logging_context.log(f"Subscribing on '{subscription_path}'")
    flow_control = FlowControl(max_messages=MAX_MESSAGES_PROCESSED-10)
    subscriber = subscriber_client.subscribe(
        subscription=subscription_path,
        callback=create_process_message_handler(job_queue, sfm_queue),
        flow_control=flow_control,
        scheduler=ThreadScheduler(ThreadPoolExecutor(
            max_workers=MAX_WORKERS,
            thread_name_prefix="PubSubSubscription"
    )))
    worker_loop = create_log_sending_worker_loop(SENDING_WORKER_EXECUTION_PERIOD_SECONDS, job_queue, sfm_queue)
    logs_sending_worker_thread = Thread(target=worker_loop, name="LogsSendingWorkerThread", daemon=True)
    logs_sending_worker_thread.start()

    asyncio.run_coroutine_threadsafe(create_sfm_worker_loop(sfm_queue, logging_context, instance_metadata), asyncio_loop)

    try:
        subscriber.result()
    except Exception as subscription_exception:
        logging_context.error(f"Pub/sub subscriber crashed for path {subscription_path}")
        raise subscription_exception
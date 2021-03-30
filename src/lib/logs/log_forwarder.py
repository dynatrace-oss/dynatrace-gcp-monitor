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

import os
from concurrent.futures.thread import ThreadPoolExecutor
from queue import Queue
from threading import Thread

from google.cloud import pubsub
from google.cloud.pubsub_v1.subscriber.scheduler import ThreadScheduler
from google.cloud.pubsub_v1.types import FlowControl

from lib.context import LoggingContext
from lib.logs.logs_processor import create_process_message_handler, SENDING_WORKER_EXECUTION_PERIOD_SECONDS
from lib.logs.logs_sending_worker import create_log_sending_worker_loop

PROJECT_ID = os.environ.get('LOGS_SUBSCRIPTION_PROJECT', None)
SUBSCRIPTION_ID = os.environ.get('LOGS_SUBSCRIPTION_ID', None)


MAX_MESSAGES_PROCESSED = 10_000
MAX_WORKERS = 10_000


def run_logs(logging_context: LoggingContext):
    if not PROJECT_ID or not SUBSCRIPTION_ID:
        raise Exception("Cannot start pubsub streaming pull - LOGS_SUBSCRIPTION_PROJECT or LOGS_SUBSCRIPTION_ID are not defined")
    # Settings for job queue size and subscriber should be fine tuned, but we have to do performance tests first
    job_queue = Queue(MAX_MESSAGES_PROCESSED)
    subscriber_client = pubsub.SubscriberClient()
    subscription_path = subscriber_client.subscription_path(PROJECT_ID, SUBSCRIPTION_ID)
    logging_context.log(f"Subscribing on '{subscription_path}'")
    flow_control = FlowControl(max_messages=MAX_MESSAGES_PROCESSED)
    subscriber = subscriber_client.subscribe(
        subscription=subscription_path,
        callback=create_process_message_handler(job_queue),
        flow_control=flow_control,
        scheduler=ThreadScheduler(ThreadPoolExecutor(
            max_workers=MAX_WORKERS,
            thread_name_prefix="PubSubSubscription"
    )))
    worker_loop = create_log_sending_worker_loop(SENDING_WORKER_EXECUTION_PERIOD_SECONDS, job_queue)
    logs_sending_worker_thread = Thread(target=worker_loop, name="LogsSendingWorkerThread", daemon=True)
    logs_sending_worker_thread.start()

    subscriber.result()
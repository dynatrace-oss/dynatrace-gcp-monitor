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

import copy
import threading
import time
#from queue import Queue
from typing import List
import sys

from google.api_core.exceptions import Forbidden
from google.cloud import pubsub
from google.cloud.pubsub_v1 import SubscriberClient
from google.pubsub_v1 import PullRequest, PullResponse
#from multiprocessing import Lock, Process, Queue,JoinableQueue, current_process
from queue import Queue
import time
#import queue # imported for using queue.Empty exception

from lib.context import LoggingContext, create_logs_context
from lib.instance_metadata import InstanceMetadata
from lib.logs.dynatrace_client import perform_flush, send_logs, flush_worker
from lib.logs.log_forwarder_variables import MAX_SFM_MESSAGES_PROCESSED, LOGS_SUBSCRIPTION_PROJECT, \
    LOGS_SUBSCRIPTION_ID, \
    PROCESSING_WORKERS, PROCESSING_WORKER_PULL_REQUEST_MAX_MESSAGES, REQUEST_BODY_MAX_SIZE
from lib.logs.log_self_monitoring import create_sfm_loop
from lib.logs.logs_processor import _prepare_context_and_process_message
from lib.logs.worker_state import WorkerState
from lib.utilities import chunks


def run_logs(logging_context: LoggingContext, instance_metadata: InstanceMetadata):
    if not LOGS_SUBSCRIPTION_PROJECT or not LOGS_SUBSCRIPTION_ID:
        raise Exception(
            "Cannot start pubsub streaming pull - GCP_PROJECT or LOGS_SUBSCRIPTION_ID are not defined")

    sfm_queue = Queue(MAX_SFM_MESSAGES_PROCESSED)
    send_queue = Queue(MAX_SFM_MESSAGES_PROCESSED)


    subscriber_client = pubsub.SubscriberClient()


    subscription_path = subscriber_client.subscription_path(LOGS_SUBSCRIPTION_PROJECT, LOGS_SUBSCRIPTION_ID)

    #for i in range(0, PROCESSING_WORKERS):
    #    p = Process(target=custom_pull, args=(None,None,pull_queue))
    #    p.start()
    
    for i in range(0, PROCESSING_WORKERS):
        p = threading.Thread(target=flush_worker, args=(send_queue,sfm_queue,LOGS_SUBSCRIPTION_PROJECT,LOGS_SUBSCRIPTION_ID))
        p.start()


    processes = []
    # Open worker threads to process logs from PubSub queue and ingest them into DT
    for i in range(0, PROCESSING_WORKERS):
        p = threading.Thread(target=pull_and_flush_logs_forever, args=(f"Worker-{i}",sfm_queue, send_queue, subscriber_client,subscription_path,))
        processes.append(p)
        p.start()
        
        #threading.Thread(target=pull_and_flush_logs_forever,
        #                 args=(f"Worker-{i}", sfm_queue, subscriber_client, subscription_path,),
        #                 name=f"worker-{i}").start()

    # Create loop with a timer to gather self monitoring metrics and send them to GCP (if enabled)
    create_sfm_loop(sfm_queue, logging_context, instance_metadata)


def pull_and_flush_logs_forever(worker_name: str,
                                sfm_queue: Queue,
                                send_queue: Queue,
                                subscriber_client: SubscriberClient,
                                subscription_path: str):
    logging_context = LoggingContext(worker_name)
    worker_state = WorkerState(worker_name)
    pull_request = PullRequest()
    pull_request.max_messages = PROCESSING_WORKER_PULL_REQUEST_MAX_MESSAGES
    pull_request.subscription = subscription_path
    logging_context.log(f"Starting processing")
    while True:
        try:
            worker_state = perform_pull(worker_state, sfm_queue, send_queue, subscriber_client, subscription_path, pull_request)
        except Exception as e:
            if isinstance(e, Forbidden):
                logging_context.error(f"{e} Please check whether assigned service account has permission to fetch Pub/Sub messages.")
            else:
                logging_context.exception("Failed to pull messages")
            # Backoff for 1 minute to avoid spamming requests and logs
            time.sleep(60)


def perform_pull(worker_state: WorkerState,
                 sfm_queue: Queue,
                 send_queue: Queue,
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
            worker_state = prepare_flush(worker_state, sfm_queue, send_queue,subscriber_client, subscription_path)

        worker_state.add_job(message_job, received_message.ack_id)

    # check if worker_state should flush because of time
    if worker_state.should_flush():
        worker_state = prepare_flush(worker_state, sfm_queue,send_queue, subscriber_client, subscription_path)
    
    return worker_state



def prepare_flush(worker_state: WorkerState,
                  sfm_queue: Queue,
                  send_queue: Queue,
                  subscriber_client: SubscriberClient,
                  subscription_path: str):

    context = create_logs_context(sfm_queue)

    if send_queue.qsize() >= 50:
        print("Queue is Full!")
        # Too many tasks in queue
        # Perform it using main process to slow down. 
        
        perform_flush(worker_state,sfm_queue,subscriber_client,subscription_path)
    else:
        try:
            send_queue.put((worker_state,None))
        except Exception:
            context.exception(worker_state.worker_name, "Failed to create flush task")
        finally:
            worker_state = WorkerState(worker_name=worker_state.worker_name)
    
    return worker_state



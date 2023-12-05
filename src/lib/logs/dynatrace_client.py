#   Copyright 2021 Dynatrace LLC
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

import ssl
import time
import urllib
from typing import List, Dict, NamedTuple, Tuple
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request

from multiprocessing import Lock, Process, Queue,JoinableQueue, current_process



from lib.logs.worker_state import WorkerState
from lib.configuration import config
from lib.context import DynatraceConnectivity, LogsContext, create_logs_context
from lib.logs.log_self_monitoring import LogSelfMonitoring, aggregate_self_monitoring_metrics, put_sfm_into_queue
from lib.logs.logs_processor import LogProcessingJob
from google.cloud.pubsub_v1 import SubscriberClient
from google.cloud import pubsub

from google.cloud.pubsub_v1 import SubscriberClient
from google.pubsub_v1 import PullRequest, PullResponse


ssl_context = ssl.create_default_context()
if not config.require_valid_certificate():
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE


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




FlushTask = NamedTuple('FlushTask', [('worker_state', WorkerState)])



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
                context.error()
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


def flush_worker(queue,sfm_queue,LOGS_SUBSCRIPTION_PROJECT,LOGS_SUBSCRIPTION_ID):

    subscriber_client = pubsub.SubscriberClient()
    subscription_path = subscriber_client.subscription_path(LOGS_SUBSCRIPTION_PROJECT, LOGS_SUBSCRIPTION_ID)



    while True:
        task = queue.get()

        worker_state = task[0]

        perform_flush(worker_state,sfm_queue,subscriber_client,subscription_path)


def send_logs(context: LogsContext, logs: List[LogProcessingJob], batch: str):
    # pylint: disable=R0912
    context.self_monitoring = aggregate_self_monitoring_metrics(LogSelfMonitoring(), [log.self_monitoring for log in logs])
    context.self_monitoring.sending_time_start = time.perf_counter()
    log_ingest_url = urlparse(context.dynatrace_url.rstrip('/') + "/api/v2/logs/ingest").geturl()

    try:
        encoded_body_bytes = batch.encode("UTF-8")
        context.self_monitoring.all_requests += 1
        status, reason, response = _perform_http_request(
            method="POST",
            url=log_ingest_url,
            encoded_body_bytes=encoded_body_bytes,
            headers={
                "Authorization": f"Api-Token {context.dynatrace_api_key}",
                "Content-Type": "application/json; charset=utf-8"
            }
        )
        if status > 299:
            context.t_error(f'Log ingest error: {status}, reason: {reason}, url: {log_ingest_url}, body: "{response}"')
            if status == 400:
                context.self_monitoring.dynatrace_connectivity.append(DynatraceConnectivity.InvalidInput)
            elif status == 401:
                context.self_monitoring.dynatrace_connectivity.append(DynatraceConnectivity.ExpiredToken)
            elif status == 403:
                context.self_monitoring.dynatrace_connectivity.append(DynatraceConnectivity.WrongToken)
            elif status == 404 or status == 405:
                context.self_monitoring.dynatrace_connectivity.append(DynatraceConnectivity.WrongURL)
            elif status == 413 or status == 429:
                context.self_monitoring.dynatrace_connectivity.append(DynatraceConnectivity.TooManyRequests)
            elif status == 500:
                context.self_monitoring.dynatrace_connectivity.append(DynatraceConnectivity.Other)

            raise HTTPError(log_ingest_url, status, reason, "", "")
        else:
            context.self_monitoring.dynatrace_connectivity.append(DynatraceConnectivity.Ok)
    except Exception as e:
        # Handle non-HTTP Errors
        if not isinstance(e, HTTPError):
            context.self_monitoring.dynatrace_connectivity.append(DynatraceConnectivity.Other)
        raise e
    finally:
        context.self_monitoring.calculate_sending_time()
        put_sfm_into_queue(context)


def _perform_http_request(
        method: str,
        url: str,
        encoded_body_bytes: bytes,
        headers: Dict
) -> Tuple[int, str, str]:
    request = Request(
        url,
        encoded_body_bytes,
        headers,
        method=method
    )
    try:
        response = urllib.request.urlopen(url=request,
                                          context=ssl_context,
                                          timeout=config.get_int_environment_value("DYNATRACE_TIMEOUT_SECONDS", 30))
        return response.code, response.reason, response.read().decode("utf-8")
    except HTTPError as e:
        response_body = e.read().decode("utf-8")
        return e.code, e.reason, response_body

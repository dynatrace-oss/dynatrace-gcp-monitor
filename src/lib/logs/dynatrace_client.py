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

import json
import ssl
import time
import urllib
from typing import List, Dict, Tuple
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request

from lib.context import get_should_require_valid_certificate, get_int_environment_value, \
    DynatraceConnectivity, LogsContext
from lib.logs.log_forwarder_variables import REQUEST_BODY_MAX_SIZE, REQUEST_MAX_EVENTS
from lib.logs.log_self_monitoring import LogSelfMonitoring, aggregate_self_monitoring_metrics, put_sfm_into_queue

ssl_context = ssl.create_default_context()
if not get_should_require_valid_certificate():
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

_TIMEOUT = get_int_environment_value("DYNATRACE_TIMEOUT_SECONDS", 30)


def send_logs(context: LogsContext, logs: List[Dict], processing_sfm_list: List[LogSelfMonitoring]):
    # pylint: disable=R0912
    context.self_monitoring = aggregate_self_monitoring_metrics(LogSelfMonitoring(), processing_sfm_list)
    context.self_monitoring.sending_time_start = time.perf_counter()
    log_ingest_url = urlparse(context.dynatrace_url + "/api/v2/logs/ingest").geturl()
    batches = prepare_serialized_batches(context, logs)

    number_of_http_errors = 0
    for batch in batches:
        try:
            encoded_body_bytes = batch.encode("UTF-8")
            ingest_payload_size = round((len(encoded_body_bytes) / 1024), 3)
            context.log(f'Log ingest payload size: {ingest_payload_size} kB')
            context.self_monitoring.log_ingest_payload_size += ingest_payload_size
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
                context.error(f'Log ingest error: {status}, reason: {reason}, url: {log_ingest_url}, body: "{response}"')
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
                    raise HTTPError(log_ingest_url, 429, "Dynatrace throttling response", "", "")
                elif status == 500:
                    context.self_monitoring.dynatrace_connectivity.append(DynatraceConnectivity.Other)
                    raise HTTPError(log_ingest_url, 500, "Dynatrace server error", "", "")
            else:
                context.self_monitoring.dynatrace_connectivity.append(DynatraceConnectivity.Ok)
                context.log("Log ingest payload pushed successfully")
        except HTTPError as e:
            context.self_monitoring.calculate_sending_time()
            put_sfm_into_queue(context)
            raise e
        except Exception as e:
            context.error("Failed to ingest logs")
            number_of_http_errors += 1
            context.self_monitoring.dynatrace_connectivity.append(DynatraceConnectivity.Other)
            # all http requests failed and this is the last batch, raise this exception
            if number_of_http_errors == len(batches):
                context.self_monitoring.calculate_sending_time()
                put_sfm_into_queue(context)
                raise e

    context.self_monitoring.calculate_sending_time()
    put_sfm_into_queue(context)


def _perform_http_request(
        method: str,
        url: str,
        encoded_body_bytes: bytes,
        headers: Dict
) -> Tuple[int, str, str]:
    req = Request(
        url,
        encoded_body_bytes,
        headers,
        method=method
    )
    try:
        response = urllib.request.urlopen(req, context=ssl_context, timeout=_TIMEOUT)
        return response.code, response.reason, response.read().decode("utf-8")
    except HTTPError as e:
        response_body = e.read().decode("utf-8")
        return e.code, e.reason, response_body


# Heavily based on AWS log forwarder batching implementation
def prepare_serialized_batches(context: LogsContext, logs: List[Dict]) -> List[str]:

    log_entry_max_size = REQUEST_BODY_MAX_SIZE - 2  # account for braces

    batches: List[str] = []

    logs_for_next_batch: List[str] = []
    logs_for_next_batch_total_len = 0
    logs_for_next_batch_events_count = 0

    for log_entry in logs:
        new_batch_len = logs_for_next_batch_total_len + 2 + len(logs_for_next_batch) - 1 # add bracket length (2) and commas for each entry but last one.

        next_entry_serialized = json.dumps(log_entry)

        next_entry_size = len(next_entry_serialized.encode("UTF-8"))
        if next_entry_size > log_entry_max_size:
            # shouldn't happen as we are already truncating the content field, but just for safety
            context.log(f"Dropping entry, as it's size is {next_entry_size}, bigger than max entry size: {log_entry_max_size}")

        batch_length_if_added_entry = new_batch_len + 1 + len(next_entry_serialized)  # +1 is for comma

        if batch_length_if_added_entry > REQUEST_BODY_MAX_SIZE or logs_for_next_batch_events_count >= REQUEST_MAX_EVENTS:
            # would overflow limit, close batch and prepare new
            batch = "[" + ",".join(logs_for_next_batch) + "]"
            batches.append(batch)

            logs_for_next_batch = []
            logs_for_next_batch_total_len = 0
            logs_for_next_batch_events_count = 0

        logs_for_next_batch.append(next_entry_serialized)
        logs_for_next_batch_total_len += next_entry_size
        logs_for_next_batch_events_count += 1

    if len(logs_for_next_batch) >= 1:
        # finalize last batch
        batch = "[" + ",".join(logs_for_next_batch) + "]"
        batches.append(batch)

    return batches
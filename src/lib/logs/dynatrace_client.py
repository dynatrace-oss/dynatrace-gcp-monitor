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
from lib.logs.log_self_monitoring import LogSelfMonitoring, aggregate_self_monitoring_metrics, put_sfm_into_queue
from lib.logs.logs_processor import LogProcessingJob

ssl_context = ssl.create_default_context()
if not get_should_require_valid_certificate():
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

_TIMEOUT = get_int_environment_value("DYNATRACE_TIMEOUT_SECONDS", 30)


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

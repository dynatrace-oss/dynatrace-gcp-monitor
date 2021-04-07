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
import os
import ssl
import time
import urllib
from typing import List, Dict, Tuple
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request

from lib.context import LogsContext, get_should_require_valid_certificate

ssl_context = ssl.create_default_context()
if not get_should_require_valid_certificate():
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE


def send_logs(context: LogsContext, logs: List[Dict]):
    # pylint: disable=R0912
    start_time = time.time()
    log_ingest_url = urlparse(context.dynatrace_url + "/api/v2/logs/ingest").geturl()
    batches = prepare_serialized_batches(context, logs)

    number_of_http_errors = 0
    for batch in batches:
        try:
            encoded_body_bytes = batch.encode("UTF-8")
            context.log('Log ingest payload size: {} kB'.format(round((len(encoded_body_bytes) / 1024), 3)))

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
                number_of_http_errors += 1
            else:
                context.log("Log ingest payload pushed successfully")
        except HTTPError as e:
            raise e
        except Exception as e:
            context.error("Failed to ingest logs")
            number_of_http_errors += 1
            # all http requests failed and this is the last batch, raise this exception to trigger retry
            if number_of_http_errors == len(batches):
                raise e


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
        response = urllib.request.urlopen(req, context=ssl_context)
        return response.code, response.reason, response.read().decode("utf-8")
    except HTTPError as e:
        response_body = e.read().decode("utf-8")
        return e.code, e.reason, response_body


# Heavily based on AWS log forwarder batching implementation
def prepare_serialized_batches(context: LogsContext, logs: List[Dict]) -> List[str]:

    log_entry_max_size = context.request_body_max_size - 2  # account for braces

    batches: List[str] = []

    logs_for_next_batch: List[str] = []
    logs_for_next_batch_total_len = 0

    for log_entry in logs:
        brackets_len = 2
        commas_len = len(logs_for_next_batch) - 1

        new_batch_len = logs_for_next_batch_total_len + brackets_len + commas_len

        next_entry_serialized = json.dumps(log_entry)

        next_entry_size = len(next_entry_serialized.encode("UTF-8"))
        if next_entry_size > log_entry_max_size:
            # shouldn't happen as we are already truncating the content field, but just for safety
            context.log(f"Dropping entry, as it's size is {next_entry_size}, bigger than max entry size: {log_entry_max_size}")

        batch_length_if_added_entry = new_batch_len + 1 + len(next_entry_serialized)  # +1 is for comma

        if batch_length_if_added_entry > context.request_body_max_size:
            # would overflow limit, close batch and prepare new
            batch = "[" + ",".join(logs_for_next_batch) + "]"
            batches.append(batch)

            logs_for_next_batch = []
            logs_for_next_batch_total_len = 0

        logs_for_next_batch.append(next_entry_serialized)
        logs_for_next_batch_total_len += next_entry_size

    if len(logs_for_next_batch) >= 1:
        # finalize last batch
        batch = "[" + ",".join(logs_for_next_batch) + "]"
        batches.append(batch)

    return batches
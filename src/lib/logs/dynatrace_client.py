#   Copyright 2024 Dynatrace LLC
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

import asyncio
import gzip
from typing import Union
from urllib.parse import urlparse

from aiohttp import ClientResponseError

from lib.configuration import config

from lib.context import DynatraceConnectivity, LogsContext
from lib.logs.logs_processor import LogBatch

# Status codes that indicate transient failures worth retrying
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
MAX_RETRIES = 3
INITIAL_BACKOFF_SECONDS = 1

DYNATRACE_ERROR_CODE_DESC_DICT = {
    400: DynatraceConnectivity.InvalidInput,
    401: DynatraceConnectivity.ExpiredToken,
    403: DynatraceConnectivity.WrongToken,
    404: DynatraceConnectivity.WrongURL,
    405: DynatraceConnectivity.WrongURL,
    413: DynatraceConnectivity.TooManyRequests,
    429: DynatraceConnectivity.TooManyRequests,
    500: DynatraceConnectivity.Other
}


class DynatraceClient:
    log_ingest_url: str
    verify_ssl: Union[bool, None]

    def __init__(
        self,
        url: str,
        api_key: str
    ):
        self.log_ingest_url = url
        self.dynatrace_api_key = api_key
        self.verify_ssl = None if config.require_valid_certificate() else False

    async def send_logs(self, context: LogsContext, dt_session, batch: LogBatch, ack_ids_to_send):
        headers = {
            "Authorization": f"Api-Token {self.dynatrace_api_key}",
            "Content-Type": "application/json; charset=utf-8",
            "Content-Encoding": "gzip"
        }
        encoded_body_bytes = batch.serialized_batch.encode("UTF-8")
        encoded_body_size_kb = round((batch.size_batch_bytes / 1024), 3)

        compressed_body_bytes = gzip.compress(encoded_body_bytes, compresslevel=6)
        compressed_size_kb = round(len(compressed_body_bytes) / 1024.0, 3)

        try:
            for attempt in range(MAX_RETRIES):
                try:
                    context.self_monitoring.all_requests += 1
                    async with dt_session.request(
                        method="POST",
                        url=self.log_ingest_url,
                        data=compressed_body_bytes,
                        headers=headers,
                        ssl=self.verify_ssl,
                    ) as response:
                        response_text = await response.text()
                        resp_status = response.status

                    if resp_status > 299:
                        context.t_error(
                            f'Log ingest error: {resp_status}, reason: {response.reason}, url: {self.log_ingest_url}, body: "{response_text}"'
                        )
                        error_code_description = DYNATRACE_ERROR_CODE_DESC_DICT.get(resp_status, 0)
                        if error_code_description:
                            context.self_monitoring.dynatrace_connectivity.append(
                                error_code_description
                            )

                        # Retry on transient errors
                        if resp_status in RETRYABLE_STATUS_CODES and attempt < MAX_RETRIES - 1:
                            backoff = INITIAL_BACKOFF_SECONDS * (2 ** attempt)
                            context.t_error(f"Retrying in {backoff}s (attempt {attempt + 1}/{MAX_RETRIES})")
                            await asyncio.sleep(backoff)
                            continue

                        response.raise_for_status()
                    else:
                        ack_ids_to_send.extend(batch.ack_ids)
                        context.self_monitoring.dynatrace_connectivity.append(DynatraceConnectivity.Ok)
                        context.self_monitoring.sent_logs_entries += batch.number_of_logs_in_batch
                        context.self_monitoring.log_ingest_payload_size += compressed_size_kb
                        context.self_monitoring.log_ingest_raw_size += encoded_body_size_kb
                        return  # Success
                except Exception as e:
                    if not isinstance(e, ClientResponseError):
                        context.self_monitoring.dynatrace_connectivity.append(DynatraceConnectivity.Other)
                    # Retry on network errors
                    if attempt < MAX_RETRIES - 1:
                        backoff = INITIAL_BACKOFF_SECONDS * (2 ** attempt)
                        context.t_error(f"Request failed: {e}, retrying in {backoff}s (attempt {attempt + 1}/{MAX_RETRIES})")
                        await asyncio.sleep(backoff)
                        continue
                    raise e
        finally:
            await context.sfm_queue.put(batch.self_monitoring)

         

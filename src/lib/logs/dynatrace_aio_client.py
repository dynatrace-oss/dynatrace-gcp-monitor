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

import ssl
import time
import aiohttp
from typing import List
from urllib.parse import urlparse

from aiohttp import ClientResponseError

from lib.configuration import config
from lib.context import DynatraceConnectivity, LogsContext
from lib.logs.log_self_monitoring import (
    LogSelfMonitoring,
    aggregate_self_monitoring_metrics,
    put_sfm_into_queue,
)
from lib.logs.logs_processor import LogProcessingJob
from lib.logs.aio_client_base import DynatraceAioClientBase

ssl_context = ssl.create_default_context()
if not config.require_valid_certificate():
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE


class DynatraceAioClientFactory:
    dynatrace_api_key: str
    log_ingest_url: str

    def __init__(self):
        dynatrace_url = config.get_dynatrace_log_ingest_url_from_env()  # type: ignore

        self.dynatrace_api_key = config.get_dynatrace_api_key_from_env()  # type: ignore
        self.log_ingest_url = urlparse(dynatrace_url.rstrip("/") + "/api/v2/logs/ingest").geturl()

    def get_dynatrace_client(self, concurrent_con_limit: int = 900):
        my_conn = aiohttp.TCPConnector(limit=concurrent_con_limit)
        aio_http_session = aiohttp.ClientSession(connector=my_conn)
        return DynatraceAioClient(self.dynatrace_api_key, self.log_ingest_url, aio_http_session)


class DynatraceAioClient(DynatraceAioClientBase):
    dynatrace_api_key: str
    log_ingest_url: str

    def __init__(self, dynatrace_api_key, log_ingest_url, aio_http_session):
        self.dynatrace_api_key = dynatrace_api_key
        self.log_ingest_url = log_ingest_url
        super().__init__(aio_http_session)

    async def send_logs(self, context: LogsContext, logs: List[LogProcessingJob], batch: str):
        context.self_monitoring = aggregate_self_monitoring_metrics(
            LogSelfMonitoring(), [log.self_monitoring for log in logs]
        )
        context.self_monitoring.sending_time_start = time.perf_counter()

        headers = {
            "Authorization": f"Api-Token {context.dynatrace_api_key}",
            "Content-Type": "application/json; charset=utf-8",
        }




        encoded_body_bytes = batch.encode("UTF-8")

        try:
            context.self_monitoring.all_requests += 1
            async with self.aio_http_session.request(
                method="POST", url=self.log_ingest_url, data=encoded_body_bytes, headers=headers
            ) as response:
                response_text = await response.text()
                resp_status = response.status

            if resp_status > 299:
                context.t_error(
                    f'Log ingest error: {resp_status}, reason: {response.reason}, url: {self.log_ingest_url}, body: "{response_text}"'
                )
                if resp_status == 400:
                    context.self_monitoring.dynatrace_connectivity.append(
                        DynatraceConnectivity.InvalidInput
                    )
                elif resp_status == 401:
                    context.self_monitoring.dynatrace_connectivity.append(
                        DynatraceConnectivity.ExpiredToken
                    )
                elif resp_status == 403:
                    context.self_monitoring.dynatrace_connectivity.append(
                        DynatraceConnectivity.WrongToken
                    )
                elif resp_status == 404 or resp_status == 405:
                    context.self_monitoring.dynatrace_connectivity.append(
                        DynatraceConnectivity.WrongURL
                    )
                elif resp_status == 413 or resp_status == 429:
                    context.self_monitoring.dynatrace_connectivity.append(
                        DynatraceConnectivity.TooManyRequests
                    )
                elif resp_status == 500:
                    context.self_monitoring.dynatrace_connectivity.append(
                        DynatraceConnectivity.Other
                    )

                response.raise_for_status()
            else:
                context.self_monitoring.dynatrace_connectivity.append(DynatraceConnectivity.Ok)
        except Exception as e:
            if not isinstance(e, ClientResponseError):
                context.self_monitoring.dynatrace_connectivity.append(DynatraceConnectivity.Other)
            raise e
        finally:
            context.self_monitoring.calculate_sending_time()
            put_sfm_into_queue(context)

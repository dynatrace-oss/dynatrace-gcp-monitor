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

import time
from typing import Union
from urllib.parse import urlparse

from aiohttp import ClientResponseError

from lib.configuration import config
from lib.context import DynatraceConnectivity, LogsContext
from lib.logs.log_self_monitoring import (
    LogSelfMonitoring,
    aggregate_self_monitoring_metrics,
    put_sfm_into_queue,
)

from lib.logs.logs_processor import LogBatch


class DynatraceClient():
    dynatrace_api_key: str
    log_ingest_url: str
    verify_ssl: Union[bool, None]

    def __init__(
        self,
    ):
        dynatrace_url: str = config.get_dynatrace_log_ingest_url_from_env()  # type: ignore

        self.dynatrace_api_key = config.get_dynatrace_api_key_from_env()  # type: ignore
        self.log_ingest_url = urlparse(dynatrace_url.rstrip("/") + "/api/v2/logs/ingest").geturl()
        self.verify_ssl = None if config.require_valid_certificate() else False

    async def send_logs(self, context: LogsContext, dt_session, batch: LogBatch, ack_ids_to_send):
        # context.self_monitoring = aggregate_self_monitoring_metrics(
        #     LogSelfMonitoring(), [log.self_monitoring for log in logs]
        # )
        context.self_monitoring.sending_time_start = time.perf_counter()

        headers = {
            "Authorization": f"Api-Token {context.dynatrace_api_key}",
            "Content-Type": "application/json; charset=utf-8",
        }

        encoded_body_bytes = batch.serialized_batch.encode("UTF-8")

        try:
            context.self_monitoring.all_requests += 1
            async with dt_session.request(
                method="POST",
                url=self.log_ingest_url,
                data=encoded_body_bytes,
                headers=headers,
                ssl=self.verify_ssl,
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
                ack_ids_to_send.extend(batch.ack_ids)
                context.self_monitoring.dynatrace_connectivity.append(DynatraceConnectivity.Ok)
        except Exception as e:
            if not isinstance(e, ClientResponseError):
                context.self_monitoring.dynatrace_connectivity.append(DynatraceConnectivity.Other)
            raise e
        finally:
            context.self_monitoring.calculate_sending_time()
            put_sfm_into_queue(context)


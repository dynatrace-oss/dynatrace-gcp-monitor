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

import enum
import os
from datetime import datetime, timedelta
from queue import Queue
from typing import Optional

import aiohttp


def get_int_environment_value(key: str, default_value: int) -> int:
    environment_value = os.environ.get(key, None)
    return int(environment_value) if environment_value and environment_value.isdigit() else default_value


class LoggingContext:
    def __init__(self, scheduled_execution_id: Optional[str]):
        self.scheduled_execution_id: str = scheduled_execution_id[0:8] if scheduled_execution_id else None

    def error(self, *args):
        self.log("ERROR", *args)

    def log(self, *args):
        """
        Prints message log with context data. Last argument is treated as a message, all arguments before that
        are context identifiers, printed in square brackets to easily identify which part of coroutine produced the log
        e.g. >>> LoggingContext("context").log("project_id", "Message")
        produces`2020-11-30 11:29:42.010732 [context] [project_id] : Message`
        :param args:
        :return:
        """
        if not args:
            return
        message = args[-1]

        timestamp_utc = datetime.utcnow()
        timestamp_utc_iso = timestamp_utc.isoformat(sep=" ")

        context_strings = []
        if self.scheduled_execution_id:
            context_strings.append(f"[{self.scheduled_execution_id}]")
        for arg in args[:-1]:
            context_strings.append(f"[{arg}]")
        context_section = " ".join(context_strings)

        print(f"{timestamp_utc_iso} {context_section} : {message}")


class ExecutionContext(LoggingContext):
    def __init__(
            self,
            project_id_owner: str,
            dynatrace_api_key: str,
            dynatrace_url: str,
            scheduled_execution_id: Optional[str]
    ):
        super().__init__(scheduled_execution_id)
        self.project_id_owner = project_id_owner
        self.dynatrace_api_key = dynatrace_api_key
        self.dynatrace_url = dynatrace_url
        self.function_name = os.environ.get("FUNCTION_NAME", "Local")
        self.location = os.environ.get("FUNCTION_REGION", "us-east1")
        self.require_valid_certificate = os.environ.get("REQUIRE_VALID_CERTIFICATE", "True") in ["True", "T", "true"]


class LogsContext(ExecutionContext):
    def __init__(
            self,
            project_id_owner: str,
            dynatrace_api_key: str,
            dynatrace_url: str,
            scheduled_execution_id: Optional[str],
            job_queue: Queue
    ):
        super().__init__(
            project_id_owner=project_id_owner,
            dynatrace_api_key=dynatrace_api_key,
            dynatrace_url=dynatrace_url,
            scheduled_execution_id=scheduled_execution_id
        )

        self.job_queue = job_queue
        self.request_body_max_size = get_int_environment_value("DYNATRACE_LOG_INGEST_REQUEST_MAX_SIZE", 1048576)
        self.batch_max_messages = get_int_environment_value("DYNATRACE_LOG_INGEST_BATCH_MAX_MESSAGES", 10_000)


class MetricsContext(ExecutionContext):
    def __init__(
            self,
            gcp_session: aiohttp.ClientSession,
            dt_session: aiohttp.ClientSession,
            project_id_owner: str,
            token: str,
            execution_time: datetime,
            execution_interval_seconds: int,
            dynatrace_api_key: str,
            dynatrace_url: str,
            print_metric_ingest_input: bool,
            scheduled_execution_id: Optional[str]
    ):
        super().__init__(
            project_id_owner=project_id_owner,
            dynatrace_api_key=dynatrace_api_key,
            dynatrace_url=dynatrace_url,
            scheduled_execution_id=scheduled_execution_id
        )
        self.dt_session = dt_session
        self.gcp_session = gcp_session
        self.token = token
        self.execution_time = execution_time.replace(microsecond=0)
        self.execution_interval = timedelta(seconds=execution_interval_seconds)
        self.print_metric_ingest_input = print_metric_ingest_input
        self.maximum_metric_data_points_per_minute = get_int_environment_value("MAXIMUM_METRIC_DATA_POINTS_PER_MINUTE", 100000)
        self.metric_ingest_batch_size = get_int_environment_value("METRIC_INGEST_BATCH_SIZE", 1000)
        self.use_x_goog_user_project_header = {project_id_owner: False}

        # self monitoring data
        self.dynatrace_request_count = {}
        self.dynatrace_connectivity = DynatraceConnectivity.Ok

        self.gcp_metric_request_count = {}

        self.dynatrace_ingest_lines_ok_count = {}
        self.dynatrace_ingest_lines_invalid_count = {}
        self.dynatrace_ingest_lines_dropped_count = {}

        self.start_processing_timestamp = 0

        self.setup_execution_time = {}
        self.fetch_gcp_data_execution_time = {}
        self.push_to_dynatrace_execution_time = {}


class DynatraceConnectivity(enum.Enum):
    Ok = 0,
    ExpiredToken = 1,
    WrongToken = 2,
    WrongURL = 3,
    Other = 4

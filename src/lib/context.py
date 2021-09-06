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
import traceback
from datetime import datetime, timedelta
from queue import Queue
from typing import Optional, Dict

import aiohttp

from lib.logs.log_sfm_metric_descriptor import LOG_SELF_MONITORING_METRIC_MAP
from lib.logs.log_sfm_metrics import LogSelfMonitoring
from lib.metric_descriptor import SELF_MONITORING_METRIC_MAP
from operation_mode import OperationMode

LOG_THROTTLING_LIMIT_PER_MESSAGE = 10


def get_int_environment_value(key: str, default_value: int) -> int:
    environment_value = os.environ.get(key, None)
    return int(environment_value) if environment_value and environment_value.isdigit() else default_value


def get_should_require_valid_certificate() -> bool:
    return os.environ.get("REQUIRE_VALID_CERTIFICATE", "TRUE").upper() in ["TRUE", "YES"]


def get_selected_services() -> []:
    selected_services_string = os.environ.get("GCP_SERVICES", "")
    return selected_services_string.strip('"').split(",") if selected_services_string else []


class LoggingContext:
    def __init__(self, scheduled_execution_id: Optional[str]):
        self.scheduled_execution_id: str = scheduled_execution_id[0:8] if scheduled_execution_id else None
        self.throttled_log_call_count = dict()

    def error(self, *args):
        self.log("ERROR", *args)

    def exception(self, *args):
        self.log("ERROR", *args)
        traceback.print_exc()

    def t_error(self, *args):
        """
        Prints error with throttling limit per message. Limit per message set in LOG_THROTTLING_LIMIT_PER_CALLER
        Use for potentially frequent log.
        :param args:
        :return:
        """
        if args and self.__check_if_message_exceeded_limit(args[-1]):
            return
        self.error(*args)

    def t_exception(self, *args):
        """
        Prints exception with throttling limit per message. Limit per message set in LOG_THROTTLING_LIMIT_PER_CALLER
        Use for potentially frequent log.
        :param args:
        :return:
        """
        if args and self.__check_if_message_exceeded_limit(args[-1]):
            return
        self.exception(*args)

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

    def __check_if_message_exceeded_limit(self, message: str):
        log_calls_performed = self.throttled_log_call_count.get(message, 0)
        log_calls_left = LOG_THROTTLING_LIMIT_PER_MESSAGE - log_calls_performed

        if log_calls_left == 0:
            self.throttled_log_call_count[message] = log_calls_performed + 1
            self.log(f"Logging calls for message '{message}' exceeded the throttling limit of"
                     f" {LOG_THROTTLING_LIMIT_PER_MESSAGE}. Further logs from this caller will be discarded")

        message_exceeded_limit = log_calls_left <= 0
        if not message_exceeded_limit:
            self.throttled_log_call_count[message] = log_calls_performed + 1

        return message_exceeded_limit


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
        self.require_valid_certificate = get_should_require_valid_certificate()


class LogsContext(ExecutionContext):
    def __init__(
            self,
            project_id_owner: str,
            dynatrace_api_key: str,
            dynatrace_url: str,
            scheduled_execution_id: Optional[str],
            sfm_queue: Queue,
    ):
        super().__init__(
            project_id_owner=project_id_owner,
            dynatrace_api_key=dynatrace_api_key,
            dynatrace_url=dynatrace_url,
            scheduled_execution_id=scheduled_execution_id
        )

        self.sfm_queue = sfm_queue
        self.self_monitoring = LogSelfMonitoring()


class LogsProcessingContext(LogsContext):
    def __init__(
            self,
            scheduled_execution_id: Optional[str],
            message_publish_time: Optional[datetime],
            sfm_queue: Queue
    ):
        super().__init__(
            project_id_owner="",
            dynatrace_api_key="",
            dynatrace_url="",
            scheduled_execution_id=scheduled_execution_id,
            sfm_queue = sfm_queue
        )
        self.message_publish_time = message_publish_time


class SfmDashboardsContext(LoggingContext):
    def __init__(
            self,
            project_id_owner: str,
            token,
            gcp_session: aiohttp.ClientSession,
            operation_mode: OperationMode,
            scheduled_execution_id: Optional[str]
    ):
        super().__init__(scheduled_execution_id)
        self.project_id_owner = project_id_owner
        self.token = token
        self.gcp_session = gcp_session
        self.operation_mode = operation_mode


class SfmContext(ExecutionContext):
    def __init__(
            self,
            project_id_owner: str,
            dynatrace_api_key: str,
            dynatrace_url: str,
            token,
            scheduled_execution_id: Optional[str],
            self_monitoring_enabled: bool,
            sfm_metric_map: Dict,
            gcp_session: aiohttp.ClientSession,
    ):
        super().__init__(
            project_id_owner=project_id_owner,
            dynatrace_api_key=dynatrace_api_key,
            dynatrace_url=dynatrace_url,
            scheduled_execution_id=scheduled_execution_id
        )
        self.token = token
        self.self_monitoring_enabled = self_monitoring_enabled
        self.sfm_metric_map = sfm_metric_map
        self.gcp_session = gcp_session


class LogsSfmContext(SfmContext):
    def __init__(
            self,
            project_id_owner: str,
            dynatrace_url: str,
            logs_subscription_id: str,
            token: str,
            scheduled_execution_id: Optional[str],
            sfm_queue: Queue,
            self_monitoring_enabled: bool,
            gcp_session: aiohttp.ClientSession,
            container_name: str,
            zone: str
    ):
        super().__init__(
            project_id_owner=project_id_owner,
            dynatrace_api_key="",
            dynatrace_url=dynatrace_url,
            token=token,
            scheduled_execution_id=scheduled_execution_id,
            self_monitoring_enabled = self_monitoring_enabled,
            sfm_metric_map = LOG_SELF_MONITORING_METRIC_MAP,
            gcp_session = gcp_session
        )
        self.sfm_queue = sfm_queue
        self.logs_subscription_id = logs_subscription_id
        self.timestamp = datetime.utcnow()
        self.container_name = container_name
        self.zone = zone


class MetricsContext(SfmContext):
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
            self_monitoring_enabled: bool,
            scheduled_execution_id: Optional[str]
    ):
        super().__init__(
            project_id_owner=project_id_owner,
            dynatrace_api_key=dynatrace_api_key,
            dynatrace_url=dynatrace_url,
            token=token,
            scheduled_execution_id=scheduled_execution_id,
            self_monitoring_enabled=self_monitoring_enabled,
            sfm_metric_map=SELF_MONITORING_METRIC_MAP,
            gcp_session=gcp_session
        )
        self.dt_session = dt_session
        self.execution_time = execution_time.replace(microsecond=0)
        self.execution_interval = timedelta(seconds=execution_interval_seconds)
        self.print_metric_ingest_input = print_metric_ingest_input
        self.self_monitoring_enabled = self_monitoring_enabled
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
    Ok = 0
    ExpiredToken = 1
    WrongToken = 2
    WrongURL = 3
    InvalidInput = 4
    TooManyRequests = 5
    Other = 6

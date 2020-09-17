import enum
import os
from datetime import datetime, timedelta

import aiohttp


class Context:
    def __init__(
            self,
            session: aiohttp.ClientSession,
            project_id: str,
            token: str,
            execution_time: datetime,
            execution_interval_seconds: int,
            dynatrace_api_key: str,
            dynatrace_url: str,
            print_metric_ingest_input: bool
    ):
        self.session = session
        self.project_id = project_id
        self.url = "https://monitoring.googleapis.com/v3/projects/{name}/timeSeries".format(name=project_id)
        self.token = token
        self.execution_time = execution_time.replace(microsecond=0)
        self.execution_interval = timedelta(seconds=execution_interval_seconds)
        self.dynatrace_api_key = dynatrace_api_key
        self.dynatrace_url = dynatrace_url
        self.print_metric_ingest_input = print_metric_ingest_input
        self.function_name = os.environ.get("FUNCTION_NAME", "Local")
        self.location = os.environ.get("FUNCTION_REGION", "us-east1")

        # self monitoring data
        self.dynatrace_request_count = {}
        self.dynatrace_connectivity = DynatraceConnectivity.Ok
        self.dynatrace_ingest_lines_ok_count = 0
        self.dynatrace_ingest_lines_invalid_count = 0
        self.setup_execution_time = 0
        self.fetch_gcp_data_execution_time = 0
        self.push_to_dynatrace_execution_time = 0


class DynatraceConnectivity(enum.Enum):
    Ok = 0,
    ExpiredToken = 1,
    WrongToken = 2,
    WrongURL = 3,
    Other = 4

import enum
from abc import abstractmethod
from typing import List

from lib.sfm.for_metrics.metric_descriptor import SELF_MONITORING_METRIC_PREFIX
from lib.sfm.metrics_timeseries_datatpoint import create_timeseries_datapoint


class SfmKeys(enum.Enum):
    dynatrace_request_count = 1
    gcp_metric_request_count = 2
    dynatrace_ingest_lines_ok_count = 3
    dynatrace_ingest_lines_invalid_count = 4
    dynatrace_ingest_lines_dropped_count = 5
    setup_execution_time = 6
    fetch_gcp_data_execution_time = 7
    push_to_dynatrace_execution_time = 8
    dynatrace_connectivity = 9
    gcp_metric_empty_response_count = 10
    gcp_api_latency = 11
    gcp_api_error_count = 12
    gcp_api_response_count = 13
    dimension_name_truncated_count = 14
    dimension_value_truncated_count = 15


class SfmMetric:
    @property
    @abstractmethod
    def key(self):
        pass

    @abstractmethod
    def generate_timeseries_datapoints(self, context, interval) -> List[dict]:
        pass


class SFMMetricDynatraceRequestCount(SfmMetric):
    key = SELF_MONITORING_METRIC_PREFIX + "/request_count"
    description = "GCP Monitoring API request count [per project]"

    def __init__(self):
        self.value = {}

    def increment(self, status):
        self.value[status] = self.value.get(status, 0) + 1

    def generate_timeseries_datapoints(self, context, interval):
        time_series = []

        for status_code, count in self.value.items():
            time_series.append(create_timeseries_datapoint(
                context, self.key,
                {
                    "response_code": str(status_code),
                    "function_name": context.function_name,
                    "dynatrace_tenant_url": context.dynatrace_url
                },
                [{
                    "interval": interval,
                    "value": {"int64Value": count}
                }]
            ))

        return time_series


class SFMMetricGCPMetricRequestCount(SfmMetric):
    key = None
    description = "GCP Monitoring API request count [per project]"

    def __init__(self):
        self.value = {}

    def increment(self, project):
        self.value[project] = self.value.get(project, 0) + 1

    def generate_timeseries_datapoints(self, context, interval):
        # no timeseries generated before, preserving behaviour!!!
        return []


class SFMMetricGCPEmptyResponseCount(SfmMetric):
    """Tracks when GCP Monitoring API returns no data for a metric query.
    Useful for diagnosing data gaps in Dynatrace."""
    key = SELF_MONITORING_METRIC_PREFIX + "/gcp_empty_response_count"
    description = "GCP Monitoring API empty response count [per project]"

    def __init__(self):
        self.value = {}

    def increment(self, project: str):
        self.value[project] = self.value.get(project, 0) + 1

    def generate_timeseries_datapoints(self, context, interval) -> List[dict]:
        time_series = []
        for project_id, count in self.value.items():
            time_series.append(create_timeseries_datapoint(
                context, self.key,
                {
                    "function_name": context.function_name,
                    "dynatrace_tenant_url": context.dynatrace_url,
                    "project_id": project_id,
                },
                [{
                    "interval": interval,
                    "value": {"int64Value": count}
                }]
            ))
        return time_series


class SFMMetricGCPApiLatency(SfmMetric):
    """Tracks GCP Monitoring API response latency for gap diagnosis."""
    key = SELF_MONITORING_METRIC_PREFIX + "/gcp_api_latency"
    description = "GCP Monitoring API latency in seconds [per project]"

    def __init__(self):
        self.values = []  # list of (project_id, latency_seconds)

    @property
    def value(self):
        """Return max latency per project as dict for consistency with other SFM metrics."""
        if not self.values:
            return {}
        max_by_project = {}
        for project_id, latency in self.values:
            if project_id not in max_by_project or latency > max_by_project[project_id]:
                max_by_project[project_id] = latency
        return max_by_project

    def record(self, project: str, latency_seconds: float):
        self.values.append((project, latency_seconds))

    def generate_timeseries_datapoints(self, context, interval) -> List[dict]:
        # Aggregate by project: report max latency per project
        max_latency_by_project = {}
        for project_id, latency in self.values:
            if project_id not in max_latency_by_project or latency > max_latency_by_project[project_id]:
                max_latency_by_project[project_id] = latency

        time_series = []
        for project_id, max_latency in max_latency_by_project.items():
            time_series.append(create_timeseries_datapoint(
                context, self.key,
                {
                    "function_name": context.function_name,
                    "dynatrace_tenant_url": context.dynatrace_url,
                    "project_id": project_id,
                },
                [{
                    "interval": interval,
                    "value": {"doubleValue": max_latency}
                }],
                "DOUBLE"
            ))
        return time_series


class SFMMetricGCPApiErrorCount(SfmMetric):
    """Tracks GCP Monitoring API errors by status code."""
    key = SELF_MONITORING_METRIC_PREFIX + "/gcp_api_error_count"
    description = "GCP Monitoring API error count by status code"

    def __init__(self):
        self.value = {}  # {(project_id, status_code): count}

    def increment(self, project: str, status_code: int):
        key = (project, status_code)
        self.value[key] = self.value.get(key, 0) + 1

    def generate_timeseries_datapoints(self, context, interval) -> List[dict]:
        time_series = []
        for (project_id, status_code), count in self.value.items():
            time_series.append(create_timeseries_datapoint(
                context, self.key,
                {
                    "function_name": context.function_name,
                    "dynatrace_tenant_url": context.dynatrace_url,
                    "project_id": project_id,
                    "status_code": str(status_code),
                },
                [{
                    "interval": interval,
                    "value": {"int64Value": count}
                }]
            ))
        return time_series


class SFMMetricGCPApiResponseCount(SfmMetric):
    """Tracks GCP Monitoring API responses by status code (similar to Dynatrace request count)."""
    key = SELF_MONITORING_METRIC_PREFIX + "/gcp_api_response_count"
    description = "GCP Monitoring API response count by status code"

    def __init__(self):
        self.value = {}  # {status_code: count}

    def increment(self, status_code: int):
        self.value[status_code] = self.value.get(status_code, 0) + 1

    def generate_timeseries_datapoints(self, context, interval) -> List[dict]:
        time_series = []
        for status_code, count in self.value.items():
            time_series.append(create_timeseries_datapoint(
                context, self.key,
                {
                    "function_name": context.function_name,
                    "dynatrace_tenant_url": context.dynatrace_url,
                    "response_code": str(status_code),
                },
                [{
                    "interval": interval,
                    "value": {"int64Value": count}
                }]
            ))
        return time_series


class SFMMetricDimensionNameTruncatedCount(SfmMetric):
    key = SELF_MONITORING_METRIC_PREFIX + "/dimension_name_truncated_count"
    description = "Number of truncated dimension names [per project]"

    def __init__(self):
        self.value = {}

    def increment(self, project: str):
        self.value[project] = self.value.get(project, 0) + 1

    def generate_timeseries_datapoints(self, context, interval) -> List[dict]:
        time_series = []
        for project_id, count in self.value.items():
            time_series.append(create_timeseries_datapoint(
                context, self.key,
                {
                    "function_name": context.function_name,
                    "dynatrace_tenant_url": context.dynatrace_url,
                    "project_id": project_id,
                },
                [{
                    "interval": interval,
                    "value": {"int64Value": count}
                }]
            ))
        return time_series


class SFMMetricDimensionValueTruncatedCount(SfmMetric):
    key = SELF_MONITORING_METRIC_PREFIX + "/dimension_value_truncated_count"
    description = "Number of truncated dimension values [per project]"

    def __init__(self):
        self.value = {}

    def increment(self, project: str):
        self.value[project] = self.value.get(project, 0) + 1

    def generate_timeseries_datapoints(self, context, interval) -> List[dict]:
        time_series = []
        for project_id, count in self.value.items():
            time_series.append(create_timeseries_datapoint(
                context, self.key,
                {
                    "function_name": context.function_name,
                    "dynatrace_tenant_url": context.dynatrace_url,
                    "project_id": project_id,
                },
                [{
                    "interval": interval,
                    "value": {"int64Value": count}
                }]
            ))
        return time_series


class SFMMetricDynatraceIngestLinesOkCount(SfmMetric):
    key = SELF_MONITORING_METRIC_PREFIX + "/ingest_lines"
    description = "Dynatrace MINT accepted lines count [per project]"

    def __init__(self):
        self.value = {}

    def update(self, project, lines: int):
        self.value[project] = self.value.get(project, 0) + lines

    def generate_timeseries_datapoints(self, context, interval) -> List[dict]:
        time_series = []

        for project_id, count in self.value.items():
            time_series.append(create_timeseries_datapoint(
                context, self.key,
                {
                    "function_name": context.function_name,
                    "dynatrace_tenant_url": context.dynatrace_url,
                    "status": "Ok",
                    "project_id": project_id,
                },
                [{
                    "interval": interval,
                    "value": {"int64Value": count}
                }]))
        return time_series


class SFMMetricDynatraceIngestLinesInvalidCount(SfmMetric):
    key = SELF_MONITORING_METRIC_PREFIX + "/ingest_lines"
    description = "Dynatrace MINT invalid lines count [per project]"

    def __init__(self):
        self.value = {}

    def update(self, project, lines: int):
        self.value[project] = self.value.get(project, 0) + lines

    def generate_timeseries_datapoints(self, context, interval):
        time_series = []
        for project_id, count in self.value.items():
            time_series.append(create_timeseries_datapoint(
                context, self.key,
                {
                    "function_name": context.function_name,
                    "dynatrace_tenant_url": context.dynatrace_url,
                    "status": "Invalid",
                    "project_id": project_id,
                },
                [{
                    "interval": interval,
                    "value": {"int64Value": count}
                }]))
        return time_series


class SFMMetricDynatraceIngestLinesDroppedCount(SfmMetric):
    key = SELF_MONITORING_METRIC_PREFIX + "/ingest_lines"
    description = "Dynatrace MINT dropped lines count [per project]"

    def __init__(self):
        self.value = {}

    def update(self, project, lines: int):
        self.value[project] = self.value.get(project, 0) + lines

    def generate_timeseries_datapoints(self, context, interval):
        time_series = []
        for project_id, count in self.value.items():
            time_series.append(create_timeseries_datapoint(
                context, self.key,
                {
                    "function_name": context.function_name,
                    "dynatrace_tenant_url": context.dynatrace_url,
                    "status": "Dropped",
                    "project_id": project_id,
                },
                [{
                    "interval": interval,
                    "value": {"int64Value": count}
                }]))
        return time_series


class SFMMetricSetupExecutionTime(SfmMetric):
    key = SELF_MONITORING_METRIC_PREFIX + "/phase_execution_time"
    description = "Setup execution time"

    def __init__(self):
        self.value = {}

    def update(self, project, time):
        self.value[project] = time

    def generate_timeseries_datapoints(self, context, interval):
        time_series = []
        for project_id, time in self.value.items():
            time_series.append(create_timeseries_datapoint(
                context, self.key,
                {
                    "function_name": context.function_name,
                    "dynatrace_tenant_url": context.dynatrace_url,
                    "phase": "setup",
                    "project_id": project_id,
                },
                [{
                    "interval": interval,
                    "value": {"doubleValue": time}
                }],
                "DOUBLE"))
        return time_series


class SFMMetricFetchGCPDataExecutionTime(SfmMetric):
    key = SELF_MONITORING_METRIC_PREFIX + "/phase_execution_time"
    description = "Fetch GCP data execution time [per project]"

    def __init__(self):
        self.value = {}

    def update(self, project, time):
        self.value[project] = time

    def generate_timeseries_datapoints(self, context, interval):
        time_series = []
        for project_id, time in self.value.items():
            time_series.append(create_timeseries_datapoint(
                context, self.key,
                {
                    "function_name": context.function_name,
                    "dynatrace_tenant_url": context.dynatrace_url,
                    "phase": "fetch_gcp_data",
                    "project_id": project_id,
                },
                [{
                    "interval": interval,
                    "value": {"doubleValue": time}
                }],
                "DOUBLE"))
        return time_series


class SFMMetricPushToDynatraceExecutionTime(SfmMetric):
    key = SELF_MONITORING_METRIC_PREFIX + "/phase_execution_time"
    description = "Push data to Dynatrace execution time [per project]"

    def __init__(self):
        self.value = {}

    def update(self, project, time):
        self.value[project] = time

    def generate_timeseries_datapoints(self, context, interval):
        time_series = []
        for project_id, time in self.value.items():
            time_series.append(create_timeseries_datapoint(
                context, self.key,
                {
                    "function_name": context.function_name,
                    "dynatrace_tenant_url": context.dynatrace_url,
                    "phase": "push_to_dynatrace",
                    "project_id": project_id,
                },
                [{
                    "interval": interval,
                    "value": {"doubleValue": time}
                }],
                "DOUBLE"))
        return time_series


class SFMMetricDynatraceConnectivity(SfmMetric):
    key = SELF_MONITORING_METRIC_PREFIX + "/connectivity"
    description = "Dynatrace Connectivity"

    def __init__(self):
        self.value = {}

    def update(self, value):
        self.value = value

    def generate_timeseries_datapoints(self, context, interval):
        return [create_timeseries_datapoint(
            context, self.key,
            {
                "function_name": context.function_name,
                "dynatrace_tenant_url": context.dynatrace_url,
                "reason": self.value.name,
            },
            [{
                "interval": interval,
                "value": {"int64Value": 1}
            }])]

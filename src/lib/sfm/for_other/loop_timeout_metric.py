from lib.sfm.for_metrics.metric_descriptor import SELF_MONITORING_METRIC_PREFIX
from lib.sfm.for_metrics.metrics_definitions import SfmMetric
from lib.sfm.metrics_timeseries_datatpoint import create_timeseries_datapoint


class SFMMetricLoopTimeouts(SfmMetric):
    key = SELF_MONITORING_METRIC_PREFIX + "/loop_timeouts"
    value = 0
    description = "GCP Monitoring API request count [per project]"

    def update(self, finished_before_timeout: bool):
        if not finished_before_timeout:
            self.value = 1

    def generate_timeseries_datapoints(self, context, interval):
        time_series = [create_timeseries_datapoint(
            context, self.key,
            {
                "function_name": context.function_name,
                "dynatrace_tenant_url": context.dynatrace_url
            },
            [{
                "interval": interval,
                "value": {"int64Value": self.value}
            }]
        )]

        return time_series

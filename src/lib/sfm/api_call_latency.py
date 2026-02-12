from collections import defaultdict

from lib.context import LoggingContext
from lib.utilities import percentile


class ApiCallLatency:
    _value = defaultdict(list)

    @staticmethod
    def update(api_url, time):
        ApiCallLatency._value[api_url].append(time)

    @staticmethod
    def print_statistics(context: LoggingContext):
        log_line = "API call latency statistics: "
        for api_url, times in ApiCallLatency._value.items():
            sorted_times = sorted(times)
            p50 = percentile(sorted_times, 50)
            p90 = percentile(sorted_times, 90)
            p99 = percentile(sorted_times, 99)
            log_line += (
                f"({api_url}: [p50 - {p50:.3}s, p90 - {p90:.3}s, p99 - {p99:.3}s, max - {max(times):.3}s], "
                f"[calls - {len(times)}])"
            )
        context.log(log_line)
        ApiCallLatency._value = defaultdict(list)

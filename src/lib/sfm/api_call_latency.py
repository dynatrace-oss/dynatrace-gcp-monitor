from lib.context import LoggingContext
from collections import defaultdict


class ApiCallLatency:
    _value = defaultdict(list)

    @staticmethod
    def update(api_url, time):
        ApiCallLatency._value[api_url].append(time)

    @staticmethod
    def print_statistics(context: LoggingContext):
        log_line = "API call latency statistics: "
        for api_url, times in ApiCallLatency._value.items():
            log_line += (
                f"({api_url}: [min - {min(times):.3}s, avg - {sum(times) / len(times):.3}s, max - {max(times):.3}s], "
                f"[number_of_calls - {len(times)}])"
            )
        context.log(log_line)
        ApiCallLatency._value = defaultdict(list)

from lib.context import LoggingContext
from collections import defaultdict


class ApiCallLatency:
    _value = defaultdict(list)

    @staticmethod
    def update(api_url, time):
        ApiCallLatency._value[api_url].append(time)

    @staticmethod
    def print_statistics(context: LoggingContext):
        print("Print_statistics has been called :)")
        for api_url, times in ApiCallLatency._value.items():
            context.log(
                f"Api call latency: [url - {api_url}], [number_of_calls - {len(times)}], "
                f"[min - {min(times):.3}s, avg - {sum(times) / len(times):.3}s, max - {max(times):.3}s]"
            )
        ApiCallLatency._value = defaultdict(list)

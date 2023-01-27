from lib.context import LoggingContext
from collections import defaultdict


class ApiCallLatency:
    _value = defaultdict(list)

    @staticmethod
    def update(api_url, time):
        if api_url in ApiCallLatency._value:
            ApiCallLatency._value[api_url].append(time)
        else:
            ApiCallLatency._value[api_url] = [time]

    @staticmethod
    def print_statistics(context: LoggingContext):
        for api_url, times in ApiCallLatency._value.items():
            context.log(f"Url: {api_url}, min: {min(times):.3}s, avg: {sum(times) / len(times):.3}s, max: {max(times):.3}s")
        ApiCallLatency._value = {}

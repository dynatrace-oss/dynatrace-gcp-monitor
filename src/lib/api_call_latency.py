from src.lib.context import LoggingContext


class ApiCallLatency(object):
    _instance = None
    _value = {}

    @staticmethod
    def update(api_url, time):
        if api_url in ApiCallLatency._value:
            ApiCallLatency._value[api_url].append(time)
        else:
            ApiCallLatency._value[api_url] = [time]


    @staticmethod
    def generate_statistics(context: LoggingContext):
        for api_url, times in ApiCallLatency._value.items():
            context.log(f"Url: {api_url}, min: {min(times)}, avg: { sum(times) / len(times)}, max: {max(times)}")
        ApiCallLatency._value = {}

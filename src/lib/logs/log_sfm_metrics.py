import time


class LogSelfMonitoring:
    def __init__(self):
        self.too_old_records: int = 0
        self.publish_time_fallback_records: int = 0
        self.parsing_errors: int = 0
        self.records_with_too_long_content: int = 0
        self.all_requests: int = 0
        self.dynatrace_connectivity = []
        self.processing_time_start: float = 0
        self.processing_time: float = 0
        self.sending_time_start: float = 0
        self.sending_time: float = 0
        self.log_ingest_payload_size: float = 0
        self.sent_logs_entries: int = 0

    def calculate_processing_time(self):
        self.processing_time = (time.perf_counter() - self.processing_time_start)

    def calculate_sending_time(self):
        self.sending_time = (time.perf_counter() - self.sending_time_start)
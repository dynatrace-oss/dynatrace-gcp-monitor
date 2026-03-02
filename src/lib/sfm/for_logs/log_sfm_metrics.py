#     Copyright 2024 Dynatrace LLC
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

import time


class LogSelfMonitoring:
    def __init__(self):
        self.too_old_records: int = 0
        self.publish_time_fallback_records: int = 0
        self.parsing_errors: int = 0
        self.records_with_too_long_content: int = 0
        self.all_requests: int = 0
        self.dt_connectivity = []  # HTTP status codes from DT API (0 = network error)
        self.gcp_connectivity = []  # HTTP status codes from GCP Pub/Sub API (0 = network error)
        self.processing_time_start: float = 0
        # Note: processing_time is CUMULATIVE across all coroutines (may exceed wall-clock time)
        self.processing_time: float = 0
        self.pulling_time_start: float = 0
        # Note: pulling_time is CUMULATIVE across all coroutines (may exceed wall-clock time)
        self.pulling_time: float = 0
        self.sending_time_start: float = 0
        # Note: sending_time is CUMULATIVE across all coroutines (may exceed wall-clock time)
        self.sending_time: float = 0
        self.log_ingest_payload_size: float = 0
        self.log_ingest_raw_size: float = 0
        self.pulled_logs_entries: int = 0
        self.sent_logs_entries: int = 0
        self.ack_failures: int = 0
        self.acks_succeeded: int = 0
        self.ack_backlog: int = 0
        # Bottleneck detection metrics
        self.push_queue_size_max: int = 0
        self.push_wait_time: float = 0
        self.messages_per_second: float = 0
        self.batch_latency_total: float = 0
        self.batch_latency_count: int = 0

    def calculate_processing_time(self):
        self.processing_time = (time.perf_counter() - self.processing_time_start)

    def calculate_sending_time(self):
        self.sending_time = (time.perf_counter() - self.sending_time_start)
    
    def calculate_pulling_time(self):
        self.pulling_time = (time.perf_counter() - self.pulling_time_start)
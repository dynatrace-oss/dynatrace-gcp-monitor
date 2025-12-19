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
        self.dynatrace_connectivity = []
        self.processing_time_start: float = 0
        self.processing_time: float = 0
        self.pulling_time_start: float = 0
        self.pulling_time: float = 0
        self.sending_time_start: float = 0
        self.sending_time: float = 0
        self.log_ingest_payload_size: float = 0
        self.log_ingest_raw_size: float = 0
        self.sent_logs_entries: int = 0
        self.ack_failures: int = 0

    def calculate_processing_time(self):
        self.processing_time = (time.perf_counter() - self.processing_time_start)

    def calculate_sending_time(self):
        self.sending_time = (time.perf_counter() - self.sending_time_start)
    
    def calculate_pulling_time(self):
        self.pulling_time = (time.perf_counter() - self.pulling_time_start)
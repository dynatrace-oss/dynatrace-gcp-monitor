#     Copyright 2020 Dynatrace LLC
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
from typing import List, Optional

from lib.logs.log_forwarder_variables import REQUEST_MAX_EVENTS, REQUEST_BODY_MAX_SIZE, \
    SENDING_WORKER_EXECUTION_PERIOD_SECONDS
from lib.logs.logs_processor import LogProcessingJob


class WorkerState:
    worker_name: str
    ack_ids: List[str]  # May be greater than jobs, worker is ACKing failed (too old or too big) messages too
    last_flush_time: float
    jobs: List[LogProcessingJob]
    batch_bytes_size: int
    batch: str

    def __init__(self, worker_name: str):
        self.reset()
        self.worker_name = worker_name

    def reset(self):
        self.last_flush_time = time.time()
        self.ack_ids = []
        self.jobs = []
        self.batch = "["
        self.batch_bytes_size = 1

    def add_job(self, log_processing_job: LogProcessingJob, ack_id: str):
        self.ack_ids.append(ack_id)
        if self.jobs:
            self.batch += ","
            self.batch_bytes_size += 1
        self.batch += log_processing_job.payload
        self.batch_bytes_size += log_processing_job.bytes_size
        self.jobs.append(log_processing_job)

    def merge_worker(self,worker):
        self.ack_ids.extend(worker.ack_ids)
        self.jobs.extend(worker.jobs)
        self.batch += ", " + worker.batch[1:]
        self.batch_bytes_size += worker.batch_bytes_size


    def should_flush(self, next_log_processing_job: Optional[LogProcessingJob] = None) -> bool:
        """
        Check if worker state should be flushed before calling #add_job on this WorkerState instance
        :param next_log_processing_job: next log message to process
        :return: bool value indicating if state should be flushed
        """
        time_has_passed = (time.time() - self.last_flush_time) > SENDING_WORKER_EXECUTION_PERIOD_SECONDS
        if not next_log_processing_job:
            return time_has_passed

        too_many_messages = len(self.jobs) + 1 > REQUEST_MAX_EVENTS
        batch_is_big = self.batch_bytes_size + next_log_processing_job.bytes_size + 2 >= REQUEST_BODY_MAX_SIZE
        return too_many_messages or batch_is_big or time_has_passed

    @property
    def finished_batch(self):
        return self.batch + "]"

    @property
    def finished_batch_bytes_size(self):
        return self.batch_bytes_size + 1

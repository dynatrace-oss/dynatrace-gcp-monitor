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
import traceback
from functools import partial
from queue import Queue
from time import sleep, time
from typing import List, Callable

from lib.context import LogsContext
from lib.credentials import get_dynatrace_api_key_from_env, get_dynatrace_log_ingest_url_from_env, \
    get_project_id_from_environment
from lib.logs.dynatrace_client import send_logs
from lib.logs.log_forwarder_variables import BATCH_MAX_MESSAGES
from lib.logs.logs_processor import LogProcessingJob


def create_log_sending_worker_loop(execution_period_seconds : int, job_queue: Queue, sfm_queue: Queue) -> Callable:
    return partial(_log_sending_worker_loop, execution_period_seconds, job_queue, sfm_queue)


def create_logs_context(job_queue: Queue, sfm_queue: Queue):
    dynatrace_api_key = get_dynatrace_api_key_from_env()
    dynatrace_url = get_dynatrace_log_ingest_url_from_env()
    project_id_owner = get_project_id_from_environment()

    return LogsContext(
        project_id_owner=project_id_owner,
        dynatrace_api_key=dynatrace_api_key,
        dynatrace_url=dynatrace_url,
        scheduled_execution_id=str(int(time()))[-8:],
        job_queue=job_queue,
        sfm_queue=sfm_queue
    )


def _log_sending_worker_loop(execution_period_seconds: int, job_queue: Queue, sfm_queue: Queue):
    while True:
        try:
            _loop_single_period(execution_period_seconds, job_queue, sfm_queue)
        except Exception:
            print("Logs Sending Worker Loop Exception:")
            traceback.print_exc()


def _loop_single_period(execution_period_seconds: int, job_queue: Queue, sfm_queue: Queue):
    try:
        context = create_logs_context(job_queue, sfm_queue)
        _sleep_until_next_execution(execution_period_seconds)
        _process_jobs(context)
    except Exception:
        print("Logs Sending Worker Loop Exception:")
        traceback.print_exc()


def _sleep_until_next_execution(execution_period_seconds):
    if execution_period_seconds > 0:
        execution_period_seconds = execution_period_seconds
        current_timestamp = int(time())
        next_execution_time = (int(current_timestamp / execution_period_seconds) + 1) * execution_period_seconds
        sleep_time = next_execution_time - current_timestamp

        if sleep_time > 0:
            sleep(sleep_time)


def _process_jobs(context: LogsContext):
    context.log("Starting log sending worker execution")
    jobs = _pull_jobs(context)
    number_of_messages = len(jobs)
    context.log(f"Processing {number_of_messages} messages")
    payloads = [job.payload for job in jobs]
    if payloads:
        sfm_list = [job.self_monitoring for job in jobs]
        send_logs(context, payloads, sfm_list)
        context.self_monitoring.sent_logs_entries += number_of_messages
        for job in jobs:
            job.message.ack()
            context.job_queue.task_done()
    else:
        context.log("Found no messages, skipping")
    context.log("Finished Processing")


def _pull_jobs(context):
    jobs: List[LogProcessingJob] = []
    # Limit for batch size to avoid pulling forever
    while len(jobs) < BATCH_MAX_MESSAGES and context.job_queue.qsize() > 0:
        job: LogProcessingJob = context.job_queue.get()
        jobs.append(job)
    return jobs


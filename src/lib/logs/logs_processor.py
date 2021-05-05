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

import json
import queue
import time
import traceback
from datetime import datetime, timezone
from functools import partial
from queue import Queue
from typing import Optional, Dict, Callable

from dateutil.parser import *
from google.cloud.pubsub_v1.subscriber.message import Message

from lib.context import LogsProcessingContext, LogsContext
from lib.logs.log_forwarder_variables import EVENT_AGE_LIMIT_SECONDS, SENDING_WORKER_EXECUTION_PERIOD_SECONDS, \
    CONTENT_LENGTH_LIMIT
from lib.logs.log_self_monitoring import LogSelfMonitoring, put_sfm_into_queue
from lib.logs.metadata_engine import MetadataEngine, ATTRIBUTE_CONTENT, ATTRIBUTE_TIMESTAMP

_metadata_engine = MetadataEngine()


class LogProcessingJob:
    payload: Dict
    message: Message
    self_monitoring: LogSelfMonitoring

    def __init__(self, payload: Dict, message: Message, self_monitoring: LogSelfMonitoring):
        self.payload = payload
        self.message = message
        self.self_monitoring: LogSelfMonitoring = self_monitoring


def create_process_message_handler(log_jobs_queue: Queue, sfm_queue: Queue) -> Callable[[Message], None]:
    return partial(_process_message, log_jobs_queue, sfm_queue)


def _process_message(log_jobs_queue: Queue, sfm_queue: Queue, message: Message):
    context = LogsProcessingContext(
        scheduled_execution_id=str(message.ack_id.__hash__())[-8:],
        job_queue=log_jobs_queue,
        sfm_queue=sfm_queue
    )
    try:
        _do_process_message(context, message)
    except Exception as exception:
        if isinstance(exception, queue.Full):
            context.error(f"Failed to process message due full job queue, rejecting the message")
            message.nack()
        else:
            context.error(f"Failed to process message due to {type(exception).__name__}")
            message.ack()
            context.self_monitoring.parsing_errors += 1
            context.self_monitoring.calculate_processing_time()
            put_sfm_into_queue(context)
            traceback.print_exc()


def _do_process_message(context: LogsContext, message: Message):
    context.self_monitoring.processing_time_start = time.perf_counter()
    data = message.data.decode("UTF-8")
    # context.log(f"Data: {data}")

    payload = _create_dt_log_payload(context, data)
    # context.log(f"Payload: {payload}")
    context.self_monitoring.calculate_processing_time()

    if not payload:
        message.ack()
        put_sfm_into_queue(context)
    else:
        job = LogProcessingJob(payload, message, context.self_monitoring)
        context.job_queue.put(job, True, SENDING_WORKER_EXECUTION_PERIOD_SECONDS + 1)


def _create_dt_log_payload(context: LogsContext, message_data: str) -> Optional[Dict]:
    record = json.loads(message_data)
    parsed_record = {}

    _metadata_engine.apply(context, record, parsed_record)

    parsed_timestamp = parsed_record.get(ATTRIBUTE_TIMESTAMP, None)
    if _is_log_too_old(parsed_timestamp):
        context.log(f"Skipping message due to too old timestamp: {parsed_timestamp}")
        context.self_monitoring.too_old_records += 1
        return None

    content = parsed_record.get(ATTRIBUTE_CONTENT, None)
    if content:
        if not isinstance(content, str):
            parsed_record[ATTRIBUTE_CONTENT] = json.dumps(parsed_record[ATTRIBUTE_CONTENT])
        if len(parsed_record[ATTRIBUTE_CONTENT]) >= CONTENT_LENGTH_LIMIT:
            parsed_record[ATTRIBUTE_CONTENT] = parsed_record[ATTRIBUTE_CONTENT][:CONTENT_LENGTH_LIMIT]
            context.self_monitoring.records_with_too_long_content += 1

    return parsed_record


def _is_log_too_old(timestamp: Optional[str]):
    timestamp_datetime = parse(timestamp)
    event_age_in_seconds = (datetime.now(timezone.utc) - timestamp_datetime).total_seconds()
    return event_age_in_seconds > EVENT_AGE_LIMIT_SECONDS
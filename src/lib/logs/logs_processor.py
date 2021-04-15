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
import traceback
from datetime import datetime, timedelta, timezone
from functools import partial
from typing import Optional, Dict, Callable
from queue import Queue

from dateutil.parser import *
from google.cloud.pubsub_v1.subscriber.message import Message

from lib.context import LoggingContext, get_int_environment_value
from lib.logs.metadata_engine import MetadataEngine, ATTRIBUTE_CONTENT, ATTRIBUTE_TIMESTAMP

_CONTENT_LENGTH_LIMIT = get_int_environment_value("DYNATRACE_LOG_INGEST_CONTENT_MAX_LENGTH", 8192)
_EVENT_AGE_LIMIT_SECONDS = get_int_environment_value("DYNATRACE_LOG_INGEST_EVENT_MAX_AGE_SECONDS", int(timedelta(days=1).total_seconds()))
SENDING_WORKER_EXECUTION_PERIOD_SECONDS = get_int_environment_value("DYNATRACE_LOG_INGEST_SENDING_WORKER_EXECUTION_PERIOD", 60)

_metadata_engine = MetadataEngine()


class LogProcessingJob:
    payload: Dict
    message: Message

    def __init__(self, payload: Dict, message: Message):
        self.payload = payload
        self.message = message


def create_process_message_handler(log_jobs_queue: Queue) -> Callable[[Message], None]:
    return partial(_process_message, log_jobs_queue)


def _process_message(log_jobs_queue: Queue, message: Message):
    context = LoggingContext(str(message.ack_id.__hash__())[-8:])
    try:
        _do_process_message(context, log_jobs_queue, message)
    except Exception as exception:
        if isinstance(exception, queue.Full):
            context.error(f"Failed to process message due full job queue, rejecting the message")
            message.nack()
        else:
            context.error(f"Failed to process message due to {type(exception).__name__}")
            traceback.print_exc()


def _do_process_message(context: LoggingContext, log_jobs_queue: Queue, message: Message):
    data = message.data.decode("UTF-8")
    # context.log(f"Data: {data}")

    payload = _create_dt_log_payload(context, data)
    # context.log(f"Payload: {payload}")

    if not payload:
        message.ack()
    else:
        job = LogProcessingJob(payload, message)
        log_jobs_queue.put(job, True, SENDING_WORKER_EXECUTION_PERIOD_SECONDS + 1)


def _create_dt_log_payload(context: LoggingContext, message_data: str) -> Optional[Dict]:
    record = json.loads(message_data)
    parsed_record = {}

    _metadata_engine.apply(context, record, parsed_record)

    parsed_timestamp = parsed_record.get(ATTRIBUTE_TIMESTAMP, None)
    if _is_log_too_old(parsed_timestamp):
        context.log(f"Skipping message due to too old timestamp: {parsed_timestamp}")
        return None

    content = parsed_record.get(ATTRIBUTE_CONTENT, None)
    if content:
        if not isinstance(content, str):
            parsed_record[ATTRIBUTE_CONTENT] = json.dumps(parsed_record[ATTRIBUTE_CONTENT])
        if len(parsed_record[ATTRIBUTE_CONTENT]) >= _CONTENT_LENGTH_LIMIT:
            parsed_record[ATTRIBUTE_CONTENT] = parsed_record[ATTRIBUTE_CONTENT][:_CONTENT_LENGTH_LIMIT]

    return parsed_record


def _is_log_too_old(timestamp: Optional[str]):
    timestamp_datetime = parse(timestamp)
    event_age_in_seconds = (datetime.now(timezone.utc) - timestamp_datetime).total_seconds()
    return event_age_in_seconds > _EVENT_AGE_LIMIT_SECONDS
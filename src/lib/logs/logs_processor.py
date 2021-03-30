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

_CONTENT_LENGTH_LIMIT = get_int_environment_value("DYNATRACE_LOG_INGEST_CONTENT_MAX_LENGTH", 8192)
_EVENT_AGE_LIMIT_SECONDS = get_int_environment_value("DYNATRACE_LOG_INGEST_EVENT_MAX_AGE_SECONDS", int(timedelta(days=1).total_seconds()))


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
        log_jobs_queue.put(job, True, 61)


def _create_dt_log_payload(context: LoggingContext, message_data: str) -> Optional[Dict]:
    event = json.loads(message_data)
    payload = {}

    timestamp = event['timestamp']
    if 'timestamp' in event:
        timestamp_datetime = parse(timestamp)
        event_age_in_seconds = (datetime.now(timezone.utc) - timestamp_datetime).total_seconds()
        if event_age_in_seconds > _EVENT_AGE_LIMIT_SECONDS:
            context.log(f"Skipping message due to too old timestamp: {timestamp}")
            return None

    payload['timestamp'] = timestamp
    payload['cloud.provider'] = 'gcp'
    payload['content'] = message_data[:_CONTENT_LENGTH_LIMIT]
    payload['severity'] = event.get("severity", None)

    return payload


def _adjust_log_content(content: str, max_len: Optional[int] = 8192, trailing_chars: Optional[str] = "...more"):
    """
    Truncate log content to the actual Dynatrace log content length limit
    """
    if max_len is not None and len(content) >= max_len:
        return content[0:max_len - len(trailing_chars)] + trailing_chars if trailing_chars else content[0:max_len]
    return content
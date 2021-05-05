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
from datetime import datetime, timezone
from queue import Queue
from typing import Optional, Dict

from dateutil.parser import *
from google.pubsub_v1 import ReceivedMessage, PubsubMessage

from lib.context import LogsProcessingContext, LogsContext
from lib.logs.log_forwarder_variables import EVENT_AGE_LIMIT_SECONDS, CONTENT_LENGTH_LIMIT, ATTRIBUTE_VALUE_LENGTH_LIMIT
from lib.logs.log_self_monitoring import LogSelfMonitoring, put_sfm_into_queue
from lib.logs.metadata_engine import MetadataEngine, ATTRIBUTE_CONTENT, ATTRIBUTE_TIMESTAMP

_metadata_engine = MetadataEngine()


class LogProcessingJob:
    payload: str
    self_monitoring: LogSelfMonitoring

    def __init__(self, payload: str, self_monitoring: LogSelfMonitoring):
        self.payload = payload
        self.self_monitoring: LogSelfMonitoring = self_monitoring
        self.bytes_size = len(payload.encode("UTF-8"))


def _process_message(sfm_queue: Queue, message: ReceivedMessage):
    context = LogsProcessingContext(
        scheduled_execution_id=str(message.ack_id.__hash__())[-8:],
        sfm_queue=sfm_queue
    )
    try:
        return _do_process_message(context, message.message)
    except Exception as exception:
        if isinstance(exception, queue.Full):
            context.error(f"Failed to process message due full job queue, rejecting the message")
        else:
            context.exception(f"Failed to process message due to {type(exception).__name__}")
            context.self_monitoring.parsing_errors += 1
            context.self_monitoring.calculate_processing_time()
            put_sfm_into_queue(context)
        return None


def _do_process_message(context: LogsContext, message: PubsubMessage):
    context.self_monitoring.processing_time_start = time.perf_counter()
    data = message.data.decode("UTF-8")
    # context.log(f"Data: {data}")

    payload = _create_dt_log_payload(context, data)
    # context.log(f"Payload: {payload}")
    context.self_monitoring.calculate_processing_time()

    if not payload:
        put_sfm_into_queue(context)
        return None
    else:
        job = LogProcessingJob(json.dumps(payload), context.self_monitoring)
        return job


def _create_dt_log_payload(context: LogsContext, message_data: str) -> Optional[Dict]:
    record = json.loads(message_data)
    parsed_record = {}

    _metadata_engine.apply(context, record, parsed_record)

    parsed_timestamp = parsed_record.get(ATTRIBUTE_TIMESTAMP, None)
    if _is_log_too_old(parsed_timestamp):
        context.log(f"Skipping message due to too old timestamp: {parsed_timestamp}")
        context.self_monitoring.too_old_records += 1
        return None

    for attribute_key, attribute_value in parsed_record.items():
        if attribute_key not in ["content", "severity", "timestamp"] and attribute_value:
            string_attribute_value = attribute_value
            if not isinstance(attribute_value, str):
                string_attribute_value = str(attribute_value)
            parsed_record[attribute_key] = string_attribute_value[: ATTRIBUTE_VALUE_LENGTH_LIMIT]

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
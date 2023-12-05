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
import ciso8601

from dateutil.parser import *
from google.pubsub_v1 import ReceivedMessage, PubsubMessage

from lib.context import LogsProcessingContext
from lib.logs.log_forwarder_variables import EVENT_AGE_LIMIT_SECONDS, CONTENT_LENGTH_LIMIT, \
    ATTRIBUTE_VALUE_LENGTH_LIMIT, DYNATRACE_LOG_INGEST_CONTENT_MARK_TRIMMED, CLOUD_LOG_FORWARDER, \
    CLOUD_LOG_FORWARDER_POD
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


def _prepare_context_and_process_message(sfm_queue: Queue, message: ReceivedMessage) -> Optional[LogProcessingJob]:
    context = None
    try:
        context = LogsProcessingContext(
            scheduled_execution_id=str(message.ack_id.__hash__())[-8:],
            message_publish_time=message.message.publish_time,
            sfm_queue=sfm_queue
        )
        return _process_message(context, message.message)
    except Exception as exception:
        if not context:
            context = LogsProcessingContext(None, None, sfm_queue)
        if isinstance(exception, queue.Full):
            context.error(f"Failed to process message due full job queue, rejecting the message")
        else:
            if isinstance(exception, UnicodeDecodeError):
                context.error(f"Failed to process message due to message data not being valid UTF-8. Binary data is not supported")
            else:
                context.t_exception(f"Failed to process message due to {type(exception).__name__}")
            context.self_monitoring.parsing_errors += 1
            context.self_monitoring.calculate_processing_time()
            put_sfm_into_queue(context)
        return None


def _process_message(context: LogsProcessingContext, message: PubsubMessage) -> Optional[LogProcessingJob]:
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


def _create_dt_log_payload(context: LogsProcessingContext, message_data: str) -> Optional[Dict]:
    if not message_data:
        context.log("Skipping empty message")
        return None

    parsed_record = _create_parsed_record(context, message_data)

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
        if len(parsed_record[ATTRIBUTE_CONTENT]) > CONTENT_LENGTH_LIMIT:
            trimmed_len = CONTENT_LENGTH_LIMIT - len(DYNATRACE_LOG_INGEST_CONTENT_MARK_TRIMMED)
            parsed_record[ATTRIBUTE_CONTENT] = parsed_record[ATTRIBUTE_CONTENT][
                                               :trimmed_len] + DYNATRACE_LOG_INGEST_CONTENT_MARK_TRIMMED
            context.self_monitoring.records_with_too_long_content += 1

    return parsed_record


def _create_parsed_record(context: LogsProcessingContext, message_data: str):
    try:
        record = json.loads(message_data)
    except ValueError:
        record = {
            ATTRIBUTE_CONTENT: message_data
        }
    parsed_record = {}
    _metadata_engine.apply(context, record, parsed_record)

    if ATTRIBUTE_TIMESTAMP not in parsed_record.keys() or _is_invalid_datetime(parsed_record[ATTRIBUTE_TIMESTAMP]):
        context.self_monitoring.publish_time_fallback_records += 1
        parsed_record[ATTRIBUTE_TIMESTAMP] = context.message_publish_time.isoformat()

    _set_cloud_log_forwarder(parsed_record)

    return parsed_record


def _set_cloud_log_forwarder(parsed_record):
    cloud_log_forwarder = (
                CLOUD_LOG_FORWARDER + "/pods/" + CLOUD_LOG_FORWARDER_POD) if CLOUD_LOG_FORWARDER and CLOUD_LOG_FORWARDER_POD else CLOUD_LOG_FORWARDER
    if cloud_log_forwarder:
        parsed_record["cloud.log_forwarder"] = cloud_log_forwarder


def _is_invalid_datetime(datetime_str: str) -> bool:
    try:
        ciso8601.parse_datetime(datetime_str)
        return False
    except ValueError:
        return True


def _is_log_too_old(timestamp: Optional[str]):
    timestamp_datetime = ciso8601.parse_datetime(timestamp)
    event_age_in_seconds = int((datetime.now(timezone.utc) - timestamp_datetime).total_seconds())
    return event_age_in_seconds > EVENT_AGE_LIMIT_SECONDS

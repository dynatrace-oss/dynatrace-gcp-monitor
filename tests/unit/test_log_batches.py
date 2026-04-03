#   Copyright 2021 Dynatrace LLC
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
import copy
import json
import random
from typing import NewType, Any, List
from unittest.mock import patch

from lib.logs.logs_processor import prepare_batches, LogProcessingJob
from lib.logs.metadata_engine import ATTRIBUTE_CLOUD_PROVIDER, ATTRIBUTE_CONTENT, ATTRIBUTE_SEVERITY
from lib.sfm.for_logs.log_sfm_metrics import LogSelfMonitoring

log_message = "WALTHAM, Mass.--(BUSINESS WIRE)-- Software intelligence company Dynatrace (NYSE: DT) announced today its entry into the cloud application security market with the addition of a new module to its industry-leading Software Intelligence Platform. The Dynatrace® Application Security Module provides continuous runtime application self-protection (RASP) capabilities for applications in production as well as preproduction and is optimized for Kubernetes architectures and DevSecOps approaches. This module inherits the automation, AI, scalability, and enterprise-grade robustness of the Dynatrace® Software Intelligence Platform and extends it to modern cloud RASP use cases. Dynatrace customers can launch this module with the flip of a switch, empowering the world’s leading organizations currently using the Dynatrace platform to immediately increase security coverage and precision.;"

MonkeyPatchFixture = NewType("MonkeyPatchFixture", Any)


def create_log_entry_msg(min_len: int = 1, max_len: int = None):
    max_len = len(log_message) if max_len is None else max_len
    random_len = random.randint(min_len, max_len)
    random_len_str = log_message[:random_len]

    as_dict = {
        ATTRIBUTE_CONTENT: random_len_str,
        ATTRIBUTE_CLOUD_PROVIDER: 'gcp',
        ATTRIBUTE_SEVERITY: 'INFO'
    }

    return LogProcessingJob(json.dumps(as_dict), LogSelfMonitoring(), '')


def calculate_log_size(jobs: List[LogProcessingJob]):
    return sum(len(log_message.payload.encode("UTF-8")) for log_message in
               jobs) + len(jobs) + 2 - 1


def test_batch_divide_exceeding_request_size():
    how_many_logs = 100
    logs = [create_log_entry_msg() for x in range(how_many_logs)]
    limit = calculate_log_size(logs) - 1  # one byte bellow size

    first_batch_size = calculate_log_size(logs[:-1])
    second_batch_size = calculate_log_size(logs[-1:])
    with patch('lib.logs.logs_processor.REQUEST_BODY_MAX_SIZE', limit):
        batches = prepare_batches(logs)

        assert len(batches) == 2
        assert batches[0].size_batch_bytes == first_batch_size
        assert batches[1].size_batch_bytes == second_batch_size
        assert len(batches[1].serialized_batch.encode("UTF-8")) == second_batch_size
        assert len(batches[0].serialized_batch.encode("UTF-8")) == first_batch_size
        assert len(batches[1].serialized_batch.encode("UTF-8")) == second_batch_size


def test_batch_divide_exceeding_request_max_events():
    how_many_logs = 100
    request_max_events = 10
    logs = [create_log_entry_msg(max_len=10) for x in range(how_many_logs)]

    limit = calculate_log_size(logs)
    with patch('lib.logs.logs_processor.REQUEST_BODY_MAX_SIZE', limit), patch(
            'lib.logs.logs_processor.REQUEST_MAX_EVENTS', 10):
        batches = prepare_batches(logs)

        assert len(batches) == how_many_logs / request_max_events


def test_batch_self_monitoring():
    how_many_logs = 100
    logs = [create_log_entry_msg() for x in range(how_many_logs)]

    log_sfm = LogSelfMonitoring()
    log_sfm.too_old_records = 1
    log_sfm.publish_time_fallback_records = 1
    log_sfm.parsing_errors = 1
    log_sfm.records_with_too_long_content = 1
    log_sfm.all_requests = 1
    log_sfm.dt_connectivity = [200]
    log_sfm.processing_time = 1
    log_sfm.pulling_time = 1
    log_sfm.sending_time = 1
    log_sfm.log_ingest_payload_size = 1
    log_sfm.sent_logs_entries = 1

    for log in logs:
        log.self_monitoring = copy.copy(log_sfm)

    limit = sum(len(log_message.payload.encode("UTF-8")) for log_message in
                logs) + how_many_logs + 2 - 1 + 1

    with patch('lib.logs.logs_processor.REQUEST_BODY_MAX_SIZE', limit):
        batches = prepare_batches(logs)

        assert len(batches) == 1

        assert batches[0].self_monitoring.too_old_records == 100
        assert batches[0].self_monitoring.publish_time_fallback_records == 100
        assert batches[0].self_monitoring.parsing_errors == 100
        assert batches[0].self_monitoring.records_with_too_long_content == 100
        assert batches[0].self_monitoring.all_requests == 100
        assert len(batches[0].self_monitoring.dt_connectivity) == 100
        assert batches[0].self_monitoring.processing_time == 100
        assert batches[0].self_monitoring.pulling_time == 100
        assert batches[0].self_monitoring.sending_time == 100
        assert batches[0].self_monitoring.log_ingest_payload_size == 100
        assert batches[0].self_monitoring.sent_logs_entries == 100


def test_no_logs():
    logs = []

    batches = prepare_batches(logs)

    assert batches == []
    assert len(batches) == 0

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

import json
import random
from typing import NewType, Any

from lib.logs import worker_state
from lib.logs.log_forwarder_variables import SENDING_WORKER_EXECUTION_PERIOD_SECONDS
from lib.sfm.for_logs.log_sfm_metrics import LogSelfMonitoring
from lib.logs.logs_processor import LogProcessingJob
from lib.logs.metadata_engine import ATTRIBUTE_CLOUD_PROVIDER, ATTRIBUTE_CONTENT, ATTRIBUTE_SEVERITY
from lib.logs.worker_state import WorkerState

log_message = "WALTHAM, Mass.--(BUSINESS WIRE)-- Software intelligence company Dynatrace (NYSE: DT) announced today its entry into the cloud application security market with the addition of a new module to its industry-leading Software Intelligence Platform. The Dynatrace® Application Security Module provides continuous runtime application self-protection (RASP) capabilities for applications in production as well as preproduction and is optimized for Kubernetes architectures and DevSecOps approaches. This module inherits the automation, AI, scalability, and enterprise-grade robustness of the Dynatrace® Software Intelligence Platform and extends it to modern cloud RASP use cases. Dynatrace customers can launch this module with the flip of a switch, empowering the world’s leading organizations currently using the Dynatrace platform to immediately increase security coverage and precision.;"

MonkeyPatchFixture = NewType("MonkeyPatchFixture", Any)


def create_log_entry_with_random_len_msg():
    random_len = random.randint(1, len(log_message))
    random_len_str = log_message[0: random_len]

    as_dict = {
        ATTRIBUTE_CONTENT: random_len_str,
        ATTRIBUTE_CLOUD_PROVIDER: 'gcp',
        ATTRIBUTE_SEVERITY: 'INFO'
    }

    return LogProcessingJob(json.dumps(as_dict).encode("UTF-8"), LogSelfMonitoring())


def test_should_flush_on_batch_exceeding_request_size(monkeypatch: MonkeyPatchFixture):
    how_many_logs = 100
    logs = [create_log_entry_with_random_len_msg() for x in range(how_many_logs)]
    limit = sum(len(log_message.payload) for log_message in logs) + how_many_logs + 2 + 1

    monkeypatch.setattr(worker_state, 'REQUEST_BODY_MAX_SIZE', limit)

    test_state = WorkerState("TEST")
    for log in logs:
        assert not test_state.should_flush(log)
        test_state.add_job(log, "")

    assert test_state.should_flush(create_log_entry_with_random_len_msg())
    assert len(test_state.finished_batch) == test_state.finished_batch_bytes_size


def test_should_flush_on_too_many_events(monkeypatch: MonkeyPatchFixture):
    max_events = 5
    monkeypatch.setattr(worker_state, 'REQUEST_MAX_EVENTS', max_events)

    logs = [create_log_entry_with_random_len_msg() for x in range(max_events)]
    test_state = WorkerState("TEST")

    for log in logs:
        assert not test_state.should_flush(log)
        test_state.add_job(log, "")

    assert test_state.should_flush(create_log_entry_with_random_len_msg())
    assert len(test_state.jobs) == max_events


def test_should_flush_on_time_passed(monkeypatch: MonkeyPatchFixture):
    test_state = WorkerState("TEST")
    test_state.last_flush_time -= (2 * SENDING_WORKER_EXECUTION_PERIOD_SECONDS)

    assert test_state.should_flush(create_log_entry_with_random_len_msg())

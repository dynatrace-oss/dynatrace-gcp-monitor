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
from datetime import datetime, timezone
from typing import NewType, Any

from lib.logs import logs_processor
from lib.logs.logs_processor import _create_dt_log_payload
from lib.logs.metadata_engine import ATTRIBUTE_CONTENT
from unit.extraction_rules.common import TEST_LOGS_PROCESSING_CONTEXT

MonkeyPatchFixture = NewType("MonkeyPatchFixture", Any)
log_message = "WALTHAM, Mass.--(BUSINESS WIRE)-- Software intelligence company Dynatrace (NYSE: DT) announced today its entry into the cloud application security market with the addition of a new module to its industry-leading Software Intelligence Platform. The Dynatrace® Application Security Module provides continuous runtime application self-protection (RASP) capabilities for applications in production as well as preproduction and is optimized for Kubernetes architectures and DevSecOps approaches. This module inherits the automation, AI, scalability, and enterprise-grade robustness of the Dynatrace® Software Intelligence Platform and extends it to modern cloud RASP use cases. Dynatrace customers can launch this module with the flip of a switch, empowering the world’s leading organizations currently using the Dynatrace platform to immediately increase security coverage and precision.;"
timestamp = datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"


def create_log_entry(message=None):
    return {
        ATTRIBUTE_CONTENT: message,
        "timestamp": timestamp
    }


def test_content_trimmed(monkeypatch: MonkeyPatchFixture):
    # given
    monkeypatch.setattr(logs_processor, 'CONTENT_LENGTH_LIMIT', 100)
    log_entry = create_log_entry(log_message)

    # when
    actual_output = _create_dt_log_payload(TEST_LOGS_PROCESSING_CONTEXT, json.dumps(log_entry))

    # then
    expected_content = "WALTHAM, Mass.--(BUSINESS WIRE)-- Software intelligence company Dynatrace (NYSE: DT) anno[TRUNCATED]"
    assert len(actual_output["content"]) == 100
    assert actual_output["content"] == expected_content


def test_content_with_exact_len_not_trimmed(monkeypatch: MonkeyPatchFixture):
    message = "WALTHAM, Mass.--(BUSINESS WIRE)-- Software intelligence company Dynatrace (NYSE: DT)"

    # given
    log_entry = create_log_entry(message)
    monkeypatch.setattr(logs_processor, 'CONTENT_LENGTH_LIMIT', len(message))

    # when
    actual_output = _create_dt_log_payload(TEST_LOGS_PROCESSING_CONTEXT, json.dumps(log_entry))

    # then
    assert actual_output["content"] == message

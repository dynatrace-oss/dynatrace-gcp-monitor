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
from datetime import datetime
from typing import NewType, Any

from lib.logs import logs_processor
from lib.logs.logs_processor import _create_dt_log_payload
from lib.logs.metadata_engine import ATTRIBUTE_CONTENT
from unit.extraction_rules.common import TEST_LOGS_PROCESSING_CONTEXT

MonkeyPatchFixture = NewType("MonkeyPatchFixture", Any)
timestamp = datetime.utcnow().isoformat() + "Z"
log_message = "WALTHAM, Mass.--(BUSINESS WIRE)-- Software intelligence company Dynatrace (NYSE: DT)"

test_record = {
    ATTRIBUTE_CONTENT: log_message,
    "timestamp": timestamp
}


def test_log_forwarder_attr(monkeypatch: MonkeyPatchFixture):
    # given
    monkeypatch.setattr(logs_processor, "CLOUD_LOG_FORWARDER",
                        "projects/myProject/clusters/myCluster/namespaces/myNamespace")
    monkeypatch.setattr(logs_processor, "CLOUD_LOG_FORWARDER_POD", "myPod")

    # when
    actual_output = _create_dt_log_payload(TEST_LOGS_PROCESSING_CONTEXT, json.dumps(test_record))

    # then
    expected_output = "projects/myProject/clusters/myCluster/namespaces/myNamespace/pods/myPod"
    assert actual_output['cloud.log_forwarder'] == expected_output


def test_log_forwarder_attr_with_empty_pod(monkeypatch: MonkeyPatchFixture):
    # given
    monkeypatch.setattr(logs_processor, 'CLOUD_LOG_FORWARDER',
                        "projects/myProject/clusters/myCluster/namespaces/myNamespace")
    monkeypatch.setattr(logs_processor, 'CLOUD_LOG_FORWARDER_POD', "")

    # when
    actual_output = _create_dt_log_payload(TEST_LOGS_PROCESSING_CONTEXT, json.dumps(test_record))

    # then
    expected_output = "projects/myProject/clusters/myCluster/namespaces/myNamespace"
    assert actual_output['cloud.log_forwarder'] == expected_output


def test_log_forwarder_attr_with_empty_forwarder(monkeypatch: MonkeyPatchFixture):
    # given
    monkeypatch.setattr(logs_processor, 'CLOUD_LOG_FORWARDER', "")
    monkeypatch.setattr(logs_processor, 'CLOUD_LOG_FORWARDER_POD', "myPod")

    # when
    actual_output = _create_dt_log_payload(TEST_LOGS_PROCESSING_CONTEXT, json.dumps(test_record))

    # then
    if not actual_output.get('cloud.log_forwarder'):
        assert True


def test_log_forwarder_attr_with_empty_forwarder_and_pod(monkeypatch: MonkeyPatchFixture):
    # given
    monkeypatch.setattr(logs_processor, 'CLOUD_LOG_FORWARDER', "")
    monkeypatch.setattr(logs_processor, 'CLOUD_LOG_FORWARDER_POD', "")

    # when
    actual_output = _create_dt_log_payload(TEST_LOGS_PROCESSING_CONTEXT, json.dumps(test_record))

    # then
    if not actual_output.get('cloud.log_forwarder'):
        assert True

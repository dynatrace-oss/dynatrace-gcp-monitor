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
from datetime import datetime

from lib.context import LoggingContext
from lib.logs.logs_processor import _create_dt_log_payload
from lib.logs.metadata_engine import ATTRIBUTE_GCP_PROJECT_ID, ATTRIBUTE_GCP_RESOURCE_TYPE, ATTRIBUTE_SEVERITY, \
    ATTRIBUTE_CLOUD_PROVIDER, ATTRIBUTE_CLOUD_REGION, ATTRIBUTE_GCP_REGION, ATTRIBUTE_CONTENT, ATTRIBUTE_TIMESTAMP, \
    ATTRIBUTE_DT_LOGPATH

timestamp = datetime.utcnow().isoformat() + "Z"

record = {
    "insertId": "6075332400049b1f937691ca",
    "labels": {
        "instanceId": "00bf4bf02d68c4b9968ace4f97f127bad96e1f32a0cb3d624ed74842c248e63867a0376c37fea457fa18dbb0c5a6315fe54e96754df0b8998e2cdfebac"
    },
    "logName": "projects/dynatrace-gcp-extension/logs/run.googleapis.com%2Fstdout",
    "receiveTimestamp": "2021-04-13T05:59:00.305070638Z",
    "resource": {
        "labels": {
            "configuration_name": "datastore-test",
            "location": "us-central1",
            "project_id": "dynatrace-gcp-extension",
            "revision_name": "datastore-test-00002-hot",
            "service_name": "datastore-test"
        },
        "type": "cloud_run_revision"
    },
    "textPayload": "Saved 6333542b-b5fd-4996-8138-8b86e8156e29: ",
    "timestamp": timestamp
}

record_string = json.dumps(record)

expected_output = {
    ATTRIBUTE_CLOUD_PROVIDER: 'gcp',
    ATTRIBUTE_CLOUD_REGION: 'us-central1',
    ATTRIBUTE_GCP_REGION: 'us-central1',
    ATTRIBUTE_GCP_PROJECT_ID: 'dynatrace-gcp-extension',
    ATTRIBUTE_GCP_RESOURCE_TYPE: 'cloud_run_revision',
    ATTRIBUTE_TIMESTAMP: timestamp,
    ATTRIBUTE_CONTENT: record_string,
    ATTRIBUTE_DT_LOGPATH: 'projects/dynatrace-gcp-extension/logs/run.googleapis.com%2Fstdout'
}


def test_extraction():
    actual_output = _create_dt_log_payload(LoggingContext("TEST"), record_string)
    assert actual_output == expected_output
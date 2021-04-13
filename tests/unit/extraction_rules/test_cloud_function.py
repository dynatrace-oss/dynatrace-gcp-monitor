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

from lib.context import LoggingContext
from lib.logs.logs_processor import _create_dt_log_payload
from lib.logs.metadata_engine import ATTRIBUTE_GCP_PROJECT_ID, ATTRIBUTE_GCP_RESOURCE_TYPE, ATTRIBUTE_SEVERITY, \
    ATTRIBUTE_CLOUD_PROVIDER, ATTRIBUTE_CLOUD_REGION, ATTRIBUTE_GCP_REGION, ATTRIBUTE_GCP_INSTANCE_NAME, \
    ATTRIBUTE_CONTENT, ATTRIBUTE_TIMESTAMP, ATTRIBUTE_DT_LOGPATH

record = {
    "insertId": "000000-34c62aef-5df9-4f63-b692-a92f64febd2c",
    "labels": {
        "execution_id": "j22o0ucdhpop"
    },
    "logName": "projects/dynatrace-gcp-extension/logs/cloudfunctions.googleapis.com%2Fcloud-functions",
    "receiveTimestamp": "2021-04-13T10:27:11.946869081Z",
    "resource": {
        "labels": {
            "function_name": "dynatrace-gcp-function",
            "project_id": "dynatrace-gcp-extension",
            "region": "us-central1"
        },
        "type": "cloud_function"
    },
    "severity": "DEBUG",
    "textPayload": "Function execution started",
    "timestamp": "2021-04-13T10:27:01.747066421Z",
    "trace": "projects/dynatrace-gcp-extension/traces/b24dd86d3aa6a386ff2aa6a7f16660a0"
}


record_string = json.dumps(record)

expected_output = {
    ATTRIBUTE_SEVERITY: 'DEBUG',
    ATTRIBUTE_CLOUD_PROVIDER: 'gcp',
    ATTRIBUTE_CLOUD_REGION: 'us-central1',
    ATTRIBUTE_GCP_REGION: 'us-central1',
    ATTRIBUTE_GCP_PROJECT_ID: 'dynatrace-gcp-extension',
    ATTRIBUTE_GCP_RESOURCE_TYPE: 'cloud_function',
    ATTRIBUTE_GCP_INSTANCE_NAME: 'dynatrace-gcp-function',
    ATTRIBUTE_TIMESTAMP: '2021-04-13T10:27:01.747066421Z',
    ATTRIBUTE_CONTENT: "Function execution started",
    ATTRIBUTE_DT_LOGPATH: 'projects/dynatrace-gcp-extension/logs/cloudfunctions.googleapis.com%2Fcloud-functions',
    'faas.id': 'j22o0ucdhpop'
}


def test_extraction():
    actual_output = _create_dt_log_payload(LoggingContext("TEST"), record_string)
    assert actual_output == expected_output
#     Copyright 2026 Dynatrace LLC
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

from lib.logs.logs_processor import _create_dt_log_payload
from lib.logs.metadata_engine import ATTRIBUTE_CLOUD_PROVIDER, ATTRIBUTE_CLOUD_REGION, ATTRIBUTE_CONTENT, \
    ATTRIBUTE_DT_LOGPATH, ATTRIBUTE_DT_SECURITY_CONTEXT, ATTRIBUTE_GCP_INSTANCE_NAME, ATTRIBUTE_GCP_PROJECT_ID, \
    ATTRIBUTE_GCP_REGION, ATTRIBUTE_GCP_RESOURCE_TYPE, ATTRIBUTE_SEVERITY, ATTRIBUTE_TIMESTAMP
from unit.extraction_rules.common import TEST_LOGS_PROCESSING_CONTEXT

timestamp = datetime.utcnow().isoformat() + "Z"

record = {
    "insertId": "6a4daf64000c9ab21ad78339",
    "logName": "projects/dynatrace-gcp-extension/logs/run.googleapis.com%2Fstdout",
    "receiveTimestamp": "2026-07-08T07:31:09.210000000Z",
    "resource": {
        "labels": {
            "job_name": "grun-cae-cdh-dbt-orch-ew4-jb-01",
            "location": "europe-west4",
            "project_id": "dynatrace-gcp-extension"
        },
        "type": "cloud_run_job"
    },
    "severity": "INFO",
    "textPayload": "Cloud Run job output",
    "timestamp": timestamp
}

expected_output = {
    ATTRIBUTE_SEVERITY: "INFO",
    ATTRIBUTE_CLOUD_PROVIDER: "gcp",
    ATTRIBUTE_CLOUD_REGION: "europe-west4",
    ATTRIBUTE_GCP_REGION: "europe-west4",
    ATTRIBUTE_GCP_PROJECT_ID: "dynatrace-gcp-extension",
    ATTRIBUTE_GCP_RESOURCE_TYPE: "cloud_run_job",
    ATTRIBUTE_GCP_INSTANCE_NAME: "grun-cae-cdh-dbt-orch-ew4-jb-01",
    ATTRIBUTE_TIMESTAMP: timestamp,
    ATTRIBUTE_CONTENT: json.dumps(record),
    ATTRIBUTE_DT_LOGPATH: "projects/dynatrace-gcp-extension/logs/run.googleapis.com%2Fstdout",
    ATTRIBUTE_DT_SECURITY_CONTEXT: ""
}


def test_extraction_cloud_run_job():
    actual_output = _create_dt_log_payload(TEST_LOGS_PROCESSING_CONTEXT, json.dumps(record))
    assert actual_output == expected_output

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

from lib.logs.logs_processor import _create_dt_log_payload
from lib.logs.metadata_engine import ATTRIBUTE_GCP_PROJECT_ID, ATTRIBUTE_GCP_RESOURCE_TYPE, ATTRIBUTE_SEVERITY, \
    ATTRIBUTE_CLOUD_PROVIDER, ATTRIBUTE_CLOUD_REGION, ATTRIBUTE_GCP_REGION, ATTRIBUTE_GCP_INSTANCE_NAME, \
    ATTRIBUTE_CONTENT, ATTRIBUTE_TIMESTAMP, ATTRIBUTE_DT_LOGPATH, ATTRIBUTE_GCP_INSTANCE_ID, ATTRIBUTE_DT_SECURITY_CONTEXT
from unit.extraction_rules.common import TEST_LOGS_PROCESSING_CONTEXT

timestamp = datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"

log_record = {
  "textPayload": "ON DUPLICATE KEY UPDATE master_time=UTC_TIMESTAMP(6);",
  "insertId": "2#207603163766#5855464153465817469#slow#1627301304221698000#0000000000027311-0-0@a1",
  "resource": {
    "type": "cloudsql_database",
    "labels": {
      "project_id": "dynatrace-gcp-extension",
      "region": "europe-north1",
      "database_id": "dynatrace-gcp-extension:test-001-mysql"
    }
  },
  "timestamp": timestamp,
  "logName": "projects/dynatrace-gcp-extension/logs/cloudsql.googleapis.com%2Fmysql-slow.log",
  "receiveTimestamp": "2021-07-26T12:08:26.686970384Z"
}
expected_output = {
    ATTRIBUTE_CLOUD_PROVIDER: 'gcp',
    ATTRIBUTE_CLOUD_REGION: 'europe-north1',
    ATTRIBUTE_GCP_REGION: 'europe-north1',
    ATTRIBUTE_GCP_PROJECT_ID: 'dynatrace-gcp-extension',
    ATTRIBUTE_GCP_RESOURCE_TYPE: 'cloudsql_database',
    ATTRIBUTE_GCP_INSTANCE_ID: 'dynatrace-gcp-extension:test-001-mysql',
    ATTRIBUTE_TIMESTAMP: timestamp,
    ATTRIBUTE_CONTENT: json.dumps(log_record),
    ATTRIBUTE_DT_LOGPATH: 'projects/dynatrace-gcp-extension/logs/cloudsql.googleapis.com%2Fmysql-slow.log',
    ATTRIBUTE_SEVERITY: "INFO",
    ATTRIBUTE_DT_SECURITY_CONTEXT : ''
}


def test_extraction_debug_text():
    actual_output = _create_dt_log_payload(TEST_LOGS_PROCESSING_CONTEXT, json.dumps(log_record))
    assert actual_output == expected_output

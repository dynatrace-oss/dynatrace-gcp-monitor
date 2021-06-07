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
from queue import Queue
from typing import NewType, Any

from lib.context import LogsContext
from lib.logs import logs_processor
from lib.logs.metadata_engine import ATTRIBUTE_GCP_PROJECT_ID, ATTRIBUTE_GCP_RESOURCE_TYPE, ATTRIBUTE_SEVERITY, \
    ATTRIBUTE_CLOUD_PROVIDER, ATTRIBUTE_CLOUD_REGION, ATTRIBUTE_GCP_REGION, ATTRIBUTE_CONTENT, ATTRIBUTE_TIMESTAMP, \
    ATTRIBUTE_DT_LOGPATH, ATTRIBUTE_AUDIT_IDENTITY, ATTRIBUTE_AUDIT_ACTION, ATTRIBUTE_AUDIT_RESULT

MonkeyPatchFixture = NewType("MonkeyPatchFixture", Any)

timestamp = datetime.utcnow().isoformat() + "Z"

# From https://cloud.google.com/vpc-service-controls/docs/troubleshooting
record = {
    "insertId": "222lvajc6f7",
    "logName": "projects/dynatrace-gcp-extension/logs/cloudaudit.googleapis.com%2Fpolicy",
    "protoPayload": {
        "@type": "type.googleapis.com/google.cloud.audit.AuditLog",
        "authenticationInfo": {
            "principalEmail": "someone@google.com"
        },
        "metadata": {
            "@type": "type.googleapis.com/google.cloud.audit.VpcServiceControlAuditMetadata",
            "resourceNames": [
                "projects/_"
            ],
            "violationReason": "NO_MATCHING_ACCESS_LEVEL"
        },
        "methodName": "google.storage.NoBillingOk",
        "requestMetadata": {
            "callerIp": "x.x.x.x",
            "destinationAttributes": {},
            "requestAttributes": {}
        },
        "resourceName": "projects/690885588241",
        "serviceName": "storage.googleapis.com",
        "status": {
            "code": 7,
            "details": [
                {
                    "@type": "type.googleapis.com/google.rpc.PreconditionFailure",
                    "violations": [
                        {
                            "type": "VPC_SERVICE_CONTROLS"
                        }
                    ]
                }
            ],
            "message": "Request is prohibited by organization's policy"
        }
    },
    "receiveTimestamp": "2018-11-27T21:40:43.823209571Z",
    "resource": {
        "labels": {
            "method": "google.storage.NoBillingOk",
            "project_id": "dynatrace-gcp-extension",
            "service": "storage.googleapis.com"
        },
        "type": "audited_resource"
    },
    "severity": "ERROR",
    "timestamp": timestamp
}


expected_output_list = [
    {
        ATTRIBUTE_CLOUD_PROVIDER: 'gcp',
        ATTRIBUTE_GCP_PROJECT_ID: 'dynatrace-gcp-extension',
        ATTRIBUTE_GCP_RESOURCE_TYPE: 'audited_resource',
        ATTRIBUTE_TIMESTAMP: timestamp,
        ATTRIBUTE_CONTENT: json.dumps(record),
        ATTRIBUTE_DT_LOGPATH: 'projects/dynatrace-gcp-extension/logs/cloudaudit.googleapis.com%2Fpolicy',
        ATTRIBUTE_AUDIT_IDENTITY: 'someone@google.com',
        ATTRIBUTE_AUDIT_ACTION: 'google.storage.NoBillingOk',
        ATTRIBUTE_AUDIT_RESULT: 'Failure.PermissionDenied',
        ATTRIBUTE_SEVERITY: 'ERROR',
    }
]

logs_context = LogsContext(
    project_id_owner="",
    dynatrace_api_key="",
    dynatrace_url="",
    scheduled_execution_id="",
    sfm_queue=Queue()
)


def test_extraction():
    for entry in expected_output_list:
        actual_output = logs_processor._create_dt_log_payload(logs_context, entry[ATTRIBUTE_CONTENT])
        assert actual_output == entry

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
from typing import NewType, Any

from lib.logs import logs_processor
from lib.logs.metadata_engine import ATTRIBUTE_GCP_PROJECT_ID, ATTRIBUTE_GCP_RESOURCE_TYPE, ATTRIBUTE_SEVERITY, \
    ATTRIBUTE_CLOUD_PROVIDER, ATTRIBUTE_CLOUD_REGION, ATTRIBUTE_GCP_REGION, ATTRIBUTE_CONTENT, ATTRIBUTE_TIMESTAMP, \
    ATTRIBUTE_DT_LOGPATH, ATTRIBUTE_AUDIT_IDENTITY, ATTRIBUTE_AUDIT_ACTION, ATTRIBUTE_AUDIT_RESULT, \
    ATTRIBUTE_GCP_INSTANCE_NAME
from unit.extraction_rules.common import TEST_LOGS_PROCESSING_CONTEXT

MonkeyPatchFixture = NewType("MonkeyPatchFixture", Any)

timestamp = datetime.utcnow().isoformat() + "Z"

record = {
    "protoPayload": {
        "@type": "type.googleapis.com/google.cloud.audit.AuditLog",
        "authenticationInfo": {
            "principalEmail": "service-125992521190@container-engine-robot.iam.gserviceaccount.com"
        },
        "requestMetadata": {
            "callerIp": "x.x.x.x",
            "callerSuppliedUserAgent": "google-api-go-client/0.5,gzip(gfe)",
            "requestAttributes": {
                "time": "2021-06-01T14:01:29.378665Z",
                "auth": {}
            },
            "destinationAttributes": {}
        },
        "serviceName": "compute.googleapis.com",
        "methodName": "v1.compute.instanceGroupManagers.list",
        "authorizationInfo": [
            {
                "permission": "compute.instanceGroupManagers.list",
                "granted": True,
                "resourceAttributes": {
                    "service": "resourcemanager",
                    "name": "projects/dynatrace-gcp-extension",
                    "type": "resourcemanager.projects"
                }
            }
        ],
        "resourceName": "projects/dynatrace-gcp-extension/zones/us-central1-b/instanceGroupManagers",
        "numResponseItems": "3",
        "request": {
            "@type": "type.googleapis.com/compute.instanceGroupManagers.list"
        },
        "resourceLocation": {
            "currentLocations": [
                "us-central1-b"
            ]
        }
    },
    "insertId": "uj1fsde27tew",
    "resource": {
        "type": "gce_instance_group_manager",
        "labels": {
            "instance_group_manager_id": "",
            "instance_group_manager_name": "",
            "project_id": "dynatrace-gcp-extension",
            "location": "us-central1-b"
        }
    },
    "timestamp": timestamp,
    "severity": "INFO",
    "logName": "projects/dynatrace-gcp-extension/logs/cloudaudit.googleapis.com%2Fdata_access",
    "receiveTimestamp": "2021-06-01T14:01:29.900534777Z"
}

record2 = {
    "protoPayload": {
        "@type": "type.googleapis.com/google.cloud.audit.AuditLog",
        "status": {},
        "authenticationInfo": {
            "principalEmail": "dynatrace-gcp-service@dynatrace-gcp-extension.iam.gserviceaccount.com",
            "serviceAccountDelegationInfo": [
                {
                    "firstPartyPrincipal": {
                        "principalEmail": "service-125992521190@gcf-admin-robot.iam.gserviceaccount.com"
                    }
                }
            ]
        },
        "requestMetadata": {
            "callerIp": "x.x.x.x",
            "requestAttributes": {
                "time": "2021-06-01T14:02:21.369142Z",
                "auth": {}
            },
            "destinationAttributes": {}
        },
        "serviceName": "cloudsql.googleapis.com",
        "methodName": "cloudsql.instances.list",
        "authorizationInfo": [
            {
                "resource": "projects/dynatrace-gcp-extension",
                "permission": "cloudsql.instances.list",
                "granted": True,
                "resourceAttributes": {}
            }
        ],
        "resourceName": "projects/dynatrace-gcp-extension",
        "request": {
            "@type": "type.googleapis.com/google.cloud.sql.v1beta4.SqlInstancesListRequest",
            "project": "dynatrace-gcp-extension"
        }
    },
    "insertId": "-najkl1daerp",
    "resource": {
        "type": "cloudsql_database",
        "labels": {
            "region": "",
            "project_id": "dynatrace-gcp-extension",
            "database_id": ""
        }
    },
    "timestamp": timestamp,
    "severity": "INFO",
    "logName": "projects/dynatrace-gcp-extension/logs/cloudaudit.googleapis.com%2Fdata_access",
    "receiveTimestamp": "2021-06-01T14:02:22.357489956Z"
}

record3 = {
    "protoPayload": {
        "@type": "type.googleapis.com/google.cloud.audit.AuditLog",
        "status": {},
        "authenticationInfo": {
            "principalEmail": "maria.swiatkowska@dynatrace.com"
        },
        "requestMetadata": {
            "callerIp": "x.x.x.x",
            "callerSuppliedUserAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36,gzip(gfe)",
            "requestAttributes": {
                "time": "2021-06-01T09:53:17.700228641Z",
                "auth": {}
            },
            "destinationAttributes": {}
        },
        "serviceName": "storage.googleapis.com",
        "methodName": "storage.buckets.list",
        "authorizationInfo": [
            {
                "permission": "storage.buckets.list",
                "granted": True,
                "resourceAttributes": {}
            }
        ],
        "resourceLocation": {
            "currentLocations": [
                "global"
            ]
        }
    },
    "insertId": "-jos90d74ug",
    "resource": {
        "type": "gcs_bucket",
        "labels": {
            "location": "global",
            "bucket_name": "",
            "project_id": "dynatrace-gcp-extension"
        }
    },
    "timestamp": timestamp,
    "severity": "INFO",
    "logName": "projects/dynatrace-gcp-extension/logs/cloudaudit.googleapis.com%2Fdata_access",
    "receiveTimestamp": "2021-06-01T09:53:18.571784927Z"
}

record4 = {
    "protoPayload": {
        "@type": "type.googleapis.com/google.cloud.audit.AuditLog",
        "status": {
            "code": 7,
            "message": "PERMISSION_DENIED"
        },
        "authenticationInfo": {},
        "requestMetadata": {
            "callerIp": "x.x.x.x",
            "callerSuppliedUserAgent": "Go-http-client/1.1,gzip(gfe)",
            "requestAttributes": {
                "time": "2021-06-01T04:45:54.746685130Z",
                "auth": {}
            },
            "destinationAttributes": {}
        },
        "serviceName": "storage.googleapis.com",
        "methodName": "storage.objects.list",
        "authorizationInfo": [
            {
                "resource": "projects/_/buckets/ror-test",
                "permission": "storage.objects.list",
                "resourceAttributes": {}
            }
        ],
        "resourceName": "projects/_/buckets/ror-test",
        "resourceLocation": {
            "currentLocations": [
                "us"
            ]
        }
    },
    "insertId": "jffqz2eewxni",
    "resource": {
        "type": "gcs_bucket",
        "labels": {
            "project_id": "dynatrace-gcp-extension",
            "location": "us",
            "bucket_name": "ror-test"
        }
    },
    "timestamp": timestamp,
    "severity": "ERROR",
    "logName": "projects/dynatrace-gcp-extension/logs/cloudaudit.googleapis.com%2Fdata_access",
    "receiveTimestamp": "2021-06-01T04:45:55.452179480Z"
}

expected_output_list = [
    {
        ATTRIBUTE_CLOUD_PROVIDER: 'gcp',
        ATTRIBUTE_CLOUD_REGION: 'us-central1-b',
        ATTRIBUTE_GCP_REGION: 'us-central1-b',
        ATTRIBUTE_GCP_PROJECT_ID: 'dynatrace-gcp-extension',
        ATTRIBUTE_GCP_RESOURCE_TYPE: 'gce_instance_group_manager',
        ATTRIBUTE_TIMESTAMP: timestamp,
        ATTRIBUTE_CONTENT: json.dumps(record),
        ATTRIBUTE_DT_LOGPATH: 'projects/dynatrace-gcp-extension/logs/cloudaudit.googleapis.com%2Fdata_access',
        ATTRIBUTE_AUDIT_IDENTITY: 'service-125992521190@container-engine-robot.iam.gserviceaccount.com',
        ATTRIBUTE_AUDIT_ACTION: 'v1.compute.instanceGroupManagers.list',
        ATTRIBUTE_AUDIT_RESULT: 'Succeeded',
        ATTRIBUTE_SEVERITY: "INFO",
        'dt.security_context' : ''
    },
    {
        ATTRIBUTE_CLOUD_PROVIDER: 'gcp',
        ATTRIBUTE_GCP_PROJECT_ID: 'dynatrace-gcp-extension',
        ATTRIBUTE_GCP_RESOURCE_TYPE: 'cloudsql_database',
        ATTRIBUTE_TIMESTAMP: timestamp,
        ATTRIBUTE_CONTENT: json.dumps(record2),
        ATTRIBUTE_DT_LOGPATH: 'projects/dynatrace-gcp-extension/logs/cloudaudit.googleapis.com%2Fdata_access',
        ATTRIBUTE_AUDIT_IDENTITY: 'dynatrace-gcp-service@dynatrace-gcp-extension.iam.gserviceaccount.com',
        ATTRIBUTE_AUDIT_ACTION: 'cloudsql.instances.list',
        ATTRIBUTE_AUDIT_RESULT: 'Succeeded',
        ATTRIBUTE_SEVERITY: "INFO",
        'dt.security_context' : ''
    },
    {
        ATTRIBUTE_CLOUD_PROVIDER: 'gcp',
        ATTRIBUTE_CLOUD_REGION: 'global',
        ATTRIBUTE_GCP_REGION: 'global',
        ATTRIBUTE_GCP_PROJECT_ID: 'dynatrace-gcp-extension',
        ATTRIBUTE_GCP_RESOURCE_TYPE: 'gcs_bucket',
        ATTRIBUTE_TIMESTAMP: timestamp,
        ATTRIBUTE_CONTENT: json.dumps(record3),
        ATTRIBUTE_DT_LOGPATH: 'projects/dynatrace-gcp-extension/logs/cloudaudit.googleapis.com%2Fdata_access',
        ATTRIBUTE_AUDIT_IDENTITY: 'maria.swiatkowska@dynatrace.com',
        ATTRIBUTE_AUDIT_ACTION: 'storage.buckets.list',
        ATTRIBUTE_AUDIT_RESULT: 'Succeeded',
        ATTRIBUTE_SEVERITY: "INFO",
        'dt.security_context' : ''
    },
    {
        ATTRIBUTE_CLOUD_PROVIDER: 'gcp',
        ATTRIBUTE_CLOUD_REGION: 'us',
        ATTRIBUTE_GCP_REGION: 'us',
        ATTRIBUTE_GCP_PROJECT_ID: 'dynatrace-gcp-extension',
        ATTRIBUTE_GCP_INSTANCE_NAME: 'ror-test',
        ATTRIBUTE_GCP_RESOURCE_TYPE: 'gcs_bucket',
        ATTRIBUTE_TIMESTAMP: timestamp,
        ATTRIBUTE_CONTENT: json.dumps(record4),
        ATTRIBUTE_DT_LOGPATH: 'projects/dynatrace-gcp-extension/logs/cloudaudit.googleapis.com%2Fdata_access',
        ATTRIBUTE_AUDIT_ACTION: 'storage.objects.list',
        ATTRIBUTE_AUDIT_RESULT: 'Failed.PermissionDenied',
        ATTRIBUTE_SEVERITY: "ERROR",
        'dt.security_context' : ''
    },
]


def test_extraction():
    for entry in expected_output_list:
        actual_output = logs_processor._create_dt_log_payload(TEST_LOGS_PROCESSING_CONTEXT, entry[ATTRIBUTE_CONTENT])
        assert actual_output == entry

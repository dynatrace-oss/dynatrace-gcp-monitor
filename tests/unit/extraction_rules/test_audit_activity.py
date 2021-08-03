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
    ATTRIBUTE_GCP_INSTANCE_ID
from unit.extraction_rules.common import TEST_LOGS_PROCESSING_CONTEXT

MonkeyPatchFixture = NewType("MonkeyPatchFixture", Any)

timestamp = datetime.utcnow().isoformat() + "Z"

record = {
    "protoPayload": {
        "@type": "type.googleapis.com/google.cloud.audit.AuditLog",
        "authenticationInfo": {
            "principalEmail": "system:vpa-recommender"
        },
        "authorizationInfo": [
            {
                "granted": True,
                "permission": "io.k8s.core.v1.endpoints.update",
                "resource": "core/v1/namespaces/kube-system/endpoints/vpa-recommender"
            }
        ],
        "methodName": "io.k8s.core.v1.endpoints.update",
        "request": {
            "@type": "core.k8s.io/v1.Endpoints",
            "apiVersion": "v1",
            "kind": "Endpoints",
            "metadata": {
                "annotations": {
                    "control-plane.alpha.kubernetes.io/leader": "{\"holderIdentity\":\"gke-7c2765753c45498d9427-c6a4-ee8a-vm\",\"leaseDurationSeconds\":30,\"acquireTime\":\"2021-05-24T20:53:16Z\",\"renewTime\":\"2021-06-01T13:46:22Z\",\"leaderTransitions\":5}"
                },
                "creationTimestamp": "2021-05-05T11:17:10Z",
                "managedFields": [
                    {
                        "apiVersion": "v1",
                        "fieldsType": "FieldsV1",
                        "fieldsV1": {
                            "f:metadata": {
                                "f:annotations": {
                                    ".": {},
                                    "f:control-plane.alpha.kubernetes.io/leader": {}
                                }
                            }
                        },
                        "manager": "vpa-recommender",
                        "operation": "Update",
                        "time": "2021-05-05T11:17:10Z"
                    }
                ],
                "name": "vpa-recommender",
                "namespace": "kube-system",
                "resourceVersion": "13396222",
                "selfLink": "/api/v1/namespaces/kube-system/endpoints/vpa-recommender",
                "uid": "61da1c87-12aa-4425-896a-05cd375d7c99"
            }
        },
        "requestMetadata": {
            "callerIp": "::1",
            "callerSuppliedUserAgent": "vpa-recommender/v0.0.0 (linux/amd64) kubernetes/$Format"
        },
        "resourceName": "core/v1/namespaces/kube-system/endpoints/vpa-recommender",
        "response": {
            "@type": "core.k8s.io/v1.Endpoints",
            "apiVersion": "v1",
            "kind": "Endpoints",
            "metadata": {
                "annotations": {
                    "control-plane.alpha.kubernetes.io/leader": "{\"holderIdentity\":\"gke-7c2765753c45498d9427-c6a4-ee8a-vm\",\"leaseDurationSeconds\":30,\"acquireTime\":\"2021-05-24T20:53:16Z\",\"renewTime\":\"2021-06-01T13:46:22Z\",\"leaderTransitions\":5}"
                },
                "creationTimestamp": "2021-05-05T11:17:10Z",
                "managedFields": [
                    {
                        "apiVersion": "v1",
                        "fieldsType": "FieldsV1",
                        "fieldsV1": {
                            "f:metadata": {
                                "f:annotations": {
                                    ".": {},
                                    "f:control-plane.alpha.kubernetes.io/leader": {}
                                }
                            }
                        },
                        "manager": "vpa-recommender",
                        "operation": "Update",
                        "time": "2021-05-05T11:17:10Z"
                    }
                ],
                "name": "vpa-recommender",
                "namespace": "kube-system",
                "resourceVersion": "13396246",
                "selfLink": "/api/v1/namespaces/kube-system/endpoints/vpa-recommender",
                "uid": "61da1c87-12aa-4425-896a-05cd375d7c99"
            }
        },
        "serviceName": "k8s.io",
        "status": {
            "code": 0
        }
    },
    "insertId": "1eba2903-6843-4ef7-a903-51e7ccdbe585",
    "resource": {
        "type": "k8s_cluster",
        "labels": {
            "project_id": "dynatrace-gcp-extension",
            "location": "us-central1-c",
            "cluster_name": "mg-logs-docs-test"
        }
    },
    "timestamp": timestamp,
    "labels": {
        "authorization.k8s.io/decision": "allow",
        "authorization.k8s.io/reason": "RBAC: allowed by ClusterRoleBinding \"system:gke-controller\" of ClusterRole \"system:gke-controller\" to User \"system:vpa-recommender\""
    },
    "logName": "projects/dynatrace-gcp-extension/logs/cloudaudit.googleapis.com%2Factivity",
    "operation": {
        "id": "1eba2903-6843-4ef7-a903-51e7ccdbe585",
        "producer": "k8s.io",
        "first": True,
        "last": True
    },
    "receiveTimestamp": "2021-06-01T13:46:24.606609316Z"
}

record2 = {
    "protoPayload": {
        "@type": "type.googleapis.com/google.cloud.audit.AuditLog",
        "status": {
            "code": 7,
            "message": "Permission monitoring.metricDescriptors.create denied (or the resource may not exist)."
        },
        "authenticationInfo": {
            "principalEmail": "svc-gke-dynatrace-npd@mgmt-ple-prd-83f7.iam.gserviceaccount.com"
        },
        "requestMetadata": {
            "callerIp": "gce-internal-ip",
            "callerSuppliedUserAgent": "Python/3.8 aiohttp/3.7.4,gzip(gfe)",
            "requestAttributes": {
                "time": "2021-06-01T13:46:13.799387360Z",
                "auth": {}
            },
            "destinationAttributes": {}
        },
        "serviceName": "monitoring.googleapis.com",
        "methodName": "google.monitoring.v3.MetricService.CreateMetricDescriptor",
        "authorizationInfo": [
            {
                "resource": "125992521190",
                "permission": "monitoring.metricDescriptors.create",
                "resourceAttributes": {}
            }
        ],
        "resourceName": "projects/dynatrace-gcp-extension",
        "request": {
            "@type": "type.googleapis.com/google.monitoring.v3.CreateMetricDescriptorRequest",
            "name": "projects/dynatrace-gcp-extension",
            "metricDescriptor": {
                "monitoredResourceTypes": [
                    "generic_task"
                ],
                "type": "custom.googleapis.com/dynatrace/phase_execution_time",
                "unit": "s",
                "metricKind": "GAUGE",
                "valueType": "DOUBLE",
                "displayName": "Dynatrace Integration Phase Execution Time",
                "description": "Dynatrace integration self monitoring metric"
            }
        }
    },
    "insertId": "ziy2qeejg3ll",
    "resource": {
        "type": "audited_resource",
        "labels": {
            "method": "google.monitoring.v3.MetricService.CreateMetricDescriptor",
            "project_id": "dynatrace-gcp-extension",
            "service": "monitoring.googleapis.com"
        }
    },
    "timestamp": timestamp,
    "severity": "ERROR",
    "logName": "projects/dynatrace-gcp-extension/logs/cloudaudit.googleapis.com%2Factivity",
    "receiveTimestamp": "2021-06-01T13:46:13.923598562Z"
}

record3 = {
    "protoPayload": {
        "@type": "type.googleapis.com/google.cloud.audit.AuditLog",
        "status": {},
        "authenticationInfo": {
            "principalEmail": "dynatrace-gcp-extension@appspot.gserviceaccount.com",
            "serviceAccountDelegationInfo": [
                {
                    "firstPartyPrincipal": {
                        "principalEmail": "app-engine-appserver@prod.google.com"
                    }
                }
            ]
        },
        "requestMetadata": {
            "callerIp": "x.x.x.x",
            "requestAttributes": {
                "time": "2021-06-01T13:28:03.152740Z",
                "auth": {}
            },
            "destinationAttributes": {}
        },
        "serviceName": "cloudsql.googleapis.com",
        "methodName": "cloudsql.instances.connect",
        "authorizationInfo": [
            {
                "resource": "instances/test-001-mysql",
                "permission": "cloudsql.instances.connect",
                "granted": True,
                "resourceAttributes": {}
            }
        ],
        "resourceName": "instances/test-001-mysql",
        "request": {
            "@type": "type.googleapis.com/google.cloud.sql.v1beta4.SqlInstancesCreateEphemeralCertRequest",
            "body": {},
            "instance": "pawel-001-mysql",
            "project": "dynatrace-gcp-extension"
        },
        "response": {
            "kind": "sql#sslCert",
            "@type": "type.googleapis.com/google.cloud.sql.v1beta4.SslCert"
        }
    },
    "insertId": "28fvludipfi",
    "resource": {
        "type": "cloudsql_database",
        "labels": {
            "region": "europe-north1",
            "project_id": "dynatrace-gcp-extension",
            "database_id": "dynatrace-gcp-extension:pawel-001-mysql"
        }
    },
    "timestamp": timestamp,
    "severity": "NOTICE",
    "logName": "projects/dynatrace-gcp-extension/logs/cloudaudit.googleapis.com%2Factivity",
    "receiveTimestamp": "2021-06-01T13:28:03.475642010Z"
}

record4 = {
    "protoPayload": {
        "@type": "type.googleapis.com/google.cloud.audit.AuditLog",
        "authenticationInfo": {
            "principalEmail": "user@dynatrace.com",
            "principalSubject": "user:user@dynatrace.com"
        },
        "requestMetadata": {
            "callerIp": "x.x.x.x",
            "callerSuppliedUserAgent": "google-cloud-sdk gcloud/340.0.0 command/gcloud.services.enable invocation-id/1784492894a24a10a84a55e7be4d223e environment/devshell environment-version/None interactive/True from-script/True python/3.7.3 term/screen (Linux 5.4.104+),gzip(gfe)",
            "requestAttributes": {
                "time": "2021-06-01T10:11:14.729180Z",
                "auth": {}
            },
            "destinationAttributes": {}
        },
        "serviceName": "serviceusage.googleapis.com",
        "methodName": "google.longrunning.Operations.GetOperation",
        "authorizationInfo": [
            {
                "resource": "projectnumbers/125992521190",
                "permission": "serviceusage.services.enable",
                "granted": True,
                "resourceAttributes": {}
            }
        ]
    },
    "insertId": "1d42slpd1rhn",
    "resource": {
        "type": "audited_resource",
        "labels": {
            "service": "serviceusage.googleapis.com",
            "project_id": "dynatrace-gcp-extension",
            "method": "google.longrunning.Operations.GetOperation"
        }
    },
    "timestamp": timestamp,
    "severity": "NOTICE",
    "logName": "projects/dynatrace-gcp-extension/logs/cloudaudit.googleapis.com%2Factivity",
    "receiveTimestamp": "2021-06-01T10:11:15.496797224Z"
}

expected_output_list = [
    {
        ATTRIBUTE_CLOUD_PROVIDER: 'gcp',
        ATTRIBUTE_CLOUD_REGION: 'us-central1-c',
        ATTRIBUTE_GCP_REGION: 'us-central1-c',
        ATTRIBUTE_GCP_PROJECT_ID: 'dynatrace-gcp-extension',
        ATTRIBUTE_GCP_RESOURCE_TYPE: 'k8s_cluster',
        ATTRIBUTE_TIMESTAMP: timestamp,
        ATTRIBUTE_CONTENT: json.dumps(record),
        ATTRIBUTE_DT_LOGPATH: 'projects/dynatrace-gcp-extension/logs/cloudaudit.googleapis.com%2Factivity',
        ATTRIBUTE_AUDIT_IDENTITY: 'system:vpa-recommender',
        ATTRIBUTE_AUDIT_ACTION: 'io.k8s.core.v1.endpoints.update',
        ATTRIBUTE_AUDIT_RESULT: 'Succeeded',
    },
    {
        ATTRIBUTE_CLOUD_PROVIDER: 'gcp',
        ATTRIBUTE_GCP_PROJECT_ID: 'dynatrace-gcp-extension',
        ATTRIBUTE_GCP_RESOURCE_TYPE: 'audited_resource',
        ATTRIBUTE_TIMESTAMP: timestamp,
        ATTRIBUTE_CONTENT: json.dumps(record2),
        ATTRIBUTE_DT_LOGPATH: 'projects/dynatrace-gcp-extension/logs/cloudaudit.googleapis.com%2Factivity',
        ATTRIBUTE_AUDIT_IDENTITY: 'svc-gke-dynatrace-npd@mgmt-ple-prd-83f7.iam.gserviceaccount.com',
        ATTRIBUTE_AUDIT_ACTION: 'google.monitoring.v3.MetricService.CreateMetricDescriptor',
        ATTRIBUTE_AUDIT_RESULT: 'Failed.PermissionDenied',
        ATTRIBUTE_SEVERITY: "ERROR"
    },
    {
        ATTRIBUTE_CLOUD_PROVIDER: 'gcp',
        ATTRIBUTE_CLOUD_REGION: 'europe-north1',
        ATTRIBUTE_GCP_REGION: 'europe-north1',
        ATTRIBUTE_GCP_PROJECT_ID: 'dynatrace-gcp-extension',
        ATTRIBUTE_GCP_RESOURCE_TYPE: 'cloudsql_database',
        ATTRIBUTE_GCP_INSTANCE_ID: 'dynatrace-gcp-extension:pawel-001-mysql',
        ATTRIBUTE_TIMESTAMP: timestamp,
        ATTRIBUTE_CONTENT: json.dumps(record3),
        ATTRIBUTE_DT_LOGPATH: 'projects/dynatrace-gcp-extension/logs/cloudaudit.googleapis.com%2Factivity',
        ATTRIBUTE_AUDIT_IDENTITY: 'dynatrace-gcp-extension@appspot.gserviceaccount.com',
        ATTRIBUTE_AUDIT_ACTION: 'cloudsql.instances.connect',
        ATTRIBUTE_AUDIT_RESULT: 'Succeeded',
        ATTRIBUTE_SEVERITY: "NOTICE"
    },
    {
        ATTRIBUTE_CLOUD_PROVIDER: 'gcp',
        ATTRIBUTE_GCP_PROJECT_ID: 'dynatrace-gcp-extension',
        ATTRIBUTE_GCP_RESOURCE_TYPE: 'audited_resource',
        ATTRIBUTE_TIMESTAMP: timestamp,
        ATTRIBUTE_CONTENT: json.dumps(record4),
        ATTRIBUTE_DT_LOGPATH: 'projects/dynatrace-gcp-extension/logs/cloudaudit.googleapis.com%2Factivity',
        ATTRIBUTE_AUDIT_IDENTITY: 'user@dynatrace.com',
        ATTRIBUTE_AUDIT_ACTION: 'google.longrunning.Operations.GetOperation',
        ATTRIBUTE_AUDIT_RESULT: 'Succeeded',
        ATTRIBUTE_SEVERITY: "NOTICE"
    }
]


def test_extraction():
    for entry in expected_output_list:
        actual_output = logs_processor._create_dt_log_payload(TEST_LOGS_PROCESSING_CONTEXT, entry[ATTRIBUTE_CONTENT])
        assert actual_output == entry

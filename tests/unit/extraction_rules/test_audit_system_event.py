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
    ATTRIBUTE_DT_LOGPATH, ATTRIBUTE_AUDIT_IDENTITY, ATTRIBUTE_AUDIT_ACTION, ATTRIBUTE_AUDIT_RESULT
from unit.extraction_rules.common import TEST_LOGS_PROCESSING_CONTEXT

MonkeyPatchFixture = NewType("MonkeyPatchFixture", Any)

timestamp = datetime.utcnow().isoformat() + "Z"

record = {
    "protoPayload": {
        "@type": "type.googleapis.com/google.cloud.audit.AuditLog",
        "status": {
            "message": "Instance migrated during Compute Engine maintenance."
        },
        "authenticationInfo": {
            "principalEmail": "system@google.com"
        },
        "serviceName": "compute.googleapis.com",
        "methodName": "compute.instances.migrateOnHostMaintenance",
        "resourceName": "projects/dynatrace-gcp-extension/zones/us-central1-c/instances/gke-gke-helm-ms-default-pool-56e1a146-z9hp",
        "request": {
            "@type": "type.googleapis.com/compute.instances.migrateOnHostMaintenance"
        }
    },
    "insertId": "-v2jb93e1idm2",
    "resource": {
        "type": "gce_instance",
        "labels": {
            "project_id": "dynatrace-gcp-extension",
            "zone": "us-central1-c",
            "instance_id": "783056456320399836"
        }
    },
    "timestamp": timestamp,
    "severity": "INFO",
    "logName": "projects/dynatrace-gcp-extension/logs/cloudaudit.googleapis.com%2Fsystem_event",
    "operation": {
        "id": "systemevent-1622206140000-5c3634cba2700-a1c9a436-380ea389",
        "producer": "compute.instances.migrateOnHostMaintenance",
        "first": True,
        "last": True
    },
    "receiveTimestamp": "2021-05-28T12:49:35.760642486Z"
}

record2 = {
    "protoPayload": {
        "@type": "type.googleapis.com/google.cloud.audit.AuditLog",
        "status": {
            "message": "Ready condition status changed to True for Service user-test."
        },
        "serviceName": "run.googleapis.com",
        "resourceName": "namespaces/dynatrace-gcp-extension/services/user-test",
        "response": {
            "metadata": {
                "name": "user-test",
                "namespace": "125992521190",
                "selfLink": "/apis/serving.knative.dev/v1/namespaces/125992521190/services/user-test",
                "uid": "31507df8-baf4-4b1d-9fb3-6951da0cfffb",
                "resourceVersion": "AAXDIkEBm98",
                "generation": 1,
                "creationTimestamp": "2021-05-25T07:12:42.946813Z",
                "labels": {
                    "cloud.googleapis.com/location": "us-central1"
                },
                "annotations": {
                    "run.googleapis.com/client-name": "cloud-console",
                    "serving.knative.dev/creator": "michal.franczak@dynatrace.com",
                    "serving.knative.dev/lastModifier": "michal.franczak@dynatrace.com",
                    "client.knative.dev/user-image": "us-docker.pkg.dev/cloudrun/container/hello",
                    "run.googleapis.com/ingress": "all",
                    "run.googleapis.com/ingress-status": "all"
                }
            },
            "apiVersion": "serving.knative.dev/v1",
            "kind": "Service",
            "spec": {
                "template": {
                    "metadata": {
                        "name": "user-test-00001-box",
                        "annotations": {
                            "run.googleapis.com/client-name": "cloud-console",
                            "autoscaling.knative.dev/maxScale": "100",
                            "run.googleapis.com/sandbox": "gvisor"
                        }
                    },
                    "spec": {
                        "containerConcurrency": 80,
                        "timeoutSeconds": 300,
                        "serviceAccountName": "125992521190-compute@developer.gserviceaccount.com",
                        "containers": [
                            {
                                "image": "us-docker.pkg.dev/cloudrun/container/hello",
                                "ports": [
                                    {
                                        "containerPort": 8080
                                    }
                                ],
                                "resources": {
                                    "limits": {
                                        "cpu": "1000m",
                                        "memory": "512Mi"
                                    }
                                }
                            }
                        ]
                    }
                },
                "traffic": [
                    {
                        "percent": 100,
                        "latestRevision": True
                    }
                ]
            },
            "status": {
                "observedGeneration": 1,
                "conditions": [
                    {
                        "type": "Ready",
                        "status": "True",
                        "lastTransitionTime": "2021-05-25T07:12:50.482143Z"
                    },
                    {
                        "type": "ConfigurationsReady",
                        "status": "True",
                        "lastTransitionTime": "2021-05-25T07:12:49.747245Z"
                    },
                    {
                        "type": "RoutesReady",
                        "status": "True",
                        "lastTransitionTime": "2021-05-25T07:12:50.482143Z"
                    }
                ],
                "latestReadyRevisionName": "user-test-00001-box",
                "latestCreatedRevisionName": "user-test-00001-box",
                "traffic": [
                    {
                        "revisionName": "user-test-00001-box",
                        "percent": 100,
                        "latestRevision": True
                    }
                ],
                "url": "https://user-test-znf4tqelca-uc.a.run.app",
                "address": {
                    "url": "https://user-test-znf4tqelca-uc.a.run.app"
                }
            },
            "@type": "type.googleapis.com/google.cloud.run.v1.Service"
        }
    },
    "insertId": "-xujmfncgd0",
    "resource": {
        "type": "cloud_run_revision",
        "labels": {
            "location": "us-central1",
            "revision_name": "",
            "service_name": "user-test",
            "project_id": "dynatrace-gcp-extension",
            "configuration_name": ""
        }
    },
    "timestamp": timestamp,
    "severity": "INFO",
    "logName": "projects/dynatrace-gcp-extension/logs/cloudaudit.googleapis.com%2Fsystem_event",
    "receiveTimestamp": "2021-05-25T07:12:51.131933174Z"
}

expected_output_list = [
    {
        ATTRIBUTE_CLOUD_PROVIDER: 'gcp',
        ATTRIBUTE_CLOUD_REGION: 'us-central1-c',
        ATTRIBUTE_GCP_REGION: 'us-central1-c',
        ATTRIBUTE_GCP_PROJECT_ID: 'dynatrace-gcp-extension',
        ATTRIBUTE_GCP_RESOURCE_TYPE: 'gce_instance',
        ATTRIBUTE_TIMESTAMP: timestamp,
        ATTRIBUTE_CONTENT: json.dumps(record),
        ATTRIBUTE_DT_LOGPATH: 'projects/dynatrace-gcp-extension/logs/cloudaudit.googleapis.com%2Fsystem_event',
        ATTRIBUTE_AUDIT_IDENTITY: 'system@google.com',
        ATTRIBUTE_AUDIT_ACTION: 'compute.instances.migrateOnHostMaintenance',
        ATTRIBUTE_AUDIT_RESULT: 'Succeeded',
        ATTRIBUTE_SEVERITY: "INFO",
        'gcp.instance.id': '783056456320399836',
        'dt.security_context' : ''
    },
    {
        ATTRIBUTE_CLOUD_PROVIDER: 'gcp',
        ATTRIBUTE_CLOUD_REGION: 'us-central1',
        ATTRIBUTE_GCP_REGION: 'us-central1',
        ATTRIBUTE_GCP_PROJECT_ID: 'dynatrace-gcp-extension',
        ATTRIBUTE_GCP_RESOURCE_TYPE: 'cloud_run_revision',
        ATTRIBUTE_TIMESTAMP: timestamp,
        ATTRIBUTE_CONTENT: json.dumps(record2),
        ATTRIBUTE_DT_LOGPATH: 'projects/dynatrace-gcp-extension/logs/cloudaudit.googleapis.com%2Fsystem_event',
        ATTRIBUTE_AUDIT_RESULT: 'Succeeded',
        ATTRIBUTE_SEVERITY: "INFO",
        'dt.security_context' : ''
    },
]


def test_extraction():
    for entry in expected_output_list:
        actual_output = logs_processor._create_dt_log_payload(TEST_LOGS_PROCESSING_CONTEXT, entry[ATTRIBUTE_CONTENT])
        assert actual_output == entry

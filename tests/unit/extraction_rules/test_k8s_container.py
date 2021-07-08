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

from lib.context import LogsContext
from lib.logs.logs_processor import _create_dt_log_payload
from lib.logs.metadata_engine import ATTRIBUTE_GCP_PROJECT_ID, ATTRIBUTE_GCP_RESOURCE_TYPE, ATTRIBUTE_SEVERITY, \
    ATTRIBUTE_CLOUD_PROVIDER, ATTRIBUTE_CLOUD_REGION, ATTRIBUTE_GCP_REGION, ATTRIBUTE_GCP_INSTANCE_NAME, \
    ATTRIBUTE_CONTENT, ATTRIBUTE_TIMESTAMP, ATTRIBUTE_DT_LOGPATH, ATTRIBUTE_AUDIT_ACTION, ATTRIBUTE_AUDIT_IDENTITY, \
    ATTRIBUTE_AUDIT_RESULT
from tests.unit.extraction_rules.common import TEST_LOGS_PROCESSING_CONTEXT

timestamp = datetime.utcnow().isoformat() + "Z"

log_record = {
  "insertId": "1a2b3c4d",
  "labels": {
    "compute.googleapis.com/resource_name": "resource-123",
    "k8s-pod/app": "test-app",
    "k8s-pod/app_kubernetes_io/managed-by": "",
    "k8s-pod/app_kubernetes_io/name": "test-app-api",
    "k8s-pod/namespace": "dynatrace",
    "k8s-pod/pod-template-hash": "a1b2c3d4"
  },
  "logName": "projects/dynatrace-gcp-extension/logs/stdout",
  "receiveTimestamp": timestamp,
  "resource": {
    "labels": {
      "cluster_name": "test-cluster",
      "container_name": "test-app-api",
      "location": "us-central1",
      "namespace_name": "dynatrace",
      "pod_name": "testpod",
      "project_id": "dynatrace-gcp-extension"
    },
    "type": "k8s_container"
  },
  "severity": "INFO",
  "textPayload": "2021-03-17 19:58:17.890 DEBUG 1 --- [io-8080-exec-18] o.s.web.servlet.DispatcherServlet        : Completed 200 OK\n",
  "timestamp": timestamp
}
expected_output = {
    ATTRIBUTE_SEVERITY: 'INFO',
    ATTRIBUTE_CLOUD_PROVIDER: 'gcp',
    ATTRIBUTE_CLOUD_REGION: 'us-central1',
    ATTRIBUTE_GCP_REGION: 'us-central1',
    ATTRIBUTE_GCP_PROJECT_ID: 'dynatrace-gcp-extension',
    ATTRIBUTE_GCP_RESOURCE_TYPE: 'k8s_container',
    ATTRIBUTE_GCP_INSTANCE_NAME: 'test-app-api',
    ATTRIBUTE_TIMESTAMP: timestamp,
    ATTRIBUTE_CONTENT: '2021-03-17 19:58:17.890 DEBUG 1 --- [io-8080-exec-18] o.s.web.servlet.DispatcherServlet        : Completed 200 OK\n',
    ATTRIBUTE_DT_LOGPATH: 'projects/dynatrace-gcp-extension/logs/stdout',
    'container.name': 'test-app-api',
    'k8s.cluster.name': 'test-cluster',
    'k8s.namespace.name': 'dynatrace',
    'k8s.pod.name': 'testpod'
}


def test_extraction_debug_text():
    actual_output = _create_dt_log_payload(TEST_LOGS_PROCESSING_CONTEXT, json.dumps(log_record))
    assert actual_output == expected_output

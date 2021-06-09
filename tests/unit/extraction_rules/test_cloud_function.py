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

timestamp = datetime.utcnow().isoformat() + "Z"

debug_text_record = {
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
    "timestamp": timestamp,
    "trace": "projects/dynatrace-gcp-extension/traces/b24dd86d3aa6a386ff2aa6a7f16660a0"
}

debug_text_record_expected_output = {
    ATTRIBUTE_SEVERITY: 'DEBUG',
    ATTRIBUTE_CLOUD_PROVIDER: 'gcp',
    ATTRIBUTE_CLOUD_REGION: 'us-central1',
    ATTRIBUTE_GCP_REGION: 'us-central1',
    ATTRIBUTE_GCP_PROJECT_ID: 'dynatrace-gcp-extension',
    ATTRIBUTE_GCP_RESOURCE_TYPE: 'cloud_function',
    ATTRIBUTE_GCP_INSTANCE_NAME: 'dynatrace-gcp-function',
    ATTRIBUTE_TIMESTAMP: timestamp,
    ATTRIBUTE_CONTENT: "Function execution started",
    ATTRIBUTE_DT_LOGPATH: 'projects/dynatrace-gcp-extension/logs/cloudfunctions.googleapis.com%2Fcloud-functions',
    'faas.id': 'j22o0ucdhpop',
    'faas.name': 'dynatrace-gcp-function'
}

notice_json_record = {
   "insertId": "7e0a707e_33ce3878_748a329b_32cf1b8f_3285fcc5",
   "jsonPayload": {
     "message": "Error detected in dynatrace-logs-ingest",
     "errorEvent": {
       "serviceContext": {
         "resourceType": "cloud_function",
         "service": "dynatrace-logs-ingest"
       },
       "message": "Traceback (most recent call last):\n  File \"/workspace/main.py\", line 37, in dynatrace_logs_ingest\n    asyncio.run(handle_logs_ingest(event, project_id))\n  File \"/opt/python3.8/lib/python3.8/asyncio/runners.py\", line 43, in run\n    return loop.run_until_complete(main)\n  File \"/opt/python3.8/lib/python3.8/asyncio/base_events.py\", line 616, in run_until_complete\n    return future.result()\n  File \"/workspace/main.py\", line 69, in handle_logs_ingest\n    dynatrace_url = await fetch_dynatrace_url(session=session, project_id=project_id, token=token)\n  File \"/workspace/lib/credentials.py\", line 37, in fetch_dynatrace_url\n    return await fetch_secret(session, project_id, token, _DYNATRACE_URL_SECRET_NAME)\n  File \"/workspace/lib/credentials.py\", line 49, in fetch_secret\n    response = await session.get(url, headers=headers)\n  File \"/layers/google.python.pip/pip/lib/python3.8/site-packages/aiohttp/client.py\", line 544, in _request\n    await resp.start(conn)\n  File \"/layers/google.python.pip/pip/lib/python3.8/site-packages/aiohttp/client_reqrep.py\", line 890, in start\n    message, payload = await self._protocol.read()  # type: ignore\n  File \"/layers/google.python.pip/pip/lib/python3.8/site-packages/aiohttp/streams.py\", line 604, in read\n    await self._waiter\naiohttp.client_exceptions.ServerDisconnectedError: Server disconnected",
       "eventTime": timestamp
     },
     "@type": "type.googleapis.com/google.devtools.clouderrorreporting.v1beta1.Insight",
     "errorGroup": "CMG2wtj7h_2mMw"
   },
   "resource": {
     "type": "cloud_function",
     "labels": {
       "region": "us-central1",
       "project_id": "dynatrace-gcp-extension",
       "function_name": "dynatrace-gcp-function"
     }
   },
   "timestamp": timestamp,
   "severity": "NOTICE",
   "logName": "projects/dynatrace-gcp-extension/logs/clouderrorreporting.googleapis.com%2Finsights",
   "receiveTimestamp": "2021-02-04T15:08:22.515974198Z"
 }

notice_json_record_expected_output = {
    ATTRIBUTE_SEVERITY: 'NOTICE',
    ATTRIBUTE_CLOUD_PROVIDER: 'gcp',
    ATTRIBUTE_CLOUD_REGION: 'us-central1',
    ATTRIBUTE_GCP_REGION: 'us-central1',
    ATTRIBUTE_GCP_PROJECT_ID: 'dynatrace-gcp-extension',
    ATTRIBUTE_GCP_RESOURCE_TYPE: 'cloud_function',
    ATTRIBUTE_GCP_INSTANCE_NAME: 'dynatrace-gcp-function',
    ATTRIBUTE_TIMESTAMP: timestamp,
    ATTRIBUTE_CONTENT: "Error detected in dynatrace-logs-ingest",
    ATTRIBUTE_DT_LOGPATH: 'projects/dynatrace-gcp-extension/logs/clouderrorreporting.googleapis.com%2Finsights',
    'faas.name': 'dynatrace-gcp-function'
}

error_proto_record = {
  "protoPayload": {
    "@type": "type.googleapis.com/google.cloud.audit.AuditLog",
    "status": {
      "code": 3,
      "message": "Build failed: build succeeded but did not produce the class \"com.example.Example\" specified as the function target: Error: class not found: com.example.Example; Error ID: 108a9950"
    },
    "authenticationInfo": {
      "principalEmail": "xxxxx@dynatrace.com"
    },
    "serviceName": "cloudfunctions.googleapis.com",
    "methodName": "google.cloud.functions.v1.CloudFunctionsService.UpdateFunction",
    "resourceName": "projects/dynatrace-gcp-extension/locations/europe-central2/functions/function-dk-test"
  },
  "insertId": "-p8lidzb8g",
  "resource": {
    "type": "cloud_function",
    "labels": {
      "function_name": "dynatrace-gcp-function",
      "project_id": "dynatrace-gcp-extension",
      "region": "europe-central2"
    }
  },
  "timestamp": timestamp,
  "severity": "ERROR",
  "logName": "projects/dynatrace-gcp-extension/logs/cloudaudit.googleapis.com%2Factivity",
  "operation": {
    "id": "operations/ZHluYXRyYWNlLWdjcC1leHRlbnNpb24vZXVyb3BlLWNlbnRyYWwyL2Z1bmN0aW9uLWRrLXRlc3QvbVA2UzEtMGpIa0k",
    "producer": "cloudfunctions.googleapis.com",
    "last": True
  },
  "receiveTimestamp": timestamp
}

error_proto_record_expected_output = {
    ATTRIBUTE_AUDIT_ACTION: 'google.cloud.functions.v1.CloudFunctionsService.UpdateFunction',
    ATTRIBUTE_AUDIT_IDENTITY: 'xxxxx@dynatrace.com',
    ATTRIBUTE_AUDIT_RESULT: 'Failed.InvalidArgument',
    ATTRIBUTE_SEVERITY: 'ERROR',
    ATTRIBUTE_CLOUD_PROVIDER: 'gcp',
    ATTRIBUTE_CLOUD_REGION: 'europe-central2',
    ATTRIBUTE_GCP_REGION: 'europe-central2',
    ATTRIBUTE_GCP_PROJECT_ID: 'dynatrace-gcp-extension',
    ATTRIBUTE_GCP_RESOURCE_TYPE: 'cloud_function',
    ATTRIBUTE_GCP_INSTANCE_NAME: 'dynatrace-gcp-function',
    ATTRIBUTE_TIMESTAMP: timestamp,
    ATTRIBUTE_CONTENT: json.dumps(error_proto_record),
    ATTRIBUTE_DT_LOGPATH: 'projects/dynatrace-gcp-extension/logs/cloudaudit.googleapis.com%2Factivity',
    'faas.name': 'dynatrace-gcp-function'
}

logs_context = LogsContext(
    project_id_owner="",
    dynatrace_api_key="",
    dynatrace_url="",
    scheduled_execution_id="",
    sfm_queue=Queue()
)


def test_extraction_debug_text():
    actual_output = _create_dt_log_payload(logs_context, json.dumps(debug_text_record))
    assert actual_output == debug_text_record_expected_output


def test_extraction_notice_json():
    actual_output = _create_dt_log_payload(logs_context, json.dumps(notice_json_record))
    assert actual_output == notice_json_record_expected_output


def test_extraction_error_proto():
    actual_output = _create_dt_log_payload(logs_context, json.dumps(error_proto_record))
    assert actual_output == error_proto_record_expected_output
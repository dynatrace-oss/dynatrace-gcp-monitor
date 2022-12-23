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

SELF_MONITORING_METRIC_PREFIX = "custom.googleapis.com/dynatrace"
SELF_MONITORING_CONNECTIVITY_METRIC_TYPE = SELF_MONITORING_METRIC_PREFIX + "/connectivity"
SELF_MONITORING_INGEST_LINES_METRIC_TYPE = SELF_MONITORING_METRIC_PREFIX + "/ingest_lines"
SELF_MONITORING_REQUEST_COUNT_METRIC_TYPE = SELF_MONITORING_METRIC_PREFIX + "/request_count"
SELF_MONITORING_PHASE_EXECUTION_TIME_METRIC_TYPE = SELF_MONITORING_METRIC_PREFIX + "/phase_execution_time"

DYNATRACE_TENANT_URL_LABEL_DESCRIPTOR = {
    "key": "dynatrace_tenant_url",
    "valueType": "STRING",
    "description": "URL of Dynatrace tenant used for integration"
}

FUNCTION_NAME_LABEL_DESCRIPTOR = {
    "key": "function_name",
    "valueType": "STRING",
    "description": "Name of deployed function"
}

PROJECT_ID_LABEL_DESCRIPTOR = {
    "key": "project_id",
    "valueType": "STRING",
    "description": "GCP project id"
}


SELF_MONITORING_CONNECTIVITY_METRIC_DESCRIPTOR = {
    "type": SELF_MONITORING_CONNECTIVITY_METRIC_TYPE,
    "valueType": "INT64",
    "metricKind": "GAUGE",
    "description": "Dynatrace integration self monitoring metric",
    "displayName": "Dynatrace Integration Connectivity",
    "unit": "1",
    "monitoredResourceTypes": ["generic_task"],
    "labels": [
        FUNCTION_NAME_LABEL_DESCRIPTOR,
        DYNATRACE_TENANT_URL_LABEL_DESCRIPTOR,
        {
            "key": "reason",
            "valueType": "STRING",
            "description": "reason of Ok/Error"
        },
    ]
}

SELF_MONITORING_INGEST_LINES_METRIC_DESCRIPTOR = {
    "type": SELF_MONITORING_INGEST_LINES_METRIC_TYPE,
    "valueType": "INT64",
    "metricKind": "GAUGE",
    "description": "Dynatrace integration self monitoring metric",
    "displayName": "Dynatrace Integration Ingest Lines Count",
    "unit": "1",
    "monitoredResourceTypes": ["generic_task"],
    "labels": [
        FUNCTION_NAME_LABEL_DESCRIPTOR,
        DYNATRACE_TENANT_URL_LABEL_DESCRIPTOR,
        PROJECT_ID_LABEL_DESCRIPTOR,
        {
            "key": "status",
            "valueType": "STRING",
            "description": "reason of Ok/Error"
        },
    ]
}

SELF_MONITORING_REQUEST_COUNT_METRIC_DESCRIPTOR = {
    "type": SELF_MONITORING_REQUEST_COUNT_METRIC_TYPE,
    "valueType": "INT64",
    "metricKind": "GAUGE",
    "description": "Dynatrace integration self monitoring metric",
    "displayName": "Dynatrace Integration Request Count",
    "unit": "1",
    "monitoredResourceTypes": ["generic_task"],
    "labels": [
        FUNCTION_NAME_LABEL_DESCRIPTOR,
        DYNATRACE_TENANT_URL_LABEL_DESCRIPTOR,
        {
            "key": "response_code",
            "valueType": "STRING",
            "description": "reason of Ok/Error"
        },
    ]
}

SELF_MONITORING_PHASE_EXECUTION_TIME_METRIC_DESCRIPTOR = {
    "type": SELF_MONITORING_PHASE_EXECUTION_TIME_METRIC_TYPE,
    "valueType": "DOUBLE",
    "metricKind": "GAUGE",
    "description": "Dynatrace integration self monitoring metric",
    "displayName": "Dynatrace Integration Phase Execution Time",
    "unit": "s",
    "monitoredResourceTypes": ["generic_task"],
    "labels": [
        FUNCTION_NAME_LABEL_DESCRIPTOR,
        DYNATRACE_TENANT_URL_LABEL_DESCRIPTOR,
        PROJECT_ID_LABEL_DESCRIPTOR,
        {
            "key": "phase",
            "valueType": "STRING",
            "description": "Phase of integration worker execution"
        },
    ]
}

SELF_MONITORING_METRIC_MAP = {
    SELF_MONITORING_CONNECTIVITY_METRIC_TYPE: SELF_MONITORING_CONNECTIVITY_METRIC_DESCRIPTOR,
    SELF_MONITORING_INGEST_LINES_METRIC_TYPE: SELF_MONITORING_INGEST_LINES_METRIC_DESCRIPTOR,
    SELF_MONITORING_REQUEST_COUNT_METRIC_TYPE: SELF_MONITORING_REQUEST_COUNT_METRIC_DESCRIPTOR,
    SELF_MONITORING_PHASE_EXECUTION_TIME_METRIC_TYPE: SELF_MONITORING_PHASE_EXECUTION_TIME_METRIC_DESCRIPTOR,
}


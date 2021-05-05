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

LOG_SELF_MONITORING_METRIC_PREFIX = "custom.googleapis.com/dynatrace/logs"
LOG_SELF_MONITORING_ALL_REQUESTS_METRIC_TYPE = LOG_SELF_MONITORING_METRIC_PREFIX + "/all_requests"
LOG_SELF_MONITORING_CONNECTIVITY_METRIC_TYPE = LOG_SELF_MONITORING_METRIC_PREFIX + "/connectivity"
LOG_SELF_MONITORING_TOO_OLD_RECORDS_METRIC_TYPE = LOG_SELF_MONITORING_METRIC_PREFIX + "/too_old_records"
LOG_SELF_MONITORING_PARSING_ERRORS_METRIC_TYPE = LOG_SELF_MONITORING_METRIC_PREFIX + "/parsing_errors"
LOG_SELF_MONITORING_TOO_LONG_CONTENT_METRIC_TYPE = LOG_SELF_MONITORING_METRIC_PREFIX + "/too_long_content_size"
LOG_SELF_MONITORING_PROCESSING_TIME_METRIC_TYPE = LOG_SELF_MONITORING_METRIC_PREFIX + "/processing_time"
LOG_SELF_MONITORING_SENDING_TIME_SIZE_METRIC_TYPE = LOG_SELF_MONITORING_METRIC_PREFIX + "/sending_time"
LOG_SELF_MONITORING_LOG_INGEST_PAYLOAD_SIZE_METRIC_TYPE = LOG_SELF_MONITORING_METRIC_PREFIX + "/log_ingest_payload_size"
LOG_SELF_MONITORING_SENT_LOGS_ENTRIES_METRIC_TYPE = LOG_SELF_MONITORING_METRIC_PREFIX + "/sent_logs_entries"

DYNATRACE_TENANT_URL_LABEL_DESCRIPTOR = {
    "key": "dynatrace_tenant_url",
    "valueType": "STRING",
    "description": "URL of Dynatrace tenant used for gcp log integration"
}

LOGS_SUBSCRIPTION_ID_LABEL_DESCRIPTOR = {
    "key": "logs_subscription_id",
    "valueType": "STRING",
    "description": "Subscription id of log sink pubsub subscription"
}


CONTAINER_NAME = {
    "key": "container_name",
    "valueType": "STRING",
    "description": "Container name"
}

LOG_SELF_MONITORING_ALL_REQUESTS_METRIC_DESCRIPTOR = {
    "type": LOG_SELF_MONITORING_ALL_REQUESTS_METRIC_TYPE,
    "valueType": "INT64",
    "metricKind": "GAUGE",
    "description": "Number of all log ingest requests sent to Dynatrace",
    "displayName": "Dynatrace Log Integration all requests",
    "unit": "1",
    "monitoredResourceTypes": ["generic_task"],
    "labels": [
        DYNATRACE_TENANT_URL_LABEL_DESCRIPTOR,
        LOGS_SUBSCRIPTION_ID_LABEL_DESCRIPTOR,
        CONTAINER_NAME
    ]
}

LOG_SELF_MONITORING_CONNECTIVITY_METRIC_DESCRIPTOR = {
    "type": LOG_SELF_MONITORING_CONNECTIVITY_METRIC_TYPE,
    "valueType": "INT64",
    "metricKind": "GAUGE",
    "description": "Dynatrace connectivity status",
    "displayName": "Dynatrace Log Integration Dynatrace connectivity",
    "unit": "1",
    "monitoredResourceTypes": ["generic_task"],
    "labels": [
        DYNATRACE_TENANT_URL_LABEL_DESCRIPTOR,
        LOGS_SUBSCRIPTION_ID_LABEL_DESCRIPTOR,
        CONTAINER_NAME,
        {
            "key": "connectivity_status",
            "valueType": "STRING",
            "description": "Dynatrace connectivity status"
        }
    ]
}

LOG_SELF_MONITORING_TOO_OLD_RECORDS_METRIC_DESCRIPTOR = {
    "type": LOG_SELF_MONITORING_TOO_OLD_RECORDS_METRIC_TYPE,
    "valueType": "INT64",
    "metricKind": "GAUGE",
    "description": "Number of invalid log records due to too old timestamp",
    "displayName": "Dynatrace Log Integration too old records",
    "unit": "1",
    "monitoredResourceTypes": ["generic_task"],
    "labels": [
        DYNATRACE_TENANT_URL_LABEL_DESCRIPTOR,
        LOGS_SUBSCRIPTION_ID_LABEL_DESCRIPTOR,
        CONTAINER_NAME
    ]
}

LOG_SELF_MONITORING_PARSING_ERRORS_METRIC_DESCRIPTOR = {
    "type": LOG_SELF_MONITORING_PARSING_ERRORS_METRIC_TYPE,
    "valueType": "INT64",
    "metricKind": "GAUGE",
    "description": "Number of errors occurred during parsing logs",
    "displayName": "Dynatrace Log Integration parsing errors",
    "unit": "1",
    "monitoredResourceTypes": ["generic_task"],
    "labels": [
        DYNATRACE_TENANT_URL_LABEL_DESCRIPTOR,
        LOGS_SUBSCRIPTION_ID_LABEL_DESCRIPTOR,
        CONTAINER_NAME
    ]
}

LOG_SELF_MONITORING_TOO_LONG_CONTENT_METRIC_DESCRIPTOR = {
    "type": LOG_SELF_MONITORING_TOO_LONG_CONTENT_METRIC_TYPE,
    "valueType": "INT64",
    "metricKind": "GAUGE",
    "description": "Number of records with content exceeding content max length",
    "displayName": "Dynatrace Log Integration too long content",
    "unit": "1",
    "monitoredResourceTypes": ["generic_task"],
    "labels": [
        DYNATRACE_TENANT_URL_LABEL_DESCRIPTOR,
        LOGS_SUBSCRIPTION_ID_LABEL_DESCRIPTOR,
        CONTAINER_NAME
    ]
}

LOG_SELF_MONITORING_PROCESSING_TIME_METRIC_DESCRIPTOR = {
    "type": LOG_SELF_MONITORING_PROCESSING_TIME_METRIC_TYPE,
    "valueType": "DOUBLE",
    "metricKind": "GAUGE",
    "description": "Total logs processing time",
    "displayName": "Dynatrace Log Integration processing time",
    "unit": "s",
    "monitoredResourceTypes": ["generic_task"],
    "labels": [
        DYNATRACE_TENANT_URL_LABEL_DESCRIPTOR,
        LOGS_SUBSCRIPTION_ID_LABEL_DESCRIPTOR,
        CONTAINER_NAME
    ]
}

LOG_SELF_MONITORING_SENDING_TIME_SIZE_METRIC_DESCRIPTOR = {
    "type": LOG_SELF_MONITORING_SENDING_TIME_SIZE_METRIC_TYPE,
    "valueType": "DOUBLE",
    "metricKind": "GAUGE",
    "description": "Total logs sending time",
    "displayName": "Dynatrace Log Integration sending time",
    "unit": "s",
    "monitoredResourceTypes": ["generic_task"],
    "labels": [
        DYNATRACE_TENANT_URL_LABEL_DESCRIPTOR,
        LOGS_SUBSCRIPTION_ID_LABEL_DESCRIPTOR,
        CONTAINER_NAME
    ]
}

LOG_SELF_MONITORING_LOG_INGEST_PAYLOAD_SIZE_METRIC_DESCRIPTOR = {
    "type": LOG_SELF_MONITORING_LOG_INGEST_PAYLOAD_SIZE_METRIC_TYPE,
    "valueType": "DOUBLE",
    "metricKind": "GAUGE",
    "description": "Log ingest payload size",
    "displayName": "Dynatrace Log Integration log ingest payload size",
    "unit": "kBy",
    "monitoredResourceTypes": ["generic_task"],
    "labels": [
        DYNATRACE_TENANT_URL_LABEL_DESCRIPTOR,
        LOGS_SUBSCRIPTION_ID_LABEL_DESCRIPTOR,
        CONTAINER_NAME
    ]
}

LOG_SELF_MONITORING_SENT_LOGS_ENTRIES_METRIC_DESCRIPTOR = {
    "type": LOG_SELF_MONITORING_SENT_LOGS_ENTRIES_METRIC_TYPE,
    "valueType": "INT64",
    "metricKind": "GAUGE",
    "description": "Number of sent logs entries to Dynatrace",
    "displayName": "Dynatrace Log Integration number of sent logs entries",
    "unit": "1",
    "monitoredResourceTypes": ["generic_task"],
    "labels": [
        DYNATRACE_TENANT_URL_LABEL_DESCRIPTOR,
        LOGS_SUBSCRIPTION_ID_LABEL_DESCRIPTOR,
        CONTAINER_NAME
    ]
}

LOG_SELF_MONITORING_METRIC_MAP = {
    LOG_SELF_MONITORING_ALL_REQUESTS_METRIC_TYPE: LOG_SELF_MONITORING_ALL_REQUESTS_METRIC_DESCRIPTOR,
    LOG_SELF_MONITORING_CONNECTIVITY_METRIC_TYPE: LOG_SELF_MONITORING_CONNECTIVITY_METRIC_DESCRIPTOR,
    LOG_SELF_MONITORING_TOO_OLD_RECORDS_METRIC_TYPE: LOG_SELF_MONITORING_TOO_OLD_RECORDS_METRIC_DESCRIPTOR,
    LOG_SELF_MONITORING_PARSING_ERRORS_METRIC_TYPE: LOG_SELF_MONITORING_PARSING_ERRORS_METRIC_DESCRIPTOR,
    LOG_SELF_MONITORING_TOO_LONG_CONTENT_METRIC_TYPE: LOG_SELF_MONITORING_TOO_LONG_CONTENT_METRIC_DESCRIPTOR,
    LOG_SELF_MONITORING_PROCESSING_TIME_METRIC_TYPE: LOG_SELF_MONITORING_PROCESSING_TIME_METRIC_DESCRIPTOR,
    LOG_SELF_MONITORING_SENDING_TIME_SIZE_METRIC_TYPE: LOG_SELF_MONITORING_SENDING_TIME_SIZE_METRIC_DESCRIPTOR,
    LOG_SELF_MONITORING_LOG_INGEST_PAYLOAD_SIZE_METRIC_TYPE: LOG_SELF_MONITORING_LOG_INGEST_PAYLOAD_SIZE_METRIC_DESCRIPTOR,
    LOG_SELF_MONITORING_SENT_LOGS_ENTRIES_METRIC_TYPE: LOG_SELF_MONITORING_SENT_LOGS_ENTRIES_METRIC_DESCRIPTOR
}


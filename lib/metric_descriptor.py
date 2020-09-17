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
    "type": SELF_MONITORING_REQUEST_COUNT_METRIC_TYPE,
    "valueType": "INT64",
    "metricKind": "DOUBLE",
    "description": "Dynatrace integration self monitoring metric",
    "displayName": "Dynatrace Integration Phase Execution Time",
    "unit": "s",
    "monitoredResourceTypes": ["generic_task"],
    "labels": [
        FUNCTION_NAME_LABEL_DESCRIPTOR,
        DYNATRACE_TENANT_URL_LABEL_DESCRIPTOR,
        {
            "key": "execution_phase",
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


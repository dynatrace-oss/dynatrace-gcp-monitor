from queue import Queue

from lib.context import DynatraceConnectivity, LogsSfmContext
from lib.logs.log_self_monitoring import create_self_monitoring_time_series
from lib.sfm.for_logs.log_sfm_metrics import LogSelfMonitoring


context = LogsSfmContext("project_id", "http://localhost:9011", "dynatrace-gcp-log-forwarder-sub", "token", "", Queue(),
                         True, None, "container_name", "us-east1", "12345")

end_time = context.timestamp.isoformat() + "Z"

expected_metric_data = {
    "timeSeries": [
        {
            "resource": {
                "type": "generic_task",
                "labels": {
                    "project_id": "project_id",
                    "location": "us-east1",
                    "namespace": "Local",
                    "job": "Local",
                    "task_id": "Local"
                }
            },
            "metric": {
                "type": "custom.googleapis.com/dynatrace/logs/all_requests",
                "labels": {
                    "dynatrace_tenant_url": "http://localhost:9011",
                    "logs_subscription_id": "dynatrace-gcp-log-forwarder-sub",
                    "container_name": "container_name",
                    "worker_pid": "12345"
                }
            },
            "valueType": "INT64",
            "metricKind": "GAUGE",
            "points": [
                {
                    "interval": {
                        "endTime": end_time
                    },
                    "value": {
                        "int64Value": 3
                    }
                }
            ]
        },
        {
            "resource": {
                "type": "generic_task",
                "labels": {
                    "project_id": "project_id",
                    "location": "us-east1",
                    "namespace": "Local",
                    "job": "Local",
                    "task_id": "Local"
                }
            },
            "metric": {
                "type": "custom.googleapis.com/dynatrace/logs/too_old_records",
                "labels": {
                    "dynatrace_tenant_url": "http://localhost:9011",
                    "logs_subscription_id": "dynatrace-gcp-log-forwarder-sub",
                    "container_name": "container_name",
                    "worker_pid": "12345"
                }
            },
            "valueType": "INT64",
            "metricKind": "GAUGE",
            "points": [
                {
                    "interval": {
                        "endTime": end_time
                    },
                    "value": {
                        "int64Value": 6
                    }
                }
            ]
        },
        {
            "resource": {
                "type": "generic_task",
                "labels": {
                    "project_id": "project_id",
                    "location": "us-east1",
                    "namespace": "Local",
                    "job": "Local",
                    "task_id": "Local"
                }
            },
            "metric": {
                "type": "custom.googleapis.com/dynatrace/logs/parsing_errors",
                "labels": {
                    "dynatrace_tenant_url": "http://localhost:9011",
                    "logs_subscription_id": "dynatrace-gcp-log-forwarder-sub",
                    "container_name": "container_name",
                    "worker_pid": "12345"
                }
            },
            "valueType": "INT64",
            "metricKind": "GAUGE",
            "points": [
                {
                    "interval": {
                        "endTime": end_time
                    },
                    "value": {
                        "int64Value": 3
                    }
                }
            ]
        },
        {
            "resource": {
                "type": "generic_task",
                "labels": {
                    "project_id": "project_id",
                    "location": "us-east1",
                    "namespace": "Local",
                    "job": "Local",
                    "task_id": "Local"
                }
            },
            "metric": {
                "type": "custom.googleapis.com/dynatrace/logs/too_long_content_size",
                "labels": {
                    "dynatrace_tenant_url": "http://localhost:9011",
                    "logs_subscription_id": "dynatrace-gcp-log-forwarder-sub",
                    "container_name": "container_name",
                    "worker_pid": "12345"
                }
            },
            "valueType": "INT64",
            "metricKind": "GAUGE",
            "points": [
                {
                    "interval": {
                        "endTime": end_time
                    },
                    "value": {
                        "int64Value": 4
                    }
                }
            ]
        },
        {
            "resource": {
                "type": "generic_task",
                "labels": {
                    "project_id": "project_id",
                    "location": "us-east1",
                    "namespace": "Local",
                    "job": "Local",
                    "task_id": "Local"
                }
            },
            "metric": {
                "type": "custom.googleapis.com/dynatrace/logs/processing_time",
                "labels": {
                    "dynatrace_tenant_url": "http://localhost:9011",
                    "logs_subscription_id": "dynatrace-gcp-log-forwarder-sub",
                    "container_name": "container_name",
                    "worker_pid": "12345"
                }
            },
            "valueType": "DOUBLE",
            "metricKind": "GAUGE",
            "points": [
                {
                    "interval": {
                        "endTime": end_time
                    },
                    "value": {
                        "doubleValue": 0.0878758430480957
                    }
                }
            ]
        },
        {
            "resource": {
                "type": "generic_task",
                "labels": {
                    "project_id": "project_id",
                    "location": "us-east1",
                    "namespace": "Local",
                    "job": "Local",
                    "task_id": "Local"
                }
            },
            "metric": {
                "type": "custom.googleapis.com/dynatrace/logs/sending_time",
                "labels": {
                    "dynatrace_tenant_url": "http://localhost:9011",
                    "logs_subscription_id": "dynatrace-gcp-log-forwarder-sub",
                    "container_name": "container_name",
                    "worker_pid": "12345"
                }
            },
            "valueType": "DOUBLE",
            "metricKind": "GAUGE",
            "points": [
                {
                    "interval": {
                        "endTime": end_time
                    },
                    "value": {
                        "doubleValue": 0.3609178066253662
                    }
                }
            ]
        },
        {
            "resource": {
                "type": "generic_task",
                "labels": {
                    "project_id": "project_id",
                    "location": "us-east1",
                    "namespace": "Local",
                    "job": "Local",
                    "task_id": "Local"
                }
            },
            "metric": {
                "type": "custom.googleapis.com/dynatrace/logs/pulling_time",
                "labels": {
                    "dynatrace_tenant_url": "http://localhost:9011",
                    "logs_subscription_id": "dynatrace-gcp-log-forwarder-sub",
                    "container_name": "container_name",
                    "worker_pid": "12345"
                }
            },
            "valueType": "DOUBLE",
            "metricKind": "GAUGE",
            "points": [
                {
                    "interval": {
                        "endTime": end_time
                    },
                    "value": {
                        "doubleValue": 0.0945120120242137
                    }
                }
            ]
        },
        {
            "resource": {
                "type": "generic_task",
                "labels": {
                    "project_id": "project_id",
                    "location": "us-east1",
                    "namespace": "Local",
                    "job": "Local",
                    "task_id": "Local"
                }
            },
            "metric": {
                "type": "custom.googleapis.com/dynatrace/logs/connectivity_failures",
                "labels": {
                    "dynatrace_tenant_url": "http://localhost:9011",
                    "logs_subscription_id": "dynatrace-gcp-log-forwarder-sub",
                    "connectivity_status": "Other",
                    "container_name": "container_name",
                    "worker_pid": "12345"
                }
            },
            "valueType": "INT64",
            "metricKind": "GAUGE",
            "points": [
                {
                    "interval": {
                        "endTime": end_time
                    },
                    "value": {
                        "int64Value": 2
                    }
                }
            ]
        },
        {
            "resource": {
                "type": "generic_task",
                "labels": {
                    "project_id": "project_id",
                    "location": "us-east1",
                    "namespace": "Local",
                    "job": "Local",
                    "task_id": "Local"
                }
            },
            "metric": {
                "type": "custom.googleapis.com/dynatrace/logs/connectivity_failures",
                "labels": {
                    "dynatrace_tenant_url": "http://localhost:9011",
                    "logs_subscription_id": "dynatrace-gcp-log-forwarder-sub",
                    "connectivity_status": "TooManyRequests",
                    "container_name": "container_name",
                    "worker_pid": "12345"
                }
            },
            "valueType": "INT64",
            "metricKind": "GAUGE",
            "points": [
                {
                    "interval": {
                        "endTime": end_time
                    },
                    "value": {
                        "int64Value": 1
                    }
                }
            ],
        },
        {
            "resource": {
                "type": "generic_task",
                "labels": {
                    "project_id": "project_id",
                    "location": "us-east1",
                    "namespace": "Local",
                    "job": "Local",
                    "task_id": "Local"
                }
            },
            "metric": {
                "type": "custom.googleapis.com/dynatrace/logs/log_ingest_payload_size",
                "labels": {
                    "dynatrace_tenant_url": "http://localhost:9011",
                    "logs_subscription_id": "dynatrace-gcp-log-forwarder-sub",
                    "container_name": "container_name",
                    "worker_pid": "12345"
                }
            },
            "valueType": "DOUBLE",
            "metricKind": "GAUGE",
            "points": [
                {
                    "interval": {
                        "endTime": end_time
                    },
                    "value": {
                        "doubleValue": 10.123
                    }
                }
            ]
        },
        {
            "resource": {
                "type": "generic_task",
                "labels": {
                    "project_id": "project_id",
                    "location": "us-east1",
                    "namespace": "Local",
                    "job": "Local",
                    "task_id": "Local"
                }
            },
            "metric": {
                "type": "custom.googleapis.com/dynatrace/logs/raw_log_ingest_payload_size",
                "labels": {
                    "dynatrace_tenant_url": "http://localhost:9011",
                    "logs_subscription_id": "dynatrace-gcp-log-forwarder-sub",
                    "container_name": "container_name",
                    "worker_pid": "12345"
                }
            },
            "valueType": "DOUBLE",
            "metricKind": "GAUGE",
            "points": [
                {
                    "interval": {
                        "endTime": end_time
                    },
                    "value": {
                        "doubleValue": 21.37
                    }
                }
            ]
        },
        {
            "resource": {
                "type": "generic_task",
                "labels": {
                    "project_id": "project_id",
                    "location": "us-east1",
                    "namespace": "Local",
                    "job": "Local",
                    "task_id": "Local"
                }
            },
            "metric": {
                "type": "custom.googleapis.com/dynatrace/logs/sent_logs_entries",
                "labels": {
                    "dynatrace_tenant_url": "http://localhost:9011",
                    "logs_subscription_id": "dynatrace-gcp-log-forwarder-sub",
                    "container_name": "container_name",
                    "worker_pid": "12345"
                }
            },
            "valueType": "INT64",
            "metricKind": "GAUGE",
            "points": [
                {
                    "interval": {
                        "endTime": end_time
                    },
                    "value": {
                        "int64Value": 5
                    }
                }
            ],
        }
    ]
}


def test_self_monitoring_metrics():
    self_monitoring = LogSelfMonitoring()
    self_monitoring.dynatrace_connectivity = [DynatraceConnectivity.Other, DynatraceConnectivity.Other, DynatraceConnectivity.TooManyRequests]
    self_monitoring.too_old_records = 6
    self_monitoring.parsing_errors = 3
    self_monitoring.all_requests = 3
    self_monitoring.processing_time = 0.0878758430480957
    self_monitoring.pulling_time = 0.0945120120242137
    self_monitoring.sending_time = 0.3609178066253662
    self_monitoring.records_with_too_long_content = 4
    self_monitoring.log_ingest_payload_size = 10.123
    self_monitoring.log_ingest_raw_size = 21.37
    self_monitoring.sent_logs_entries = 5

    metric_data = create_self_monitoring_time_series(self_monitoring, context)
    assert metric_data == expected_metric_data

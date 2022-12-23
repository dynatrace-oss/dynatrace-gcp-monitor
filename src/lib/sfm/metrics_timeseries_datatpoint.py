from typing import Dict, List


def create_timeseries_datapoint(
        context,
        metric_type: str,
        metric_labels: Dict,
        points: List[Dict],
        value_type: str = "INT64"):
    return {
        "resource": {
            "type": "generic_task",
            "labels": {
                "project_id": context.project_id_owner,
                "location": context.location,
                "namespace": context.function_name,
                "job": context.function_name,
                "task_id": context.function_name
            }
        },
        "metric": {
            "type": metric_type,
            "labels": metric_labels
        },
        "valueType": value_type,
        "metricKind": "GAUGE",
        "points": points
    }

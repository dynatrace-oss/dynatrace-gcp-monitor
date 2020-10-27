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
from typing import Dict, List

from lib.context import Context
from lib.metric_descriptor import SELF_MONITORING_METRIC_PREFIX, SELF_MONITORING_METRIC_MAP, \
    SELF_MONITORING_CONNECTIVITY_METRIC_TYPE, SELF_MONITORING_INGEST_LINES_METRIC_TYPE, \
    SELF_MONITORING_REQUEST_COUNT_METRIC_TYPE, SELF_MONITORING_PHASE_EXECUTION_TIME_METRIC_TYPE


async def push_self_monitoring_time_series(context: Context):
    try:
        context.log(f"Pushing self monitoring time series to GCP Monitor...")
        await create_metric_descriptors_if_missing(context)

        time_series = create_self_monitoring_time_series(context)
        self_monitoring_response = await context.session.request(
            "POST",
            url=f"https://monitoring.googleapis.com/v3/projects/{context.project_id}/timeSeries",
            data=json.dumps(time_series),
            headers={"Authorization": "Bearer {token}".format(token=context.token)}
        )
        status = self_monitoring_response.status
        if status != 200:
            self_monitoring_response_json = await self_monitoring_response.json()
            context.log(f"Failed to push self monitoring time series, error is: {status} => {self_monitoring_response_json}")
        else:
            context.log(f"Finished pushing self monitoring time series to GCP Monitor")
        self_monitoring_response.close()
    except Exception as e:
        context.log(f"Failed to push self monitoring time series, reason is {type(e).__name__} {e}")


async def create_metric_descriptors_if_missing(context: Context):
    try:
        dynatrace_metrics_descriptors = await context.session.request(
            'GET',
            url=f"https://monitoring.googleapis.com/v3/projects/{context.project_id}/metricDescriptors",
            params=[('filter', f'metric.type = starts_with("{SELF_MONITORING_METRIC_PREFIX}")')],
            headers={"Authorization": f"Bearer {context.token}"}
        )
        dynatrace_metrics_descriptors_json = await dynatrace_metrics_descriptors.json()
        types = [metric.get("type", "") for metric in dynatrace_metrics_descriptors_json.get("metricDescriptors", [])]
        for metric_type, metric_descriptor in SELF_MONITORING_METRIC_MAP.items():
            if metric_type not in types:
                context.log(f"Creating missing metric descriptor for '{metric_type}'")
                await context.session.request(
                    "POST",
                    url=f"https://monitoring.googleapis.com/v3/projects/{context.project_id}/metricDescriptors",
                    data=json.dumps(metric_descriptor),
                    headers={"Authorization": f"Bearer {context.token}"}
                )
    except Exception as e:
        context.log(f"Failed to create self monitoring metrics descriptors, reason is {type(e).__name__} {e}")


def create_time_serie(
        context: Context,
        metric_type: str,
        metric_labels: Dict,
        points: List[Dict],
        value_type: str = "INT64"):
    return {
        "resource": {
            "type": "generic_task",
            "labels": {
                "project_id": context.project_id,
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


def create_self_monitoring_time_series(context: Context) -> Dict:
    interval = {"endTime": context.execution_time.isoformat() + "Z"}
    time_series = [
        create_time_serie(
            context,
            SELF_MONITORING_CONNECTIVITY_METRIC_TYPE,
            {
                "function_name": context.function_name,
                "dynatrace_tenant_url": context.dynatrace_url,
                "reason": context.dynatrace_connectivity.name,
            },
            [{
                "interval": interval,
                "value": {"int64Value": 1}
            }]),
        create_time_serie(
            context,
            SELF_MONITORING_INGEST_LINES_METRIC_TYPE,
            {
                "function_name": context.function_name,
                "dynatrace_tenant_url": context.dynatrace_url,
                "status": "Ok"
            },
            [{
                "interval": interval,
                "value": {"int64Value": context.dynatrace_ingest_lines_ok_count}
            }]),
        create_time_serie(
            context,
            SELF_MONITORING_INGEST_LINES_METRIC_TYPE,
            {
                "function_name": context.function_name,
                "dynatrace_tenant_url": context.dynatrace_url,
                "status": "Invalid"
            },
            [{
                "interval": interval,
                "value": {"int64Value": context.dynatrace_ingest_lines_invalid_count}
            }]),
        create_time_serie(
            context,
            SELF_MONITORING_INGEST_LINES_METRIC_TYPE,
            {
                "function_name": context.function_name,
                "dynatrace_tenant_url": context.dynatrace_url,
                "status": "Dropped"
            },
            [{
                "interval": interval,
                "value": {"int64Value": context.dynatrace_ingest_lines_dropped_count}
            }]),
        create_time_serie(
            context,
            SELF_MONITORING_PHASE_EXECUTION_TIME_METRIC_TYPE,
            {
                "function_name": context.function_name,
                "dynatrace_tenant_url": context.dynatrace_url,
                "phase": "setup"
            },
            [{
                "interval": interval,
                "value": {"doubleValue": context.setup_execution_time}
            }],
            "DOUBLE"),
        create_time_serie(
            context,
            SELF_MONITORING_PHASE_EXECUTION_TIME_METRIC_TYPE,
            {
                "function_name": context.function_name,
                "dynatrace_tenant_url": context.dynatrace_url,
                "phase": "fetch_gcp_data"
            },
            [{
                "interval": interval,
                "value": {"doubleValue": context.fetch_gcp_data_execution_time}
            }],
            "DOUBLE"),
        create_time_serie(
            context,
            SELF_MONITORING_PHASE_EXECUTION_TIME_METRIC_TYPE,
            {
                "function_name": context.function_name,
                "dynatrace_tenant_url": context.dynatrace_url,
                "phase": "push_to_dynatrace"
            },
            [{
                "interval": interval,
                "value": {"doubleValue": context.push_to_dynatrace_execution_time}
            }],
            "DOUBLE"),
    ]

    for status_code, count in context.dynatrace_request_count.items():
        time_series.append(create_time_serie(
            context,
            SELF_MONITORING_REQUEST_COUNT_METRIC_TYPE,
            {
                "response_code": str(status_code),
                "function_name": context.function_name,
                "dynatrace_tenant_url": context.dynatrace_url
            },
            [{
                "interval": interval,
                "value": {"int64Value": count}
            }]
        ))

    return {"timeSeries": time_series}



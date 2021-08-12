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
import asyncio
import json
import os
from typing import Dict, List

from lib.context import SfmContext, MetricsContext, SfmDashboardsContext
from lib.metric_descriptor import SELF_MONITORING_METRIC_PREFIX, SELF_MONITORING_METRIC_MAP, \
    SELF_MONITORING_CONNECTIVITY_METRIC_TYPE, SELF_MONITORING_INGEST_LINES_METRIC_TYPE, \
    SELF_MONITORING_REQUEST_COUNT_METRIC_TYPE, SELF_MONITORING_PHASE_EXECUTION_TIME_METRIC_TYPE
from lib.utilities import chunks
from operation_mode import OperationMode


def log_self_monitoring_data(context: MetricsContext):
    context.log("SFM", f"GCP Monitoring API request count [per project]: {context.gcp_metric_request_count}")
    context.log("SFM", f"Dynatrace MINT API request count [per response code]: {context.dynatrace_request_count}")
    context.log("SFM", f"Dynatrace MINT accepted lines count [per project]: {context.dynatrace_ingest_lines_ok_count}")
    context.log("SFM", f"Dynatrace MINT invalid lines count [per project]: {context.dynatrace_ingest_lines_invalid_count}")
    context.log("SFM", f"Dynatrace MINT dropped lines count [per project]: {context.dynatrace_ingest_lines_dropped_count}")
    context.log("SFM", f"Setup execution time: {context.setup_execution_time.get(context.project_id_owner, None)}") # values are the same for all projects
    context.log("SFM", f"Fetch GCP data execution time [per project]: {context.fetch_gcp_data_execution_time}")
    context.log("SFM", f"Push data to Dynatrace execution time [per project]: {context.push_to_dynatrace_execution_time}")


async def push_self_monitoring(context: MetricsContext):
    time_series = create_self_monitoring_time_series(context)
    await push_self_monitoring_time_series(context, time_series)


async def push_self_monitoring_time_series(context: SfmContext, time_series: Dict):
    try:
        context.log(f"Pushing self monitoring time series to GCP Monitor...")
        await create_metric_descriptors_if_missing(context)
        for single_series in batch_time_series(time_series):
            await push_single_self_monitoring_time_series(context, False, single_series)
    except Exception as e:
        context.log(f"Failed to push self monitoring time series, reason is {type(e).__name__} {e}")


def batch_time_series(time_series: Dict) -> List[Dict]:
    time_series_data = time_series.get("timeSeries", [])
    if len(time_series_data) > 200:
        return list([{"timeSeries": chunk} for chunk in chunks(time_series_data, 200)])
    else:
        return [time_series]


async def push_single_self_monitoring_time_series(context: SfmContext, is_retry: bool, time_series: Dict):
    self_monitoring_response = await context.gcp_session.request(
        "POST",
        url=f"https://monitoring.googleapis.com/v3/projects/{context.project_id_owner}/timeSeries",
        data=json.dumps(time_series),
        headers={"Authorization": "Bearer {token}".format(token=context.token)}
    )
    status = self_monitoring_response.status
    if status == 500 and not is_retry:
        context.log(
            "GCP Monitor responded with 500 Internal Error, it may occur when metric descriptor is updated. Retrying after 5 seconds")
        await asyncio.sleep(5)
        await push_single_self_monitoring_time_series(context, True, time_series)
    elif status != 200:
        self_monitoring_response_json = await self_monitoring_response.json()
        context.log(
            f"Failed to push self monitoring time series, error is: {status} => {self_monitoring_response_json}")
    else:
        context.log(f"Finished pushing self monitoring time series to GCP Monitor")
    self_monitoring_response.close()


async def create_metric_descriptors_if_missing(context: SfmContext):
    try:
        dynatrace_metrics_descriptors = await context.gcp_session.request(
            'GET',
            url=f"https://monitoring.googleapis.com/v3/projects/{context.project_id_owner}/metricDescriptors",
            params=[('filter', f'metric.type = starts_with("{SELF_MONITORING_METRIC_PREFIX}")')],
            headers={"Authorization": f"Bearer {context.token}"}
        )
        dynatrace_metrics_descriptors_json = await dynatrace_metrics_descriptors.json()
        existing_metric_types = {metric.get("type", ""): metric for metric in dynatrace_metrics_descriptors_json.get("metricDescriptors", [])}
        for metric_type, metric_descriptor in context.sfm_metric_map.items():
            existing_metric_descriptor = existing_metric_types.get(metric_type, None)
            if existing_metric_descriptor:
                await replace_metric_descriptor_if_required(context,
                                                            existing_metric_descriptor,
                                                            metric_descriptor,
                                                            metric_type)
            else:
                await create_metric_descriptor(context, metric_descriptor, metric_type)
    except Exception as e:
        context.log(f"Failed to create self monitoring metrics descriptors, reason is {type(e).__name__} {e}")


async def replace_metric_descriptor_if_required(context: SfmContext,
                                                existing_metric_descriptor: Dict,
                                                metric_descriptor: Dict,
                                                metric_type: str):
    existing_label_keys = extract_label_keys(existing_metric_descriptor)
    descriptor_label_keys = extract_label_keys(metric_descriptor)
    if existing_label_keys != descriptor_label_keys:
        await delete_metric_descriptor(context, metric_type)
        await create_metric_descriptor(context, metric_descriptor, metric_type)


async def delete_metric_descriptor(context: SfmContext, metric_type: str):
    context.log(f"Removing old descriptor for '{metric_type}'")
    response = await context.gcp_session.request(
        "DELETE",
        url=f"https://monitoring.googleapis.com/v3/projects/{context.project_id_owner}/metricDescriptors/{metric_type}",
        headers={"Authorization": f"Bearer {context.token}"}
    )
    if response.status != 200:
        response_body = await response.json()
        context.log(f"Failed to remove descriptor for '{metric_type}' due to '{response_body}'")


async def create_metric_descriptor(context: SfmContext, metric_descriptor: Dict, metric_type: str):
    context.log(f"Creating missing metric descriptor for '{metric_type}'")
    response = await context.gcp_session.request(
        "POST",
        url=f"https://monitoring.googleapis.com/v3/projects/{context.project_id_owner}/metricDescriptors",
        data=json.dumps(metric_descriptor),
        headers={"Authorization": f"Bearer {context.token}"}
    )

    if response.status > 202:
        response_body = await response.json()
        context.log(f"Failed to create descriptor for '{metric_type}' due to '{response_body}'")


def extract_label_keys(metric_descriptor: Dict):
    return sorted([label.get("key", "") for label in metric_descriptor.get("labels", [])])


def create_time_serie(
        context: MetricsContext,
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


def create_self_monitoring_time_series(context: MetricsContext) -> Dict:
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
            }])
    ]

    for project_id, count in context.dynatrace_ingest_lines_ok_count.items():
        time_series.append(create_time_serie(
            context,
            SELF_MONITORING_INGEST_LINES_METRIC_TYPE,
            {
                "function_name": context.function_name,
                "dynatrace_tenant_url": context.dynatrace_url,
                "status": "Ok",
                "project_id": project_id,
            },
            [{
                "interval": interval,
                "value": {"int64Value": count}
            }]))

    for project_id, count in context.dynatrace_ingest_lines_invalid_count.items():
        time_series.append(create_time_serie(
            context,
            SELF_MONITORING_INGEST_LINES_METRIC_TYPE,
            {
                "function_name": context.function_name,
                "dynatrace_tenant_url": context.dynatrace_url,
                "status": "Invalid",
                "project_id": project_id,
            },
            [{
                "interval": interval,
                "value": {"int64Value": count}
            }]))

    for project_id, count in context.dynatrace_ingest_lines_dropped_count.items():
        time_series.append(create_time_serie(
            context,
            SELF_MONITORING_INGEST_LINES_METRIC_TYPE,
            {
                "function_name": context.function_name,
                "dynatrace_tenant_url": context.dynatrace_url,
                "status": "Dropped",
                "project_id": project_id,
            },
            [{
                "interval": interval,
                "value": {"int64Value": count}
            }]))

    for project_id, time in context.setup_execution_time.items():
        time_series.append(create_time_serie(
            context,
            SELF_MONITORING_PHASE_EXECUTION_TIME_METRIC_TYPE,
            {
                "function_name": context.function_name,
                "dynatrace_tenant_url": context.dynatrace_url,
                "phase": "setup",
                "project_id": project_id,
            },
            [{
                "interval": interval,
                "value": {"doubleValue": time}
            }],
            "DOUBLE"))

    for project_id, time in context.fetch_gcp_data_execution_time.items():
        time_series.append(create_time_serie(
            context,
            SELF_MONITORING_PHASE_EXECUTION_TIME_METRIC_TYPE,
            {
                "function_name": context.function_name,
                "dynatrace_tenant_url": context.dynatrace_url,
                "phase": "fetch_gcp_data",
                "project_id": project_id,
            },
            [{
                "interval": interval,
                "value": {"doubleValue": time}
            }],
            "DOUBLE"))

    for project_id, time in context.push_to_dynatrace_execution_time.items():
        time_series.append(create_time_serie(
            context,
            SELF_MONITORING_PHASE_EXECUTION_TIME_METRIC_TYPE,
            {
                "function_name": context.function_name,
                "dynatrace_tenant_url": context.dynatrace_url,
                "phase": "push_to_dynatrace",
                "project_id": project_id,
            },
            [{
                "interval": interval,
                "value": {"doubleValue": time}
            }],
            "DOUBLE"))

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


async def is_self_monitoring_dashboard_exists(context: SfmDashboardsContext, dashboard_display_name: str) -> bool:
    try:
        response = await context.gcp_session.request(
            'GET',
            url=f"https://monitoring.googleapis.com/v1/projects/{context.project_id_owner}/dashboards",
            headers={"Authorization": f"Bearer {context.token}"}
        )
        if response.status <= 202:
            response_json = await response.json()
            return dashboard_display_name in [dashboard.get("displayName") for dashboard in response_json.get("dashboards")]
    except Exception as e:
        context.log(f"Failed to list self monitoring dashboards, because: {e}")
    return False


async def create_new_dashboard(context: SfmDashboardsContext, dashboard: Dict):
    response = await context.gcp_session.request(
        "POST",
        url=f"https://monitoring.googleapis.com/v1/projects/{context.project_id_owner}/dashboards",
        data=json.dumps(dashboard),
        headers={"Authorization": f"Bearer {context.token}"}
    )

    if response.status > 202:
        response_body = await response.json()
        context.log(f"Failed to create self monitoring dashboard due to '{response_body}'")
    else:
        context.log(f"The self monitoring dashboard '{dashboard.get('displayName')}' correctly imported")


async def import_self_monitoring_dashboard(context: SfmDashboardsContext):
    if context.operation_mode == OperationMode.Metrics:
        dashboard_filename = "dynatrace-gcp-function_self_monitoring.json"
    elif context.operation_mode == OperationMode.Logs:
        dashboard_filename = "dynatrace-gcp-function-log-self-monitoring.json"
    else:
        context.log(f"Lack of self monitoring dashboard for '{context.operation_mode}' operation mode")
        return

    working_directory = os.path.dirname(os.path.realpath(__file__))
    dashboards_directory = os.path.join(working_directory, "../dashboards")
    dashboard_file_path = os.path.join(dashboards_directory, dashboard_filename)

    try:
        with open(dashboard_file_path, encoding="utf-8") as dashboard_file:
            dashboard = json.load(dashboard_file)

            if await is_self_monitoring_dashboard_exists(context, dashboard.get('displayName')):
                context.log(f"The self monitoring dashboard '{dashboard.get('displayName')}' already exists")
            else:
                await create_new_dashboard(context, dashboard)
    except Exception as e:
        context.log(f"Failed to import a self monitoring dashboard, because: {e}")

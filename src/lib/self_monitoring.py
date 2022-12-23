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
from typing import Dict, List

from lib.context import SfmContext, MetricsContext
from lib.sfm.for_metrics.metric_descriptor import SELF_MONITORING_METRIC_PREFIX
from lib.utilities import chunks


def log_self_monitoring_metrics(context: MetricsContext):
    for key, sfm_metric in context.sfm.items():
        context.log("SFM", f"{sfm_metric.description}: {sfm_metric.value}")


async def push_self_monitoring_metrics(context: MetricsContext):
    time_series = create_sfm_timeseries_datapoints(context)
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


def create_sfm_timeseries_datapoints(context: MetricsContext) -> Dict:
    interval = {"endTime": context.execution_time.isoformat() + "Z"}
    time_series = []

    for key, sfm_metric in context.sfm.items():
        time_series.extend(sfm_metric.generate_timeseries_datapoints(context, interval))

    return {"timeSeries": time_series}


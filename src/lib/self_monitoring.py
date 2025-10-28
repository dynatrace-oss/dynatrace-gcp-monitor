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
import random
from datetime import datetime
from typing import Dict, List

from lib.context import SfmContext, MetricsContext
from lib.sfm.for_metrics.metric_descriptor import SELF_MONITORING_METRIC_PREFIX
from lib.sfm.for_metrics.metrics_definitions import SfmMetric
from lib.utilities import chunks


def log_self_monitoring_metrics(context: MetricsContext):
    sfm_entries: List[str] = []
    for key, sfm_metric in context.sfm.items():
        sfm_entries.append(f"[{sfm_metric.description}: {sfm_metric.value}]")
    context.log("SFM", "Metrics SFM: " + ", ".join(sfm_entries))


async def sfm_push_metrics(sfm_metrics: List[SfmMetric], context: SfmContext, metrics_endtime: datetime):
    prepared_keys: List[str] = [sfm_metric.key for sfm_metric in sfm_metrics]
    context.log(f"Pushing SFM metrics: {prepared_keys}")
    time_series = create_sfm_timeseries_datapoints(sfm_metrics, context, metrics_endtime)
    await push_self_monitoring_time_series(context, time_series)


async def _request_with_retries(context: SfmContext, method: str, url: str, *, headers: Dict = None,
                                params: Dict = None, data: str = None, timeout: int = 10,
                                max_retries: int = 3, base_delay: float = 2.0,
                                retry_statuses: set = {429, 500, 502, 503, 504}):
    """Issue an HTTP request with timeout and limited retry/backoff on transient errors.

    Caller is responsible for consuming/closing the returned response.
    """
    for attempt in range(max_retries + 1):
        response = await context.gcp_session.request(
            method,
            url=url,
            headers=headers,
            params=params,
            data=data,
            timeout=timeout,
        )
        if response.status == 200:
            return response
        if response.status in retry_statuses and attempt < max_retries:
            delay = base_delay * (2 ** attempt) + random.uniform(0, 0.5)
            context.log(
                f"SFM {method} {url} received {response.status}. Retrying in {delay:.1f}s (attempt {attempt + 1}/{max_retries})"
            )
            response.close()
            await asyncio.sleep(delay)
            continue
        return response


async def push_self_monitoring_time_series(context: SfmContext, time_series: Dict):
    try:
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
    """Push SFM time series with timeout and limited retry/backoff on transient errors.

    Retries on 429/500/502/503/504 with exponential backoff + jitter.
    """
    max_retries = 3
    base_delay = 2.0
    retry_statuses = {429, 500, 502, 503, 504}

    for attempt in range(max_retries + 1):
        response = await context.gcp_session.request(
            "POST",
            url=f"https://monitoring.googleapis.com/v3/projects/{context.project_id_owner}/timeSeries",
            data=json.dumps(time_series),
            headers={"Authorization": "Bearer {token}".format(token=context.token)},
            timeout=10,
        )
        status = response.status

        if status == 200:
            context.log(f"Successful pushing of SFM time series to GCP Monitor")
            response.close()
            return

        # transient errors -> backoff and retry if attempts left
        if status in retry_statuses and attempt < max_retries:
            delay = base_delay * (2 ** attempt) + random.uniform(0, 0.5)
            context.log(
                f"SFM push received {status}. Retrying in {delay:.1f}s (attempt {attempt + 1}/{max_retries})"
            )
            response.close()
            await asyncio.sleep(delay)
            continue

        # no retry or attempts exhausted
        try:
            response_body = await response.json()
        except Exception:
            response_body = await response.text()
        context.log(
            f"Failed to push self monitoring time series, error is: {status} => {response_body}"
        )
        response.close()
        return


async def sfm_create_descriptors_if_missing(context: SfmContext):
    try:
        dynatrace_metrics_descriptors = await _request_with_retries(
            context,
            'GET',
            url=f"https://monitoring.googleapis.com/v3/projects/{context.project_id_owner}/metricDescriptors",
            params={'filter': f'metric.type = starts_with("{SELF_MONITORING_METRIC_PREFIX}")'},
            headers={"Authorization": f"Bearer {context.token}"},
            timeout=10,
        )
        dynatrace_metrics_descriptors_json = await dynatrace_metrics_descriptors.json()
        dynatrace_metrics_descriptors.close()
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


async def replace_metric_descriptor_if_required(
    context: SfmContext, existing_metric_descriptor: Dict, metric_descriptor: Dict, metric_type: str
):
    existing_label_keys = extract_label_keys(existing_metric_descriptor)
    descriptor_label_keys = extract_label_keys(metric_descriptor)
    # Compare both label keys and the display name; if either differs, replace the descriptor.
    # Bug fix: previously compared existing displayName to a non-existent key 'metric_descriptor',
    # which always triggered a replace on every SFM cycle.
    if existing_label_keys != descriptor_label_keys or existing_metric_descriptor.get(
        "displayName", "") != metric_descriptor.get("displayName", ""):
        await delete_metric_descriptor(context, metric_type)
        await create_metric_descriptor(context, metric_descriptor, metric_type)


async def delete_metric_descriptor(context: SfmContext, metric_type: str):
    context.log(f"Removing old descriptor for '{metric_type}'")
    response = await _request_with_retries(
        context,
        "DELETE",
        url=f"https://monitoring.googleapis.com/v3/projects/{context.project_id_owner}/metricDescriptors/{metric_type}",
        headers={"Authorization": f"Bearer {context.token}"},
        timeout=10,
    )
    if response.status != 200:
        try:
            response_body = await response.json()
        except Exception:
            response_body = await response.text()
        context.log(f"Failed to remove descriptor for '{metric_type}' due to '{response_body}'")
    response.close()


async def create_metric_descriptor(context: SfmContext, metric_descriptor: Dict, metric_type: str):
    context.log(f"Creating missing metric descriptor for '{metric_type}'")
    response = await _request_with_retries(
        context,
        "POST",
        url=f"https://monitoring.googleapis.com/v3/projects/{context.project_id_owner}/metricDescriptors",
        data=json.dumps(metric_descriptor),
        headers={"Authorization": f"Bearer {context.token}"},
        timeout=10,
    )

    if response.status > 202:
        try:
            response_body = await response.json()
        except Exception:
            response_body = await response.text()
        context.log(f"Failed to create descriptor for '{metric_type}' due to '{response_body}'")
    response.close()


def extract_label_keys(metric_descriptor: Dict):
    return sorted([label.get("key", "") for label in metric_descriptor.get("labels", [])])


def create_sfm_timeseries_datapoints(sfm_metrics: List[SfmMetric], context: SfmContext, endtime: datetime) -> Dict:
    interval = {"endTime": endtime.isoformat() + "Z"}
    time_series = []

    for sfm_metric in sfm_metrics:
        time_series.extend(sfm_metric.generate_timeseries_datapoints(context, interval))

    return {"timeSeries": time_series}


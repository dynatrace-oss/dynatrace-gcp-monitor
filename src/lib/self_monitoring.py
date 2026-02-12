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
from datetime import datetime
from typing import Dict, List

from lib.context import SfmContext, MetricsContext
from lib.sfm.for_metrics.metric_descriptor import SELF_MONITORING_METRIC_PREFIX
from lib.sfm.for_metrics.metrics_definitions import SfmMetric, SfmKeys
from lib.utilities import chunks, percentile


def _format_percentiles(values: dict) -> str:
    """Format dict values as p50/p90/p99/max string."""
    if not values:
        return "N/A"
    sorted_vals = sorted(values.values())
    p50 = percentile(sorted_vals, 50)
    p90 = percentile(sorted_vals, 90)
    p99 = percentile(sorted_vals, 99)
    max_val = max(sorted_vals)
    return f"p50={p50:.2f}s, p90={p90:.2f}s, p99={p99:.2f}s, max={max_val:.2f}s"


def log_self_monitoring_metrics(context: MetricsContext):
    """Log SFM metrics in a readable format, one metric per line."""
    sfm = context.sfm

    # Dynatrace connectivity
    context.log("SFM", f"Dynatrace connectivity: {sfm[SfmKeys.dynatrace_connectivity].value.name}")

    # GCP API stats
    gcp_requests = sfm[SfmKeys.gcp_metric_request_count].value
    total_requests = sum(gcp_requests.values()) if gcp_requests else 0
    context.log("SFM", f"GCP Monitoring API requests: {total_requests}")

    empty_responses = sfm[SfmKeys.gcp_metric_empty_response_count].value
    total_empty = sum(empty_responses.values()) if empty_responses else 0
    context.log("SFM", f"GCP Monitoring API empty responses: {total_empty}")

    # GCP API response codes (separate connection failures from HTTP responses)
    gcp_responses = sfm[SfmKeys.gcp_api_response_count].value
    if gcp_responses:
        # -1 means connection/transport failure (DNS, timeout, etc.)
        connection_failures = gcp_responses.get(-1, 0)
        http_responses = {code: count for code, count in gcp_responses.items() if code != -1}

        if http_responses:
            http_summary = ", ".join(f"{code}:{count}" for code, count in sorted(http_responses.items()))
            context.log("SFM", f"GCP Monitoring API responses: {http_summary}")

        if connection_failures > 0:
            context.log("SFM", f"GCP Monitoring API connection failures: {connection_failures}")

    # Dynatrace ingest stats
    lines_ok = sfm[SfmKeys.dynatrace_ingest_lines_ok_count].value
    total_ok = sum(lines_ok.values()) if lines_ok else 0
    context.log("SFM", f"Dynatrace MINT lines accepted: {total_ok}")

    lines_invalid = sfm[SfmKeys.dynatrace_ingest_lines_invalid_count].value
    total_invalid = sum(lines_invalid.values()) if lines_invalid else 0
    if total_invalid > 0:
        context.log("SFM", f"Dynatrace MINT lines invalid: {total_invalid}")

    lines_dropped = sfm[SfmKeys.dynatrace_ingest_lines_dropped_count].value
    total_dropped = sum(lines_dropped.values()) if lines_dropped else 0
    if total_dropped > 0:
        context.log("SFM", f"Dynatrace MINT lines dropped (429): {total_dropped}")

    # Dimension truncation visibility
    name_trunc = sfm[SfmKeys.dimension_name_truncated_count].value
    value_trunc = sfm[SfmKeys.dimension_value_truncated_count].value
    total_name_trunc = sum(name_trunc.values()) if name_trunc else 0
    total_value_trunc = sum(value_trunc.values()) if value_trunc else 0
    if total_name_trunc or total_value_trunc:
        context.log("SFM", f"Truncated dimensions: names={total_name_trunc}, values={total_value_trunc}")

    # Timing stats with percentiles
    fetch_times = sfm[SfmKeys.fetch_gcp_data_execution_time].value
    if fetch_times:
        context.log("SFM", f"Fetch GCP data time: {_format_percentiles(fetch_times)}")

    push_times = sfm[SfmKeys.push_to_dynatrace_execution_time].value
    if push_times:
        context.log("SFM", f"Push to Dynatrace time: {_format_percentiles(push_times)}")

    # Dynatrace API stats (separate connection failures from HTTP responses)
    dt_requests = sfm[SfmKeys.dynatrace_request_count].value
    if dt_requests:
        # -1 means connection/transport failure
        dt_conn_failures = dt_requests.get(-1, 0)
        dt_http_responses = {code: count for code, count in dt_requests.items() if code != -1}

        if dt_http_responses:
            dt_summary = ", ".join(f"{code}:{count}" for code, count in sorted(dt_http_responses.items()))
            context.log("SFM", f"Dynatrace API responses: {dt_summary}")

        if dt_conn_failures > 0:
            context.log("SFM", f"Dynatrace API connection failures: {dt_conn_failures}")


async def sfm_push_metrics(sfm_metrics: List[SfmMetric], context: SfmContext, metrics_endtime: datetime):
    prepared_keys: List[str] = [sfm_metric.key for sfm_metric in sfm_metrics]
    context.log(f"Pushing SFM metrics: {prepared_keys}")
    time_series = create_sfm_timeseries_datapoints(sfm_metrics, context, metrics_endtime)
    await push_self_monitoring_time_series(context, time_series)


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
        context.log(f"Successful pushing of SFM time series to GCP Monitor")
    self_monitoring_response.close()


async def sfm_create_descriptors_if_missing(context: SfmContext):
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


async def replace_metric_descriptor_if_required(
    context: SfmContext, existing_metric_descriptor: Dict, metric_descriptor: Dict, metric_type: str
):
    existing_label_keys = extract_label_keys(existing_metric_descriptor)
    descriptor_label_keys = extract_label_keys(metric_descriptor)
    if existing_label_keys != descriptor_label_keys or existing_metric_descriptor.get(
        "displayName", "" ) != metric_descriptor.get("metric_descriptor", ""):
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


def create_sfm_timeseries_datapoints(sfm_metrics: List[SfmMetric], context: SfmContext, endtime: datetime) -> Dict:
    interval = {"endTime": endtime.isoformat() + "Z"}
    time_series = []

    for sfm_metric in sfm_metrics:
        time_series.extend(sfm_metric.generate_timeseries_datapoints(context, interval))

    return {"timeSeries": time_series}


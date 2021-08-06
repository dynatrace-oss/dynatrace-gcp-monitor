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
import os
import time
from datetime import timezone, datetime
from http.client import InvalidURL
from typing import Dict, List, Any

from lib.context import MetricsContext, LoggingContext, DynatraceConnectivity
from lib.entities.ids import _create_mmh3_hash
from lib.entities.model import Entity
from lib.metrics import DISTRIBUTION_VALUE_KEY, Metric, TYPED_VALUE_KEY_MAPPING, GCPService, \
    DimensionValue, IngestLine

UNIT_10TO2PERCENT = "10^2.%"
MAX_DIMENSION_NAME_LENGTH = os.environ.get("MAX_DIMENSION_NAME_LENGTH", 100)
MAX_DIMENSION_VALUE_LENGTH = os.environ.get("MAX_DIMENSION_VALUE_LENGTH", 250)

_MONITORING_ROOT = "https://monitoring.googleapis.com/v3"


async def push_ingest_lines(context: MetricsContext, project_id: str, fetch_metric_results: List[IngestLine]):
    if context.dynatrace_connectivity != DynatraceConnectivity.Ok:
        context.log(project_id, f"Skipping push due to detected connectivity error")
        return

    if not fetch_metric_results:
        context.log(project_id, "Skipping push due to no data to push")

    lines_sent = 0
    maximum_lines_threshold = context.maximum_metric_data_points_per_minute
    start_time = time.time()
    try:
        lines_batch = []
        for result in fetch_metric_results:
            lines_batch.append(result)
            lines_sent += 1
            if len(lines_batch) >= context.metric_ingest_batch_size:
                await _push_to_dynatrace(context, project_id, lines_batch)
                lines_batch = []
            if lines_sent >= maximum_lines_threshold:
                await _push_to_dynatrace(context, project_id, lines_batch)
                lines_dropped_count = len(fetch_metric_results) - maximum_lines_threshold
                context.dynatrace_ingest_lines_dropped_count[project_id] = \
                    context.dynatrace_ingest_lines_dropped_count.get(project_id, 0) + lines_dropped_count
                context.log(project_id, f"Number of metric lines exceeded maximum {maximum_lines_threshold}, dropped {lines_dropped_count} lines")
                return
        if lines_batch:
            await _push_to_dynatrace(context, project_id, lines_batch)
    except Exception as e:
        if isinstance(e, InvalidURL):
            context.dynatrace_connectivity = DynatraceConnectivity.WrongURL
        context.log(project_id, f"Failed to push ingest lines to Dynatrace due to {type(e).__name__} {e}")
    finally:
        push_data_time = time.time() - start_time
        context.push_to_dynatrace_execution_time[project_id] = push_data_time
        context.log(project_id, f"Finished uploading metric ingest lines to Dynatrace in {push_data_time} s")


async def _push_to_dynatrace(context: MetricsContext, project_id: str, lines_batch: List[IngestLine]):
    ingest_input = "\n".join([line.to_string() for line in lines_batch])
    if context.print_metric_ingest_input:
        context.log("Ingest input is: ")
        context.log(ingest_input)
    dt_url=f"{context.dynatrace_url.rstrip('/')}/api/v2/metrics/ingest"
    ingest_response = await context.dt_session.post(
        url=dt_url,
        headers={
            "Authorization": f"Api-Token {context.dynatrace_api_key}",
            "Content-Type": "text/plain; charset=utf-8"
        },
        data=ingest_input,
        verify_ssl=context.require_valid_certificate
    )

    if ingest_response.status == 401:
        context.dynatrace_connectivity = DynatraceConnectivity.ExpiredToken
        raise Exception("Expired token")
    elif ingest_response.status == 403:
        context.dynatrace_connectivity = DynatraceConnectivity.WrongToken
        raise Exception("Wrong token - missing 'Ingest metrics using API V2' permission")
    elif ingest_response.status == 404 or ingest_response.status == 405:
        context.dynatrace_connectivity = DynatraceConnectivity.WrongURL
        raise Exception(f"Wrong URL {dt_url}")

    ingest_response_json = await ingest_response.json()
    context.dynatrace_request_count[ingest_response.status] \
        = context.dynatrace_request_count.get(ingest_response.status, 0) + 1
    context.dynatrace_ingest_lines_ok_count[project_id] \
        = context.dynatrace_ingest_lines_ok_count.get(project_id, 0) + ingest_response_json.get("linesOk", 0)
    context.dynatrace_ingest_lines_invalid_count[project_id] \
        = context.dynatrace_ingest_lines_invalid_count.get(project_id, 0) + ingest_response_json.get("linesInvalid", 0)
    context.log(project_id, f"Ingest response: {ingest_response_json}")
    await log_invalid_lines(context, ingest_response_json, lines_batch)


async def log_invalid_lines(context: MetricsContext, ingest_response_json: Dict, lines_batch: List[IngestLine]):
    error = ingest_response_json.get("error", None)
    if error is None:
        return

    invalid_lines = error.get("invalidLines", [])
    if invalid_lines:
        for invalid_line_error_message in invalid_lines:
            line_index = invalid_line_error_message.get("line", 0) - 1
            if line_index > -1:
                invalid_line_error_message = invalid_line_error_message.get("error", "")
                context.log(f"INVALID LINE: '{lines_batch[line_index].to_string()}', reason: '{invalid_line_error_message}'")


async def fetch_metric(
        context: MetricsContext,
        project_id: str,
        service: GCPService,
        metric: Metric
) -> List[IngestLine]:
    end_time = (context.execution_time - metric.ingest_delay)
    start_time = (end_time - context.execution_interval)

    reducer = 'REDUCE_SUM'
    aligner = 'ALIGN_SUM'

    if metric.value_type.lower() == 'bool':
        aligner = 'ALIGN_COUNT_TRUE'
    elif metric.google_metric_kind.lower().startswith('cumulative'):
        aligner = 'ALIGN_DELTA'

    params = [
        ('filter', f'metric.type = "{metric.google_metric}" {service.monitoring_filter}'.strip()),
        ('interval.startTime', start_time.isoformat() + "Z"),
        ('interval.endTime', end_time.isoformat() + "Z"),
        ('aggregation.alignmentPeriod', f"{metric.sample_period_seconds.total_seconds()}s"),
        ('aggregation.perSeriesAligner', aligner),
        ('aggregation.crossSeriesReducer', reducer)
    ]

    all_dimensions = (service.dimensions + metric.dimensions)
    dt_dimensions_by_source_dimension = {}
    for dimension in all_dimensions:
        source = dimension.key_for_fetch_metric
        if dimension.key_for_send_to_dynatrace:
            dt_dimensions_by_source_dimension[dimension.key_for_fetch_metric] = dimension.key_for_send_to_dynatrace

        params.append(('aggregation.groupByFields', source))

    headers = {
        "Authorization": "Bearer {token}".format(token=context.token)
    }
    if context.use_x_goog_user_project_header.get(project_id, False):
        headers["x-goog-user-project"] = project_id

    should_fetch = True

    lines = []
    while should_fetch:
        context.gcp_metric_request_count[project_id] = context.gcp_metric_request_count.get(project_id, 0) + 1

        url = f"{_MONITORING_ROOT}/projects/{project_id}/timeSeries"
        resp = await context.gcp_session.request('GET', url=url, params=params, headers=headers)
        page = await resp.json()
        # response body is https://cloud.google.com/monitoring/api/ref_v3/rest/v3/projects.timeSeries/list#response-body
        if 'error' in page:
            raise Exception(str(page))
        if 'timeSeries' not in page:
            break

        for time_serie in page['timeSeries']:
            typed_value_key = extract_typed_value_key(time_serie)
            dimensions = create_dimensions(context, time_serie, dt_dimensions_by_source_dimension)
            entity_id = create_entity_id(service, time_serie)

            for point in time_serie['points']:
                line = convert_point_to_ingest_line(dimensions, metric, point, typed_value_key, entity_id)
                if line:
                    lines.append(line)

        next_page_token = page.get('nextPageToken', None)
        if next_page_token:
            update_params(next_page_token, params)
        else:
            should_fetch = False

    return lines


def update_params(next_page_token, params):
    replace_index = -1
    for index, param in enumerate(params):
        if param[0] == 'pageToken':
            replace_index = index
            break
    next_page_token_tuple = ('pageToken', next_page_token)
    if replace_index > -1:
        params[replace_index] = next_page_token_tuple
    else:
        params.append(next_page_token_tuple)


def extract_typed_value_key(time_serie):
    value_type = time_serie['valueType'].upper()
    typed_value_key = TYPED_VALUE_KEY_MAPPING.get(value_type, None)
    if typed_value_key is None:
        raise Exception(f"Value type {value_type} is not supported")
    return typed_value_key


def create_dimension(name: str, value: Any, context: LoggingContext = LoggingContext(None)) -> DimensionValue:
    string_value = str(value)

    if len(name) > MAX_DIMENSION_NAME_LENGTH:
        context.log(f'MINT rejects dimension names longer that {MAX_DIMENSION_NAME_LENGTH} chars. Dimension name \"{name}\" "has been truncated')
        name = name[:MAX_DIMENSION_NAME_LENGTH]
    if len(string_value) > MAX_DIMENSION_VALUE_LENGTH:
        context.log(f'MINT rejects dimension values longer that {MAX_DIMENSION_VALUE_LENGTH} chars. Dimension value \"{string_value}\" has been truncated')
        string_value = string_value[:MAX_DIMENSION_VALUE_LENGTH]

    return DimensionValue(name, string_value)


def create_dimensions(context: MetricsContext, time_serie: Dict, dt_dimensions_by_source_dimension: Dict) -> List[DimensionValue]:
    metric_labels = time_serie.get('metric', {}).get('labels', {})
    dt_labels = dict(
        ( dt_dimensions_by_source_dimension.get(f"metric.labels.{label}", label),  value)
        for label, value in metric_labels.items() )

    resource_labels = time_serie.get('resource', {}).get('labels', {})
    dt_labels.update(
        (dt_dimensions_by_source_dimension.get(f"resource.labels.{label}", label), value)
        for label, value in resource_labels.items())

    system_labels = time_serie.get('metadata', {}).get('systemLabels', {})
    dt_labels.update(
        (dt_dimensions_by_source_dimension.get(f"metadata.systemLabels.{label}", label), value)
        for label, value in system_labels.items())

    dimension_values = [ create_dimension( dt_label, value, context)
                        for dt_label, value in dt_labels.items()]

    return dimension_values


def flatten_and_enrich_metric_results(
        context: MetricsContext,
        fetch_metric_results: List[List[IngestLine]],
        entity_id_map: Dict[str, Entity]
) -> List[IngestLine]:
    results = []

    entity_dimension_prefix = "entity."
    for ingest_lines in fetch_metric_results:
        for ingest_line in ingest_lines:
            entity = entity_id_map.get(ingest_line.entity_id, None)
            if entity:
                if entity.dns_names:
                    dimension_value = create_dimension(
                        name=entity_dimension_prefix + "dns_name",
                        value=entity.dns_names[0],
                        context=context
                    )
                    ingest_line.dimension_values.append(dimension_value)

                if entity.ip_addresses:
                    dimension_value = create_dimension(
                        name=entity_dimension_prefix + "ip_address",
                        value=entity.ip_addresses[0],
                        context=context
                    )
                    ingest_line.dimension_values.append(dimension_value)

                for cd_property in entity.properties:
                    dimension_value = create_dimension(
                        name=entity_dimension_prefix + cd_property.key.replace(" ", "_").lower(),
                        value=cd_property.value,
                        context=context
                    )
                    ingest_line.dimension_values.append(dimension_value)

            results.append(ingest_line)

    return results


def create_entity_id(service: GCPService, time_serie):
    resource = time_serie['resource']
    resource_labels = resource.get('labels', {})
    parts = [service.name]
    for dimension in service.dimensions:
        key = dimension.key_for_create_entity_id

        dimension_value = resource_labels.get(key)
        if dimension_value:
            parts.append(dimension_value)
    entity_id = _create_mmh3_hash(parts)
    return entity_id


def convert_point_to_ingest_line(
        dimensions: List[DimensionValue],
        metric: Metric,
        point: Dict,
        typed_value_key: str,
        entity_id: str
) -> IngestLine:
    # Why endtime? see https://cloud.google.com/monitoring/api/ref_v3/rest/v3/TimeInterval
    timestamp_iso = point['interval']['endTime']

    try:
        timestamp_parsed = datetime.strptime(timestamp_iso, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        timestamp_parsed = datetime.strptime(timestamp_iso, "%Y-%m-%dT%H:%M:%S.%fZ")

    timestamp_datetime = timestamp_parsed.replace(tzinfo=timezone.utc)
    timestamp = int(timestamp_datetime.timestamp() * 1000)
    value = extract_value(point, typed_value_key, metric)
    line = None
    if value:
        line = IngestLine(
            entity_id=entity_id,
            metric_name=metric.dynatrace_name,
            metric_type=metric.dynatrace_metric_type,
            value=value,
            timestamp=timestamp,
            dimension_values=dimensions.copy()
        )
    return line


def gauge_line(min, max, count, sum) -> str:
    return f"min={min},max={max},count={count},sum={sum}"


def extract_value(point, typed_value_key: str, metric: Metric):
    value = point['value'][typed_value_key]
    if typed_value_key == DISTRIBUTION_VALUE_KEY:
        count = int(value.get('count', '0'))

        if count == 0:
            return None
        elif 'mean' in value:
            mean = value['mean']
            sum = mean * count
            min = mean
            max = mean
        else:
            sum = 0
            min = 0
            max = 0

        # No point in calculating min and max from distribution here
        if count == 1 or count == 2:
            return gauge_line(min, max, count, sum)

        bucket_options = value['bucketOptions']
        bucket_counts = [int(bucket_count) for bucket_count in value['bucketCounts']]
        bucket_counts_length = len(bucket_counts)

        max_bucket = bucket_counts_length - 1
        min_bucket = max_bucket
        for index, bucket_count in enumerate(bucket_counts):
            if bucket_count > 0:
                min_bucket = index
                break

        # https://cloud.google.com/monitoring/api/ref_v3/rest/v3/TypedValue#exponential
        if 'exponentialBuckets' in bucket_options:
            exponential_buckets_options = bucket_options['exponentialBuckets']
            num_finite_buckets = exponential_buckets_options['numFiniteBuckets']
            if bucket_counts_length < num_finite_buckets and min_bucket != 0:
                growth_factor = exponential_buckets_options['growthFactor']
                scale = exponential_buckets_options['scale']

                min = scale * (growth_factor ** (min_bucket - 1))
                max = scale * (growth_factor ** max_bucket)
        elif 'linearBuckets' in bucket_options:
            linear_bucket_options = bucket_options['linearBuckets']
            num_finite_buckets = linear_bucket_options['numFiniteBuckets']

            if bucket_counts_length < num_finite_buckets and min_bucket != 0:
                offset = linear_bucket_options["offset"]
                width = linear_bucket_options["width"]

                min = offset + (width * (min_bucket - 1))
                max = offset + (width * max_bucket)
        elif 'explicitBuckets' in bucket_options:
            bounds = bucket_options['explicitBuckets']['bounds']
            if min_bucket != 0:
                min = bounds[min_bucket]
                max = bounds[max_bucket]

        if metric.unit == UNIT_10TO2PERCENT:
            min = 100 * min
            max = 100 * max
            sum = 100 * sum

        return gauge_line(min, max, count, sum)
    else:
        if metric.unit == UNIT_10TO2PERCENT:
            value = 100 * value
        return value

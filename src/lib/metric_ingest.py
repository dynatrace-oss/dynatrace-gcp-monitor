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
from lib.sfm.for_metrics.metrics_definitions import SfmKeys
from lib.configuration import config

UNIT_10TO2PERCENT = "10^2.%"
MAX_DIMENSION_NAME_LENGTH = os.environ.get("MAX_DIMENSION_NAME_LENGTH", 100)
MAX_DIMENSION_VALUE_LENGTH = os.environ.get("MAX_DIMENSION_VALUE_LENGTH", 250)

GCP_MONITORING_URL = config.gcp_monitoring_url()


async def push_ingest_lines(context: MetricsContext, project_id: str, fetch_metric_results: List[IngestLine]):
    if context.dynatrace_connectivity != DynatraceConnectivity.Ok:
        context.log(project_id, f"Skipping push due to detected connectivity error")
        return

    if not fetch_metric_results:
        context.log(project_id, "Skipping push due to no data to push")

    start_time = time.time()
    try:
        lines_batch = []
        for result in fetch_metric_results:
            lines_batch.append(result)
            if len(lines_batch) >= context.metric_ingest_batch_size:
                await _push_to_dynatrace(context, project_id, lines_batch)
                lines_batch = []
        if lines_batch:
            await _push_to_dynatrace(context, project_id, lines_batch)
    except Exception as e:
        if isinstance(e, InvalidURL):
            context.update_dt_connectivity_status(DynatraceConnectivity.WrongURL)
        context.log(project_id, f"Failed to push ingest lines to Dynatrace due to {type(e).__name__} {e}")
    finally:
        push_data_time = time.time() - start_time
        context.sfm[SfmKeys.push_to_dynatrace_execution_time].update(project_id, push_data_time)
        context.log(project_id, f"Finished uploading metric ingest lines to Dynatrace in {push_data_time} s")


async def _push_to_dynatrace(context: MetricsContext, project_id: str, lines_batch: List[IngestLine]):
    ingest_input = "\n".join([line.to_string() for line in lines_batch])
    if context.print_metric_ingest_input:
        context.log("Ingest input is: ")
        context.log(ingest_input)
    dt_url = f"{context.dynatrace_url.rstrip('/')}/api/v2/metrics/ingest"
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
        context.update_dt_connectivity_status(DynatraceConnectivity.ExpiredToken)
        raise Exception("Expired token")
    elif ingest_response.status == 403:
        context.update_dt_connectivity_status(DynatraceConnectivity.WrongToken)
        raise Exception("Wrong token - missing 'Ingest metrics using API V2' permission")
    elif ingest_response.status == 404 or ingest_response.status == 405:
        context.update_dt_connectivity_status(DynatraceConnectivity.WrongURL)
        raise Exception(f"Wrong URL {dt_url}")
    elif ingest_response.status == 429:
        context.sfm[SfmKeys.dynatrace_ingest_lines_dropped_count].update(project_id, len(lines_batch))

    ingest_response_json = await ingest_response.json()

    lines_ok = ingest_response_json.get("linesOk", 0)
    lines_invalid = ingest_response_json.get("linesInvalid", 0)

    context.sfm[SfmKeys.dynatrace_request_count].increment(ingest_response.status)
    context.sfm[SfmKeys.dynatrace_ingest_lines_ok_count].update(project_id, lines_ok)
    context.sfm[SfmKeys.dynatrace_ingest_lines_invalid_count].update(project_id, lines_invalid)

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

class DtDimensionsMap:
    def __init__(self) -> None:
            self.dt_dimensions_set_by_source_dimension = {}

    def add_label_mapping(self, source_dimension, dt_target_dimension):
        all_dt_dims_for_source_dim = self.dt_dimensions_set_by_source_dimension.get(source_dimension, set())
        all_dt_dims_for_source_dim.add(dt_target_dimension)
        self.dt_dimensions_set_by_source_dimension[source_dimension] = all_dt_dims_for_source_dim

    def get_dt_dimensions(self, source_dimension, dt_dimension_if_unmapped) -> List:
        # dt_label_if_unmapped - shouldn't happen, but if we get dimension back that we didn't query for (=not defined in map), it would be unsafe to discard it
        # (could result in duplicate metric entries for remaining dim label+value set):
        # report it to Dt under dt_label_if_unmapped - this is expected to be last part for full source dimension label, e.g.:
        # resource.label.unrequestedDimensionLabel > unrequestedDimensionLabel
        dt_dimensions_set = self.dt_dimensions_set_by_source_dimension.get(source_dimension, {dt_dimension_if_unmapped})
        dt_dimension_sorted_list = sorted(dt_dimensions_set)
        return dt_dimension_sorted_list


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
    dt_dimensions_mapping = DtDimensionsMap()
    for dimension in all_dimensions:
        if dimension.key_for_send_to_dynatrace:
            dt_dimensions_mapping.add_label_mapping(dimension.key_for_fetch_metric, dimension.key_for_send_to_dynatrace)

        params.append(('aggregation.groupByFields', dimension.key_for_fetch_metric))

    headers = context.create_gcp_request_headers(project_id)

    should_fetch = True

    lines = []
    while should_fetch:
        context.sfm[SfmKeys.gcp_metric_request_count].increment(project_id)

        url = f"{GCP_MONITORING_URL}/projects/{project_id}/timeSeries"
        resp = await context.gcp_session.request('GET', url=url, params=params, headers=headers)
        page = await resp.json()
        # response body is https://cloud.google.com/monitoring/api/ref_v3/rest/v3/projects.timeSeries/list#response-body
        if 'error' in page:
            raise Exception(str(page))
        if 'timeSeries' not in page:
            break

        for single_time_series in page['timeSeries']:
            typed_value_key = extract_typed_value_key(single_time_series)
            dimensions = create_dimensions(context, service.name, single_time_series, dt_dimensions_mapping)
            entity_id = create_entity_id(service, single_time_series)

            for point in single_time_series['points']:
                line = convert_point_to_ingest_line(context, dimensions, metric, point, typed_value_key, entity_id)
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


def extract_typed_value_key(time_series):
    value_type = time_series['valueType'].upper()
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


def create_dimensions(context: MetricsContext, service_name: str, time_series: Dict, dt_dimensions_mapping: DtDimensionsMap) -> List[DimensionValue]:
    # "gcp.resource.type" is required to easily differentiate services with the same metric set
    # e.g. internal_tcp_lb_rule and internal_udp_lb_rule
    dt_dimensions = [create_dimension("gcp.resource.type", service_name, context)]

    metric_labels = time_series.get('metric', {}).get('labels', {})
    for short_source_label, dim_value in metric_labels.items():
        mapped_dt_dim_labels = dt_dimensions_mapping.get_dt_dimensions(f"metric.labels.{short_source_label}", short_source_label)
        for dt_dim_label in mapped_dt_dim_labels:
            dt_dimensions.append( create_dimension(dt_dim_label, dim_value, context) )

    resource_labels = time_series.get('resource', {}).get('labels', {})
    for short_source_label, dim_value in resource_labels.items():
        mapped_dt_dim_labels = dt_dimensions_mapping.get_dt_dimensions(f"resource.labels.{short_source_label}", short_source_label)
        for dt_dim_label in mapped_dt_dim_labels:
            dt_dimensions.append( create_dimension(dt_dim_label, dim_value, context) )

    system_labels = time_series.get('metadata', {}).get('systemLabels', {})
    for short_source_label, dim_value in system_labels.items():
        mapped_dt_dim_labels = dt_dimensions_mapping.get_dt_dimensions(f"metadata.systemLabels.{short_source_label}", short_source_label)
        for dt_dim_label in mapped_dt_dim_labels:
            dt_dimensions.append( create_dimension(dt_dim_label, dim_value, context) )

    return dt_dimensions


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


def create_entity_id(service: GCPService, time_series):
    resource = time_series['resource']
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
        context: MetricsContext,
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

    value = None
    line = None
    try:
        value = extract_value(point, typed_value_key, metric)
    except Exception as e:
        context.log(f"Failed to extract value from data point: {point}, due to {type(e).__name__} {e}")

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

            if bucket_counts_length < num_finite_buckets and min_bucket != 0 \
                    and 'offset' in linear_bucket_options and 'width' in linear_bucket_options:
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

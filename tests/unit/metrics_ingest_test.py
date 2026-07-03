#   Copyright 2021 Dynatrace LLC
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from lib.entities.model import CdProperty
from lib.metric_ingest import *
from lib.metric_ingest import _set_reducer
from lib.topology.topology import build_entity_id_map


def test_create_dimension_correct_values():
    name = "n" * (MAX_DIMENSION_NAME_LENGTH - 1)
    value = "v" * (MAX_DIMENSION_VALUE_LENGTH - 1)

    dimension_value = create_dimension(name, value)

    assert dimension_value.name == name
    assert dimension_value.value == value


def test_create_dimension_too_long_dimension():
    name = "n" * (MAX_DIMENSION_NAME_LENGTH + 100)
    value = "v" * (MAX_DIMENSION_VALUE_LENGTH + 100)

    dimension_value = create_dimension(name, value)

    assert len(dimension_value.name) == MAX_DIMENSION_NAME_LENGTH
    assert len(dimension_value.value) == MAX_DIMENSION_VALUE_LENGTH


def test_create_dimension_escapes_quotes_and_removes_control_chars():
    name = "querystring"
    value = '"C:\\Program Files\\Foo\\bar.exe" -flag\nnext'

    dimension_value = create_dimension(name, value)

    assert dimension_value.value == '\\"C:\\\\Program Files\\\\Foo\\\\bar.exe\\" -flag next'
    assert "\n" not in dimension_value.value
    assert "\r" not in dimension_value.value
    assert "\t" not in dimension_value.value


def test_create_dimensions_includes_min_sample_period_override_when_overridden():
    context = LoggingContext(None)
    service_name = "test.service"
    time_series = {
        "metric": {"labels": {}},
        "resource": {"labels": {}},
        "metadata": {"systemLabels": {}, "userLabels": {}},
    }

    metric = type("MetricStub", (), {})()
    metric.autodiscovered_metric = False
    metric.sample_period_overridden = True
    metric.sample_period_seconds = timedelta(seconds=120)

    dt_dimensions_mapping = DtDimensionsMap()
    dimensions = create_dimensions(context, service_name, time_series, dt_dimensions_mapping, metric)

    override_dims = [d for d in dimensions if d.name == "dt.min_sample_period_override"]
    assert len(override_dims) == 1
    assert override_dims[0].value == "120"


def test_create_dimensions_omits_min_sample_period_override_when_not_overridden():
    context = LoggingContext(None)
    service_name = "test.service"
    time_series = {
        "metric": {"labels": {}},
        "resource": {"labels": {}},
        "metadata": {"systemLabels": {}, "userLabels": {}},
    }

    metric = type("MetricStub", (), {})()
    metric.autodiscovered_metric = False
    metric.sample_period_overridden = False
    metric.sample_period_seconds = timedelta(seconds=60)

    dt_dimensions_mapping = DtDimensionsMap()
    dimensions = create_dimensions(context, service_name, time_series, dt_dimensions_mapping, metric)
    assert all(d.name != "dt.min_sample_period_override" for d in dimensions)


def test_create_dimensions_adds_gcp_project_id_alias_for_returned_resource_project_id():
    context = LoggingContext(None)
    service_name = "test.autodiscovered"
    time_series = {
        "metric": {"labels": {}},
        "resource": {"labels": {"project_id": "test-project"}},
        "metadata": {"systemLabels": {}, "userLabels": {}},
    }

    metric = type("MetricStub", (), {})()
    metric.autodiscovered_metric = True
    metric.sample_period_overridden = False

    dimensions = create_dimensions(context, service_name, time_series, DtDimensionsMap(), metric)
    dimensions_by_name = {dimension.name: dimension.value for dimension in dimensions}

    assert dimensions_by_name["project_id"] == "test-project"
    assert dimensions_by_name["gcp.project.id"] == "test-project"


def test_create_dimensions_includes_override_for_autodiscovered_metric_via_effective_sample_period():
    context = LoggingContext(None)
    service_name = "test.autodiscovered"
    time_series = {
        "metric": {"labels": {}},
        "resource": {"labels": {}},
        "metadata": {"systemLabels": {}, "userLabels": {}},
    }

    metric = type("MetricStub", (), {})()
    metric.autodiscovered_metric = True
    metric.sample_period_overridden = False  # not overridden at Metric construction time
    metric.sample_period_seconds = timedelta(seconds=60)

    dt_dimensions_mapping = DtDimensionsMap()
    # Simulate fetch_metric passing an effective_sample_period derived from the linked service override
    effective_sp = timedelta(seconds=300)
    dimensions = create_dimensions(context, service_name, time_series, dt_dimensions_mapping, metric, effective_sp)

    override_dims = [d for d in dimensions if d.name == "dt.min_sample_period_override"]
    assert len(override_dims) == 1
    assert override_dims[0].value == "300"


def test_create_dimensions_omits_excluded_returned_metric_label():
    context = LoggingContext(None)
    metric = type("MetricStub", (), {})()
    metric.autodiscovered_metric = False
    metric.sample_period_overridden = False

    time_series = {
        "metric": {"labels": {"querystring": "SELECT 1", "query_hash": "abc"}},
        "resource": {"labels": {"project_id": "test-project"}},
        "metadata": {"systemLabels": {}, "userLabels": {}},
    }

    dimensions = create_dimensions(
        context,
        "cloudsql_database",
        time_series,
        DtDimensionsMap(),
        metric,
        excluded_source_dimensions={"metric.labels.querystring"},
    )

    dimensions_by_name = {dimension.name: dimension.value for dimension in dimensions}
    assert "querystring" not in dimensions_by_name
    assert dimensions_by_name["query_hash"] == "abc"


def test_create_dimensions_omits_excluded_metadata_labels():
    context = LoggingContext(None)
    metric = type("MetricStub", (), {})()
    metric.autodiscovered_metric = False
    metric.sample_period_overridden = False

    time_series = {
        "metric": {"labels": {}},
        "resource": {"labels": {}},
        "metadata": {
            "systemLabels": {"machine_type": "n2-standard-4", "location": "us-east1"},
            "userLabels": {"team": "payments", "env": "prod"},
        },
    }

    dimensions = create_dimensions(
        context,
        "gce_instance",
        time_series,
        DtDimensionsMap(),
        metric,
        excluded_source_dimensions={"metadata.system_labels.machine_type", "metadata.user_labels.team"},
    )

    dimensions_by_name = {dimension.name: dimension.value for dimension in dimensions}
    assert "machine_type" not in dimensions_by_name
    assert "team" not in dimensions_by_name
    assert dimensions_by_name["location"] == "us-east1"
    assert dimensions_by_name["env"] == "prod"


def test_cumulative_reducer_uses_sum_only_when_dimensions_are_excluded():
    assert _set_reducer("CUMULATIVE", "INT64") == "REDUCE_NONE"
    assert _set_reducer("CUMULATIVE", "INT64", aggregate_excluded_dimensions=True) == "REDUCE_SUM"
    assert _set_reducer("CUMULATIVE", "DISTRIBUTION", aggregate_excluded_dimensions=True) == "REDUCE_SUM"


class _FakeGcpResponse:
    async def json(self):
        await asyncio.sleep(0)
        return {}


class _FakeGcpSession:
    def __init__(self):
        self.params = None

    async def request(self, _method, url, params, headers):
        await asyncio.sleep(0)
        _ = (url, headers)
        self.params = list(params)
        return _FakeGcpResponse()


@pytest.mark.asyncio
async def test_fetch_metric_aggregates_cumulative_metric_when_dimension_excluded():
    gcp_session = _FakeGcpSession()
    context = MetricsContext(gcp_session, None, "owner", "token", datetime.now(timezone.utc), 60, "", "", False, False, None)
    service = GCPService(service="cloudsql_database", dimensions=[], metrics=[])
    metric = Metric(
        name="Per query execution time",
        value="metric:cloudsql.googleapis.com/database/postgresql/insights/perquery/execution_time",
        key="cloud.gcp.cloudsql_googleapis_com.database.postgresql.insights.perquery.execution_time.count",
        type="count",
        gcpOptions={"ingestDelay": 0, "samplePeriod": 60, "valueType": "INT64", "metricKind": "CUMULATIVE"},
        dimensions=[
            {"key": "querystring", "value": "label:metric.labels.querystring"},
            {"key": "query_hash", "value": "label:metric.labels.query_hash"},
        ],
    )

    await fetch_metric(
        context,
        "test-project",
        service,
        metric,
        [{"metric": metric.google_metric, "dimensions": {"querystring"}}],
        NO_GROUPING_CATEGORY,
    )

    assert ("aggregation.perSeriesAligner", "ALIGN_DELTA") in gcp_session.params
    assert ("aggregation.crossSeriesReducer", "REDUCE_SUM") in gcp_session.params
    assert ("aggregation.groupByFields", "metric.labels.querystring") not in gcp_session.params
    assert ("aggregation.groupByFields", "metric.labels.query_hash") in gcp_session.params


def test_flatten_and_enrich_metric_results_all_additional_dimensions():
    context_mock = MetricsContext(None, None, "", "", datetime.now(timezone.utc), 0, "", "", False, False, None)
    metric_results = [[IngestLine("entity_id", "m1", "count", 1, 10000, [])]]
    entity_id_map = build_entity_id_map([[Entity("entity_id", "", "", ip_addresses=["1.1.1.1", "0.0.0.0"], listen_ports=[],
                                         favicon_url="", dtype="", properties=[CdProperty("Example property", "example_value")],
                                         tags=[], dns_names=["other.dns.name", "dns.name"])]])

    lines = flatten_and_enrich_metric_results(context=context_mock, fetch_metric_results=metric_results, entity_id_map=entity_id_map)

    assert len(lines) == 1
    ingest_line = lines[0]
    expected_dimensions = [DimensionValue(name="entity.ip_address", value="0.0.0.0"),
                           DimensionValue(name="entity.dns_name", value="dns.name"),
                           DimensionValue(name="entity.example_property", value="example_value")]
    assert set(expected_dimensions) == set(ingest_line.dimension_values)


def test_extract_value_explicit_buckets_overflow():
    """extract_value should not crash when the last non-empty bucket is the overflow bucket."""
    from unittest.mock import MagicMock

    metric = MagicMock()
    metric.unit = ""

    point = {
        'interval': {'startTime': '2026-02-10T10:03:54Z', 'endTime': '2026-02-10T10:04:54Z'},
        'value': {
            'distributionValue': {
                'count': '677',
                'mean': 57386.23180962643,
                'bucketOptions': {
                    'explicitBuckets': {
                        'bounds': [0, 0.01, 0.05, 0.1, 0.3, 0.6, 0.8, 1, 2, 3, 4, 5, 6, 8,
                                   10, 13, 16, 20, 25, 30, 40, 50, 65, 80, 100, 130, 160, 200,
                                   250, 300, 400, 500, 650, 800, 1000, 2000, 5000, 10000, 20000,
                                   50000, 100000]
                    }
                },
                'bucketCounts': ['0'] * 36 + ['1', '10', '37', '203', '401', '25']
            }
        }
    }

    result = extract_value(point, DISTRIBUTION_VALUE_KEY, metric)
    assert result is not None
    # Should contain min, max, count, sum
    assert "count=677" in result
    # min should be bounds[35]=2000 (lower bound of first non-empty bucket 36)
    assert result.startswith("min=2000")
    # max should be bounds[40]=100000 (last finite bound, since max_bucket is overflow)
    assert "max=100000" in result


def test_extract_value_explicit_buckets_no_overflow():
    """extract_value should work when the last non-empty bucket is within bounds."""
    from unittest.mock import MagicMock

    metric = MagicMock()
    metric.unit = ""

    # 5 bounds → 6 buckets; items in buckets 1-4 (no overflow)
    point = {
        'interval': {'startTime': '2026-02-10T10:00:00Z', 'endTime': '2026-02-10T10:01:00Z'},
        'value': {
            'distributionValue': {
                'count': '10',
                'mean': 50.0,
                'bucketOptions': {
                    'explicitBuckets': {'bounds': [10, 20, 50, 100, 200]}
                },
                'bucketCounts': ['0', '2', '3', '3', '2', '0']
            }
        }
    }

    result = extract_value(point, DISTRIBUTION_VALUE_KEY, metric)
    assert result is not None
    assert "count=10" in result

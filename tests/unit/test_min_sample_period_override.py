#   Copyright 2023 Dynatrace LLC
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

from datetime import datetime, timedelta

from lib.metrics import Metric, GCPService
from lib.metric_ingest import create_dimensions, DtDimensionsMap
from lib.context import MetricsContext


# --- Metric override logic tests ---


def test_metric_override_applied_when_larger_than_extension_sample_period():
    metric = Metric(
        gcpOptions={"samplePeriod": 60, "valueType": "INT64"},
        min_sample_period_override=300,
    )
    assert metric.sample_period_seconds == timedelta(seconds=300)
    assert metric.sample_period_overridden is True


def test_metric_override_not_applied_when_smaller_than_extension_sample_period():
    metric = Metric(
        gcpOptions={"samplePeriod": 600, "valueType": "INT64"},
        min_sample_period_override=300,
    )
    assert metric.sample_period_seconds == timedelta(seconds=600)
    assert metric.sample_period_overridden is False


def test_metric_override_not_applied_when_equal_to_extension_sample_period():
    metric = Metric(
        gcpOptions={"samplePeriod": 300, "valueType": "INT64"},
        min_sample_period_override=300,
    )
    assert metric.sample_period_seconds == timedelta(seconds=300)
    assert metric.sample_period_overridden is False


def test_metric_override_zero_means_disabled():
    metric = Metric(
        gcpOptions={"samplePeriod": 60, "valueType": "INT64"},
        min_sample_period_override=0,
    )
    assert metric.sample_period_seconds == timedelta(seconds=60)
    assert metric.sample_period_overridden is False


def test_metric_override_not_provided():
    metric = Metric(
        gcpOptions={"samplePeriod": 60, "valueType": "INT64"},
    )
    assert metric.sample_period_seconds == timedelta(seconds=60)
    assert metric.sample_period_overridden is False


def test_metric_default_sample_period_with_override():
    """When no samplePeriod in gcpOptions, default is 60s; override should still apply."""
    metric = Metric(
        gcpOptions={"valueType": "INT64"},
        min_sample_period_override=300,
    )
    assert metric.sample_period_seconds == timedelta(seconds=300)
    assert metric.sample_period_overridden is True


# --- GCPService defensive parsing tests ---


def test_gcp_service_parses_valid_override():
    service = GCPService(
        service="test_service",
        activation={"minSamplePeriodOverride": 300},
        metrics=[{"gcpOptions": {"samplePeriod": 60, "valueType": "INT64"}}],
    )
    assert service.min_sample_period_override == 300
    assert service.metrics[0].sample_period_overridden is True


def test_gcp_service_handles_string_override_gracefully():
    """Non-numeric string like '300s' should be treated as 0 (disabled)."""
    service = GCPService(
        service="test_service",
        activation={"minSamplePeriodOverride": "300s"},
        metrics=[{"gcpOptions": {"samplePeriod": 60, "valueType": "INT64"}}],
    )
    assert service.min_sample_period_override == 0
    assert service.metrics[0].sample_period_overridden is False


def test_gcp_service_handles_empty_string_override():
    service = GCPService(
        service="test_service",
        activation={"minSamplePeriodOverride": ""},
        metrics=[{"gcpOptions": {"samplePeriod": 60, "valueType": "INT64"}}],
    )
    assert service.min_sample_period_override == 0
    assert service.metrics[0].sample_period_overridden is False


def test_gcp_service_handles_none_override():
    service = GCPService(
        service="test_service",
        activation={"minSamplePeriodOverride": None},
        metrics=[{"gcpOptions": {"samplePeriod": 60, "valueType": "INT64"}}],
    )
    assert service.min_sample_period_override == 0
    assert service.metrics[0].sample_period_overridden is False


def test_gcp_service_handles_negative_override():
    service = GCPService(
        service="test_service",
        activation={"minSamplePeriodOverride": -100},
        metrics=[{"gcpOptions": {"samplePeriod": 60, "valueType": "INT64"}}],
    )
    assert service.min_sample_period_override == 0
    assert service.metrics[0].sample_period_overridden is False


def test_gcp_service_handles_missing_override_key():
    service = GCPService(
        service="test_service",
        activation={},
        metrics=[{"gcpOptions": {"samplePeriod": 60, "valueType": "INT64"}}],
    )
    assert service.min_sample_period_override == 0
    assert service.metrics[0].sample_period_overridden is False


# --- create_dimensions dimension emission tests ---


def test_create_dimensions_includes_override_dimension_when_overridden():
    context = MetricsContext(None, None, "", "", datetime.utcnow(), 0, "", "", False, False, None)
    metric = Metric(
        gcpOptions={"samplePeriod": 60, "valueType": "INT64"},
        min_sample_period_override=300,
    )
    time_series = {"metric": {}, "resource": {}}
    dt_dims_map = DtDimensionsMap()

    dims = create_dimensions(context, "test_service", time_series, dt_dims_map, metric)

    override_dims = [d for d in dims if d.name == "dt.min_sample_period_override"]
    assert len(override_dims) == 1
    assert override_dims[0].value == "300"


def test_create_dimensions_excludes_override_dimension_when_not_overridden():
    context = MetricsContext(None, None, "", "", datetime.utcnow(), 0, "", "", False, False, None)
    metric = Metric(
        gcpOptions={"samplePeriod": 600, "valueType": "INT64"},
        min_sample_period_override=300,
    )
    time_series = {"metric": {}, "resource": {}}
    dt_dims_map = DtDimensionsMap()

    dims = create_dimensions(context, "test_service", time_series, dt_dims_map, metric)

    override_dims = [d for d in dims if d.name == "dt.min_sample_period_override"]
    assert len(override_dims) == 0


def test_create_dimensions_excludes_override_dimension_when_no_override():
    context = MetricsContext(None, None, "", "", datetime.utcnow(), 0, "", "", False, False, None)
    metric = Metric(
        gcpOptions={"samplePeriod": 60, "valueType": "INT64"},
    )
    time_series = {"metric": {}, "resource": {}}
    dt_dims_map = DtDimensionsMap()

    dims = create_dimensions(context, "test_service", time_series, dt_dims_map, metric)

    override_dims = [d for d in dims if d.name == "dt.min_sample_period_override"]
    assert len(override_dims) == 0

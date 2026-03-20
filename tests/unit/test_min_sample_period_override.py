from datetime import timedelta

from lib.metrics import Metric, GCPService


def _make_metric(**overrides):
    """Create a Metric with sensible defaults; override any kwarg."""
    defaults = dict(
        name="test",
        value="metric:compute.googleapis.com/instance/cpu/utilization",
        key="cloud.gcp.compute_googleapis_com.instance.cpu.utilization",
        type="gauge",
        gcpOptions={"ingestDelay": 60, "samplePeriod": 60, "valueType": "DOUBLE", "metricKind": "GAUGE"},
        dimensions=[],
    )
    defaults.update(overrides)
    return Metric(**defaults)


# --- Metric-level tests ---

class TestMetricOverride:
    def test_no_override_keeps_extension_period(self):
        m = _make_metric()
        assert m.sample_period_seconds == timedelta(seconds=60)
        assert m.sample_period_overridden is False

    def test_override_larger_than_extension_applies(self):
        m = _make_metric(min_sample_period_override=300)
        assert m.sample_period_seconds == timedelta(seconds=300)
        assert m.sample_period_overridden is True

    def test_override_equal_to_extension_not_applied(self):
        m = _make_metric(min_sample_period_override=60)
        assert m.sample_period_seconds == timedelta(seconds=60)
        assert m.sample_period_overridden is False

    def test_override_smaller_than_extension_not_applied(self):
        m = _make_metric(min_sample_period_override=30)
        assert m.sample_period_seconds == timedelta(seconds=60)
        assert m.sample_period_overridden is False

    def test_override_zero_not_applied(self):
        m = _make_metric(min_sample_period_override=0)
        assert m.sample_period_seconds == timedelta(seconds=60)
        assert m.sample_period_overridden is False

    def test_override_negative_not_applied(self):
        m = _make_metric(min_sample_period_override=-100)
        assert m.sample_period_seconds == timedelta(seconds=60)
        assert m.sample_period_overridden is False

    def test_override_invalid_string_not_applied(self):
        m = _make_metric(min_sample_period_override="300s")
        assert m.sample_period_seconds == timedelta(seconds=60)
        assert m.sample_period_overridden is False

    def test_override_empty_string_not_applied(self):
        m = _make_metric(min_sample_period_override="")
        assert m.sample_period_seconds == timedelta(seconds=60)
        assert m.sample_period_overridden is False

    def test_override_none_not_applied(self):
        m = _make_metric(min_sample_period_override=None)
        assert m.sample_period_seconds == timedelta(seconds=60)
        assert m.sample_period_overridden is False


# --- GCPService-level tests ---

def _make_service(activation=None):
    """Create a GCPService with one metric."""
    return GCPService(
        service="test_service",
        featureSet="default_metrics",
        tech_name="N/A",
        dimensions=[],
        metrics=[
            dict(
                name="test",
                value="metric:compute.googleapis.com/instance/cpu/utilization",
                key="cloud.gcp.compute_googleapis_com.instance.cpu.utilization",
                type="gauge",
                gcpOptions={"ingestDelay": 60, "samplePeriod": 60, "valueType": "DOUBLE", "metricKind": "GAUGE"},
                dimensions=[],
            )
        ],
        activation=activation or {},
    )


class TestGCPServiceOverride:
    def test_no_activation_override(self):
        svc = _make_service()
        assert svc.min_sample_period_override == 0
        assert svc.metrics[0].sample_period_overridden is False

    def test_activation_override_applied(self):
        svc = _make_service(activation={"minSamplePeriodOverride": 300})
        assert svc.min_sample_period_override == 300
        assert svc.metrics[0].sample_period_seconds == timedelta(seconds=300)
        assert svc.metrics[0].sample_period_overridden is True

    def test_activation_override_string_value(self):
        svc = _make_service(activation={"minSamplePeriodOverride": "600"})
        assert svc.min_sample_period_override == 600
        assert svc.metrics[0].sample_period_seconds == timedelta(seconds=600)

    def test_activation_override_invalid_value_ignored(self):
        svc = _make_service(activation={"minSamplePeriodOverride": "abc"})
        assert svc.min_sample_period_override == 0
        assert svc.metrics[0].sample_period_overridden is False

    def test_activation_override_negative_ignored(self):
        svc = _make_service(activation={"minSamplePeriodOverride": -5})
        assert svc.min_sample_period_override == 0

    def test_activation_override_empty_string_ignored(self):
        svc = _make_service(activation={"minSamplePeriodOverride": ""})
        assert svc.min_sample_period_override == 0

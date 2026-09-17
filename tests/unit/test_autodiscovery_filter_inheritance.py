import asyncio
from datetime import datetime, timezone

import pytest

from lib.autodiscovery.models import AutodiscoveryResourceLinking
from lib.context import MetricsContext
from lib.metric_ingest import fetch_metric
from lib.metrics import AutodiscoveryGCPService, GCPService, Metric
from lib.utilities import NO_GROUPING_CATEGORY

FILTER_PARAM = "filter"


def _metric_dict(google_metric: str) -> dict:
    return {
        "key": f"cloud.gcp.test.{google_metric.replace('/', '.').replace('.', '_')}",
        "value": f"metric:{google_metric}",
        "type": "gauge",
        "dimensions": [],
        "gcpOptions": {"valueType": "INT64", "metricKind": "GAUGE", "samplePeriod": 60, "ingestDelay": 60},
    }


def _create_metric(google_metric: str, autodiscovered_metric: bool = True) -> Metric:
    return Metric(**_metric_dict(google_metric), autodiscovered_metric=autodiscovered_metric)


def _create_linked_service(name: str, own_metrics: list, filter_conditions: str = "") -> GCPService:
    return GCPService(
        service=name,
        featureSet="default",
        extension_name="dynatrace.test",
        gcpMonitoringFilter=filter_conditions,
        metrics=[_metric_dict(m) for m in own_metrics],
    )


def _create_autodiscovery_service(resource: str, metric: Metric, linked_service) -> AutodiscoveryGCPService:
    service = AutodiscoveryGCPService()
    linking = AutodiscoveryResourceLinking([linked_service], []) if linked_service else None
    service.set_metrics({resource: [metric]}, {resource: linking}, {})
    return service


class _FakeGcpResponse:
    def __init__(self, body=None):
        self.body = body or {}

    async def json(self):
        await asyncio.sleep(0)
        return self.body


class _FakeGcpSession:
    def __init__(self, response_body=None):
        self.params = None
        self.response_body = response_body

    async def request(self, _method, url, params, headers):
        await asyncio.sleep(0)
        _ = (url, headers)
        self.params = list(params)
        return _FakeGcpResponse(self.response_body)


def _make_context(gcp_session, log_recorder=None):
    context = MetricsContext(
        gcp_session, None, "owner", "token", datetime.now(timezone.utc), 60, "", "", False, False, None
    )
    if log_recorder is not None:
        context.log = lambda *args: log_recorder.append(args)
    return context


def _filter_param(gcp_session) -> str:
    return dict(gcp_session.params)[FILTER_PARAM]


@pytest.mark.asyncio
async def test_filter_inheritance_skips_metric_outside_linked_services_own_api():
    linked_service = _create_linked_service(
        "apigee_googleapis_com_Environment",
        own_metrics=["apigee.googleapis.com/environment/request_count"],
        filter_conditions='(resource.labels.env="staging")',
    )
    metric = _create_metric("logging.googleapis.com/user/Apigee-request-log")
    autodiscovery_service = _create_autodiscovery_service("apigee.googleapis.com/Environment", metric, linked_service)

    gcp_session = _FakeGcpSession()
    context = _make_context(gcp_session)

    await fetch_metric(context, "test-project", autodiscovery_service, metric, [], NO_GROUPING_CATEGORY)

    assert _filter_param(gcp_session) == f'metric.type = "{metric.google_metric}"'


@pytest.mark.asyncio
async def test_log_based_metric_not_filtered_by_apigee_environment_filter():
    linked_service = _create_linked_service(
        "apigee_googleapis_com_Environment",
        own_metrics=["apigee.googleapis.com/environment/request_count"],
        filter_conditions='(resource.labels.env="staging")',
    )
    metric = _create_metric("logging.googleapis.com/user/Apigee-response-count")
    autodiscovery_service = _create_autodiscovery_service("apigee.googleapis.com/Environment", metric, linked_service)

    gcp_session = _FakeGcpSession()
    context = _make_context(gcp_session)

    await fetch_metric(context, "test-project", autodiscovery_service, metric, [], NO_GROUPING_CATEGORY)

    filter_param = _filter_param(gcp_session)
    assert 'resource.labels.env' not in filter_param
    assert filter_param == f'metric.type = "{metric.google_metric}"'


@pytest.mark.asyncio
async def test_daq_21921_regression_same_api_autodiscovered_metric_still_inherits_filter():
    filter_conditions = 'resource.labels.env = one_of("test-env","uat","dev","pre-prod","sit","staging")'
    linked_service = _create_linked_service(
        "apigee_googleapis_com_Proxy",
        own_metrics=["apigee.googleapis.com/proxy/request_count"],
        filter_conditions=filter_conditions,
    )
    metric = _create_metric("apigee.googleapis.com/proxy/details")
    autodiscovery_service = _create_autodiscovery_service("apigee.googleapis.com/Proxy", metric, linked_service)

    gcp_session = _FakeGcpSession()
    context = _make_context(gcp_session)

    await fetch_metric(context, "test-project", autodiscovery_service, metric, [], NO_GROUPING_CATEGORY)

    filter_param = _filter_param(gcp_session)
    assert filter_param == f'metric.type = "{metric.google_metric}" {filter_conditions}'


@pytest.mark.asyncio
async def test_non_autodiscovered_metric_still_uses_own_service_filter():
    service = GCPService(
        service="apigee_googleapis_com_Environment",
        featureSet="default",
        extension_name="dynatrace.test",
        gcpMonitoringFilter='(resource.labels.env="staging")',
        metrics=[],
    )
    metric = _create_metric("apigee.googleapis.com/environment/request_count", autodiscovered_metric=False)

    gcp_session = _FakeGcpSession()
    context = _make_context(gcp_session)

    await fetch_metric(context, "test-project", service, metric, [], NO_GROUPING_CATEGORY)

    filter_param = _filter_param(gcp_session)
    assert filter_param == f'metric.type = "{metric.google_metric}" (resource.labels.env="staging")'


@pytest.mark.asyncio
async def test_logs_inherited_filter_when_applied():
    filter_conditions = 'resource.labels.env = one_of("test-env","uat","dev","pre-prod","sit","staging")'
    linked_service = _create_linked_service(
        "apigee_googleapis_com_Proxy",
        own_metrics=["apigee.googleapis.com/proxy/request_count"],
        filter_conditions=filter_conditions,
    )
    metric = _create_metric("apigee.googleapis.com/proxy/details")
    autodiscovery_service = _create_autodiscovery_service("apigee.googleapis.com/Proxy", metric, linked_service)

    gcp_session = _FakeGcpSession()
    log_calls = []
    context = _make_context(gcp_session, log_calls)

    await fetch_metric(context, "test-project", autodiscovery_service, metric, [], NO_GROUPING_CATEGORY)

    matching = [call for call in log_calls if metric.google_metric in call[-1] and linked_service.name in call[-1] and filter_conditions in call[-1]]
    assert len(matching) == 1


@pytest.mark.asyncio
async def test_logs_nothing_when_filter_not_inherited():
    linked_service = _create_linked_service(
        "apigee_googleapis_com_Environment",
        own_metrics=["apigee.googleapis.com/environment/request_count"],
        filter_conditions='(resource.labels.env="staging")',
    )
    metric = _create_metric("logging.googleapis.com/user/Apigee-request-log")
    autodiscovery_service = _create_autodiscovery_service("apigee.googleapis.com/Environment", metric, linked_service)

    gcp_session = _FakeGcpSession()
    log_calls = []
    context = _make_context(gcp_session, log_calls)

    await fetch_metric(context, "test-project", autodiscovery_service, metric, [], NO_GROUPING_CATEGORY)

    assert not any("inherits filter_conditions" in call[-1] for call in log_calls)


@pytest.mark.asyncio
async def test_zero_time_series_warning_emitted_when_filter_active():
    filter_conditions = 'resource.labels.env = one_of("test-env","uat","dev","pre-prod","sit","staging")'
    linked_service = _create_linked_service(
        "apigee_googleapis_com_Proxy",
        own_metrics=["apigee.googleapis.com/proxy/request_count"],
        filter_conditions=filter_conditions,
    )
    metric = _create_metric("apigee.googleapis.com/proxy/details")
    autodiscovery_service = _create_autodiscovery_service("apigee.googleapis.com/Proxy", metric, linked_service)

    gcp_session = _FakeGcpSession(response_body={})
    log_calls = []
    context = _make_context(gcp_session, log_calls)

    await fetch_metric(context, "test-project", autodiscovery_service, metric, [], NO_GROUPING_CATEGORY)

    matching = [call for call in log_calls if metric.google_metric in call[-1] and filter_conditions in call[-1] and "WARNING" in call[-1]]
    assert len(matching) == 1


@pytest.mark.asyncio
async def test_zero_time_series_warning_emitted_when_native_filter_active():
    filter_conditions = '(resource.labels.env="staging")'
    service = GCPService(
        service="apigee_googleapis_com_Environment",
        featureSet="default",
        extension_name="dynatrace.test",
        gcpMonitoringFilter=filter_conditions,
        metrics=[],
    )
    metric = _create_metric("apigee.googleapis.com/environment/request_count", autodiscovered_metric=False)

    gcp_session = _FakeGcpSession(response_body={})
    log_calls = []
    context = _make_context(gcp_session, log_calls)

    await fetch_metric(context, "test-project", service, metric, [], NO_GROUPING_CATEGORY)

    matching = [call for call in log_calls if metric.google_metric in call[-1] and filter_conditions in call[-1] and "WARNING" in call[-1]]
    assert len(matching) == 1


@pytest.mark.asyncio
async def test_zero_time_series_warning_not_emitted_when_no_filter_active():
    metric = _create_metric("logging.googleapis.com/user/Apigee-request-log")
    linked_service = _create_linked_service(
        "apigee_googleapis_com_Environment",
        own_metrics=["apigee.googleapis.com/environment/request_count"],
        filter_conditions='(resource.labels.env="staging")',
    )
    autodiscovery_service = _create_autodiscovery_service("apigee.googleapis.com/Environment", metric, linked_service)

    gcp_session = _FakeGcpSession(response_body={})
    log_calls = []
    context = _make_context(gcp_session, log_calls)

    await fetch_metric(context, "test-project", autodiscovery_service, metric, [], NO_GROUPING_CATEGORY)

    assert not any("WARNING" in call[-1] for call in log_calls)

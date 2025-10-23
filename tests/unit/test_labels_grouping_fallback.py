import os
import asyncio
from datetime import datetime, timedelta

import pytest

from lib.metric_ingest import fetch_metric
from lib.metrics import GCPService, Metric
from lib.context import MetricsContext


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    async def json(self):
        return self._payload


class FakeSession:
    def __init__(self):
        self.calls = []

    async def request(self, method, url, params=None, headers=None):
        # Record params for inspection
        self.calls.append({
            'method': method,
            'url': url,
            'params': list(params or []),
            'headers': dict(headers or {}),
        })

        group_fields = [p[1] for p in (params or []) if p[0] == 'aggregation.groupByFields']
        includes_user_env = any(isinstance(g, str) and g.startswith('metadata.user_labels.env') for g in group_fields)

        # Common point
        now = datetime.utcnow().replace(microsecond=0)
        end = now
        start = now - timedelta(minutes=1)
        point = {
            'interval': {
                'startTime': start.strftime('%Y-%m-%dT%H:%M:%SZ'),
                'endTime': end.strftime('%Y-%m-%dT%H:%M:%SZ'),
            },
            'value': {'int64Value': '1'},
        }

        if includes_user_env:
            # First pass: only labeled resource is returned
            ts = [{
                'metric': {
                    'type': 'pubsub.googleapis.com/subscription/num_undelivered_messages',
                    'labels': {},
                },
                'resource': {
                    'type': 'pubsub_subscription',
                    'labels': {'subscription_id': 'sub-labeled'},
                },
                'metadata': {
                    'userLabels': {'env': 'test'}
                },
                'valueType': 'INT64',
                'points': [point],
            }]
        else:
            # Second pass: unlabeled resource is returned
            ts = [{
                'metric': {
                    'type': 'pubsub.googleapis.com/subscription/num_undelivered_messages',
                    'labels': {},
                },
                'resource': {
                    'type': 'pubsub_subscription',
                    'labels': {'subscription_id': 'sub-unlabeled'},
                },
                'metadata': {},
                'valueType': 'INT64',
                'points': [point],
            }]

        return FakeResponse({'timeSeries': ts})


@pytest.mark.asyncio
async def test_labels_grouping_fallback_includes_unlabeled(monkeypatch):
    # Enable fallback behavior
    monkeypatch.setenv('LABELS_GROUPING_INCLUDE_UNLABELED', 'true')

    # Prepare minimal service and metric
    service = GCPService(
        service='pubsub_subscription',
        featureSet='default_metrics',
        dimensions=[{'key': 'subscription_id', 'value': 'resource.labels.subscription_id'}],
    )

    metric = Metric(
        name='num_undelivered_messages',
        key='gcp.pubsub.subscription.num_undelivered_messages',
        type='gauge',
        value='metric:pubsub.googleapis.com/subscription/num_undelivered_messages',
        gcpOptions={'metricKind': 'GAUGE', 'valueType': 'INT64', 'samplePeriod': 60, 'ingestDelay': 60},
        dimensions=[],
        autodiscovered_metric=False,
        description='',
    )

    fake_session = FakeSession()

    # Minimal MetricsContext
    ctx = MetricsContext(
        gcp_session=fake_session,
        dt_session=None,  # not used by fetch_metric
        project_id_owner='proj',
        token='t',
        execution_time=datetime.utcnow(),
        execution_interval_seconds=60,
        dynatrace_api_key='',
        dynatrace_url='http://dthost',
        print_metric_ingest_input=False,
        self_monitoring_enabled=False,
        scheduled_execution_id=None,
    )

    lines = await fetch_metric(
        context=ctx,
        project_id='proj',
        service=service,
        metric=metric,
        excluded_metrics_and_dimensions=[],
        grouping='env',
    )

    # Two lines expected: one labeled, one unlabeled
    assert len(lines) == 2
    # Ensure only the labeled one contains the 'env' dimension
    dims_per_line = [{d.name: d.value for d in l.dimension_values} for l in lines]
    has_env = [('env' in dims) for dims in dims_per_line]
    assert sorted(has_env) == [False, True]


class FakeSessionBothOnFallback(FakeSession):
    async def request(self, method, url, params=None, headers=None):
        res = await super().request(method, url, params=params, headers=headers)
        # When not including user env label, return both labeled and unlabeled
        group_fields = [p[1] for p in (params or []) if p[0] == 'aggregation.groupByFields']
        includes_user_env = any(isinstance(g, str) and g.startswith('metadata.user_labels.env') for g in group_fields)
        payload = await res.json()
        if not includes_user_env:
            # Append labeled series to simulate GCM returning all series (labeled + unlabeled)
            point = payload['timeSeries'][0]['points'][0]
            payload['timeSeries'].append({
                'metric': {
                    'type': 'pubsub.googleapis.com/subscription/num_undelivered_messages',
                    'labels': {},
                },
                'resource': {
                    'type': 'pubsub_subscription',
                    'labels': {'subscription_id': 'sub-labeled'},
                },
                'metadata': {
                    'userLabels': {'env': 'test'}
                },
                'valueType': 'INT64',
                'points': [point],
            })
        return FakeResponse(payload)


@pytest.mark.asyncio
async def test_labels_grouping_fallback_dedup_prefers_enriched(monkeypatch):
    # Enable fallback behavior
    monkeypatch.setenv('LABELS_GROUPING_INCLUDE_UNLABELED', 'true')

    service = GCPService(
        service='pubsub_subscription',
        featureSet='default_metrics',
        dimensions=[{'key': 'subscription_id', 'value': 'resource.labels.subscription_id'}],
    )
    metric = Metric(
        name='num_undelivered_messages',
        key='gcp.pubsub.subscription.num_undelivered_messages',
        type='gauge',
        value='metric:pubsub.googleapis.com/subscription/num_undelivered_messages',
        gcpOptions={'metricKind': 'GAUGE', 'valueType': 'INT64', 'samplePeriod': 60, 'ingestDelay': 60},
        dimensions=[],
        autodiscovered_metric=False,
        description='',
    )
    fake_session = FakeSessionBothOnFallback()
    ctx = MetricsContext(
        gcp_session=fake_session,
        dt_session=None,
        project_id_owner='proj',
        token='t',
        execution_time=datetime.utcnow(),
        execution_interval_seconds=60,
        dynatrace_api_key='',
        dynatrace_url='http://dthost',
        print_metric_ingest_input=False,
        self_monitoring_enabled=False,
        scheduled_execution_id=None,
    )
    lines = await fetch_metric(
        context=ctx,
        project_id='proj',
        service=service,
        metric=metric,
        excluded_metrics_and_dimensions=[],
        grouping='env',
    )
    # Expect only two lines (one labeled enriched + one unlabeled), not three
    assert len(lines) == 2
    dims_per_line = [{d.name: d.value for d in l.dimension_values} for l in lines]
    labeled = [dims for dims in dims_per_line if 'env' in dims]
    unlabeled = [dims for dims in dims_per_line if 'env' not in dims]
    assert len(labeled) == 1 and len(unlabeled) == 1


@pytest.mark.asyncio
async def test_labels_grouping_flag_disabled_drops_unlabeled(monkeypatch):
    # Disable fallback behavior
    monkeypatch.setenv('LABELS_GROUPING_INCLUDE_UNLABELED', 'false')

    service = GCPService(
        service='pubsub_subscription',
        featureSet='default_metrics',
        dimensions=[{'key': 'subscription_id', 'value': 'resource.labels.subscription_id'}],
    )
    metric = Metric(
        name='num_undelivered_messages',
        key='gcp.pubsub.subscription.num_undelivered_messages',
        type='gauge',
        value='metric:pubsub.googleapis.com/subscription/num_undelivered_messages',
        gcpOptions={'metricKind': 'GAUGE', 'valueType': 'INT64', 'samplePeriod': 60, 'ingestDelay': 60},
        dimensions=[],
        autodiscovered_metric=False,
        description='',
    )
    fake_session = FakeSessionBothOnFallback()
    ctx = MetricsContext(
        gcp_session=fake_session,
        dt_session=None,
        project_id_owner='proj',
        token='t',
        execution_time=datetime.utcnow(),
        execution_interval_seconds=60,
        dynatrace_api_key='',
        dynatrace_url='http://dthost',
        print_metric_ingest_input=False,
        self_monitoring_enabled=False,
        scheduled_execution_id=None,
    )
    lines = await fetch_metric(
        context=ctx,
        project_id='proj',
        service=service,
        metric=metric,
        excluded_metrics_and_dimensions=[],
        grouping='env',
    )
    # Without fallback: only labeled resource should be ingested
    assert len(lines) == 1
    dims = {d.name: d.value for d in lines[0].dimension_values}
    assert 'env' in dims


@pytest.mark.asyncio
async def test_no_grouping_no_fallback_single_pass(monkeypatch):
    # Ensure no second pass and no user label enrichment when grouping is NO_GROUPING
    monkeypatch.setenv('LABELS_GROUPING_INCLUDE_UNLABELED', 'true')

    service = GCPService(
        service='pubsub_subscription',
        featureSet='default_metrics',
        dimensions=[{'key': 'subscription_id', 'value': 'resource.labels.subscription_id'}],
    )
    metric = Metric(
        name='num_undelivered_messages',
        key='gcp.pubsub.subscription.num_undelivered_messages',
        type='gauge',
        value='metric:pubsub.googleapis.com/subscription/num_undelivered_messages',
        gcpOptions={'metricKind': 'GAUGE', 'valueType': 'INT64', 'samplePeriod': 60, 'ingestDelay': 60},
        dimensions=[],
        autodiscovered_metric=False,
        description='',
    )
    fake_session = FakeSessionBothOnFallback()
    ctx = MetricsContext(
        gcp_session=fake_session,
        dt_session=None,
        project_id_owner='proj',
        token='t',
        execution_time=datetime.utcnow(),
        execution_interval_seconds=60,
        dynatrace_api_key='',
        dynatrace_url='http://dthost',
        print_metric_ingest_input=False,
        self_monitoring_enabled=False,
        scheduled_execution_id=None,
    )
    lines = await fetch_metric(
        context=ctx,
        project_id='proj',
        service=service,
        metric=metric,
        excluded_metrics_and_dimensions=[],
        grouping='NO_GROUPING',
    )
    # Only one request should have been made (single pass)
    assert len(fake_session.calls) == 1
    # And since no user label was requested, line has no 'env'
    dims = {d.name: d.value for d in lines[0].dimension_values}
    assert 'env' not in dims

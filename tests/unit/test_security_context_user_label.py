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
from datetime import datetime, timezone

import pytest

from lib import metric_ingest
from lib.metric_ingest import fetch_metric
from lib.metrics import GCPService, Metric
from lib.context import MetricsContext
from lib.utilities import NO_GROUPING_CATEGORY

TEST_METRIC = "cloudsql.googleapis.com/database/cpu/utilization"
GROUPING_LABEL = "example_label"
GROUPING = GROUPING_LABEL
DEFAULT_SECURITY_CONTEXT = "default-context"


def _time_series(database_id, user_labels=None):
    series = {
        "valueType": "INT64",
        "metric": {"labels": {}},
        "resource": {"type": "cloudsql_database", "labels": {"database_id": database_id}},
        "points": [
            {"interval": {"endTime": "2024-01-01T00:01:00Z"}, "value": {"int64Value": "1"}}
        ],
    }
    if user_labels is not None:
        series["metadata"] = {"userLabels": user_labels}
    return series


class _FakeGcpResponse:
    def __init__(self, body):
        self.body = body

    async def json(self):
        await asyncio.sleep(0)
        return self.body


class _RecordingGcpSession:
    """Returns a queued body per request and records the params of each call."""

    def __init__(self, bodies):
        self.bodies = list(bodies)
        self.calls = []

    async def request(self, _method, url, params, headers):
        await asyncio.sleep(0)
        _ = (url, headers)
        self.calls.append(list(params))
        body = self.bodies.pop(0) if self.bodies else {}
        return _FakeGcpResponse(body)


def _context(session):
    return MetricsContext(
        session, None, "owner", "token", datetime.now(timezone.utc), 60, "", "", False, False, None
    )


def _metric():
    return Metric(
        name="CPU utilization",
        value=f"metric:{TEST_METRIC}",
        key="cloud.gcp.cloudsql_googleapis_com.database.cpu.utilization",
        type="gauge",
        gcpOptions={"ingestDelay": 0, "samplePeriod": 60, "valueType": "INT64", "metricKind": "GAUGE"},
        dimensions=[],
    )


async def _fetch(session, grouping):
    return await fetch_metric(
        _context(session),
        "test-project",
        GCPService(service="cloudsql_database", dimensions=[], metrics=[]),
        _metric(),
        [],
        grouping,
    )


def _group_by_labels(params):
    return [value for key, value in params if key == "aggregation.groupByFields"]


def _security_contexts(lines):
    return [
        dimension.value
        for line in lines
        for dimension in line.dimension_values
        if dimension.name == "dt.security_context"
    ]


# --- Commit 1: backfill ---

@pytest.mark.asyncio
async def test_grouped_fetch_backfills_resource_missing_the_label():
    # Grouped pass returns only the labelled resource; GCP omits the unlabelled one.
    grouped = {"timeSeries": [_time_series("labelled-db", {GROUPING_LABEL: "1234567"})]}
    ungrouped = {"timeSeries": [_time_series("labelled-db"), _time_series("unlabelled-db")]}
    session = _RecordingGcpSession([grouped, ungrouped])

    lines = await _fetch(session, GROUPING)

    assert len(session.calls) == 2
    assert _group_by_labels(session.calls[0]) == [f"metadata.user_labels.{GROUPING_LABEL}"]
    assert _group_by_labels(session.calls[1]) == []
    # Both resources ingested, the unlabelled one exactly once.
    assert len(lines) == 2


@pytest.mark.asyncio
async def test_grouped_fetch_does_not_duplicate_labelled_resources():
    # Every resource is labelled, so the backfill pass returns nothing new.
    series = _time_series("labelled-db", {GROUPING_LABEL: "1234567"})
    session = _RecordingGcpSession([{"timeSeries": [series]}, {"timeSeries": [_time_series("labelled-db")]}])

    lines = await _fetch(session, GROUPING)

    assert len(session.calls) == 2
    assert len(lines) == 1


@pytest.mark.asyncio
async def test_ungrouped_service_makes_a_single_request():
    session = _RecordingGcpSession([{"timeSeries": [_time_series("some-db")]}])

    lines = await _fetch(session, NO_GROUPING_CATEGORY)

    assert len(session.calls) == 1
    assert _group_by_labels(session.calls[0]) == []
    assert len(lines) == 1


# --- Commit 2: dt.security_context from the user label ---

@pytest.mark.asyncio
async def test_security_context_taken_from_user_label(monkeypatch):
    monkeypatch.setattr(metric_ingest, "DT_SECURITY_CONTEXT_USER_LABEL", GROUPING_LABEL)
    monkeypatch.setattr(metric_ingest, "DT_SECURITY_CONTEXT_VALUE", DEFAULT_SECURITY_CONTEXT)
    session = _RecordingGcpSession([
        {"timeSeries": [_time_series("labelled-db", {GROUPING_LABEL: "1234567"})]},
        {"timeSeries": []},
    ])

    lines = await _fetch(session, GROUPING)

    assert _security_contexts(lines) == ["1234567"]


@pytest.mark.asyncio
async def test_backfilled_resource_falls_back_to_default_security_context(monkeypatch):
    monkeypatch.setattr(metric_ingest, "DT_SECURITY_CONTEXT_USER_LABEL", GROUPING_LABEL)
    monkeypatch.setattr(metric_ingest, "DT_SECURITY_CONTEXT_VALUE", DEFAULT_SECURITY_CONTEXT)
    session = _RecordingGcpSession([
        {"timeSeries": []},
        {"timeSeries": [_time_series("unlabelled-db")]},
    ])

    lines = await _fetch(session, GROUPING)

    assert _security_contexts(lines) == [DEFAULT_SECURITY_CONTEXT]


@pytest.mark.asyncio
async def test_security_context_unchanged_when_label_not_configured(monkeypatch):
    monkeypatch.setattr(metric_ingest, "DT_SECURITY_CONTEXT_USER_LABEL", "")
    monkeypatch.setattr(metric_ingest, "DT_SECURITY_CONTEXT_VALUE", DEFAULT_SECURITY_CONTEXT)
    session = _RecordingGcpSession([
        {"timeSeries": [_time_series("labelled-db", {GROUPING_LABEL: "1234567"})]},
    ])

    lines = await _fetch(session, NO_GROUPING_CATEGORY)

    assert _security_contexts(lines) == [DEFAULT_SECURITY_CONTEXT]

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
from lib.configuration import config
from lib.metric_ingest import fetch_metric
from lib.metrics import GCPService, Metric
from lib.context import MetricsContext
from lib.utilities import NO_GROUPING_CATEGORY

TEST_METRIC = "cloudsql.googleapis.com/database/cpu/utilization"
GROUPING_LABEL = "example_label"
GROUPING = GROUPING_LABEL
SECURITY_CONTEXT_LABEL = "owner"
DEFAULT_SECURITY_CONTEXT = "default-context"


@pytest.fixture(autouse=True)
def _defaults(monkeypatch):
    # Module-level constants are read from the environment at import time; pin them per test.
    monkeypatch.setattr(metric_ingest, "DT_SECURITY_CONTEXT_VALUE", DEFAULT_SECURITY_CONTEXT)
    monkeypatch.setattr(metric_ingest, "DT_SECURITY_CONTEXT_USER_LABEL", "")
    monkeypatch.setattr(metric_ingest, "INCLUDE_RESOURCES_WITHOUT_GROUPING_LABELS", False)


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


def _metric(metric_kind="GAUGE"):
    return Metric(
        name="CPU utilization",
        value=f"metric:{TEST_METRIC}",
        key="cloud.gcp.cloudsql_googleapis_com.database.cpu.utilization",
        type="gauge",
        gcpOptions={"ingestDelay": 0, "samplePeriod": 60, "valueType": "INT64", "metricKind": metric_kind},
        dimensions=[],
    )


async def _fetch(session, grouping, metric_kind="GAUGE"):
    return await fetch_metric(
        _context(session),
        "test-project",
        GCPService(service="cloudsql_database", dimensions=[], metrics=[]),
        _metric(metric_kind),
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


# --- Backward compatibility: nothing configured behaves as before ---

@pytest.mark.asyncio
async def test_ungrouped_service_makes_a_single_request():
    session = _RecordingGcpSession([{"timeSeries": [_time_series("some-db")]}])

    lines = await _fetch(session, NO_GROUPING_CATEGORY)

    assert len(session.calls) == 1
    assert _group_by_labels(session.calls[0]) == []
    assert _security_contexts(lines) == [DEFAULT_SECURITY_CONTEXT]


@pytest.mark.asyncio
async def test_grouped_service_without_backfill_makes_a_single_request():
    # LABELS_GROUPING_BY_SERVICE alone keeps the previous single-pass behaviour.
    session = _RecordingGcpSession([{"timeSeries": [_time_series("labelled-db", {GROUPING_LABEL: "x"})]}])

    lines = await _fetch(session, GROUPING)

    assert len(session.calls) == 1
    assert _group_by_labels(session.calls[0]) == [f"metadata.user_labels.{GROUPING_LABEL}"]
    assert len(lines) == 1


# --- INCLUDE_RESOURCES_WITHOUT_GROUPING_LABELS: backfill for explicit groupings ---

@pytest.mark.asyncio
async def test_backfill_ingests_resource_missing_the_grouping_label(monkeypatch):
    monkeypatch.setattr(metric_ingest, "INCLUDE_RESOURCES_WITHOUT_GROUPING_LABELS", True)
    # Grouped pass returns only the labelled resource; GCP omits the unlabelled one.
    grouped = {"timeSeries": [_time_series("labelled-db", {GROUPING_LABEL: "1234567"})]}
    ungrouped = {"timeSeries": [_time_series("labelled-db"), _time_series("unlabelled-db")]}
    session = _RecordingGcpSession([grouped, ungrouped])

    lines = await _fetch(session, GROUPING)

    assert len(session.calls) == 2
    assert _group_by_labels(session.calls[0]) == [f"metadata.user_labels.{GROUPING_LABEL}"]
    assert _group_by_labels(session.calls[1]) == []
    # Both resources ingested, the labelled one exactly once.
    assert len(lines) == 2


@pytest.mark.asyncio
async def test_backfill_does_not_duplicate_labelled_resources(monkeypatch):
    monkeypatch.setattr(metric_ingest, "INCLUDE_RESOURCES_WITHOUT_GROUPING_LABELS", True)
    series = _time_series("labelled-db", {GROUPING_LABEL: "1234567"})
    session = _RecordingGcpSession([{"timeSeries": [series]}, {"timeSeries": [_time_series("labelled-db")]}])

    lines = await _fetch(session, GROUPING)

    assert len(session.calls) == 2
    assert len(lines) == 1


@pytest.mark.asyncio
async def test_backfill_is_skipped_for_cumulative_metrics(monkeypatch):
    # REDUCE_NONE ignores groupByFields, so the second pass would return the very same series.
    monkeypatch.setattr(metric_ingest, "INCLUDE_RESOURCES_WITHOUT_GROUPING_LABELS", True)
    session = _RecordingGcpSession([{"timeSeries": [_time_series("some-db")]}])

    lines = await _fetch(session, GROUPING, metric_kind="CUMULATIVE")

    assert len(session.calls) == 1
    assert ("aggregation.crossSeriesReducer", "REDUCE_NONE") in session.calls[0]
    assert len(lines) == 1


@pytest.mark.asyncio
async def test_unmatched_grouping_label_is_reported_once_per_project(monkeypatch, capsys):
    # Grouped pass matches nothing (for example a misspelled label), backfill returns everything.
    monkeypatch.setattr(metric_ingest, "INCLUDE_RESOURCES_WITHOUT_GROUPING_LABELS", True)
    monkeypatch.setattr(metric_ingest, "_REPORTED_UNMATCHED_GROUPINGS", set())
    bodies = [{"timeSeries": []}, {"timeSeries": [_time_series("some-db")]}]

    lines = await _fetch(_RecordingGcpSession(bodies), GROUPING)
    await _fetch(_RecordingGcpSession(bodies), GROUPING)

    assert _security_contexts(lines) == [DEFAULT_SECURITY_CONTEXT]
    assert capsys.readouterr().out.count(f"No resource carries the user label(s) '{GROUPING_LABEL}'") == 1


@pytest.mark.asyncio
async def test_metric_without_any_data_is_not_reported(monkeypatch, capsys):
    monkeypatch.setattr(metric_ingest, "INCLUDE_RESOURCES_WITHOUT_GROUPING_LABELS", True)
    monkeypatch.setattr(metric_ingest, "_REPORTED_UNMATCHED_GROUPINGS", set())

    lines = await _fetch(_RecordingGcpSession([{"timeSeries": []}, {"timeSeries": []}]), GROUPING)

    assert lines == []
    assert "No resource carries" not in capsys.readouterr().out


# --- DT_SECURITY_CONTEXT_USER_LABEL: dt.security_context from the resource's user label ---

@pytest.mark.asyncio
async def test_security_context_label_is_added_to_group_by_and_backfilled(monkeypatch):
    monkeypatch.setattr(metric_ingest, "DT_SECURITY_CONTEXT_USER_LABEL", SECURITY_CONTEXT_LABEL)
    grouped = {"timeSeries": [_time_series("labelled-db", {SECURITY_CONTEXT_LABEL: "team-a"})]}
    ungrouped = {"timeSeries": [_time_series("labelled-db"), _time_series("unlabelled-db")]}
    session = _RecordingGcpSession([grouped, ungrouped])

    lines = await _fetch(session, NO_GROUPING_CATEGORY)

    assert len(session.calls) == 2
    assert _group_by_labels(session.calls[0]) == [f"metadata.user_labels.{SECURITY_CONTEXT_LABEL}"]
    assert _group_by_labels(session.calls[1]) == []
    assert sorted(_security_contexts(lines)) == sorted(["team-a", DEFAULT_SECURITY_CONTEXT])


@pytest.mark.asyncio
async def test_security_context_label_is_not_added_twice_when_already_grouped(monkeypatch):
    monkeypatch.setattr(metric_ingest, "DT_SECURITY_CONTEXT_USER_LABEL", SECURITY_CONTEXT_LABEL)
    session = _RecordingGcpSession([{"timeSeries": []}, {"timeSeries": []}])

    await _fetch(session, f"{GROUPING_LABEL},{SECURITY_CONTEXT_LABEL}")

    assert _group_by_labels(session.calls[0]) == [
        f"metadata.user_labels.{GROUPING_LABEL}",
        f"metadata.user_labels.{SECURITY_CONTEXT_LABEL}",
    ]


@pytest.mark.asyncio
async def test_security_context_label_is_ignored_for_cumulative_metrics(monkeypatch):
    # GCP does not return metadata for REDUCE_NONE, so there is nothing to derive it from.
    monkeypatch.setattr(metric_ingest, "DT_SECURITY_CONTEXT_USER_LABEL", SECURITY_CONTEXT_LABEL)
    session = _RecordingGcpSession([{"timeSeries": [_time_series("some-db")]}])

    lines = await _fetch(session, NO_GROUPING_CATEGORY, metric_kind="CUMULATIVE")

    assert len(session.calls) == 1
    assert _group_by_labels(session.calls[0]) == []
    assert _security_contexts(lines) == [DEFAULT_SECURITY_CONTEXT]


@pytest.mark.asyncio
async def test_resources_in_one_project_map_to_their_own_security_context(monkeypatch):
    """Two teams own same-typed resources in one project, and a third resource is unlabelled.

    Each labelled resource must carry its own security context; the unlabelled one must still
    be ingested, under the deployment-wide default.
    """
    monkeypatch.setattr(metric_ingest, "DT_SECURITY_CONTEXT_USER_LABEL", SECURITY_CONTEXT_LABEL)
    grouped = {"timeSeries": [
        _time_series("db-alpha", {SECURITY_CONTEXT_LABEL: "12345"}),
        _time_series("db-beta", {SECURITY_CONTEXT_LABEL: "7801234"}),
    ]}
    ungrouped = {"timeSeries": [
        _time_series("db-alpha"),
        _time_series("db-beta"),
        _time_series("db-gamma"),
    ]}
    session = _RecordingGcpSession([grouped, ungrouped])

    lines = await _fetch(session, NO_GROUPING_CATEGORY)

    by_database = {
        next(d.value for d in line.dimension_values if d.name == "database_id"):
            next(d.value for d in line.dimension_values if d.name == "dt.security_context")
        for line in lines
    }
    assert by_database == {
        "db-alpha": "12345",
        "db-beta": "7801234",
        "db-gamma": DEFAULT_SECURITY_CONTEXT,
    }
    assert len(lines) == 3
    gamma = next(l for l in lines if any(d.value == "db-gamma" for d in l.dimension_values))
    assert not any(d.name == SECURITY_CONTEXT_LABEL for d in gamma.dimension_values)


# --- The default is the unchanged pre-existing constant ---

def test_blank_security_context_still_falls_back_to_the_project_id(monkeypatch):
    """The fallback chain is untouched: DT_SECURITY_CONTEXT, else the project id."""
    monkeypatch.delenv("DT_SECURITY_CONTEXT", raising=False)
    monkeypatch.setenv("GCP_PROJECT", "example-project")

    assert config.get_dt_security_context_value() == "example-project"


def test_configured_security_context_takes_precedence_over_the_project_id(monkeypatch):
    monkeypatch.setenv("DT_SECURITY_CONTEXT", "1000000")
    monkeypatch.setenv("GCP_PROJECT", "example-project")

    assert config.get_dt_security_context_value() == "1000000"


def test_new_settings_default_to_disabled(monkeypatch):
    monkeypatch.delenv("DT_SECURITY_CONTEXT_USER_LABEL", raising=False)
    monkeypatch.delenv("INCLUDE_RESOURCES_WITHOUT_GROUPING_LABELS", raising=False)

    assert config.dt_security_context_user_label() == ""
    assert config.include_resources_without_grouping_labels() is False

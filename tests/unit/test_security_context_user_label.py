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

import main
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
    monkeypatch.setattr(metric_ingest, "_REPORTED_UNMATCHED_GROUPINGS", set())


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
    """Queue responses, or route them by (group-by fields, page token) for concurrent queries."""

    def __init__(self, bodies):
        self.bodies = dict(bodies) if isinstance(bodies, dict) else list(bodies)
        self.calls = []

    async def request(self, _method, url, params, headers):
        await asyncio.sleep(0)
        _ = (url, headers)
        self.calls.append(list(params))
        if isinstance(self.bodies, dict):
            body = self.bodies.pop((tuple(_group_by_labels(params)), dict(params).get("pageToken")))
        else:
            body = self.bodies.pop(0)
        if isinstance(body, BaseException):
            raise body
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


async def _fetch(session, groupings, metric_kind="GAUGE"):
    return await fetch_metric(
        _context(session),
        "test-project",
        GCPService(service="cloudsql_database", dimensions=[], metrics=[]),
        _metric(metric_kind),
        [],
        groupings,
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

    lines = await _fetch(session, [NO_GROUPING_CATEGORY])

    assert len(session.calls) == 1
    assert _group_by_labels(session.calls[0]) == []
    assert _security_contexts(lines) == [DEFAULT_SECURITY_CONTEXT]


@pytest.mark.asyncio
async def test_grouped_service_without_backfill_makes_a_single_request():
    # LABELS_GROUPING_BY_SERVICE alone keeps the previous single-pass behaviour.
    session = _RecordingGcpSession([{"timeSeries": [_time_series("labelled-db", {GROUPING_LABEL: "x"})]}])

    lines = await _fetch(session, [GROUPING])

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

    lines = await _fetch(session, [GROUPING])

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

    lines = await _fetch(session, [GROUPING])

    assert len(session.calls) == 2
    assert len(lines) == 1


@pytest.mark.asyncio
async def test_backfill_is_skipped_for_cumulative_metrics(monkeypatch):
    # REDUCE_NONE ignores groupByFields, so the second pass would return the very same series.
    monkeypatch.setattr(metric_ingest, "INCLUDE_RESOURCES_WITHOUT_GROUPING_LABELS", True)
    session = _RecordingGcpSession([{"timeSeries": [_time_series("some-db")]}])

    lines = await _fetch(session, [GROUPING], metric_kind="CUMULATIVE")

    assert len(session.calls) == 1
    assert ("aggregation.crossSeriesReducer", "REDUCE_NONE") in session.calls[0]
    assert len(lines) == 1


@pytest.mark.asyncio
async def test_unmatched_grouping_label_is_reported_once_per_project(monkeypatch, capsys):
    # Grouped pass matches nothing (for example a misspelled label), backfill returns everything.
    monkeypatch.setattr(metric_ingest, "INCLUDE_RESOURCES_WITHOUT_GROUPING_LABELS", True)
    monkeypatch.setattr(metric_ingest, "_REPORTED_UNMATCHED_GROUPINGS", set())
    bodies = [{"timeSeries": []}, {"timeSeries": [_time_series("some-db")]}]

    lines = await _fetch(_RecordingGcpSession(bodies), [GROUPING])
    await _fetch(_RecordingGcpSession(bodies), [GROUPING])

    assert _security_contexts(lines) == [DEFAULT_SECURITY_CONTEXT]
    assert capsys.readouterr().out.count(f"No time series matched any user-label grouping in ['{GROUPING_LABEL}']") == 1


@pytest.mark.asyncio
async def test_metric_without_any_data_is_not_reported(monkeypatch, capsys):
    monkeypatch.setattr(metric_ingest, "INCLUDE_RESOURCES_WITHOUT_GROUPING_LABELS", True)
    monkeypatch.setattr(metric_ingest, "_REPORTED_UNMATCHED_GROUPINGS", set())

    lines = await _fetch(_RecordingGcpSession([{"timeSeries": []}, {"timeSeries": []}]), [GROUPING])

    assert lines == []
    assert "No time series matched" not in capsys.readouterr().out


# --- DT_SECURITY_CONTEXT_USER_LABEL: dt.security_context from the resource's user label ---

@pytest.mark.asyncio
async def test_security_context_label_is_added_to_group_by_and_backfilled(monkeypatch):
    monkeypatch.setattr(metric_ingest, "DT_SECURITY_CONTEXT_USER_LABEL", SECURITY_CONTEXT_LABEL)
    grouped = {"timeSeries": [_time_series("labelled-db", {SECURITY_CONTEXT_LABEL: "team-a"})]}
    ungrouped = {"timeSeries": [_time_series("labelled-db"), _time_series("unlabelled-db")]}
    session = _RecordingGcpSession([grouped, ungrouped])

    lines = await _fetch(session, [NO_GROUPING_CATEGORY])

    assert len(session.calls) == 2
    assert _group_by_labels(session.calls[0]) == [f"metadata.user_labels.{SECURITY_CONTEXT_LABEL}"]
    assert _group_by_labels(session.calls[1]) == []
    assert sorted(_security_contexts(lines)) == sorted(["team-a", DEFAULT_SECURITY_CONTEXT])


@pytest.mark.asyncio
async def test_security_context_label_is_not_added_twice_when_already_grouped(monkeypatch):
    monkeypatch.setattr(metric_ingest, "DT_SECURITY_CONTEXT_USER_LABEL", SECURITY_CONTEXT_LABEL)
    session = _RecordingGcpSession([{"timeSeries": []}, {"timeSeries": []}])

    await _fetch(session, [f"{GROUPING_LABEL},{SECURITY_CONTEXT_LABEL}"])

    assert _group_by_labels(session.calls[0]) == [
        f"metadata.user_labels.{GROUPING_LABEL}",
        f"metadata.user_labels.{SECURITY_CONTEXT_LABEL}",
    ]


@pytest.mark.asyncio
async def test_security_context_label_is_ignored_for_cumulative_metrics(monkeypatch):
    # GCP does not return metadata for REDUCE_NONE, so there is nothing to derive it from.
    monkeypatch.setattr(metric_ingest, "DT_SECURITY_CONTEXT_USER_LABEL", SECURITY_CONTEXT_LABEL)
    session = _RecordingGcpSession([{"timeSeries": [_time_series("some-db")]}])

    lines = await _fetch(session, [NO_GROUPING_CATEGORY], metric_kind="CUMULATIVE")

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

    lines = await _fetch(session, [NO_GROUPING_CATEGORY])

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


@pytest.mark.asyncio
@pytest.mark.parametrize("groupings", [["team", "squad"], ["squad", "team"]])
@pytest.mark.parametrize("security_context", [False, True])
async def test_multiple_groupings_share_one_backfill(monkeypatch, groupings, security_context):
    monkeypatch.setattr(metric_ingest, "INCLUDE_RESOURCES_WITHOUT_GROUPING_LABELS", not security_context)
    owner_labels = {"owner": "team-owner"} if security_context else {}
    if security_context:
        monkeypatch.setattr(metric_ingest, "DT_SECURITY_CONTEXT_USER_LABEL", "owner")
    bodies = {}
    for label in groupings:
        fields = ("resource.labels.database_id", f"metadata.user_labels.{label}")
        if security_context:
            fields += ("metadata.user_labels.owner",)
        bodies[(fields, None)] = {"timeSeries": [
            _time_series(label, {label: "x", **owner_labels}),
            _time_series("both", {label: "x", **owner_labels}),
        ]}
    bodies[(("resource.labels.database_id",), None)] = {
        "timeSeries": [_time_series(db) for db in ("team", "squad", "both", "neither")],
    }
    session = _RecordingGcpSession(bodies)

    # Exercise the real scheduler, not a copy of its grouping logic.
    monkeypatch.setattr(main.config, "scoping_project_support_enabled", lambda: True)
    monkeypatch.setattr(main, "read_labels_grouping_by_service_yaml", lambda: [
        {"service": "cloudsql_database", "groupings": groupings}
    ])
    service = GCPService(service="cloudsql_database", dimensions=[
        {"key": "database_id", "value": "label:resource.labels.database_id"},
    ], metrics=[])
    service.metrics.append(_metric())
    lines = await main.fetch_ingest_lines_task(_context(session), "test-project", [service], set(), [])

    assert len(session.calls) == 3
    assert _group_by_labels(session.calls[-1]) == ["resource.labels.database_id"]
    assert not session.bodies
    by_resource = {}
    for line in lines:
        database_id = next(d.value for d in line.dimension_values if d.name == "database_id")
        by_resource.setdefault(database_id, []).append(line)
    assert {db: len(values) for db, values in by_resource.items()} == {
        "team": 1, "squad": 1, "both": 2, "neither": 1,
    }
    for label in groupings:
        assert any(d.name == label for d in by_resource[label][0].dimension_values)
        assert _security_contexts(by_resource[label]) == ["team-owner" if security_context else DEFAULT_SECURITY_CONTEXT]
    assert _security_contexts(by_resource["neither"]) == [DEFAULT_SECURITY_CONTEXT]


@pytest.mark.asyncio
async def test_shared_backfill_waits_for_all_pages_and_has_its_own_page_tokens(monkeypatch):
    monkeypatch.setattr(metric_ingest, "INCLUDE_RESOURCES_WITHOUT_GROUPING_LABELS", True)
    session = _RecordingGcpSession({
        (("metadata.user_labels.team",), None): {"nextPageToken": "team-page-2"},
        (("metadata.user_labels.team",), "team-page-2"): {
            "timeSeries": [_time_series("team-db", {"team": "a"})],
        },
        (("metadata.user_labels.squad",), None): {"nextPageToken": "squad-page-2"},
        (("metadata.user_labels.squad",), "squad-page-2"): {
            "timeSeries": [_time_series("squad-db", {"squad": "b"})],
        },
        ((), None): {
            "timeSeries": [_time_series("team-db"), _time_series("unlabelled-db")],
            "nextPageToken": "backfill-page-2",
        },
        ((), "backfill-page-2"): {"timeSeries": [_time_series("squad-db"), _time_series("other-db")]},
    })

    lines = await _fetch(session, ["team", "squad"])

    assert len(session.calls) == 6
    assert all(_group_by_labels(params) for params in session.calls[:4])
    assert all(not _group_by_labels(params) for params in session.calls[4:])
    assert "pageToken" not in dict(session.calls[4])
    assert not session.bodies
    assert sorted(d.value for line in lines for d in line.dimension_values if d.name == "database_id") == [
        "other-db", "squad-db", "team-db", "unlabelled-db",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("metric_kind,backfill", [("GAUGE", False), ("CUMULATIVE", True)])
async def test_multiple_groupings_keep_existing_queries_without_backfill(monkeypatch, metric_kind, backfill):
    monkeypatch.setattr(metric_ingest, "INCLUDE_RESOURCES_WITHOUT_GROUPING_LABELS", backfill)
    session = _RecordingGcpSession([
        {"timeSeries": [_time_series("db", {"team": "a"})]},
        {"timeSeries": [_time_series("db", {"squad": "b"})]},
    ])

    lines = await _fetch(session, ["team", "squad"], metric_kind=metric_kind)

    assert len(session.calls) == 2
    assert [_group_by_labels(params) for params in session.calls] == [
        ["metadata.user_labels.team"], ["metadata.user_labels.squad"],
    ]
    assert len(lines) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("failed_grouping", ["team", "squad"])
async def test_failed_grouping_keeps_successful_results_but_prevents_backfill(monkeypatch, capsys, failed_grouping):
    monkeypatch.setattr(metric_ingest, "DT_SECURITY_CONTEXT_USER_LABEL", "owner")
    bodies = {}
    for label in ("team", "squad"):
        fields = (f"metadata.user_labels.{label}", "metadata.user_labels.owner")
        bodies[(fields, None)] = {
            "timeSeries": [_time_series(label, {label: "x", "owner": "team-owner"})],
        }
        if label == failed_grouping:
            bodies[(fields, None)]["nextPageToken"] = "failed-page"
            bodies[(fields, "failed-page")] = {"error": {"code": 503, "message": "unavailable"}}
    session = _RecordingGcpSession(bodies)

    lines = await _fetch(session, ["team", "squad"])

    assert len(session.calls) == 3
    assert all(_group_by_labels(params) for params in session.calls)
    assert len(lines) == 1
    assert _security_contexts(lines) == ["team-owner"]
    assert not any(d.value == failed_grouping for d in lines[0].dimension_values)
    assert "Failed to fetch" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_failed_backfill_keeps_grouped_results(monkeypatch, capsys):
    monkeypatch.setattr(metric_ingest, "INCLUDE_RESOURCES_WITHOUT_GROUPING_LABELS", True)
    session = _RecordingGcpSession([
        {"timeSeries": [_time_series("team-db", {"team": "a"})]},
        {"timeSeries": [_time_series("squad-db", {"squad": "b"})]},
        {"error": {"code": 503, "message": "unavailable"}},
    ])

    lines = await _fetch(session, ["team", "squad"])

    assert len(session.calls) == 3
    assert len(lines) == 2
    assert "Failed to backfill" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_explicit_ungrouped_query_needs_no_additional_backfill(monkeypatch):
    monkeypatch.setattr(metric_ingest, "INCLUDE_RESOURCES_WITHOUT_GROUPING_LABELS", True)
    session = _RecordingGcpSession([
        {"timeSeries": []},
        {"timeSeries": [_time_series("unlabelled-db")]},
    ])

    lines = await _fetch(session, ["team", NO_GROUPING_CATEGORY])

    assert len(session.calls) == 2
    assert len(lines) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel_backfill", [False, True])
async def test_query_cancellation_propagates(monkeypatch, cancel_backfill):
    monkeypatch.setattr(metric_ingest, "INCLUDE_RESOURCES_WITHOUT_GROUPING_LABELS", True)
    bodies = [{"timeSeries": []}, {"timeSeries": []}, asyncio.CancelledError()] if cancel_backfill else [
        asyncio.CancelledError(), {"timeSeries": []},
    ]
    session = _RecordingGcpSession(bodies)

    with pytest.raises(asyncio.CancelledError):
        await _fetch(session, ["team", "squad"])

    assert len(session.calls) == (3 if cancel_backfill else 2)


@pytest.mark.asyncio
async def test_parent_cancellation_stops_all_grouped_queries(monkeypatch):
    monkeypatch.setattr(metric_ingest, "INCLUDE_RESOURCES_WITHOUT_GROUPING_LABELS", True)
    session = _RecordingGcpSession([])
    all_started = asyncio.Event()
    never_finished = asyncio.Event()
    cancelled = []

    async def blocked_request(_method, url, params, headers):
        session.calls.append(list(params))
        if len(session.calls) == 2:
            all_started.set()
        try:
            await never_finished.wait()
        finally:
            cancelled.append(_group_by_labels(params))

    monkeypatch.setattr(session, "request", blocked_request)
    task = asyncio.create_task(_fetch(session, ["team", "squad"]))
    try:
        await asyncio.wait_for(all_started.wait(), timeout=5)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert len(session.calls) == 2
    assert len(cancelled) == 2


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

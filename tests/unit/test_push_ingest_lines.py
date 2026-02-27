#   Copyright 2026 Dynatrace LLC
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

"""
Tests for concurrent push and retry logic in metric_ingest.py.

Covers:
- push_ingest_lines: sequential (concurrency=1) and concurrent (concurrency>1)
- _push_to_dynatrace: retry on 429/5xx, no retry on 401/403/404, network errors
- Abort flag: concurrent push stops remaining batches on fatal error
- SFM counters: correct accounting across retries
"""

import asyncio
from datetime import datetime
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

from lib.context import MetricsContext, DynatraceConnectivity
from lib.metric_ingest import (
    push_ingest_lines,
    _push_to_dynatrace,
    _RETRYABLE_STATUS_CODES,
    _MAX_PUSH_RETRIES,
)
from lib.metrics import IngestLine, DimensionValue
from lib.sfm.for_metrics.metrics_definitions import SfmKeys


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_context(
    concurrency: int = 1,
    batch_size: int = 3,
    dynatrace_url: str = "https://test.live.dynatrace.com",
) -> MetricsContext:
    """Create a minimal MetricsContext suitable for push tests."""
    ctx = MetricsContext(
        gcp_session=None,
        dt_session=AsyncMock(),
        project_id_owner="test-project",
        token="tok",
        execution_time=datetime.utcnow(),
        execution_interval_seconds=180,
        dynatrace_api_key="dt-api-key",
        dynatrace_url=dynatrace_url,
        print_metric_ingest_input=False,
        self_monitoring_enabled=False,
        scheduled_execution_id=None,
    )
    ctx.metric_ingest_batch_size = batch_size
    ctx.metric_ingest_concurrent_pushes = concurrency
    return ctx


def _make_lines(n: int) -> List[IngestLine]:
    """Create n dummy IngestLine objects."""
    return [
        IngestLine(
            entity_id=f"entity_{i}",
            metric_name=f"custom.metric.test",
            metric_type="gauge",
            value=float(i),
            timestamp=1000000 + i,
            dimension_values=[],
        )
        for i in range(n)
    ]


def _ok_response(lines_ok: int = 0, lines_invalid: int = 0):
    """Create a mock aiohttp response for a successful 200 push."""
    resp = AsyncMock()
    resp.status = 200
    resp.json = AsyncMock(return_value={
        "linesOk": lines_ok,
        "linesInvalid": lines_invalid,
    })
    resp.headers = {}
    return resp


def _error_response(status: int, retry_after: str = None):
    """Create a mock aiohttp response for an error status code."""
    resp = AsyncMock()
    resp.status = status
    resp.json = AsyncMock(return_value={"error": {"message": f"HTTP {status}"}})
    resp.headers = {"Retry-After": retry_after} if retry_after else {}
    return resp


# ---------------------------------------------------------------------------
# _push_to_dynatrace — retry behavior
# ---------------------------------------------------------------------------

class TestPushToDynatraceRetry:
    """Tests for the retry logic inside _push_to_dynatrace."""

    @pytest.mark.asyncio
    async def test_success_on_first_attempt(self):
        """Normal 200 response — no retries, lines counted as ok."""
        ctx = _make_context()
        ctx.dt_session.post = AsyncMock(return_value=_ok_response(lines_ok=3))

        await _push_to_dynatrace(ctx, "proj", _make_lines(3))

        assert ctx.dt_session.post.call_count == 1
        assert ctx.sfm[SfmKeys.dynatrace_ingest_lines_ok_count].value["proj"] == 3

    @pytest.mark.asyncio
    async def test_retry_on_429_then_succeed(self):
        """429 on first attempt, 200 on second — data not lost."""
        ctx = _make_context()
        ctx.dt_session.post = AsyncMock(side_effect=[
            _error_response(429),
            _ok_response(lines_ok=3),
        ])

        with patch("lib.metric_ingest.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await _push_to_dynatrace(ctx, "proj", _make_lines(3))

        assert ctx.dt_session.post.call_count == 2
        mock_sleep.assert_called_once()  # one retry delay
        assert ctx.sfm[SfmKeys.dynatrace_ingest_lines_ok_count].value["proj"] == 3
        # The intermediate 429 should be counted in request_count
        assert ctx.sfm[SfmKeys.dynatrace_request_count].value.get(429, 0) == 1
        assert ctx.sfm[SfmKeys.dynatrace_request_count].value.get(200, 0) == 1

    @pytest.mark.asyncio
    async def test_retry_on_500_then_succeed(self):
        """500 on first attempt, 200 on second."""
        ctx = _make_context()
        ctx.dt_session.post = AsyncMock(side_effect=[
            _error_response(500),
            _ok_response(lines_ok=3),
        ])

        with patch("lib.metric_ingest.asyncio.sleep", new_callable=AsyncMock):
            await _push_to_dynatrace(ctx, "proj", _make_lines(3))

        assert ctx.dt_session.post.call_count == 2
        assert ctx.sfm[SfmKeys.dynatrace_ingest_lines_ok_count].value["proj"] == 3

    @pytest.mark.asyncio
    async def test_429_exhausted_retries_counts_dropped(self):
        """429 on all attempts — lines counted as dropped after MAX retries."""
        ctx = _make_context()
        responses = [_error_response(429) for _ in range(_MAX_PUSH_RETRIES + 1)]
        ctx.dt_session.post = AsyncMock(side_effect=responses)

        with patch("lib.metric_ingest.asyncio.sleep", new_callable=AsyncMock):
            await _push_to_dynatrace(ctx, "proj", _make_lines(3))

        assert ctx.dt_session.post.call_count == _MAX_PUSH_RETRIES + 1
        assert ctx.sfm[SfmKeys.dynatrace_ingest_lines_dropped_count].value["proj"] == 3
        # lines_ok should NOT be set (we returned early)
        assert ctx.sfm[SfmKeys.dynatrace_ingest_lines_ok_count].value == {}

    @pytest.mark.asyncio
    async def test_429_respects_retry_after_header(self):
        """Retry-After header value is used as sleep delay (capped)."""
        ctx = _make_context()
        ctx.dt_session.post = AsyncMock(side_effect=[
            _error_response(429, retry_after="2.5"),
            _ok_response(lines_ok=3),
        ])

        with patch("lib.metric_ingest.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await _push_to_dynatrace(ctx, "proj", _make_lines(3))

        mock_sleep.assert_called_once_with(2.5)

    @pytest.mark.asyncio
    async def test_429_caps_large_retry_after(self):
        """Retry-After of 60s should be capped to _MAX_RETRY_AFTER_S."""
        ctx = _make_context()
        ctx.dt_session.post = AsyncMock(side_effect=[
            _error_response(429, retry_after="60"),
            _ok_response(lines_ok=3),
        ])

        with patch("lib.metric_ingest.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await _push_to_dynatrace(ctx, "proj", _make_lines(3))

        # Should be capped at 10.0 (_MAX_RETRY_AFTER_S)
        mock_sleep.assert_called_once_with(10.0)

    @pytest.mark.asyncio
    async def test_no_retry_on_401(self):
        """401 raises immediately — never retried."""
        ctx = _make_context()
        ctx.dt_session.post = AsyncMock(return_value=_error_response(401))

        with pytest.raises(Exception, match="Expired token"):
            await _push_to_dynatrace(ctx, "proj", _make_lines(3))

        assert ctx.dt_session.post.call_count == 1
        assert ctx.dynatrace_connectivity == DynatraceConnectivity.ExpiredToken

    @pytest.mark.asyncio
    async def test_no_retry_on_403(self):
        """403 raises immediately — never retried."""
        ctx = _make_context()
        ctx.dt_session.post = AsyncMock(return_value=_error_response(403))

        with pytest.raises(Exception, match="Wrong token"):
            await _push_to_dynatrace(ctx, "proj", _make_lines(3))

        assert ctx.dt_session.post.call_count == 1
        assert ctx.dynatrace_connectivity == DynatraceConnectivity.WrongToken

    @pytest.mark.asyncio
    async def test_no_retry_on_404(self):
        """404 raises immediately — never retried."""
        ctx = _make_context()
        ctx.dt_session.post = AsyncMock(return_value=_error_response(404))

        with pytest.raises(Exception, match="Wrong URL"):
            await _push_to_dynatrace(ctx, "proj", _make_lines(3))

        assert ctx.dt_session.post.call_count == 1
        assert ctx.dynatrace_connectivity == DynatraceConnectivity.WrongURL

    @pytest.mark.asyncio
    async def test_network_error_retry_then_succeed(self):
        """Network error retried, then succeeds."""
        ctx = _make_context()
        ctx.dt_session.post = AsyncMock(side_effect=[
            ConnectionError("Connection refused"),
            _ok_response(lines_ok=3),
        ])

        with patch("lib.metric_ingest.asyncio.sleep", new_callable=AsyncMock):
            await _push_to_dynatrace(ctx, "proj", _make_lines(3))

        assert ctx.dt_session.post.call_count == 2
        assert ctx.sfm[SfmKeys.dynatrace_ingest_lines_ok_count].value["proj"] == 3

    @pytest.mark.asyncio
    async def test_network_error_exhausted_counts_dropped(self):
        """Network error on all attempts — lines dropped, no exception raised."""
        ctx = _make_context()
        ctx.dt_session.post = AsyncMock(
            side_effect=ConnectionError("Connection refused")
        )

        with patch("lib.metric_ingest.asyncio.sleep", new_callable=AsyncMock):
            # Should NOT raise — drops gracefully
            await _push_to_dynatrace(ctx, "proj", _make_lines(3))

        assert ctx.dt_session.post.call_count == _MAX_PUSH_RETRIES + 1
        assert ctx.sfm[SfmKeys.dynatrace_ingest_lines_dropped_count].value["proj"] == 3


# ---------------------------------------------------------------------------
# push_ingest_lines — sequential mode (concurrency=1)
# ---------------------------------------------------------------------------

class TestPushIngestLinesSequential:
    """Tests for push_ingest_lines with default concurrency=1."""

    @pytest.mark.asyncio
    async def test_sequential_push_all_batches(self):
        """All lines are pushed in correct number of batches."""
        ctx = _make_context(concurrency=1, batch_size=3)
        # 7 lines → 3 batches (3, 3, 1)
        ctx.dt_session.post = AsyncMock(return_value=_ok_response(lines_ok=3))

        await push_ingest_lines(ctx, "proj", _make_lines(7))

        assert ctx.dt_session.post.call_count == 3

    @pytest.mark.asyncio
    async def test_empty_results_skips_push(self):
        """Empty results list logs skip and returns without pushing."""
        ctx = _make_context()

        await push_ingest_lines(ctx, "proj", [])

        ctx.dt_session.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_connectivity_error_skips_push(self):
        """If connectivity is not Ok, push is skipped entirely."""
        ctx = _make_context()
        ctx.update_dt_connectivity_status(DynatraceConnectivity.ExpiredToken)

        await push_ingest_lines(ctx, "proj", _make_lines(5))

        ctx.dt_session.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_sequential_fatal_error_stops_remaining(self):
        """In sequential mode, a fatal error stops pushing remaining batches."""
        ctx = _make_context(concurrency=1, batch_size=2)
        # 6 lines → 3 batches. First succeeds, second gets 401.
        ctx.dt_session.post = AsyncMock(side_effect=[
            _ok_response(lines_ok=2),
            _error_response(401),
        ])

        await push_ingest_lines(ctx, "proj", _make_lines(6))

        # Should have attempted 2 batches: first OK, second 401 → stops
        assert ctx.dt_session.post.call_count == 2
        # SFM should have the OK lines from batch 1
        assert ctx.sfm[SfmKeys.dynatrace_ingest_lines_ok_count].value["proj"] == 2


# ---------------------------------------------------------------------------
# push_ingest_lines — concurrent mode (concurrency>1)
# ---------------------------------------------------------------------------

class TestPushIngestLinesConcurrent:
    """Tests for push_ingest_lines with concurrency > 1."""

    @pytest.mark.asyncio
    async def test_concurrent_push_all_batches(self):
        """All batches are pushed with concurrent mode."""
        ctx = _make_context(concurrency=5, batch_size=3)
        ctx.dt_session.post = AsyncMock(return_value=_ok_response(lines_ok=3))

        await push_ingest_lines(ctx, "proj", _make_lines(7))

        # 7 lines / 3 per batch = 3 batches
        assert ctx.dt_session.post.call_count == 3

    @pytest.mark.asyncio
    async def test_concurrent_abort_on_fatal_error(self):
        """Concurrent push aborts remaining batches when fatal error occurs."""
        ctx = _make_context(concurrency=2, batch_size=1)
        lines = _make_lines(10)  # 10 batches of 1

        call_count = 0

        async def mock_post(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _error_response(401)
            # Remaining calls should be minimized due to abort flag
            return _ok_response(lines_ok=1)

        ctx.dt_session.post = mock_post

        await push_ingest_lines(ctx, "proj", lines)

        # With concurrency=2 and abort flag, should stop early.
        # At most concurrency+1 calls can happen before abort takes effect.
        assert call_count <= 4  # generous bound: semaphore=2, so max ~3-4 before abort

    @pytest.mark.asyncio
    async def test_concurrent_with_retry(self):
        """Concurrent push where some batches need retry — all succeed."""
        ctx = _make_context(concurrency=3, batch_size=2)
        lines = _make_lines(4)  # 2 batches

        responses = [
            # Batch 1: 429 then 200
            _error_response(429),
            # Batch 2: 200 immediately
            _ok_response(lines_ok=2),
            # Batch 1 retry: 200
            _ok_response(lines_ok=2),
        ]
        ctx.dt_session.post = AsyncMock(side_effect=responses)

        with patch("lib.metric_ingest.asyncio.sleep", new_callable=AsyncMock):
            await push_ingest_lines(ctx, "proj", lines)

        # 3 HTTP calls total: batch1 fail, batch2 ok, batch1 retry ok
        assert ctx.dt_session.post.call_count == 3
        assert ctx.sfm[SfmKeys.dynatrace_ingest_lines_ok_count].value["proj"] == 4


# ---------------------------------------------------------------------------
# push_ingest_lines — batching logic
# ---------------------------------------------------------------------------

class TestBatching:
    """Tests for correct batch formation."""

    @pytest.mark.asyncio
    async def test_exact_batch_size(self):
        """Lines exactly divisible by batch size."""
        ctx = _make_context(concurrency=1, batch_size=5)
        ctx.dt_session.post = AsyncMock(return_value=_ok_response(lines_ok=5))

        await push_ingest_lines(ctx, "proj", _make_lines(10))

        assert ctx.dt_session.post.call_count == 2  # 10 / 5 = 2 batches

    @pytest.mark.asyncio
    async def test_single_line(self):
        """Single line creates one batch."""
        ctx = _make_context(concurrency=1, batch_size=1000)
        ctx.dt_session.post = AsyncMock(return_value=_ok_response(lines_ok=1))

        await push_ingest_lines(ctx, "proj", _make_lines(1))

        assert ctx.dt_session.post.call_count == 1

    @pytest.mark.asyncio
    async def test_remainder_batch(self):
        """Lines not divisible by batch size produce a smaller final batch."""
        ctx = _make_context(concurrency=1, batch_size=3)
        ctx.dt_session.post = AsyncMock(return_value=_ok_response(lines_ok=3))

        await push_ingest_lines(ctx, "proj", _make_lines(5))

        # 5 lines / 3 per batch = 2 batches (3 + 2)
        assert ctx.dt_session.post.call_count == 2


# ---------------------------------------------------------------------------
# SFM counter correctness
# ---------------------------------------------------------------------------

class TestSfmCounters:
    """Verify SFM metrics are correctly updated across retries and concurrency."""

    @pytest.mark.asyncio
    async def test_request_count_tracks_retries(self):
        """Each HTTP attempt (including retries) is counted in request_count."""
        ctx = _make_context()
        ctx.dt_session.post = AsyncMock(side_effect=[
            _error_response(429),
            _error_response(500),
            _ok_response(lines_ok=3),
        ])

        with patch("lib.metric_ingest.asyncio.sleep", new_callable=AsyncMock):
            await _push_to_dynatrace(ctx, "proj", _make_lines(3))

        # 429 counted once (retry), 500 counted once (retry), 200 counted once (final)
        assert ctx.sfm[SfmKeys.dynatrace_request_count].value[429] == 1
        assert ctx.sfm[SfmKeys.dynatrace_request_count].value[500] == 1
        assert ctx.sfm[SfmKeys.dynatrace_request_count].value[200] == 1

    @pytest.mark.asyncio
    async def test_push_time_recorded(self):
        """push_to_dynatrace_execution_time is recorded in SFM."""
        ctx = _make_context(concurrency=1, batch_size=100)
        ctx.dt_session.post = AsyncMock(return_value=_ok_response(lines_ok=3))

        await push_ingest_lines(ctx, "proj", _make_lines(3))

        # push_to_dynatrace_execution_time should have been set for "proj"
        assert "proj" in ctx.sfm[SfmKeys.push_to_dynatrace_execution_time].value
        assert ctx.sfm[SfmKeys.push_to_dynatrace_execution_time].value["proj"] >= 0

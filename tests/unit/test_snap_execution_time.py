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

import pytest
from datetime import datetime, timedelta

import main


INTERVAL_4MIN = 240  # 4 minutes in seconds


@pytest.fixture(autouse=True)
def reset_snap_state():
    """Reset module-level _last_execution_time before each test."""
    main._last_execution_time = None
    yield
    main._last_execution_time = None


class TestSnapExecutionTime:

    def test_first_run_returns_truncated_now(self):
        """First run (no history) should return now truncated to seconds, with unchanged interval."""
        now = datetime(2026, 2, 5, 12, 3, 58, 123456)

        snapped, effective_interval, snap_action = main._snap_execution_time(now, INTERVAL_4MIN)

        assert snapped == datetime(2026, 2, 5, 12, 3, 58)
        assert effective_interval == INTERVAL_4MIN
        assert snap_action == "init"
        assert main._last_execution_time == datetime(2026, 2, 5, 12, 3, 58)

    def test_normal_snap_no_drift(self):
        """Second run arriving exactly on time should use expected = last + interval."""
        # Simulate first run
        first_now = datetime(2026, 2, 5, 12, 0, 0)
        main._snap_execution_time(first_now, INTERVAL_4MIN)

        # Second run exactly 4 minutes later
        second_now = datetime(2026, 2, 5, 12, 4, 0)
        snapped, effective_interval, snap_action = main._snap_execution_time(second_now, INTERVAL_4MIN)

        assert snapped == datetime(2026, 2, 5, 12, 4, 0)
        assert effective_interval == INTERVAL_4MIN
        assert snap_action.startswith("snapped")

    def test_normal_snap_with_small_drift(self):
        """Drift of a few seconds should still snap to expected time."""
        first_now = datetime(2026, 2, 5, 12, 0, 0)
        main._snap_execution_time(first_now, INTERVAL_4MIN)

        # Second run 2 seconds late (typical drift)
        second_now = datetime(2026, 2, 5, 12, 4, 2)
        snapped, effective_interval, snap_action = main._snap_execution_time(second_now, INTERVAL_4MIN)

        # Should snap to exact expected time, not wall clock
        assert snapped == datetime(2026, 2, 5, 12, 4, 0)
        assert effective_interval == INTERVAL_4MIN
        assert snap_action == "snapped (drift=+2.0s)"

    def test_normal_snap_drift_up_to_1_minute(self):
        """Drift up to exactly 1 minute should still snap normally."""
        first_now = datetime(2026, 2, 5, 12, 0, 0)
        main._snap_execution_time(first_now, INTERVAL_4MIN)

        # Second run exactly 1 minute late
        second_now = datetime(2026, 2, 5, 12, 5, 0)
        snapped, effective_interval, snap_action = main._snap_execution_time(second_now, INTERVAL_4MIN)

        assert snapped == datetime(2026, 2, 5, 12, 4, 0)
        assert effective_interval == INTERVAL_4MIN
        assert snap_action == "snapped (drift=+60.0s)"

    def test_catch_up_when_behind_more_than_1_minute(self):
        """When >1 min behind (e.g. slow cycle), use expected time but widen interval by 60s."""
        first_now = datetime(2026, 2, 5, 12, 0, 0)
        main._snap_execution_time(first_now, INTERVAL_4MIN)

        # Second run 1 min 30 sec late
        second_now = datetime(2026, 2, 5, 12, 5, 30)
        snapped, effective_interval, snap_action = main._snap_execution_time(second_now, INTERVAL_4MIN)

        # Should use expected time (12:04:00) but widen interval
        assert snapped == datetime(2026, 2, 5, 12, 4, 0)
        assert effective_interval == INTERVAL_4MIN + 60
        assert snap_action == "catch-up (drift=+90.0s, interval widened by 60s)"

    def test_catch_up_self_corrects_next_cycle(self):
        """After a catch-up, the next normal cycle should return to normal interval."""
        first_now = datetime(2026, 2, 5, 12, 0, 0)
        main._snap_execution_time(first_now, INTERVAL_4MIN)

        # Second run: delayed, triggers catch-up
        second_now = datetime(2026, 2, 5, 12, 5, 30)
        _, _, catch_up_action = main._snap_execution_time(second_now, INTERVAL_4MIN)
        assert "catch-up" in catch_up_action
        # _last_execution_time is now 12:04:00

        # Third run: arrives roughly on time relative to last snap (12:04:00 + 4min = 12:08:00)
        third_now = datetime(2026, 2, 5, 12, 8, 1)
        snapped, effective_interval, snap_action = main._snap_execution_time(third_now, INTERVAL_4MIN)

        assert snapped == datetime(2026, 2, 5, 12, 8, 0)
        assert effective_interval == INTERVAL_4MIN  # Back to normal
        assert snap_action.startswith("snapped")

    def test_hard_reset_when_way_behind(self):
        """When >30 min behind, hard reset to wall clock."""
        first_now = datetime(2026, 2, 5, 12, 0, 0)
        main._snap_execution_time(first_now, INTERVAL_4MIN)

        # Next run is 45 minutes late (e.g. process was suspended)
        second_now = datetime(2026, 2, 5, 12, 49, 0)
        snapped, effective_interval, snap_action = main._snap_execution_time(second_now, INTERVAL_4MIN)

        # Should reset to wall clock, not try to catch up
        assert snapped == datetime(2026, 2, 5, 12, 49, 0)
        assert effective_interval == INTERVAL_4MIN
        assert snap_action.startswith("hard-reset")

    def test_hard_reset_when_clock_goes_backward(self):
        """If now is before expected (clock adjustment), hard reset."""
        first_now = datetime(2026, 2, 5, 12, 4, 0)
        main._snap_execution_time(first_now, INTERVAL_4MIN)

        # Clock jumped backward by 5 minutes
        second_now = datetime(2026, 2, 5, 12, 3, 0)
        snapped, effective_interval, snap_action = main._snap_execution_time(second_now, INTERVAL_4MIN)

        # drift = 12:03:00 - 12:08:00 = -5 min, abs > 1 min, and drift < 0 => else branch
        assert snapped == datetime(2026, 2, 5, 12, 3, 0)
        assert effective_interval == INTERVAL_4MIN
        assert snap_action.startswith("hard-reset")

    def test_consecutive_cycles_produce_tiling_windows(self):
        """Multiple consecutive cycles should produce perfectly tiling query windows."""
        interval = INTERVAL_4MIN
        interval_td = timedelta(seconds=interval)
        execution_times = []

        # Simulate 10 cycles with realistic drift (1-3 seconds late each time)
        drifts = [0, 1.5, 2.1, 1.8, 2.5, 1.2, 2.8, 1.0, 3.0, 2.2]
        base = datetime(2026, 2, 5, 12, 0, 0)

        for i, drift_s in enumerate(drifts):
            now = base + timedelta(seconds=i * interval + drift_s)
            snapped, eff_interval, _ = main._snap_execution_time(now, interval)
            execution_times.append(snapped)

        # Verify each consecutive pair tiles perfectly (no gap, no overlap)
        for i in range(1, len(execution_times)):
            gap = execution_times[i] - execution_times[i - 1]
            assert gap == interval_td, (
                f"Cycle {i}: expected {interval_td} between "
                f"{execution_times[i-1]} and {execution_times[i]}, got {gap}"
            )

    def test_catch_up_at_30_minute_boundary(self):
        """At exactly 30 min behind, should still catch up (not hard reset)."""
        first_now = datetime(2026, 2, 5, 12, 0, 0)
        main._snap_execution_time(first_now, INTERVAL_4MIN)

        # Expected is 12:04:00, now is 12:34:00 => drift = 30 min exactly
        second_now = datetime(2026, 2, 5, 12, 34, 0)
        snapped, effective_interval, snap_action = main._snap_execution_time(second_now, INTERVAL_4MIN)

        assert snapped == datetime(2026, 2, 5, 12, 4, 0)
        assert effective_interval == INTERVAL_4MIN + 60
        assert "catch-up" in snap_action

    def test_works_with_different_intervals(self):
        """Should work correctly with 1-min, 3-min, and 6-min intervals."""
        for interval_min in [1, 3, 6]:
            main._last_execution_time = None
            interval_sec = interval_min * 60

            first_now = datetime(2026, 2, 5, 12, 0, 0)
            main._snap_execution_time(first_now, interval_sec)

            second_now = first_now + timedelta(seconds=interval_sec + 2)  # 2s drift
            snapped, effective_interval, snap_action = main._snap_execution_time(second_now, interval_sec)

            expected = first_now + timedelta(seconds=interval_sec)
            assert snapped == expected, f"Failed for {interval_min}-min interval"
            assert effective_interval == interval_sec
            assert snap_action.startswith("snapped"), f"Failed for {interval_min}-min interval"

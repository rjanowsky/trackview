"""[26] The pure geometry -- cheap, deterministic, no network or figures."""
from pathlib import Path

import numpy as np
import pytest

import trackview as tv
from trackview.metrics import GRADE_CAP_CEIL, GRADE_CAP_FLOOR, GRADE_CAP_PCT, _grade_cap
from trackview.rendering import _moving_avg


class TestGradeCap:
    def test_auto_cap_is_the_high_percentile(self):
        # 0..10 % -> p98 lands mid-range, inside [FLOOR, CEIL] so it is returned as-is
        grades = list(range(0, 11))
        expected = float(np.percentile(np.abs(np.array(grades, float)), GRADE_CAP_PCT))
        assert _grade_cap(grades, None) == pytest.approx(expected)

    def test_pinned_cap_wins_over_the_auto(self):
        assert _grade_cap([0.0, 1.0, 2.0], 8.0) == 8.0

    def test_pinned_cap_beats_a_noise_spike(self):
        # a lone 40 % blip would clamp the auto cap to CEIL, but a pin ignores it
        assert _grade_cap(list(range(0, 11)) + [40.0], 8.0) == 8.0

    def test_pinned_zero_falls_back_to_auto(self):
        # a non-positive pin is "unset", so the auto percentile takes over
        flat = [0.1, -0.2, 0.0]
        assert _grade_cap(flat, 0.0) == _grade_cap(flat, None)

    def test_floor_clamps_an_all_flat_ride(self):
        # an all-flat ride's p98 is ~0, so the floor keeps it coloured
        assert _grade_cap([0.1, -0.2, 0.0, 0.05], None) == GRADE_CAP_FLOOR

    def test_ceil_clamps_a_steeper_range(self):
        # a 50 % grade would blow past the ramp, so it is clamped to the ceiling
        assert _grade_cap([50.0, 60.0, 40.0], None) == GRADE_CAP_CEIL

    def test_empty_grades_returns_the_floor(self):
        assert _grade_cap([], None) == GRADE_CAP_FLOOR


class TestMovingAvg:
    def test_window_3_over_a_linear_series(self):
        # half=1: the interior is a 3-window mean, the ends drop to a 2-window
        out = _moving_avg(np.array([1.0, 2, 3, 4, 5]), 3)
        assert out.tolist() == pytest.approx([1.5, 2.0, 3.0, 4.0, 4.5])

    def test_window_5_over_a_linear_series(self):
        out = _moving_avg(np.array([1.0, 2, 3, 4, 5]), 5)
        assert out.tolist() == pytest.approx([2.0, 2.5, 3.0, 3.5, 4.0])

    def test_skips_nan(self):
        # a NaN in the middle shortens that window but never poisons the result
        out = _moving_avg(np.array([1.0, np.nan, 3.0, 4.0]), 3)
        assert out.tolist() == pytest.approx([1.0, 2.0, 3.5, 3.5])

    def test_all_nan_stays_nan(self):
        out = _moving_avg(np.array([np.nan, np.nan, np.nan]), 3)
        assert out.shape == (3,)
        assert np.isnan(out).all()

    def test_window_below_one_is_a_no_op(self):
        # w = max(1, int(window)): a sub-1 window means no averaging at all
        out = _moving_avg(np.array([2.0, 4.0]), 0.5)
        assert out.tolist() == pytest.approx([2.0, 4.0])

    def test_output_length_matches_input(self):
        arr = np.arange(17.0)
        assert _moving_avg(arr, 5).shape == arr.shape


def track(stem, dist_km, gain_m):
    """A bare ride dict: a Wahoo-style stem (+ dist/gain) -- _select_top needs no GPX."""
    return {"path": Path("/x/%s.gpx" % stem), "name": stem,
            "dist_km": dist_km, "gain_m": gain_m}


# date-ascending as the glob gives them; distances/gains chosen so the rank order
# on one key differs from date order (so the re-sort below is actually exercised).
A = track("2026_01_15_08_00_00", 5.0, 50.0)    # earliest, shortest
B = track("2026_06_20_10_00_00", 30.0, 40.0)   # longest, low gain
C = track("2026_09_07_08_12_47", 20.0, 120.0)  # latest, highest gain


class TestSelectTop:
    def test_top1_by_recent_keeps_the_latest(self):
        kept = tv._select_top([A, B, C], 1, "recent")
        assert [t["name"] for t in kept] == [C["name"]]

    def test_top_by_km_picks_the_longest(self):
        kept = tv._select_top([A, B, C], 1, "km")
        assert [t["name"] for t in kept] == [B["name"]]

    def test_top_by_gain_picks_the_highest_gain(self):
        kept = tv._select_top([A, B, C], 1, "gain")
        assert [t["name"] for t in kept] == [C["name"]]

    def test_survivors_are_re_sorted_back_to_date_order(self):
        # top 2 by gain ranks C(120), A(50) -- out of date order -- but the result
        # must read back in date order (A Jan, then C Sep)
        kept = tv._select_top([A, B, C], 2, "gain")
        assert [t["name"] for t in kept] == [A["name"], C["name"]]

    def test_n_at_least_the_count_is_a_no_op(self):
        tracks = [A, B, C]
        assert tv._select_top(tracks, 5, "km") is tracks  # same object, untouched

    def test_non_positive_n_is_a_no_op(self):
        tracks = [A, B, C]
        assert tv._select_top(tracks, 0, "km") == tracks
        assert tv._select_top(tracks, -1, "km") == tracks

    def test_undated_ride_ranks_last_under_recent(self):
        # an undated ride (ordinal 0) is the oldest, so it drops out first
        undated = track("komoot_loop", 30.0, 120.0)
        kept = tv._select_top([A, B, undated], 2, "recent")
        assert [t["name"] for t in kept] == [A["name"], B["name"]]

    def test_undated_ride_still_wins_a_pure_value_rank(self):
        # but on a pure value it is just another ride, and a long one wins
        undated = track("komoot_loop", 100.0, 120.0)
        kept = tv._select_top([A, B, undated], 1, "km")
        assert [t["name"] for t in kept] == [undated["name"]]

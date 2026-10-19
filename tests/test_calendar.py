"""[Phase 4 / 4.1] The calendar grid's pure builders -- no figure, no network.

      _calendar_days   bins each ride by the calendar day it falls in (an ISO
                       (week, weekday) key, grouped by year), by the --calendar-by
                       metric, dropping undated rides and counting them.
      _month_ticks     the month labels for that grid (a tick at the week holding
                       the 1st of each month; a month that strays into an adjacent
                       ISO year's week is skipped).
Both read off a bare ride dict (+ the Wahoo-style filename stem), so the suite
stays pure and offline.
"""
from pathlib import Path

from trackview.activitygrid import _calendar_days, _month_ticks, _CALENDAR_METRICS


def track(stem, *, dist_km=1.0, gain_m=10.0):
    """A bare ride dict: a Wahoo-style stem (+ the metrics the grid reads)."""
    return {"path": Path("/x/%s.gpx" % stem), "name": stem,
            "dist_km": dist_km, "gain_m": gain_m}


# 2026-09-07 is a Monday (ISO week 37, weekday 1) -- the grid's anchor day.
# 2026-09-09 is the same ISO week, two days later; 2026-09-13 the same week's
# Sunday (weekday 7) -- all three land in ISO week 37.
ANCHOR = "2026_09_07_08_12_47"
SAME_DAY = "2026_09_07_09_00_00"
SAME_WEEK = "2026_09_09_08_00_00"            # Wed, same ISO week 37, a different day


class TestCalendarDays:
    def test_distance_metric_sums_km_by_day(self):
        a = track(ANCHOR, dist_km=10.0)
        b = track(SAME_DAY, dist_km=3.0)              # same day -> the km add up
        c = track(SAME_WEEK, dist_km=5.0)             # a different day, same week
        by_year, skipped = _calendar_days([a, b, c], "distance")
        assert skipped == 0
        grid = by_year[2026]
        assert grid[(37, 1)] == 13.0                  # the two same-day rides
        assert grid[(37, 3)] == 5.0                   # the Wednesday ride
        assert len(grid) == 2                          # two distinct cells

    def test_gain_metric_sums_meters(self):
        a = track(ANCHOR, gain_m=500.0)
        b = track(SAME_DAY, gain_m=100.0)
        by_year, _ = _calendar_days([a, b], "gain")
        assert by_year[2026][(37, 1)] == 600.0

    def test_rides_metric_counts_one_per_ride(self):
        a = track(ANCHOR, dist_km=10.0)
        b = track(SAME_DAY, dist_km=3.0)
        by_year, _ = _calendar_days([a, b], "rides")
        assert by_year[2026][(37, 1)] == 2.0           # two rides -> 2, not the km sum

    def test_undated_ride_is_skipped_and_counted(self):
        a = track(ANCHOR, dist_km=10.0)
        undated = track("komoot_loop", dist_km=99.0)
        by_year, skipped = _calendar_days([a, undated], "distance")
        assert skipped == 1
        assert 99.0 not in by_year[2026].values()

    def test_year_filter_isolates_one_year(self):
        a = track("2025_09_07_08_00_00", dist_km=7.0)
        b = track("2026_09_07_08_00_00", dist_km=11.0)
        by_year, skipped = _calendar_days([a, b], "distance", year=2026)
        assert skipped == 0
        assert set(by_year) == {2026}
        assert list(by_year[2026].values())[0] == 11.0

    def test_metric_keys_match_the_documented_set(self):
        # the three --calendar-by options are the only valid metric keys
        assert set(_CALENDAR_METRICS) == {"distance", "gain", "rides"}


class TestMonthTicks:
    def test_ticks_are_monotonic_in_week(self):
        ticks, labels = _month_ticks(2026, 40)
        assert ticks == sorted(ticks)
        assert len(labels) == len(ticks)

    def test_labels_are_the_twelve_month_names(self):
        _, labels = _month_ticks(2026, 52)
        assert all(len(s) == 3 for s in labels)          # "Jan", "Feb", ...
        assert labels == ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    def test_a_truncated_year_shows_fewer_months(self):
        _, labels = _month_ticks(2026, 6)
        # six weeks reach at most two distinct months (Jan + Feb)
        assert 0 < len(labels) <= 2

    def test_full_year_labels_are_in_order(self):
        _, labels = _month_ticks(2026, 52)
        # 2026's 1 Jan sits in ISO week 1 of 2026, so the full grid runs Jan..Dec
        assert labels[0] == "Jan"
        assert labels[-1] == "Dec"

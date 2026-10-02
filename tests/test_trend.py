"""[Phase 4 / 4.1] The training-trend chart's pure panel builder.

      _trend_panels   one panel per metric over ride date -- distance, gain,
                      duration -- plus a calories panel only when a ride carries
                      a power average; undated rides are skipped and counted.
A panel is (y-label, [dates], [values]); rides are sorted by date, so a panel
reads left-to-right in time.  Pure over a bare ride dict (+ the Wahoo-style
filename stem), so the suite stays offline.
"""
from pathlib import Path

from trackview.trend import _trend_panels, _TREND_COLORS


def track(stem, *, dist_km=1.0, gain_m=10.0, duration_s=3600.0, power=None):
    # a bare ride dict: a Wahoo-style stem (+ the trend's per-ride numbers)
    d = {"path": Path("/x/%s.gpx" % stem), "name": stem,
           "dist_km": dist_km, "gain_m": gain_m, "duration_s": duration_s}
    if power is not None:
        d["power"] = power                        # a [sum, count] pair -> calories
    return d


class TestTrendPanels:
    def test_three_panels_for_a_plain_ride(self):
        panels, skipped = _trend_panels([track("2026_01_15_08_00_00")])
        assert skipped == 0
        assert [p[0] for p in panels] == ["Distance (km)", "Elevation gain (m)", "Duration (h)"]

    def test_calorie_panel_appears_only_with_power(self):
        with_p = _trend_panels([track("2026_01_15_08_00_00", power=[250.0, 9.0], duration_s=7200.0)])
        without_p = _trend_panels([track("2026_01_15_08_00_00")])
        assert "Calories (kcal)" in [p[0] for p in with_p[0]]
        assert "Calories (kcal)" not in [p[0] for p in without_p[0]]

    def test_calorie_value_is_positive_when_powered(self):
        panels, _ = _trend_panels([track("2026_01_15_08_00_00", power=[250.0, 9.0], duration_s=7200.0)])
        cals = [p for p in panels if p[0] == "Calories (kcal)"]
        assert len(cals) == 1 and cals[0][2][0] > 0.0

    def test_duration_panel_is_hours(self):
        panels, _ = _trend_panels([track("2026_01_15_08_00_00", duration_s=7200.0)])
        dur = [p for p in panels if p[0] == "Duration (h)"][0]
        assert dur[2][0] == 2.0                      # 7200 s = 2 h

    def test_undated_ride_is_skipped_and_counted(self):
        panels, skipped = _trend_panels([track("komoot_loop")])
        assert skipped == 1
        assert panels[0][1] == []                    # no dated ride -> empty series

    def test_panels_are_sorted_by_ride_date(self):
        a = track("2026_09_07_08_00_00", dist_km=20.0)
        b = track("2026_01_15_08_00_00", dist_km=5.0)     # earlier, listed last
        panels, _ = _trend_panels([a, b])
        assert panels[0][2] == [5.0, 20.0]           # Jan (5 km) before Sep (20 km)

    def test_every_panel_has_matching_date_and_value_lists(self):
        panels, _ = _trend_panels([track("2026_01_15_08_00_00"),
                                 track("2026_02_15_08_00_00")])
        for _, xs, ys in panels:
            assert len(xs) == len(ys) == 2


class TestTrendColors:
    def test_four_colors_for_the_four_panels(self):
        assert len(_TREND_COLORS) == 4              # one per metric panel
        assert len(set(_TREND_COLORS)) == 4         # all distinct

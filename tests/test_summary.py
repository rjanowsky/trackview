"""[Phase 4 / 4.1] The year-in-review report's pure grouping.

      _summary_groups   splits the rides for the --summary report: dated rides by
                      calendar year then month ({year: {month: [rides]}}), plus an
                      "undated" bucket for a filename that carries no date.
Pure over a bare ride dict (+ the Wahoo-style filename stem), so the suite
stays offline.
"""
from pathlib import Path

from trackview.summary import _summary_groups


def track(stem, dist_km=1.0, gain_m=10.0):
     # a bare ride dict: a Wahoo-style stem (+ the numbers the report reads)
    return {"path": Path("/x/%s.gpx" % stem), "name": stem,
             "dist_km": dist_km, "gain_m": gain_m}


class TestSummaryGroups:
    def test_one_ride_lands_in_its_year_and_month(self):
        by_year, undated = _summary_groups([track("2026_01_15_08_00_00", dist_km=5.0)])
        assert undated == []
        assert by_year == {2026: {1: [by_year[2026][1][0]]}}
        assert by_year[2026][1][0]["name"] == "2026_01_15_08_00_00"

    def test_rides_split_across_months(self):
        a = track("2026_01_15_08_00_00", dist_km=5.0)
        b = track("2026_03_20_08_00_00", dist_km=9.0)
        by_year, _ = _summary_groups([a, b])
        assert sorted(by_year[2026]) == [1, 3]
        assert by_year[2026][1] == [a]
        assert by_year[2026][3] == [b]

    def test_rides_split_across_years(self):
        a = track("2025_12_31_08_00_00")
        b = track("2026_01_01_08_00_00")
        by_year, _ = _summary_groups([a, b])
        assert sorted(by_year) == [2025, 2026]
        assert len(by_year[2025]) == 1 and len(by_year[2026]) == 1

    def test_undated_ride_goes_to_its_own_bucket(self):
        by_year, undated = _summary_groups([track("komoot_loop")])
        assert by_year == {}
        assert [t["name"] for t in undated] == ["komoot_loop"]

    def test_mixed_dated_and_undated(self):
        a = track("2026_06_10_08_00_00")
        b = track("komoot_loop")
        by_year, undated = _summary_groups([a, b])
        assert by_year[2026][6] == [a]
        assert [t["name"] for t in undated] == ["komoot_loop"]

    def test_empty_input_is_all_empty(self):
        by_year, undated = _summary_groups([])
        assert by_year == {} and undated == []

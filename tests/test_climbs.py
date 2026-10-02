"""[Phase 4 / 4.1] Sustained-climb detection and ranking -- pure, offline.

       _ride_climbs   the maximal runs of a ride whose *smoothed* grade clears
                       CLIMB_MIN_GR over at least CLIMB_MIN_LEN of horizontal run;
       _all_climbs    every ride's climbs ranked most-significant first, by a
                       score = gain x average grade.
Both are pure over the per-ride grade / cumulative-km / elevation arrays, so the
suite builds those arrays by hand (no GPX, no network).
"""
from pathlib import Path

from trackview.climbs import _ride_climbs, _all_climbs


def climb_ride(name="2026_01_15_08_00_00", *, grade=None, cum_km=None,
               ele=None, device="Wahoo ELEMNT BOLT"):
        # a bare ride dict with the per-segment arrays _ride_climbs scans
    return {"path": Path("/x/%s.gpx" % name), "name": name, "device": device,
             "grade": grade, "cum_km": cum_km, "ele": ele}


# A clean climb: a long run of 6.0% grade (above the 4% floor, and the moving
# average keeps it high because every neighbour is 6.0%), 5 m apart over
# N points -- so the run is (N-1) x 5 m, well past the 250 m climb floor,
# with a matching 6% rise in elevation -> one climb spanning the whole run.
N = 60
GRADE = [6.0] * N
STEP_M = 5.0                                                     # horizontal spacing (m)
CUM      = [i * STEP_M / 1000.0 for i in range(N)]                # 0, 0.005, ... km
ELE      = [500.0 + i * 6.0 * STEP_M / 100.0 for i in range(N)]   # a steady 6% rise


class TestRideClimbs:
    def test_a_clear_run_is_found(self):
        climbs = _ride_climbs(climb_ride(grade=GRADE, cum_km=CUM, ele=ELE))
        assert len(climbs) == 1

    def test_climb_dict_has_the_expected_keys(self):
        c = _ride_climbs(climb_ride(grade=GRADE, cum_km=CUM, ele=ELE))[0]
        for key in ("ride", "device", "start_km", "end_km", "len_km",
                     "gain_m", "avg_gr", "max_gr", "score"):
            assert key in c

    def test_climb_spans_the_run(self):
        c = _ride_climbs(climb_ride(grade=GRADE, cum_km=CUM, ele=ELE))[0]
        assert c["start_km"] == CUM[0]
        assert c["end_km"] == CUM[-1]
        assert c["len_km"] == CUM[-1] - CUM[0]

    def test_score_is_gain_times_average_grade(self):
        c = _ride_climbs(climb_ride(grade=GRADE, cum_km=CUM, ele=ELE))[0]
        assert c["score"] == c["gain_m"] * c["avg_gr"]
        assert c["gain_m"] > 0.0 and 0.0 <= c["avg_gr"] <= 100.0

    def test_ride_and_device_fields_are_copied(self):
        c = _ride_climbs(climb_ride(grade=GRADE, cum_km=CUM, ele=ELE,
                                    device="Garmin Edge"))[0]
        assert c["ride"] == "2026_01_15_08_00_00"
        assert c["device"] == "Garmin Edge"

    def test_no_grade_yields_no_climbs(self):
        assert _ride_climbs(climb_ride(grade=[], cum_km=[], ele=[])) == []

    def test_flat_ride_yields_no_climbs(self):
        flat = climb_ride(grade=[0.0] * N, cum_km=CUM, ele=[500.0] * N)
        assert _ride_climbs(flat) == []


class TestAllClimbs:
    def test_empty_when_no_tracks(self):
        assert _all_climbs([]) == []

    def test_ranks_by_score_descending(self):
        weak = climb_ride("2026_01_01_08_00_00", grade=[4.5] * N, cum_km=CUM,
                          ele=[500.0 + i * 4.5 * STEP_M / 100.0 for i in range(N)])
        strong = climb_ride("2026_01_02_08_00_00", grade=[8.0] * N, cum_km=CUM,
                            ele=[500.0 + i * 8.0 * STEP_M / 100.0 for i in range(N)])
        ranked = _all_climbs([weak, strong])
        assert [c["ride"] for c in ranked] == ["2026_01_02_08_00_00", "2026_01_01_08_00_00"]
        assert ranked[0]["score"] >= ranked[1]["score"]

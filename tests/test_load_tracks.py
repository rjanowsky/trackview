"""The in-memory synthetic GPX fixtures ([24]) exercised through load_tracks:

a ride built *with* <extensions> telemetry carries per-point power/speed arrays
(and a [sum, count] telemetry dict), and the same ride built *without* them -- a
plain komoot-style track -- carries no telemetry values.  The climb/descent/flat
profile is readable straight off the raw points via the pure geometry helpers.
"""
from conftest import build_ride, gpx_points, write_ride
from trackview.geometry import _distance_and_gain, _grade_and_cumkm
import trackview as tv


def test_synthetic_gpx_fixture_has_telemetry(tmp_path, synthetic_gpx):
      # the "with <extensions>" fixture (a climb/descent/flat ride, device + sport)
    path = write_ride(synthetic_gpx, tmp_path / "2026_09_07_08_12_47.gpx")
    (t,) = tv.load_tracks([path], 1.0, with_ext=True)
    assert all(v is not None for v in t["power_pts"])
    assert t["device"] == "Wahoo ELEMNT BOLT" and t["sport"] == "Bike"


def test_synthetic_gpx_plain_fixture_has_no_telemetry(tmp_path, synthetic_gpx_plain):
      # the "without <extensions>" fixture -- a plain komoot-style track
    path = write_ride(synthetic_gpx_plain, tmp_path / "komoot_loop.gpx")
    (t,) = tv.load_tracks([path], 1.0, with_ext=True)
    assert all(v is None for v in t.get("power_pts", []))
    assert t["device"] is None and t["sport"] is None


def test_telemetry_ride_carries_per_point_arrays(tmp_path):
    ride = build_ride("2026_09_07_08_12_47", telemetry=True)
    path = write_ride(ride, tmp_path / "2026_09_07_08_12_47.gpx")
    (t,) = tv.load_tracks([path], 1.0, with_ext=True)

    # a per-point array, one value per decimated point (aligned with merc/ele)
    assert "power_pts" in t and "speed_pts" in t
    assert len(t["power_pts"]) == t["ndec"]
    assert all(v is not None for v in t["power_pts"])
    # the [sum, count] telemetry dict is accumulated over the RAW (pre-decimation)
    # samples -- t["n"] of each metric -- not the decimated count
    assert t["power"] == [250.0 * t["n"], t["n"]]
    assert t["speed"] == [30.0 * t["n"], t["n"]]


def test_plain_ride_carries_no_telemetry_values(tmp_path):
     # a ride with no <extensions>, even when the collector (with_ext) runs: the
     # per-point array is all-None and the [sum, count] telemetry counts zero samples
    ride = build_ride("komoot_loop", telemetry=False)
    path = write_ride(ride, tmp_path / "komoot_loop.gpx")
    (t,) = tv.load_tracks([path], 1.0, with_ext=True)

    assert t.get("power") == [0.0, 0]                # no samples counted
    assert all(v is None for v in t.get("power_pts", []))   # ...so no per-point values
    assert t["dist_km"] > 0.0                        # but the geometry is still there


def test_profile_reads_as_climb_then_descent():
    raw = gpx_points(build_ride("2026_09_07_08_12_47", telemetry=False))
    elev = [e for (_la, _lo, e) in raw]
     # flat -> climb -> peak -> descent -> flat: a rise and then a fall
    assert max(elev) - min(elev) == 200.0
    dist_km, gain_m = _distance_and_gain(raw)
    assert gain_m > 0.0
    assert dist_km > 0.0


def test_grade_and_cumkm_shape():
    raw = gpx_points(build_ride("2026_09_07_08_12_47", telemetry=False))
    grade, cum_km = _grade_and_cumkm(raw)
     # one grade per segment (n-1), one cumulative distance per point (n)
    assert len(grade) == len(raw) - 1
    assert len(cum_km) == len(raw)
    assert cum_km[0] == 0.0
    assert cum_km[-1] > 0.0

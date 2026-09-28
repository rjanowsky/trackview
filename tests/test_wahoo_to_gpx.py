"""The Wahoo ELEMNT JSON -> GPX converter (`wahoo_to_gpx.py`), exercised on a
hand-built minimal ride JSON.  Unlike fit, the Wahoo export is plain JSON, so we
can synthesise the whole file here rather than encode binary messages.

   ride_to_gpx   turns the SAMPLES stream into one gpxpy.GPX track/segment:
                     the "no fix" rows (LAT/LON 0) dropped, the 0 m altitude
                   sentinel filled, STARTTIME + SECS -> UTC "Z" times; LAT/LON
                   are already decimal degrees and KPH already km/h, so both
                   pass through untouched.
    _parse_start    'YYYY/MM/DD HH:MM:SS UTC' -> a tz-aware UTC datetime (a
                   trailing space and the "UTC" suffix are tolerated), raising
                   on a garbage string.
      _ride_date    reads the ride date off the Wahoo-style filename stem; None
                   for a foreign name (the stem is always dated, so - unlike
                   fit - there is no in-file fallback).
     main          a folder of .json -> .gpx, honouring --ext / --since /
                   --until and skipping undated / no-fix rides.
"""
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

import wahoo_to_gpx as wg


# --- a minimal, schema-valid Wahoo ride JSON builder -------------------------
# The real export is {"RIDE": {STARTTIME, RECINTSECS, DEVICETYPE, TAGS,
# SAMPLES}} with one SAMPLE row per second (RECINTSECS).  We synthesise that
# shape so ride_to_gpx has something to turn into a gpxpy.GPX; the toggles zero
# the specific rows Wahoo fills with its "no fix" / "no altitude" sentinels.
def make_ride(path, *, seconds=3, start="2026/09/01 06:07:05 UTC ",
              telemetry=True, no_fix_lead=True, no_fix_tail=False,
              no_alt_lead=True, no_alt=False, all_no_fix=False, bom=True,
              device="Wahoo ELEMNT BOLT", sport="Bike", athlete="Ronald",
              workout="Endurance"):
    """Write a minimal Wahoo ride JSON to `path`: a leading "no fix" row,
    `seconds + 1` samples, and optionally a trailing "no fix" row.
    `no_alt_lead` leaves the first *kept* sample at Wahoo's 0 "no altitude"
    sentinel (filled), `no_alt` zeroes every altitude (a no-elevation ride),
    `all_no_fix` zeroes every position (a no-points ride).  Encoded UTF-8
    *with a BOM* by default -- the real export's encoding, which ride_to_gpx
    tolerates via utf-8-sig."""
    samples = []
    for i in range(seconds + 1):
        samples.append({
            "SECS":  i,
            "KM":    0.0,
            "WATTS": 250 if telemetry else 0,
            "CAD":   90 if telemetry else 0,
            "KPH":   14.0 if telemetry else 0.0,
            "HR":    150 if telemetry else 0,
            "ALT":   300.0 + i * 2,            # 300, 302, 304, 306
            "LAT":   47.0 + i * 0.001,
            "LON":   11.0,
            "SLOPE": 5.0 if telemetry else 0.0,
            "TEMP":  15 if telemetry else 0,
        })
    if all_no_fix:
        for s in samples:
            s["LAT"], s["LON"] = 0.0, 0.0      # a "no fix" row (dropped)
    else:
        if no_fix_lead:
            samples[0]["LAT"], samples[0]["LON"] = 0.0, 0.0
        if no_fix_tail and len(samples) > 1:
            samples[-1]["LAT"], samples[-1]["LON"] = 0.0, 0.0
        if no_alt:
            for s in samples:                   # a no-elevation ride
                s["ALT"] = 0
        elif no_alt_lead and len(samples) > 1:
            idx = 1 if no_fix_lead else 0       # the first *kept* sample
            samples[idx]["ALT"] = 0            # the 0 m "no altitude" sentinel

    tags = {label: val for label, val in
            (("Athlete", athlete), ("Sport", sport), ("Workout Code", workout))
            if val}
    ride = {"STARTTIME": start, "RECINTSECS": 1, "SAMPLES": samples}
    if device is not None:
        ride["DEVICETYPE"] = device
    ride["TAGS"] = tags
    text = json.dumps({"RIDE": ride})
    payload = ("\ufeff" + text) if bom else text   # the real file is BOM'd
    path.write_text(payload, encoding="utf-8")
    return path


def _run_main(gc_dir, out_dir, *extra):
    # main() reads sys.argv, so point it at the temp dirs and call it directly.
    import sys
    old = sys.argv
    sys.argv = ["wahoo_to_gpx.py", "--gc-dir", str(gc_dir),
                "--out-dir", str(out_dir), *extra]
    try:
        wg.main()
    finally:
        sys.argv = old


# --------------------------------------------------------------------------- #
#   ride_to_gpx: the SAMPLES stream -> a gpxpy track
# --------------------------------------------------------------------------- #
class TestRideToGpx:
    def test_no_fix_records_are_dropped(self, tmp_path):
        p = make_ride(tmp_path / "r.json", seconds=3, no_fix_lead=True)
        gpx, info = wg.ride_to_gpx(p)
        pts = gpx.tracks[0].segments[0].points
        assert len(pts) == 3                    # 4 rows, 1 "no fix" lead-in dropped
        assert info["src"] == 4 and info["n"] == 3

    def test_trailing_no_fix_is_also_dropped(self, tmp_path):
        p = make_ride(tmp_path / "r.json", seconds=3,
                      no_fix_lead=True, no_fix_tail=True)
        gpx, info = wg.ride_to_gpx(p)
        assert len(gpx.tracks[0].segments[0].points) == 2       # both ends dropped
        assert info["src"] == 4 and info["n"] == 2

    def test_all_no_fix_yields_no_gpx(self, tmp_path):
        p = make_ride(tmp_path / "r.json", seconds=3, all_no_fix=True)
        gpx, info = wg.ride_to_gpx(p)
        assert gpx is None and info == {}

    def test_altitude_sentinel_is_filled(self, tmp_path):
        p = make_ride(tmp_path / "r.json", seconds=3,
                      no_fix_lead=True, no_alt_lead=True)
        gpx, _ = wg.ride_to_gpx(p)
        eles = [pt.elevation for pt in gpx.tracks[0].segments[0].points]
        assert all(e is not None for e in eles)        # the 0 m point was filled
        assert eles == [304.0, 304.0, 306.0]          # 0 -> filled 304, then 304, 306

    def test_no_altitude_anywhere(self, tmp_path):
        p = make_ride(tmp_path / "r.json", no_alt=True, no_fix_lead=False)
        gpx, info = wg.ride_to_gpx(p)
        assert info["have_alt"] is False
        eles = [pt.elevation for pt in gpx.tracks[0].segments[0].points]
        assert eles and all(e is None for e in eles)   # a real ride, no <ele>

    def test_degrees_and_kmh_pass_through(self, tmp_path):
        p = make_ride(tmp_path / "r.json", telemetry=True,
                      no_fix_lead=False, no_alt_lead=False)
        gpx, _ = wg.ride_to_gpx(p, with_ext=True)
        pt0 = gpx.tracks[0].segments[0].points[0]
        assert abs(pt0.latitude - 47.0) < 1e-3          # already decimal degrees
        speeds = [ext.text for ext in pt0.extensions if ext.tag == "speed_kmh"]
        assert speeds and abs(float(speeds[0]) - 14.0) < 0.01    # already km/h

    def test_times_are_start_time_plus_secs_in_utc(self, tmp_path):
        p = make_ride(tmp_path / "2026_09_01_08_07_05.json",
                      no_fix_lead=False, no_alt_lead=False, no_fix_tail=False)
        gpx, _ = wg.ride_to_gpx(p)
        t = gpx.tracks[0].segments[0].points[0].time
        assert t == datetime(2026, 9, 1, 6, 7, 5, tzinfo=timezone.utc)
        assert "Z" in gpx.to_xml(version="1.1")

    def test_ext_embeds_the_six_telemetry_tags(self, tmp_path):
        p = make_ride(tmp_path / "r.json", telemetry=True)
        gpx, _ = wg.ride_to_gpx(p, with_ext=True)
        xml = gpx.to_xml(version="1.1")
        for tag in ("power", "speed_kmh", "cadence", "heartrate", "grade",
                    "temperature"):
            assert f"<{tag}>" in xml

    def test_plain_ride_has_no_extensions(self, tmp_path):
        p = make_ride(tmp_path / "r.json", telemetry=False, no_fix_lead=False)
        gpx, _ = wg.ride_to_gpx(p, with_ext=True)       # --ext on, no telemetry -> none
        assert "<extensions>" not in gpx.to_xml(version="1.1")

    def test_bom_is_tolerated(self, tmp_path):
        # the real export is UTF-8 *with* a BOM; ride_to_gpx opens utf-8-sig so
        # the BOM can't corrupt the top-level "RIDE" key.
        p = make_ride(tmp_path / "r.json", bom=True)
        assert p.read_bytes().startswith(b"\xef\xbb\xbf")     # a BOM really is there
        gpx, info = wg.ride_to_gpx(p)
        assert info["n"] == 3                          # and it still parsed cleanly


# --------------------------------------------------------------------------- #
#      _parse_start: 'YYYY/MM/DD HH:MM:SS UTC' -> a tz-aware UTC datetime
# --------------------------------------------------------------------------- #
class TestParseStart:
    def test_parses_a_utc_datetime(self):
        assert wg._parse_start("2026/09/01 06:07:05 UTC") == \
            datetime(2026, 9, 1, 6, 7, 5, tzinfo=timezone.utc)

    def test_trailing_space_and_utc_are_tolerated(self):
        # the real export carries a trailing space and a " UTC" suffix
        assert wg._parse_start("    2026/08/15 07:00:00 UTC    ") == \
            datetime(2026, 8, 15, 7, 0, 0, tzinfo=timezone.utc)

    def test_garbage_raises_valueerror(self):
        with pytest.raises(ValueError):
            wg._parse_start("not a starttime")


# --------------------------------------------------------------------------- #
#      _ride_date: the calendar date off the Wahoo-style filename stem
# --------------------------------------------------------------------------- #
class TestRideDate:
    def test_from_wahoo_stem(self):
        # unlike fit, there is no in-file fallback: the stem is always dated
        assert wg._ride_date(Path("2026_09_01_08_07_05.json")) == date(2026, 9, 1)

    def test_nested_path_reads_the_stem(self):
        p = Path("gc/2026/2026_09_01_08_07_05.json")
        assert wg._ride_date(p) == date(2026, 9, 1)

    def test_foreign_name_is_undated(self):
        assert wg._ride_date(Path("ride_with_no_date.json")) is None


# --------------------------------------------------------------------------- #
#     the <desc> carries the device / sport the Wahoo way (no rewording)
# --------------------------------------------------------------------------- #
class TestDesc:
    def test_device_sport_athlete_land_in_desc(self, tmp_path):
        p = make_ride(tmp_path / "r.json",
                      device="Wahoo ELEMNT BOLT", sport="Bike", athlete="Ronald")
        gpx, _ = wg.ride_to_gpx(p)
        desc = gpx.description
        assert "Device: Wahoo ELEMNT BOLT" in desc
        assert "Sport: Bike" in desc
        assert gpx.author_name == "Ronald"

    def test_missing_device_renders_a_question_mark(self, tmp_path):
        p = make_ride(tmp_path / "r.json", device=None)
        gpx, _ = wg.ride_to_gpx(p)
        assert "Device: ?" in gpx.description


# --------------------------------------------------------------------------- #
#   main: a folder of .json -> .gpx, with the date filter composing
# --------------------------------------------------------------------------- #
class TestMain:
      # the output stem is the JSON stem (Wahoo-style YYYY_MM_DD_HH_MM_SS); the
      # STARTTIME inside the file does not affect the output name.
    @staticmethod
    def _two_rides(d):
        make_ride(d / "2026_09_01_08_07_05.json")
        make_ride(d / "2026_08_15_07_00_00.json")

    def test_output_is_named_from_the_json_stem(self, tmp_path):
        self._two_rides(tmp_path)
        out = tmp_path / "out"
        _run_main(tmp_path, out)
        names = sorted(p.name for p in out.glob("*.gpx"))
        assert names == ["2026_08_15_07_00_00.gpx", "2026_09_01_08_07_05.gpx"]

    def test_since_keeps_only_the_later_ride(self, tmp_path):
        self._two_rides(tmp_path)
        out = tmp_path / "out"
        _run_main(tmp_path, out, "--since", "2026-09-01")
        assert [p.name for p in out.glob("*.gpx")] == ["2026_09_01_08_07_05.gpx"]

    def test_until_keeps_only_the_earlier_ride(self, tmp_path):
        self._two_rides(tmp_path)
        out = tmp_path / "out"
        _run_main(tmp_path, out, "--until", "2026-08-31")
        assert [p.name for p in out.glob("*.gpx")] == ["2026_08_15_07_00_00.gpx"]

    def test_undated_ride_is_skipped_when_a_bound_is_set(self, tmp_path, capsys):
        make_ride(tmp_path / "2026_09_01_08_07_05.json")
        make_ride(tmp_path / "ride_with_no_date.json")
        out = tmp_path / "out"
        _run_main(tmp_path, out, "--since", "2000-01-01")
        assert [p.name for p in out.glob("*.gpx")] == ["2026_09_01_08_07_05.gpx"]
        assert "skip (date not in filename)" in capsys.readouterr().out

    def test_ride_without_gps_fixes_is_skipped(self, tmp_path, capsys):
        make_ride(tmp_path / "2026_09_01_08_07_05.json", all_no_fix=True)
        out = tmp_path / "out"
        _run_main(tmp_path, out)
        assert "skip (no GPS fixes)" in capsys.readouterr().out
        assert not list(out.glob("*.gpx"))

    def test_ext_writes_the_telemetry_tags(self, tmp_path):
        make_ride(tmp_path / "2026_09_01_08_07_05.json", telemetry=True)
        out = tmp_path / "out"
        _run_main(tmp_path, out, "--ext")
        xml = (out / "2026_09_01_08_07_05.gpx").read_text()
        for tag in ("power", "speed_kmh", "cadence", "heartrate", "grade",
                    "temperature"):
            assert f"<{tag}>" in xml

    def test_plain_run_omits_extensions(self, tmp_path):
        make_ride(tmp_path / "2026_09_01_08_07_05.json", telemetry=True)
        out = tmp_path / "out"
        _run_main(tmp_path, out)
        xml = (out / "2026_09_01_08_07_05.gpx").read_text()
        assert "<extensions>" not in xml

    def test_empty_dir_reports_nothing_to_convert(self, tmp_path, capsys):
        out = tmp_path / "out"
        _run_main(tmp_path / "empty", out)
        assert "nothing to convert" in capsys.readouterr().out
        assert not out.exists()

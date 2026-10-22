"""The Garmin .fit -> GPX converter (`fit_to_gpx.py`), exercised on a hand-built
minimal .fit file (fitparse is a reader, so we synthesise the bytes here).

   ride_to_gpx   turns the `record` stream into one gpxpy.GPX track/segment:
                    "no fix" records dropped, the -500 m altitude sentinel
                   filled, semicircles -> degrees and m/s -> km/h, UTC "Z" times.
    _ride_date    reads the ride date off the filename, falling back to the
                   file's start time when the name is a bare device serial.
   main          a folder of .fit -> .gpx, honouring --ext / --since / --until.
"""
import struct
import datetime
from datetime import date, timezone

import fit_to_gpx as f2g
from fitparse.records import Crc


# --- a minimal, schema-valid .fit builder ------------------------------------
# One `record` definition (the fields trackview cares about) followed by N data
# messages.  `StandardUnitsDataProcessor` later turns semicircles -> degrees,
# m/s -> km/h and applies the altitude scale/offset.
_FIELDS = [
    (0x00, 0x04, 0x85),    # position_lat    sint32 (semicircles)
    (0x01, 0x04, 0x85),    # position_long   sint32 (semicircles)
    (0x02, 0x02, 0x84),    # altitude        uint16 (scale 5, offset 500)
    (0x03, 0x01, 0x02),    # heart_rate      uint8  (bpm)
    (0x04, 0x01, 0x02),    # cadence         uint8  (rpm)
    (0x06, 0x02, 0x84),    # speed           uint16 (m/s, scale 1000)
    (0x07, 0x02, 0x84),    # power           uint16 (watts)
    (0x09, 0x02, 0x83),    # grade           sint16 (%, scale 100)
    (0x0D, 0x01, 0x01),    # temperature     sint8  (degrees C)
    (0xFD, 0x04, 0x86),    # timestamp       uint32 (s since 1989-12-31)
]
_FMT = "<iiHBBHHhbI"           # one field each, in _FIELDS order
_FIT_EPOCH = 631065600         # unix seconds for 1989-12-31 00:00:00 UTC


def _semicircles(deg):
    return int(round(deg * (2 ** 31) / 180.0))


def _alt_raw(metres):
    # the field carries a +500 m offset and x5 scale, so 0 raw decodes to -500 m
    return int((metres + 500.0) * 5)


def _ts_raw(dt):
    # fitparse adds _FIT_EPOCH back, so store seconds past the FIT epoch
    return int(dt.replace(tzinfo=timezone.utc).timestamp()) - _FIT_EPOCH


def make_fit(path, *, seconds=3, start=None, telemetry=True,
             no_alt_last=True, no_fix_lead=True, all_no_fix=False):
    """Write a minimal .fit: a 'record' definition plus `seconds + 1` records.
    Optionally a leading "no fix" record (dropped) and a final "no altitude"
    record (filled); `all_no_fix` zeroes every record's position (no-points)."""
    start = start or datetime.datetime(2026, 9, 1, 6, 7, 5)
    defs = bytes((0x40, 0x00, 0x00)) + struct.pack("<HB", 0x0014, len(_FIELDS))
    for def_num, size, base_type in _FIELDS:
        defs += bytes((def_num, size, base_type))
    body = defs
    for i in range(seconds + 1):
        t = start + datetime.timedelta(seconds=i + 1)
        lat, lon, alt = (_semicircles(47.0 + i * 0.001),
                         _semicircles(11.0), _alt_raw(300 + i * 2))
        if all_no_fix or (i == 0 and no_fix_lead):
            lat, lon = 0, 0                  # a "no fix" record (dropped)
        elif i == seconds and no_alt_last:
            alt = 0                          # the -500 m "no altitude" sentinel
        metrics = (150, 90, 40000, 250, 500, 15) if telemetry else (0, 0, 0, 0, 0, 0)
        rec = (lat, lon, alt, *metrics, _ts_raw(t))
        body += bytes((0x00,)) + struct.pack(_FMT, *rec)

    # 12-byte header; data_size excludes the trailing CRC, which fitparse reads
    # separately once the body is exhausted.
    hdr = (struct.pack("<B", 12) + bytes((0x20,)) + struct.pack("<H", 0x0210)
           + struct.pack("<I", len(body)) + b".FIT")
    crc = Crc()
    crc.update(hdr + body)
    path.write_bytes(hdr + body + struct.pack("<H", crc.value))
    return path


def _run_main(fit_dir, out_dir, *extra):
    # main() reads sys.argv, so point it at the temp dirs and call it directly
    import sys
    old = sys.argv
    sys.argv = ["fit_to_gpx.py", "--fit-dir", str(fit_dir),
                "--out-dir", str(out_dir), *extra]
    try:
        f2g.main()
    finally:
        sys.argv = old


# --------------------------------------------------------------------------- #
#   ride_to_gpx: the record stream -> a gpxpy track
# --------------------------------------------------------------------------- #
class TestRideToGpx:
    def test_no_fix_records_are_dropped(self, tmp_path):
        p = make_fit(tmp_path / "r.fit", seconds=3, no_fix_lead=True)
        gpx, info = f2g.ride_to_gpx(p)
        pts = gpx.tracks[0].segments[0].points
        assert len(pts) == 3                   # 4 records, 1 "no fix" lead-in dropped
        assert info["src"] == 4 and info["n"] == 3

    def test_all_no_fix_yields_no_gpx(self, tmp_path):
        p = make_fit(tmp_path / "r.fit", seconds=3, all_no_fix=True)
        gpx, info = f2g.ride_to_gpx(p)
        assert gpx is None and info == {}

    def test_altitude_sentinel_is_filled(self, tmp_path):
        p = make_fit(tmp_path / "r.fit", seconds=3, no_alt_last=True)
        gpx, _ = f2g.ride_to_gpx(p)
        eles = [pt.elevation for pt in gpx.tracks[0].segments[0].points]
        assert all(e is not None for e in eles)      # the -500 m point was filled
        assert eles == [302.0, 304.0, 304.0]         # 302 -> 304 -> filled 304

    def test_units_are_degrees_and_km_per_h(self, tmp_path):
        p = make_fit(tmp_path / "r.fit", seconds=3, telemetry=True, no_fix_lead=False)
        gpx, _ = f2g.ride_to_gpx(p, with_ext=True)
        pt0 = gpx.tracks[0].segments[0].points[0]
        assert abs(pt0.latitude - 47.0) < 1e-3        # semicircles -> degrees
        speeds = [ext.text for ext in pt0.extensions if ext.tag == "speed_kmh"]
        assert speeds and abs(float(speeds[0]) - 144.0) < 0.5     # 40 m/s -> 144 km/h

    def test_times_are_utc_with_z(self, tmp_path):
        p = make_fit(tmp_path / "r.fit", seconds=2, no_fix_lead=False, no_alt_last=False)
        gpx, _ = f2g.ride_to_gpx(p)
        t = gpx.tracks[0].segments[0].points[0].time
        assert t == datetime.datetime(2026, 9, 1, 6, 7, 6, tzinfo=timezone.utc)
        assert "Z" in gpx.to_xml(version="1.1")

    def test_ext_embeds_the_six_telemetry_tags(self, tmp_path):
        p = make_fit(tmp_path / "r.fit", seconds=3, telemetry=True)
        gpx, _ = f2g.ride_to_gpx(p, with_ext=True)
        xml = gpx.to_xml(version="1.1")
        for tag in ("power", "speed_kmh", "cadence", "heartrate", "grade", "temperature"):
            assert f"<{tag}>" in xml

    def test_plain_ride_has_no_extensions(self, tmp_path):
        p = make_fit(tmp_path / "r.fit", seconds=3, telemetry=False)
        gpx, _ = f2g.ride_to_gpx(p, with_ext=False)
        assert "<extensions>" not in gpx.to_xml(version="1.1")


# --------------------------------------------------------------------------- #
#     device / sport: the FIT enum words reworded to the Wahoo voice
# --------------------------------------------------------------------------- #
class _Msg:  # a stand-in for a fitparse device_info / session message
    def __init__(self, **vals):
        self._vals = vals
    def get_value(self, name):
        return self._vals.get(name)


class TestReword:
    def test_device_wahoo_fitness_becomes_element_bolt(self):
        assert f2g._device_name([_Msg(manufacturer="wahoo_fitness")], None) \
               == "Wahoo ELEMNT BOLT"

    def test_unknown_device_passes_through(self):
        assert f2g._device_name([_Msg(manufacturer="garmin")], None) == "garmin"

    def test_product_fallback_is_not_reworded(self):
        assert f2g._device_name([_Msg(product=42)], None) == "product #42"

    def test_sport_cycling_becomes_bike(self):
        assert f2g._sport_name(_Msg(sport="cycling")) == "Bike"

    def test_unknown_sport_passes_through(self):
        assert f2g._sport_name(_Msg(sport="running")) == "running"

    def test_sport_none_when_absent(self):
        assert f2g._sport_name(None) is None
        assert f2g._sport_name(_Msg()) is None


# --------------------------------------------------------------------------- #
#    _ride_date: filename first, then the file's start time
# --------------------------------------------------------------------------- #
class TestRideDate:
    def test_from_filename_wins(self, tmp_path):
        # the filename date wins even though the file's start time disagrees
        p = make_fit(tmp_path / "2026_09_01_060705_12345.fit", start=datetime.datetime(2026, 8, 1))
        assert f2g._ride_date(p) == date(2026, 9, 1)

    def test_falls_back_to_file_when_name_is_a_serial(self, tmp_path):
        p = make_fit(tmp_path / "12345678.fit", start=datetime.datetime(2026, 8, 15, 7, 0, 0))
        assert f2g._ride_date(p) == date(2026, 8, 15)


# --------------------------------------------------------------------------- #
#   main: a folder of .fit -> .gpx, with the date filter composing
# --------------------------------------------------------------------------- #
class TestMain:
    # no_fix_lead=False so the ride's first *kept* record lands one second on,
    # making the start-time-derived output stem clean and matching the time the
    # filename embeds: the output stem is the ride start time (Wahoo-style),
    # never the .fit stem.
    @staticmethod
    def _two_rides(d):
        make_fit(d / "2026_09_01_080705_12345.fit",
                 start=datetime.datetime(2026, 9, 1, 8, 7, 4), no_fix_lead=False)
        make_fit(d / "2026_08_15_070000_99999.fit",
                 start=datetime.datetime(2026, 8, 15, 6, 59, 59), no_fix_lead=False)

    def test_output_is_named_from_the_start_time(self, tmp_path):
        self._two_rides(tmp_path)
        out = tmp_path / "out"
        _run_main(tmp_path, out)
        names = sorted(p.name for p in out.glob("*.gpx"))
        assert names == ["2026_08_15_07_00_00.gpx", "2026_09_01_08_07_05.gpx"]

    def test_long_garmin_name_does_not_leak_into_output(self, tmp_path):
        # a real Connect export name carries a device model + serial; that must
        # not become the GPX stem - only the ride start time does.
        name = "2026-09-01-060705-ELEMNT BOLT A8C5-660-0_2026_09_01_08_07_05.fit"
        make_fit(tmp_path / name, start=datetime.datetime(2026, 9, 1, 8, 7, 4),
                 no_fix_lead=False)
        out = tmp_path / "out"
        _run_main(tmp_path, out)
        got = list(out.glob("*.gpx"))
        assert [g.name for g in got] == ["2026_09_01_08_07_05.gpx"]
        assert not any(("ELEMNT" in g.name) or ("660" in g.name) for g in got)

    def test_since_keeps_only_the_later_ride(self, tmp_path):
        self._two_rides(tmp_path)
        out = tmp_path / "out"
        _run_main(tmp_path, out, "--since", "2026-09-01")
        assert [p.name for p in out.glob("*.gpx")] == ["2026_09_01_08_07_05.gpx"]

    def test_empty_dir_reports_nothing_to_convert(self, tmp_path, capsys):
        out = tmp_path / "out"
        _run_main(tmp_path / "empty", out)
        assert "nothing to convert" in capsys.readouterr().out
        assert not out.exists()

    def test_default_run_creates_the_data_dir_fit_folder(self, tmp_path, capsys):
        # a default (no --fit-dir, no explicit files) run now creates the input dir
        # -- and its parents -- so a first run yields a clean ~/.trackview/fit to fill,
        # not a "nothing found in ~/.trackview/fit" over a missing private dir.  The
        # --fit-dir default is read from config at *import* time, so both are
        # reloaded after $TRACKVIEW_HOME is set (the same pattern as test_config.py).
        import os
        import importlib
        old = os.environ.get("TRACKVIEW_HOME")
        os.environ["TRACKVIEW_HOME"] = str(tmp_path / "home")
        import sys
        sys.argv = ["fit_to_gpx.py", "--out-dir", str(tmp_path / "out")]
        try:
            # the --fit-dir default is baked from config at import time, so reload
            # the *config* module (the source of DATA_DIR/IN_DIR) as well as f2g,
            # the way test_config.py does -- a bare f2g reload keeps the stale
            # config binding.
            import trackview.config as config
            importlib.reload(config)
            importlib.reload(f2g)
            f2g.main()
            fit = tmp_path / "home" / "fit"
            assert fit.is_dir() and not any(fit.iterdir())   # made, but empty
            assert "nothing to convert" in capsys.readouterr().out
        finally:
            sys.argv = ["fit_to_gpx.py"]
            if old is not None:
                os.environ["TRACKVIEW_HOME"] = old
            else:
                os.environ.pop("TRACKVIEW_HOME", None)
            importlib.reload(f2g)
            importlib.reload(config)

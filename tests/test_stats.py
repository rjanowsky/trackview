"""[Phase 4 / 4.1] The stats / ride-log report writers -- pure, offline.

     _stats_columns   the shared (header, numeric?, per-ride formatter, per-group
                      summary) column list, with the --ext telemetry columns appended
                      only when asked;
    write_stats      the per-device .txt ride-log (one row per ride + one "Summary"
                      totals row per device);
    write_csv        the same columns as a bare .csv (no padding, no totals).

All three are pure over the already-parsed ride dicts (their distance / gain /
duration plus the [sum, count] telemetry pairs), so the suite builds bare ride
dicts by hand and points the writers at a tmp_path -- no GPX, no network, no
figure.  The only behaviour that touches the filesystem is the two writers, which
are asserted through the file they produce (their stdout "wrote ..." line is the
side effect, not the result).
"""
from trackview.stats import _stats_columns, write_stats, write_csv


# --- a bare ride dict carrying just the fields the writers read ---------------
# distance / gain / a measured duration; `ext` adds the [sum, count] telemetry
# pairs (power / speed / cadence / hr / temp) + the steepest grade a --ext run
# shows.  A ride without `ext` is a plain, telemetry-free track -> a "-" cell.
def ride(name, *, dist_km=12.5, gain_m=180.0, duration_s=3600.0, device=None,
         ext=False):
    t = {"name": name, "device": device, "dist_km": dist_km,
         "gain_m": gain_m, "duration_s": duration_s, "grade": []}
    if ext:
        t["power"] = [5000.0, 10.0]
        t["speed"] = [300.0, 10.0]
        t["cadence"] = [900.0, 10.0]
        t["hr"] = [1400.0, 10.0]
        t["temp"] = [150.0, 10.0]
        t["grade"] = [3.0, 8.0, 6.0]
    return t


# The two shared, always-on columns (before --ext) and the one that always closes
# the log; --ext splices its telemetry block in before the closing Device column.
BASE_HEAD = ["Ride", "Dist (km)", "Duration", "Gain (m)", "Device"]
EXT_HEAD = ["Ride", "Dist (km)", "Duration", "Gain (m)", "Calories (kcal)",
            "Avg power (W)", "Avg speed (km/h)", "Avg cadence (rpm)", "Avg HR (bpm)",
            "Max grade (%)", "Avg temperature (°C)", "Device"]


class TestStatsColumns:
    def test_base_columns_when_no_ext(self):
        cols = _stats_columns(show_ext=False)
        assert [c[0] for c in cols] == BASE_HEAD

    def test_ext_columns_are_appended_when_ext(self):
        cols = _stats_columns(show_ext=True)
        assert [c[0] for c in cols] == EXT_HEAD

    def test_ext_is_a_superset_of_base(self):
        base = [c[0] for c in _stats_columns(False)]
        ext = [c[0] for c in _stats_columns(True)]
        # the ext columns are spliced in before the closing Device column; the
        # base headers stay in place and the device label still closes.
        assert ext[:4] == base[:4]
        assert ext[-1] == "Device" and ext[-1] == base[-1]
        assert set(base) <= set(ext)

    def test_device_column_always_closes_the_log(self):
        assert _stats_columns(False)[-1][0] == "Device"
        assert _stats_columns(True)[-1][0] == "Device"

    def test_numeric_flag_marks_the_value_columns(self):
        cols = _stats_columns(True)
        by_header = {c[0]: c[1] for c in cols}
        assert by_header["Dist (km)"] is True
        assert by_header["Gain (m)"] is True
        assert by_header["Avg power (W)"] is True
        assert by_header["Max grade (%)"] is True
        # the Ride / Duration / Device columns are text, not numbers
        assert by_header["Ride"] is False
        assert by_header["Duration"] is False
        assert by_header["Device"] is False

    def test_each_column_is_a_4_tuple(self):
        for c in _stats_columns(True):
            assert len(c) == 4           # (header, numeric?, per-ride, per-group)
            assert isinstance(c[1], bool)
            assert callable(c[2]) and callable(c[3])

    def test_ext_columns_absent_when_no_ext(self):
        headers = [c[0] for c in _stats_columns(False)]
        assert "Avg power (W)" not in headers
        assert "Max grade (%)" not in headers


class TestPerRideAndGroupFormatters:
    # the per-ride (index 2) and per-group (index 3) formatters are the heart of
    # the report: a ride cell, and a device-group's totals cell.
    def test_ride_row_values(self):
        cols = _stats_columns(show_ext=True)
        t = ride("2026_01_15_08_00_00", dist_km=12.5, gain_m=180.0,
                 duration_s=3600.0, device="Wahoo ELEMNT BOLT", ext=True)
        cells = [c[2](t) for c in cols]
        by_header = dict(zip([c[0] for c in cols], cells))
        assert by_header["Ride"] == "2026-01-15"       # _title_name reformats the stem
        assert by_header["Dist (km)"] == "12.5"
        assert by_header["Gain (m)"] == "180"
        assert by_header["Duration"] == "1h 00m"
           # avg = sum / count over the [sum, count] telemetry pairs; power's "5.0f" pads to width 5
        assert by_header["Avg power (W)"] == "  500"
        assert by_header["Avg speed (km/h)"] == "30.0"
        assert by_header["Avg cadence (rpm)"] == " 90"        # "3.0f" pads to width 3
        assert by_header["Avg HR (bpm)"] == "140"
        assert by_header["Max grade (%)"] == "8.0"      # steepest graded segment
        assert by_header["Device"] == "Wahoo ELEMNT BOLT"

    def test_telemetry_free_ride_shows_dash(self):
        cols = _stats_columns(show_ext=True)
        t = ride("komoot_loop", device=None, ext=False)   # no telemetry, no device
        by_header = dict(zip([c[0] for c in cols], [c[2](t) for c in cols]))
        assert by_header["Calories (kcal)"] == "-"
        assert by_header["Avg power (W)"] == "-"
        assert by_header["Max grade (%)"] == "-"       # no graded segment
        assert by_header["Device"] == "unknown"

    def test_group_summary_is_the_device_total(self):
        cols = _stats_columns(show_ext=True)
        g = [ride("2026_01_15_08_00_00", dist_km=12.5, gain_m=180.0,
                  duration_s=3600.0, device="Wahoo ELEMNT BOLT", ext=True),
             ride("2026_01_16_08_00_00", dist_km=8.0, gain_m=90.0,
                  duration_s=1800.0, device="Wahoo ELEMNT BOLT", ext=True)]
        cells = [c[3](g) for c in cols]
        by_header = dict(zip([c[0] for c in cols], cells))
        assert by_header["Ride"] == "Summary"
        assert by_header["Dist (km)"] == "20"           # 12.5 + 8.0, 0-dp total
        assert by_header["Gain (m)"] == "270"
        assert by_header["Device"] == "Wahoo ELEMNT BOLT"

    def test_group_average_is_point_weighted(self):
        cols = _stats_columns(show_ext=True)
        # two rides, same count: the group avg is (1000+3000)/20 = 200.0 W
        g = [ride("a", device="Garmin Edge", ext=True),
             ride("b", device="Garmin Edge", ext=True)]
        g[0]["power"] = [1000.0, 10.0]
        g[1]["power"] = [3000.0, 10.0]
        by_header = dict(zip([c[0] for c in cols],
                             [c[3](g) for c in cols]))
        assert by_header["Avg power (W)"] == "  200"       # (1000+3000)/20 = 200 W, width-5 padded


class TestWriteStats:
    def test_writes_one_row_per_ride_plus_a_summary_row(self, tmp_path):
        out = tmp_path / "sub" / "stats.txt"      # parent is created by the writer
        tracks = [ride("2026_01_15_08_00_00", dist_km=12.5, gain_m=180.0,
                       device="Wahoo ELEMNT BOLT"),
                  ride("komoot_loop", dist_km=8.0, gain_m=90.0, device=None)]
        write_stats(tracks, out, show_ext=False)
        text = out.read_text()
        # title names the ride count
        assert text.startswith("trackview - 2 rides")
        # one row per ride
        assert "2026-01-15" in text and "komoot_loop" in text
        # a per-device Summary totals row, with the device label closing
        assert "Summary" in text
        assert text.count("Summary") >= 2           # the two device groups (Wahoo + unknown)
        assert "12.5" in text and "8.0" in text

    def test_two_devices_give_two_summary_rows(self, tmp_path):
        out = tmp_path / "stats.txt"
        tracks = [ride("2026_01_15_08_00_00", dist_km=12.5, gain_m=180.0,
                       device="Wahoo ELEMNT BOLT"),
                  ride("2026_01_16_08_00_00", dist_km=8.0, gain_m=90.0,
                       device="Garmin Edge")]
        write_stats(tracks, out, show_ext=False)
        text = out.read_text()
        assert "Wahoo ELEMNT BOLT" in text
        assert "Garmin Edge" in text

    def test_ext_columns_appear_only_with_show_ext(self, tmp_path):
        out = tmp_path / "stats.txt"
        tracks = [ride("2026_01_15_08_00_00", device="Wahoo ELEMNT BOLT", ext=True)]
        write_stats(tracks, out, show_ext=False)
        assert "Avg power (W)" not in out.read_text()
        write_stats(tracks, out, show_ext=True)
        assert "Avg power (W)" in out.read_text()


class TestWriteCsv:
    def test_header_and_one_row_per_ride_no_totals(self, tmp_path):
        out = tmp_path / "rides.csv"
        tracks = [ride("2026_01_15_08_00_00", dist_km=12.5, gain_m=180.0,
                       device="Wahoo ELEMNT BOLT"),
                  ride("komoot_loop", dist_km=8.0, gain_m=90.0, device=None)]
        write_csv(tracks, out, show_ext=False)
        lines = out.read_text().splitlines()
        assert lines[0].split(";") == BASE_HEAD       # the header row
        assert len(lines) == 1 + len(tracks)          # header + one row per ride
        assert "Summary" not in out.read_text()        # no totals row in the CSV
        assert any("12.5" in ln and "Wahoo ELEMNT BOLT" in ln for ln in lines[1:])

    def test_default_delimiter_is_semicolon(self, tmp_path):
        out = tmp_path / "rides.csv"
        write_csv([ride("2026_01_15_08_00_00", device="Wahoo ELEMNT BOLT")],
                  out, show_ext=False)
        head = out.read_text().splitlines()[0]
        assert ";" in head

    def test_comma_delimiter(self, tmp_path):
        out = tmp_path / "rides.csv"
        write_csv([ride("2026_01_15_08_00_00", device="Wahoo ELEMNT BOLT")],
                  out, show_ext=False, delimiter=",")
        head = out.read_text().splitlines()[0]
        assert "," in head

    def test_numeric_cells_are_decimal_normalised(self, tmp_path):
        out = tmp_path / "rides.csv"
        # a big distance the .txt would group as "1,234" -> the CSV wants "1234"
        write_csv([ride("2026_01_15_08_00_00", dist_km=1234.6, gain_m=12345.0,
                        device="Wahoo ELEMNT BOLT")], out, show_ext=False)
        text = out.read_text()
        for row in text.splitlines()[1:]:
            assert "1,234" not in row           # no thousands grouping
        assert "1234.6" in text and "12345" in text

    def test_dash_marker_survives_into_the_csv(self, tmp_path):
        out = tmp_path / "rides.csv"
        # a telemetry-free ride -> a "-" in the ext cells, even with show_ext on
        write_csv([ride("komoot_loop", device=None, ext=False)],
                  out, show_ext=True)
        text = out.read_text()
        assert " -" in text or "-;" in text or "-," in text or '"-"' in text

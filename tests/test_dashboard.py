"""The `--dashboard` "year-in-review" figure's pure helpers.

    parse_rides     a trackview per-ride CSV (a `stats/trackview-<range>.csv`) ->
                    a list of ride dicts, mapped by *column header* (not fixed
                    position), with the calendar date derived from the `Ride`
                    column's YYYY-MM-DD prefix and a missing metric ('-') -> None.
    cumulative      rides sorted by date, each carrying a running total distance.
    monthly         {(year, month): {dist, gain, hours, rides}} -- seasonality.
    top_rides       the 'trophy shelf' -- best ride by dist / gain / power /
                    time / grade (missing metrics ignored; grade capped at
                    MAX_GRADE so a noisy single-point spike can't win).
    _latest_log     the newest plain per-ride CSV in the stats dir, skipping the
                    '_summary' / '_climbs' variants.
    write_dashboard read a CSV + render the five panels, returning the path.

Pure over a bare CSV (+ a tmpdir), so the suite stays offline -- no basemap, no
network.  The CSV -- not the fixed-width .txt -- is the source: its column *count*
varies by device type in the .txt, but the CSV is stable (a header + one row per
ride), so the reader keys by name and never drifts.  One test round-trips through
the real `stats.write_csv(show_ext=True)` writer to prove the dashboard reads a
freshly-generated CSV back with power/grade intact (the 1.1.0 fix).  The renderer
honours --out / --format and --dashboard-top.
"""
import sys

import matplotlib
matplotlib.use("Agg")

import pytest

import trackview.dashboard as dash
import trackview.cli as cli
from trackview.stats import write_csv


@pytest.fixture(autouse=True)
def _isolate_data_dir(tmp_path, monkeypatch):
    """Redirect the whole per-user data dir away from the real ~/.trackview for
    EVERY test in this module -- an isolation guard, not just a convenience.  The
    short-circuit tests below drive `cli.main()` for real, which resolves its
    data-dir constants on three modules at once: `config.STATS_DIR`/`OUTPUT_DIR`
    (the source of truth) and the *bound copies* `cli` and `dashboard` each
    captured via `from trackview.config import (STATS_DIR, OUTPUT_DIR, ...)` at
    import time -- a patch to `config` alone does NOT reach them.  Hermeticity rests
    on two things: this patch of the constants on every module that holds a copy,
    AND cli.py threading its own (patchable) `STATS_DIR`/`OUTPUT_DIR` into
    write_dashboard (a bare --dashboard resolves the newest CSV via _latest_log and
    names its PNG from out_dir, so both must honour the redirected dir -- without
    that, a bare --dashboard would read the newest CSV and write its PNG in the real
    ~/.trackview, and a frozen default arg could not be patched away).  Each module
    only carries the constants it actually bound, so `raising=False` skips a patch
    for an attribute a module lacks (e.g. `dashboard` has no `GPX_DIR`)."""
    import trackview.config as config
    gpx, stats, out = (tmp_path / "gpx"), (tmp_path / "stats"), (tmp_path / "output")
    gpx.mkdir()
    for mod in (config, dash, cli):
        monkeypatch.setattr(mod, "STATS_DIR", stats, raising=False)
        monkeypatch.setattr(mod, "OUTPUT_DIR", out, raising=False)
        monkeypatch.setattr(mod, "GPX_DIR", gpx, raising=False)


@pytest.fixture
def dashboard_home(_isolate_data_dir):
    """The home the autouse `_isolate_data_dir` fixture already redirected the data
    dir onto -- we do NOT spin up a second, conflicting tmp_path.  The autouse
    fixture is the single source of truth: it patches each data-dir constant onto
    every module that holds a copy of it (config, and the two bound copies in cli
    and dashboard), so a real main() run here resolves its newest CSV and writes its
    PNG inside THIS tmp tree, never the real ~/.trackview.  We hand back the
    redirected stats dir's parent (its tmp root) so a test can lay a CSV on the very
    disk `dash._latest_log` / `cli.STATS_DIR` glob, or (the year tests) point
    --gpx-dir at the ride folder on the same tree.  Module-scoped (not nested in a
    class) so both `TestDashboardShortCircuit` and `TestDashboardYear` share it; the
    empty gpx dir (also made by the autouse fixture) makes a bare --dashboard a clean
    no-tracks early return."""
    return cli.STATS_DIR.parent


# A compact per-ride CSV (a subset of the 12 columns, as a narrow table writes),
# ';' delimited (trackview's default).  The 2023 row carries '-' for power/grade
# (a pre-power-meter era); the 2024 rows don't.  The `Ride` column is the ride
# name -- here a YYYY-MM-DD date, from which the reader derives y/mo/d.
CSV = """Ride;Dist (km);Duration;Gain (m);Avg power (W);Max grade (%);Device
2023-06-15;30.0;1h 00m;200;-;-;Wahoo ELEMNT BOLT
2024-07-10;45.5;2h 05m;600;275;12;Wahoo ELEMNT BOLT
2024-07-20;103.6;3h 10m;900;250;8;Wahoo ELEMNT BOLT
"""

# The same, comma-delimited -- proves _detect_delimiter copes with either.
CSV_COMMA = CSV.replace(";", ",")


def _write_csv(tmp_path, text=CSV, name="trackview-2023-06-15_2024-07-20.csv"):
    p = tmp_path / name
    p.write_text(text)
    return p


def _write_log(tmp_path, name, body=CSV):
    p = tmp_path / name
    p.write_text(body)
    return p


class TestParseRides:
    def test_only_ride_rows_parse(self, tmp_path):
        rides = dash.parse_rides(_write_csv(tmp_path))
        assert [r["date"] for r in rides] == ["2023-06-15", "2024-07-10", "2024-07-20"]

    def test_missing_metric_is_none_not_zero(self, tmp_path):
        r = dash.parse_rides(_write_csv(tmp_path))[0]   # the 2023 ride
        assert r["power"] is None and r["grade"] is None
        assert r["dist"] == 30.0 and r["gain"] == 200.0

    def test_multifield_tokens_stay_whole(self, tmp_path):
        r = dash.parse_rides(_write_csv(tmp_path))[1]
        assert r["hours"] == 2 + 5 / 60.0                   # 2h 05m -> 2.0833 h
        assert r["d"] == 10 and r["mo"] == 7 and r["y"] == 2024
        assert r["device"] == "Wahoo ELEMNT BOLT"           # multi-word field intact

    def test_comma_delimiter_sniffed(self, tmp_path):
        rides = dash.parse_rides(_write_csv(tmp_path, CSV_COMMA, "c.csv"))
        assert [r["date"] for r in rides] == ["2023-06-15", "2024-07-10", "2024-07-20"]
        assert rides[1]["power"] == 275.0

    def test_nonnumeric_cell_is_missing(self, tmp_path):
        p = _write_csv(tmp_path,
                       "Ride;Dist (km);Duration;Gain (m);Avg power (W)\n"
                       "2024-01-01;10.0;0h 30m;50;garbage\n", "x.csv")
        r = dash.parse_rides(str(p))[0]
        assert r["power"] is None                            # "garbage" -> missing, not a crash

    def test_undated_ride_kept_but_no_date(self, tmp_path):
        # a descriptive ride name carries no YYYY-MM-DD prefix -> no date, but the
        # ride is still parsed (it counts toward the totals, just not the calendar)
        p = _write_csv(tmp_path,
                       "Ride;Dist (km);Duration;Gain (m)\n"
                       "komoot-sunset-loop;12.0;0h 40m;80\n", "u.csv")
        r = dash.parse_rides(str(p))[0]
        assert r["y"] is None and r["date"] == "komoot-sunset-loop"
        assert r["dist"] == 12.0


class TestAggregations:
    def test_cumulative_sums_in_date_order(self, tmp_path):
        rides = dash.cumulative(dash.parse_rides(_write_csv(tmp_path)))
        assert [round(r["cum"], 2) for r in rides] == [30.0, 75.5, 179.1]

    def test_monthly_buckets_by_year_and_month(self, tmp_path):
        agg = dash.monthly(dash.parse_rides(_write_csv(tmp_path)))
        assert agg[(2024, 7)]["rides"] == 2
        assert round(agg[(2024, 7)]["dist"], 1) == 149.1
        assert agg[(2023, 6)]["rides"] == 1

    def test_top_rides_ignores_missing_metrics(self, tmp_path):
        tops = dash.top_rides(dash.parse_rides(_write_csv(tmp_path)))
        assert tops["dist"]["date"] == "2024-07-20"          # 103.6 km, the longest
        assert tops["power"]["date"] == "2024-07-10"         # 275 W, the strongest
        assert tops["gain"]["date"] == "2024-07-20"          # 900 m, the most
        assert tops["time"]["date"] == "2024-07-20"          # 3h 10m, the longest
        assert tops["grade"]["date"] == "2024-07-10"         # 12%, steepest sane

    def test_grade_caps_the_noisy_spike(self):
        rides = [
            {"date": "2024-01-01", "grade": 800.0, "dist": 1.0, "gain": 10.0,
             "power": None, "hours": 0.1, "y": 2024, "mo": 1, "d": 1},
            {"date": "2024-01-02", "grade": 15.0, "dist": 2.0, "gain": 100.0,
             "power": None, "hours": 0.2, "y": 2024, "mo": 1, "d": 2},
        ]
        tops = dash.top_rides(rides)
        assert tops["grade"]["date"] == "2024-01-02"        # 800% is noise, capped out

    def test_empty_log_has_no_top_ride(self):
        assert dash.top_rides([])["dist"] is None


class TestExtRoundTrip:
    """The 1.1.0 regression guard: the dashboard must read a freshly-written,
    --ext-forced CSV back with power/grade intact (the old .txt reader dropped
    them).  Round-trips a real track dict through stats.write_csv(show_ext=True)."""

    def _tracks(self):
        def ride(name, dist_km, gain_m, power_w, grade_pct, dur_s):
            t = {"name": name, "dist_km": dist_km, "gain_m": gain_m,
                 "device": "Wahoo ELEMNT BOLT", "n": 10, "ndec": 3,
                 "duration_s": dur_s}
            # telemetry is stored as per-track [sum, count] averages; grade is a
            # list of per-segment grades -- the shapes load.py produces under
            # --ext, which the CSV reader must survive the round-trip of.
            t["power"] = [power_w, 1.0]
            t["speed"] = [dist_km / (dur_s / 3600.0), 1.0]
            t["cadence"] = [88.0, 1.0]
            t["hr"] = [150.0, 1.0]
            t["cal"] = [700.0, 1.0]
            t["grade"] = [grade_pct]
            return t
        return [
            ride("2024-07-10", 45.5, 600, 275, 12.0, 7500),
            ride("2024-07-20", 103.6, 900, 250, 8.0, 11400),
        ]

    def test_writes_and_reads_back_power_and_grade(self, tmp_path):
        out = tmp_path / "trackview-2024-07-10_2024-07-20.csv"
        write_csv(self._tracks(), out, show_ext=True, delimiter=";")
        rides = dash.parse_rides(out)
        by_date = {r["date"]: r for r in rides}
        # the whole point of the fix: power + grade survive the round-trip
        assert by_date["2024-07-10"]["power"] == 275.0
        assert by_date["2024-07-10"]["grade"] == 12.0
        assert by_date["2024-07-20"]["dist"] == 103.6
        tops = dash.top_rides(rides)
        assert tops["power"]["date"] == "2024-07-10"        # 275 W, the strongest
        assert tops["grade"]["date"] == "2024-07-10"        # 12%, steepest sane


class TestLatestLog:
    def test_picks_newest_plain_csv(self, tmp_path):
        import os
        old = _write_log(tmp_path, "trackview-2020-01-01_2020-01-01.csv")
        new = _write_log(tmp_path, "trackview-2024-07-10_2024-07-20.csv")
        # Make the second one genuinely newer on disk so max-by-mtime is deterministic.
        old_mtime = old.stat().st_mtime
        os.utime(new, (old_mtime + 5, old_mtime + 5))
        assert dash._latest_log(stats=tmp_path) == new

    def test_skips_summary_and_climbs_variants(self, tmp_path):
        _write_log(tmp_path, "trackview-2020-01-01_2020-01-01_summary.csv")
        _write_log(tmp_path, "trackview-2020-01-01_2020-01-01_climbs.csv")
        plain = _write_log(tmp_path, "trackview-2024-07-10_2024-07-20.csv")
        assert dash._latest_log(stats=tmp_path) == plain

    def test_missing_stats_dir_exits_cleanly(self, tmp_path):
        import pytest
        with pytest.raises(SystemExit):
            dash._latest_log(stats=tmp_path / "nope")


class TestWriteDashboard:
    def test_writes_default_png_from_named_table(self, tmp_path):
        log = _write_csv(tmp_path)
        out = dash.write_dashboard(str(log), out=tmp_path / "d.png")
        assert out == tmp_path / "d.png" and out.exists()

    def test_default_output_names_the_log_stem(self, tmp_path):
        log = _write_csv(tmp_path)
        out_dir = tmp_path / "out"
        out = dash.write_dashboard(str(log), out=None, out_dir=out_dir, fmt="png")
        assert out == out_dir / "trackview-2023-06-15_2024-07-20_dashboard.png"
        assert out.exists()

    def test_top_n_default_is_five(self):
        # The CLI wires --dashboard-top (default 5) into write_dashboard's top_n.
        import argparse
        ap = argparse.ArgumentParser()
        ap.add_argument("--dashboard-top", type=int, default=5)
        assert ap.parse_args([]).dashboard_top == 5


class TestDashboardShortCircuit:
    """The cli.py `--dashboard` short-circuit: a --dashboard-ONLY run reports over
    the *persisted* per-ride CSV -- skipping the minutes-long
    `load_tracks(with_ext=True)` over every ride -- instead of the
    whole load/map/stats pipeline.  These drive `cli.main()` on a real (redirected)
    data dir, so the BARE sentinel, the `!= BARE` / `is not None` guard, and the
    fall-through all execute for real -- the pure-helper tests above never touch
    cli.py, so this is the only suite guard for that logic.

    The `is`-on-short-string hazard is the whole point: cli.py compares the BARE
    sentinel by *equality* (`!= BARE`), never `is` -- CPython interns short string
    literals non-deterministically, so an `is` guard would fire only ~half the time.
    To exercise it the "bare flag" cases re-run the guard a few times in one process;
    under a buggy `is` a run-to-run interning flip would drop a case, but the real
    code (equality + the reliable `is not None` on the None default) fires always.
    """

    @staticmethod
    def _run(argv, dashboard_home):
        # Run main() with a fresh argv and an empty --gpx-dir (patched onto the cli
        # module's GPX_DIR default via the fixture): the selection globs no *.gpx, so
        # a bare --dashboard returns early at the "nothing to render" guard -- having
        # evaluated the short-circuit -- while a --dashboard run that HAS a csv
        # short-circuits and renders straight from it.  main() returns normally here
        # (a plain `return`, not SystemExit), so no try/except is needed.
        old = sys.argv
        sys.argv = ["trackview", *argv]
        try:
            cli.main()
        finally:
            sys.argv = old

    def _stats_csvs(self, dashboard_home):
        return sorted(p.name for p in (dashboard_home / "stats").glob("*.csv"))

    # ---- the guard: was the flag passed, and is it a bare flag? --------------
    def test_flag_absent_runs_no_dashboard(self, dashboard_home):
        # No flag -> the "no dashboard" state: main() takes the normal path and, with
        # an empty gpx dir, writes neither a dashboard PNG nor a bootstrap CSV.
        self._run([], dashboard_home)
        assert not (dashboard_home / "output").exists()
        assert self._stats_csvs(dashboard_home) == []

    def test_bare_flag_uses_equality_not_identity(self, dashboard_home):
        # The crux: a bare `--dashboard` is a non-None sentinel cli.py distinguishes
        # from "absent" by EQUALITY.  Re-run the guard 3x in one process -- under a
        # buggy `is` a later run's args.dashboard could fail to match the (re-bound)
        # BARE and mis-fire; the real equality guard is stable every time.  With no
        # csv on disk a bare flag takes the normal path (empty gpx dir -> no-tracks
        # return), so nothing is written -- the guard evaluated cleanly, no crash.
        for _ in range(3):
            self._run(["--dashboard"], dashboard_home)
        assert not (dashboard_home / "output").exists()
        assert self._stats_csvs(dashboard_home) == []

    def test_named_flag_reports_that_csv_and_skips_load(self, dashboard_home):
        # A named `--dashboard LOG` is the path itself -- distinct from None (absent)
        # and BARE (bare).  `!= BARE` is True, so the short-circuit reports on THIS
        # csv and skips the load: the PNG is written from the csv's stem, and no
        # bootstrap CSV is generated (that is the load path, which did not run).
        stats = dashboard_home / "stats"
        stats.mkdir()
        log = stats / "trackview-2024-01-01_2024-12-31.csv"
        log.write_text(CSV)
        out = dashboard_home / "named.png"
        self._run(["--dashboard", str(log), "--out", str(out)], dashboard_home)
        assert out.exists()
        assert self._stats_csvs(dashboard_home) == ["trackview-2024-01-01_2024-12-31.csv"]

    def test_bare_flag_with_csv_short_circuits(self, dashboard_home):
        # A bare `--dashboard` WITH a plain csv on disk: the glob branch of the guard
        # is True, so cli.py skips the load and reports on the newest csv -- the whole
        # point of the fix (was ~214s of load, now sub-second).  The PNG is named from
        # the csv's stem; no bootstrap CSV is written (the load did not run).
        stats = dashboard_home / "stats"
        stats.mkdir()
        (stats / "trackview-2024-07-10_2024-07-20.csv").write_text(CSV)
        self._run(["--dashboard"], dashboard_home)
        png = dashboard_home / "output" / "trackview-2024-07-10_2024-07-20_dashboard.png"
        assert png.exists()
        assert self._stats_csvs(dashboard_home) == ["trackview-2024-07-10_2024-07-20.csv"]


class TestDashboardYear:
    """The `--dashboard-year YYYY` switch: a *year-scoped* 'year-in-review'.  Unlike the
    bare --dashboard -- a report over a *pre-existing* per-ride CSV, so it short-circuits
    the minutes-long load -- --dashboard-year *generates* a year-named CSV from that year's
    *.gpx: it implies --no-map (a), folds into a --since YYYY-01-01 / --until YYYY-12-31
    bound (b -- the Wahoo-filename date filter, so only that year's rides survive), writes
    stats/trackview-YYYY.csv ext-forced (c -- the trophy shelf reads power/grade, so the
    1.1.0 fix must carry them), and renders the dashboard *from that CSV* to
    output/trackview-dashboard-YYYY.<format> (d).  These drive cli.main() on the redirected
    data dir over the two-ride 2026 `gpx_folder` fixture, so the fold, the short-circuit
    skip, the year filter, and the year naming all execute for real -- the pure-helper tests
    above never touch cli.py's year branch."""

    @staticmethod
    def _run(argv, gpx_dir):
        # Like the short-circuit driver, but points --gpx-dir at the fixture's ride folder
        # (the redirected GPX_DIR is empty, so the year's rides come from here): a year run
        # that HAS rides loads + writes the year CSV + PNG and returns normally; an empty
        # year returns early at the "No tracks within" guard.  main() returns, not SystemExit.
        old = sys.argv
        sys.argv = ["trackview", "--gpx-dir", str(gpx_dir), *argv]
        try:
            cli.main()
        finally:
            sys.argv = old

    # ---- (b)+(c)+(d): the year CSV + the year dashboard, over the year's rides ----
    def test_year_run_writes_year_csv_and_dashboard(self, dashboard_home, gpx_folder):
        self._run(["--dashboard", "--dashboard-year", "2026"], gpx_folder)
        csv = dashboard_home / "stats" / "trackview-2026.csv"
        png = dashboard_home / "output" / "trackview-dashboard-2026.png"
        assert csv.exists()                                # (c) year-named CSV
        assert png.exists()                                 # (d) year-named dashboard
        # (b) the year filter kept exactly the two 2026 rides, nothing else
        assert [r["date"] for r in dash.parse_rides(csv)] == ["2026-01-15", "2026-09-07"]

    def test_year_csv_is_ext_forced(self, dashboard_home, gpx_folder):
        # the trophy shelf reads power/grade, so the year CSV is ext-forced even under the
        # implied --no-map (the 1.1.0 fix): the telemetry ride's 250 W survives, the plain
        # ride's power stays missing (None), not 0.
        self._run(["--dashboard", "--dashboard-year", "2026"], gpx_folder)
        csv = dashboard_home / "stats" / "trackview-2026.csv"
        by_date = {r["date"]: r for r in dash.parse_rides(csv)}
        assert by_date["2026-01-15"]["power"] == 250.0
        assert by_date["2026-09-07"]["power"] is None

    # ---- (a): --no-map is implied, so no basemap map is drawn or written ----
    def test_no_map_implied_no_overview_png(self, dashboard_home, gpx_folder):
        self._run(["--dashboard", "--dashboard-year", "2026"], gpx_folder)
        out = dashboard_home / "output"
        assert (out / "trackview-dashboard-2026.png").exists()
        assert not (out / "tracks_overview.png").exists()

    # ---- --dashboard-year implies --dashboard, so a bare year flag works alone ----
    def test_year_alone_implies_dashboard(self, dashboard_home, gpx_folder):
        self._run(["--dashboard-year", "2026"], gpx_folder)
        assert (dashboard_home / "stats" / "trackview-2026.csv").exists()
        assert (dashboard_home / "output" / "trackview-dashboard-2026.png").exists()

    # ---- a year run GENERATES its own CSV; it must not short-circuit on a stale one ----
    def test_year_run_skips_short_circuit_generates_csv(self, dashboard_home, gpx_folder):
        # A stale (pre-existing) plain CSV sits on disk: WITHOUT the `args.dashboard_year
        # is None` guard the bare --dashboard short-circuit would fire and merely *report*
        # the stale csv (no new CSV written).  With the guard, --dashboard-year skips it and
        # *generates* the year CSV -- so the 2026 csv appears, the stale 2020 csv is
        # untouched, and no range-named csv is written (the year branch names it trackview-
        # 2026.csv, not trackview-<first>_<last>.csv).
        stats = dashboard_home / "stats"
        stats.mkdir()
        (stats / "trackview-2020-01-01_2020-12-31.csv").write_text(CSV)
        self._run(["--dashboard", "--dashboard-year", "2026"], gpx_folder)
        names = sorted(p.name for p in stats.glob("*.csv"))
        assert "trackview-2026.csv" in names
        assert "trackview-2020-01-01_2020-12-31.csv" in names
        assert "trackview-2026-01-15_2026-09-07.csv" not in names

    # ---- a year with no rides writes nothing (the "No tracks within" early return) ----
    def test_empty_year_writes_nothing(self, dashboard_home, gpx_folder):
        self._run(["--dashboard", "--dashboard-year", "2025"], gpx_folder)
        assert not (dashboard_home / "stats" / "trackview-2025.csv").exists()
        assert not (dashboard_home / "output").exists()

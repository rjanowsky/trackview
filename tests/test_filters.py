"""[27] Filter *composition* against the fixture folder, mirroring the real runs
documented in TODO.lst.  Each test asserts on the surviving `tracks` list (what
the map / ride-log / stats would see), not on the printed text -- the date
filter (--since/--until), the --device/--sport filter and the --top selection all
compose, in that order.
"""
from datetime import date

from conftest import build_ride, ride_paths, run_filters, run_main, write_ride
from trackview.load import load_tracks
from trackview.helpers import _filter_by_meta


# --------------------------------------------------------------------------- #
#  --since / --until narrow by the filename date
# --------------------------------------------------------------------------- #
class TestDateFilter:
    def test_since_keeps_only_the_later_ride(self, gpx_folder):
        kept = run_filters(gpx_folder, since="2026-06-01")
        assert [t["name"] for t in kept] == ["2026_09_07_08_12_47"]

    def test_until_keeps_only_the_earlier_ride(self, gpx_folder):
        kept = run_filters(gpx_folder, until="2026-06-30")
        assert [t["name"] for t in kept] == ["2026_01_15_08_00_00"]

    def test_a_gap_between_bounds_keeps_nothing(self, gpx_folder):
        kept = run_filters(gpx_folder, since="2026-03-01", until="2026-06-30")
        assert kept == []

    def test_no_bounds_keeps_everything(self, gpx_folder):
        assert len(run_filters(gpx_folder)) == 2


# --------------------------------------------------------------------------- #
#  --device / --sport match the parsed <desc> line; a ride missing it is skipped
# --------------------------------------------------------------------------- #
class TestMetaFilter:
    def test_device_keeps_the_tagged_ride(self, gpx_folder):
        kept = run_filters(gpx_folder, device="Wahoo ELEMNT BOLT")
        assert [t["name"] for t in kept] == ["2026_01_15_08_00_00"]

    def test_sport_keeps_the_tagged_ride(self, gpx_folder):
        kept = run_filters(gpx_folder, sport="Bike")
        assert [t["name"] for t in kept] == ["2026_01_15_08_00_00"]

    def test_device_match_is_case_insensitive(self, gpx_folder):
        kept = run_filters(gpx_folder, device="wahoo elemnt bolt")
        assert [t["name"] for t in kept] == ["2026_01_15_08_00_00"]

    def test_a_ride_with_no_device_line_is_skipped(self, gpx_folder):
          # the komoot-style ride carries no 'Device:' line, so any --device filter
         # drops it; only the tagged ride survives
        kept = run_filters(gpx_folder, device="anything")
        assert kept == []

    def test_non_match_prints_the_distinct_values(self, gpx_folder, capsys):
          # nothing matches -> the log prints the values it *does* carry (a typo
         # is easy to fix) and an 'unknown' marks the line-less ride
        tracks = load_tracks(ride_paths(gpx_folder), 1.0)
        kept = _filter_by_meta(tracks, device="Garmin Forerunner 965")
        out = capsys.readouterr().out
        assert kept == []
        assert "no ride matches" in out
        assert "Wahoo ELEMNT BOLT" in out
        assert "unknown" in out

    def test_no_filter_passes_everything(self, gpx_folder):
        tracks = load_tracks(ride_paths(gpx_folder), 1.0)
        assert _filter_by_meta(tracks) == tracks


# --------------------------------------------------------------------------- #
#  --top runs *after* the other filters, then re-sorts the survivors to date order
# --------------------------------------------------------------------------- #
class TestTopComposition:
    def test_top_runs_after_the_date_filter(self, gpx_folder):
          # --since leaves the Sep ride alone; --top 1 --by km keeps the longer of the
         # survivors, which is the same ride (a no-op here, but the order is right)
        kept = run_filters(gpx_folder, since="2026-06-01", top=1, by="km")
        assert [t["name"] for t in kept] == ["2026_09_07_08_12_47"]

    def test_top_recent_keeps_the_latest(self, gpx_folder):
        kept = run_filters(gpx_folder, top=1, by="recent")
        assert [t["name"] for t in kept] == ["2026_09_07_08_12_47"]

    def test_top_then_device_selects_within_the_kept_set(self, gpx_folder):
          # device keeps the Jan ride; --top of that 1-ride set is a no-op
        kept = run_filters(gpx_folder, device="Wahoo ELEMNT BOLT", top=1, by="gain")
        assert [t["name"] for t in kept] == ["2026_01_15_08_00_00"]

    def test_top_re_sorts_survivors_to_date_order(self, tmp_path):
            # a 3-ride folder: the top-2 by gain rank out of date order, but the
            # survivors come back date-ascending (and the lowest-gain ride drops out)
        sub = tmp_path / "2026"
        write_ride(build_ride("2026_01_15_08_00_00", device="Wahoo ELEMNT BOLT",
                              sport="Bike", ele=(100, 100, 200, 100, 100)),
                   sub / "2026_01_15_08_00_00.gpx")
        write_ride(build_ride("2026_06_20_10_00_00", device="Wahoo ELEMNT BOLT",
                              sport="Bike", ele=(100, 300, 600, 900, 100)),
                   sub / "2026_06_20_10_00_00.gpx")
        write_ride(build_ride("2026_09_07_08_12_47", device="Wahoo ELEMNT BOLT",
                              sport="Bike", ele=(100, 100, 500, 1000, 100)),
                   sub / "2026_09_07_08_12_47.gpx")
        kept = run_filters(tmp_path, top=2, by="gain")
        names = [t["name"] for t in kept]
        assert set(names) == {"2026_06_20_10_00_00", "2026_09_07_08_12_47"}      # the two highest-gain
        assert names == ["2026_06_20_10_00_00", "2026_09_07_08_12_47"]           # ...back in date order


# --------------------------------------------------------------------------- #
#  --today folds to '--flat --since <today>' (a no-fetch glance with --list)
# --------------------------------------------------------------------------- #
class TestToday:
    def test_today_folds_to_flat_since_today(self, tmp_path, monkeypatch, capsys):
         # a ride dated *today* at the top level is found; one of the same date in a
        # subfolder is NOT (today forces flat discovery)
        today = date.today()
        stem = f"{today:%Y_%m_%d}_08_00_00"
        write_ride(build_ride(stem, device="Wahoo ELEMNT BOLT", sport="Bike"),
                   tmp_path / f"{stem}.gpx")
        sub = tmp_path / "2026"
        write_ride(build_ride(stem, device="Wahoo ELEMNT BOLT", sport="Bike"),
                   sub / f"{stem}.gpx")

        run_main(["--gpx-dir", str(tmp_path), "--list", "--today"],
                 tmp_path, monkeypatch, capsys)
        out = capsys.readouterr().out

        assert f"flat discovery + since {today.isoformat()}" in out      # the fold
        assert stem in out                                              # the top-level ride
        # the subfolder twin is never listed: flat discovery skips it, so exactly one
        assert out.count(stem) == 1

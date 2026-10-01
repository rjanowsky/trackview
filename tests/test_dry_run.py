"""[28] Lock in the --list dry-run contract."""
from pathlib import Path

from conftest import ride_paths, run_main
from trackview.helpers import _list_rides
from trackview.load import load_tracks

# the output artifacts a *rendered* run would write -- never a --list run
_OUTPUT_EXTS = {".txt", ".csv", ".png", ".pdf", ".html"}


def _output_files(tmp_path):
    # any rendered artifact under tmp_path -- a --list run leaves none of these
    return [p for p in tmp_path.rglob("*")
            if p.is_file() and p.suffix in _OUTPUT_EXTS]


class TestListRidesTable:
    def test_header_rows_and_total(self, gpx_folder, capsys):
        tracks = load_tracks(ride_paths(gpx_folder), 1.0)
        assert len(tracks) == 2
        _list_rides(tracks)
        out = capsys.readouterr().out
        # the header
        for col in ("Date", "Ride", "Dist (km)", "Gain (m)"):
            assert col in out
        # one row per ride
        for t in tracks:
            assert t["name"] in out
        # a closing totals row
        assert "TOTAL" in out

    def test_empty_set_message(self, capsys):
        _list_rides([])
        out = capsys.readouterr().out
        assert "no ride matches the filters" in out
        assert "TOTAL" not in out    # no table when there is nothing to list

    def test_undated_ride_shows_undated(self, capsys):
        # a foreign name (no date in the stem) shows 'undated', not a crash
        t = {"path": Path("komoot_loop.gpx"), "name": "komoot_loop",
             "dist_km": 12.3, "gain_m": 250.0}
        _list_rides([t])
        out = capsys.readouterr().out
        assert "undated" in out


class TestListWritesNothing:
    def test_list_writes_no_artifacts(self, gpx_folder, tmp_path, monkeypatch, capsys):
        out_dir, stats_dir = run_main(["--gpx-dir", str(gpx_folder), "--list"],
                                      tmp_path, monkeypatch, capsys)
        out = capsys.readouterr().out
        assert "--list:" in out        # it printed its own dry-run table
        assert not out_dir.exists()     # the redirected dirs were never created
        assert not stats_dir.exists()
        assert _output_files(tmp_path) == []

    def test_no_map_plus_list_still_lists_and_writes_nothing(
            self, gpx_folder, tmp_path, monkeypatch, capsys):
        # --list outranks --no-map (it returns first): the dry-run table prints,
        # the "skipping map generation" line never does, and nothing is written
        out_dir, stats_dir = run_main(
               ["--gpx-dir", str(gpx_folder), "--list", "--no-map"],
               tmp_path, monkeypatch, capsys)
        out = capsys.readouterr().out
        assert "--list:" in out
        assert "skipping map generation" not in out
        assert not out_dir.exists()
        assert not stats_dir.exists()
        assert _output_files(tmp_path) == []

    def test_impossible_until_fires_the_no_tracks_guard_first(
            self, gpx_folder, tmp_path, monkeypatch, capsys):
        # every ride is out of range, so main's 'nothing to render' guard fires
        # *before* --list ever runs: no table, and no file written
        out_dir, stats_dir = run_main(
               ["--gpx-dir", str(gpx_folder), "--list", "--until", "2000-01-01"],
               tmp_path, monkeypatch, capsys)
        out = capsys.readouterr().out
        assert "nothing to render" in out    # the pre-existing 'no tracks' guard
        assert "--list:" not in out          # --list never got to print its table
        assert not out_dir.exists()
        assert not stats_dir.exists()
        assert _output_files(tmp_path) == []

"""Shared pytest fixtures for the trackview test suite.

The default suite is *pure* -- it touches no network and draws no figures, so it
runs offline in milliseconds.  Two markers, registered in pyproject.toml, let CI
run just the pure subset:

    .venv/bin/pytest -m "not network and not slow"

`network` marks the one path that fetches basemap tiles / the Leaflet CDN, and
`slow` marks the matplotlib figure render; the basemap+render smoke test carries
both.  See TODO.lst items [24]-[28].
"""
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

import xml.etree.ElementTree as ET
from gpxpy.gpx import GPX, GPXTrack, GPXTrackSegment, GPXTrackPoint

# Make the repo root (the dir that holds trackview.py) importable from tests/.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Re-pointed off the re-export bridge at their submodules (the bridge is the
# last leaf of Phase 1, TODO [32]): helpers / load / cli are imported directly.
import trackview.helpers as helpers     # noqa: E402  (the path must be fixed up first)
import trackview.load as load           # noqa: E402
from trackview.cli import main as cli_main     # noqa: E402


# --------------------------------------------------------------------------- #
#  [24] Building GPX rides in-memory via gpxpy -- no file on disk             #
# --------------------------------------------------------------------------- #
# A tiny climb -> peak -> descent -> flat profile (metres).  The horizontal run
# is a constant ~110 m per sample (latitude stepped by 0.001 deg), so a handful
# of points reads as a real climb and descent.
CLIMB_DES_FLAT_ELE = (100, 100, 100, 200, 300, 300, 200, 100, 100)

# Per-point telemetry, as goldencheetah_to_gpx --ext stamps it: un-namespaced
# <extensions> children, keyed by the tags trackview._TELE_TAGS reads.
_TELE = {"power": "250", "speed_kmh": "30.0", "cadence": "90",
         "heartrate": "150", "temperature": "15"}


def build_ride(stem, *, device=None, sport=None, telemetry=False,
               ele=CLIMB_DES_FLAT_ELE, start_time=None):
    """An in-memory gpxpy.GPX for one ride: a single track/segment of
    climb/descent/flat samples.  `device`/`sport` add a 'Device:'/'Sport:' line
    to <desc> (the lines goldencheetah_to_gpx stamps); `telemetry` embeds a per-point
    <extensions> block.  Nothing is written -- materialize to disk via write_ride().
    """
    g = GPX()
    g.name = stem
    parts = ["Converted from %s.gpx" % stem]
    if device is not None:
        parts.append("Device: %s" % device)
    if sport is not None:
        parts.append("Sport: %s" % sport)
    g.description = "\n".join(parts)

    trk = GPXTrack(name=stem)
    seg = GPXTrackSegment()
    trk.segments.append(seg)
    start = start_time or datetime(2026, 1, 1, 8, 0, 0, tzinfo=timezone.utc)
    for i, e in enumerate(ele):
        p = GPXTrackPoint(47.0 + i * 0.001, 8.0 + i * 0.001, float(e),
                          time=start + timedelta(seconds=i))
        if telemetry:
            for tag, text in _TELE.items():
                el = ET.Element(tag)
                el.text = text
                p.extensions.append(el)
        seg.points.append(p)
    g.tracks.append(trk)
    return g


def write_ride(gpx, path):
    """Serialize a build_ride() GPX to `path` on disk -- the only place a ride
    hits the filesystem, and only ever inside tmp_path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(gpx.to_xml(version="1.1"), encoding="utf-8")
    return path


def gpx_points(gpx):
    """The raw (lat, lon, ele) sample list of an in-memory gpxpy.GPX -- the shape
    _distance_and_gain / _grade_and_cumkm expect."""
    raw = []
    for trk in gpx.tracks:
        for seg in trk.segments:
            for p in seg.points:
                raw.append((p.latitude, p.longitude, p.elevation))
    return raw


# --------------------------------------------------------------------------- #
#  [24] A tmp_path folder the filter tests point --gpx-dir at                #
# --------------------------------------------------------------------------- #
@pytest.fixture
def synthetic_gpx():
    """A tiny climb/descent/flat ride as an in-memory gpxpy.GPX *with*
    <extensions> telemetry and a Device/Sport desc -- no file on disk."""
    return build_ride("2026_09_07_08_12_47", device="Wahoo ELEMNT BOLT",
                      sport="Bike", telemetry=True)


@pytest.fixture
def synthetic_gpx_plain():
    """The same ride with no telemetry and no Device/Sport desc -- a plain
    komoot-style track, the negative case for the telemetry/device tests."""
    return build_ride("komoot_loop", telemetry=False)


@pytest.fixture
def gpx_folder(tmp_path):
    """A tmp_path folder of two Wahoo-named rides in a year/ subfolder (so the
    recursive rglob is exercised too): one device-tagged Wahoo ride *with*
    telemetry (Jan 15, short) and one plain, telemetry-free komoot-style track
    (Sep 07, longer).  Returns the folder root; ride_paths() finds the rides."""
    sub = tmp_path / "2026"
    write_ride(build_ride("2026_01_15_08_00_00", device="Wahoo ELEMNT BOLT",
                          sport="Bike", telemetry=True,
                          ele=(100, 100, 200, 100, 100)),
               sub / "2026_01_15_08_00_00.gpx")
    write_ride(build_ride("2026_09_07_08_12_47", telemetry=False,
                          ele=(100, 300, 600, 900, 1200, 100)),
               sub / "2026_09_07_08_12_47.gpx")
    return tmp_path


def ride_paths(folder, *, flat=False):
    """The .gpx files under `folder`, date-ascending -- a recursive rglob by
    default (main()'s behaviour), a single-level glob under `flat`."""
    folder = Path(folder)
    return sorted(folder.rglob("*.gpx") if not flat else folder.glob("*.gpx"))


def run_filters(folder, *, since=None, until=None, device=None, sport=None,
                top=None, by="recent", flat=False, with_ext=True, decimate_m=1.0):
    """Mirror main()'s filter sequence on a folder and return the surviving
    tracks -- the date filter (by filename), then --device/--sport, then
    --top --by.  Tests assert on this list, not the printed text, so a filter
    change that still selects the right rides passes."""
    paths = ride_paths(folder, flat=flat)
    lo = helpers._parse_argdate(since, "--since") if since else None
    hi = helpers._parse_argdate(until, "--until") if until else None
    if lo or hi:
        paths = [p for p in paths
                 if (rd := helpers._ride_date(p)) and not ((lo and rd < lo)
                                                      or (hi and rd > hi))]
    tracks = load.load_tracks(paths, decimate_m, with_ext=with_ext)
    if device or sport:
        tracks = helpers._filter_by_meta(tracks, device, sport)
    if top is not None:
        tracks = helpers._select_top(tracks, top, by)
    return tracks


# --------------------------------------------------------------------------- #
#     [28] A safe driver for main(): a --list / --no-map dry run is asserted
#      to write nothing into the repo's output/ + stats/ dirs.
# --------------------------------------------------------------------------- #
def run_main(argv, tmp_path, monkeypatch, capsys):
    """Run trackview.cli.main (re-pointed off the bridge, TODO [32]) with a
    fresh argv, so a --list / --no-map dry run can be asserted to write nothing
    into the real output/ + stats/ dirs.   (A --list / --no-map run fetches no
    basemap and writes no file, so the suite never touches the repo's output/."""
    out_dir = tmp_path / "output"
    stats_dir = tmp_path / "stats"
    monkeypatch.setattr(sys, "argv", ["trackview", *argv])
    cli_main()
    return out_dir, stats_dir

"""The one heavy path: a real basemap fetch + a matplotlib figure render.

Marked `network` (it pulls tiles over the internet) and `slow` (it draws a
figure), so the default `pytest` run -- and CI's `-m "not network and not slow"`
-- skip it, keeping the pure suite fast and offline.  It only actually runs when
explicitly requested *and* the network is available:

     TRACKVIEW_TEST_NETWORK=1 .venv/bin/pytest -m "network and slow"
"""
import os

import pytest

from trackview.load import load_tracks
from trackview.mapfig import render
from conftest import ride_paths


@pytest.mark.network
@pytest.mark.slow
def test_render_a_combined_map(gpx_folder, tmp_path):
    if not os.environ.get("TRACKVIEW_TEST_NETWORK"):
        pytest.skip("set TRACKVIEW_TEST_NETWORK=1 to run the network/slow render")
    tracks = load_tracks(sorted(ride_paths(gpx_folder)), 5.0)
    out = tmp_path / "output" / "smoke.png"
    render(tracks, style="osm", out_path=out, detail=None, color_by="elev")
    assert out.exists() and out.stat().st_size > 0

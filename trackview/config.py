"""The centralized configuration for trackview, extracted in PLAN.md Phase 3.1.

The monolith defined these module-level constants next to `main`; they now live
here, the single home for the run-time configuration (the directory layout the
CLI reads/writes, the decimation threshold and the Web-Mercator scaling
constant).  `trackview.py` re-imports the live ones (`GPX_DIR` / `OUTPUT_DIR` /
`STATS_DIR` / `TILE_CACHE_DIR` / `DECIMATE_M`, all read by `main`); `PI_R` is
kept as the documented home for the magic number though the monolith no longer
touches it.

A one-level shift from the monolith is the only value-affecting edit: the
monolith's `trackview.py` sat *in* the repo root, so its
`Path(__file__).resolve().parent` was the repo root.  This module sits one level
deeper (`trackview/config.py`), so it reaches the same repo root with
`.parent.parent` -- the resolved paths (`gpx/`, `output/`, `stats/`, `tiles/`)
are identical to before.
"""
from __future__ import annotations

from pathlib import Path

# ------------------------------- configuration -------------------------------
# One level up from this package dir is the repo root (trackview/ -> repo root),
# where the run-time directories live; the constants resolve identically to the
# old monolith, whose `__file__` was the repo-root `trackview.py`.
GPX_DIR      = Path(__file__).resolve().parent.parent / "gpx"
OUTPUT_DIR   = Path(__file__).resolve().parent.parent / "output"
STATS_DIR    = Path(__file__).resolve().parent.parent / "stats"
# Basemap tiles are cached to disk under here (contextily's on-disk tile cache,
# keyed by z/x/y per provider), so re-renders and offline runs reuse the downloaded
# tiles instead of refetching them; --no-cache disables it, tiles/ is git-ignored.
TILE_CACHE_DIR = Path(__file__).resolve().parent.parent / "tiles"

DECIMATE_M   = 5.0        # drop track points closer than this (m): keeps the shape,
                         # cuts ~68k points to a few thousand for crisp, fast drawing

PI_R       = 20037508.342789244      # pi*R: scales the Web-Mercator x/y projection

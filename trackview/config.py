"""The centralized configuration for trackview, extracted in PLAN.md Phase 3.1.

The monolith defined these module-level constants next to `main`; they now live
here, the single home for the run-time configuration the CLI reads/writes: the
directory layout it touches, plus the decimation threshold -- and the package
version (`__version__`).  `trackview.py` re-imports the live ones
(`GPX_DIR` / `OUTPUT_DIR` / `STATS_DIR` / `TILE_CACHE_DIR` / `DECIMATE_M`, all
read by `main`); the CLI reads `__version__` for its `--version` switch.  The
Web-Mercator scaling constant `PI_R` is *not* here -- it is a geometry detail, so
it lives in `trackview.geometry` (its single source), where `latlon_to_merc` uses
it.

`__version__` is the package's *single source of truth*: `pyproject.toml` does not
hard-code a second copy, it reads this one dynamically
(`[tool.setuptools.dynamic] version = {attr = "trackview.config.__version__"}`),
so the version the build stamps into the wheel/sdist and the version
`trackview --version` (and `importlib.metadata.version("trackview")` after an
install) report can never drift apart.

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
# The package version -- the single source of truth (see the module docstring):
# `pyproject.toml` reads it dynamically rather than hard-coding a second copy, so
# the build-stamped version and `trackview --version` always agree.  A PEP 440
# release tag (a numeric X.Y.Z), bumped by hand when a release is cut.
__version__ = "0.1.0"

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

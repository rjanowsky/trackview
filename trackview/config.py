"""The centralized configuration for trackview, extracted in PLAN.md Phase 3.1.

The monolith defined these module-level constants next to `main`; they now live
here, the single home for the run-time configuration the CLI reads/writes: the
directory layout it touches, plus the decimation threshold -- and the package
version (`__version__`).  `trackview.cli` reads the live ones
(`GPX_DIR` / `OUTPUT_DIR` / `STATS_DIR` / `TILE_CACHE_DIR` / `DECIMATE_M`, all
read by `main`, which lives there) and `__version__` for its `--version` switch;
the root `trackview.py` is only a thin launcher (`from trackview.cli import main`).  The
Web-Mercator scaling constant `PI_R` is *not* here -- it is a geometry detail, so
it lives in `trackview.geometry` (its single source), where `latlon_to_merc` uses
it.

`__version__` is the package's *single source of truth*: `pyproject.toml` does not
hard-code a second copy, it reads this one dynamically
(`[tool.setuptools.dynamic] version = {attr = "trackview.config.__version__"}`),
so the version the build stamps into the wheel/sdist and the version
`trackview --version` (and `importlib.metadata.version("trackview")` after an
install) report can never drift apart.

The data directories are anchored to the *user's home*, not the package: `DATA_DIR`
is `$TRACKVIEW_HOME` when set, else `~/.trackview` (dot-prefixed so it stays out of
the way and never collides with a `~/trackview` source checkout).  `GPX_DIR` /
`OUTPUT_DIR` / `STATS_DIR` / `TILE_CACHE_DIR` sit under it (`gpx/`, `output/`,
`stats/`, `tiles/`).  This is deliberate -- the monolith anchored these to its own
`__file__`, which resolves to the install dir (`site-packages/`) once trackview is
*installed*, so an installed `trackview` run would have scattered one athlete's ride
log into the package's own tree (read-only, and the wrong place to write data).
Anchoring to home keeps the data where it belongs -- per-user, writable, independent
of where the code is installed -- and is migration-friendly: an old repo-root `gpx/`
/ `gc/` / `fit/` ride log moves to `~/.trackview/` (`$TRACKVIEW_HOME` relocates it
elsewhere, e.g. an existing install or a test).  Every writer `mkdir`s its own
parent, and the two converters `mkdir` their `fit/` / `gc/` input dir on a default
run, so pointing the whole layout at a not-yet-existing `~/.trackview` is safe --
a first run leaves a clean, ready-to-fill home dir, not a missing one.
"""
from __future__ import annotations

import os
from pathlib import Path

# ------------------------------- configuration -------------------------------
# The package version -- the single source of truth (see the module docstring):
# `pyproject.toml` reads it dynamically rather than hard-coding a second copy, so
# the build-stamped version and `trackview --version` always agree.  A PEP 440
# release tag (a numeric X.Y.Z), bumped by hand when a release is cut.
__version__ = "1.0.6"

# The per-user data root: $TRACKVIEW_HOME when set (a relocation escape hatch --
# an existing install, or a test pointing at a tmp dir), else ~/.trackview
# (dot-prefixed so it stays out of the way and never collides with a
# ~/trackview source checkout).  The run-time directories live *here*, not under
# the package -- see the module docstring for why not (an installed package's
# __file__ is site-packages/).  Each writer mkdir's its own parent (and the two
# converters mkdir their fit/ / gc/ input dir on a default run), so a not-yet-
# existing ~/.trackview is created on first use.
DATA_DIR = (Path(os.environ["TRACKVIEW_HOME"])
            if "TRACKVIEW_HOME" in os.environ
            else Path.home() / ".trackview")
GPX_DIR      = DATA_DIR / "gpx"       # the ride log to plot (input)
OUTPUT_DIR   = DATA_DIR / "output"    # rendered maps / standalone figures
STATS_DIR    = DATA_DIR / "stats"     # the ride-log table + CSV + the stats reports
# Basemap tiles are cached to disk under here (contextily's on-disk tile cache,
# keyed by z/x/y per provider), so re-renders and offline runs reuse the downloaded
# tiles instead of refetching them; --no-cache disables it, tiles/ is git-ignored.
TILE_CACHE_DIR = DATA_DIR / "tiles"

DECIMATE_M   = 5.0        # drop track points closer than this (m): keeps the shape,
                         # cuts ~68k points to a few thousand for crisp, fast drawing

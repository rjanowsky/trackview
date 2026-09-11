# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

`trackview` is a standalone single-file tool that renders every `*.gpx` in `gpx/`
onto one static map image (`output/tracks_overview.png`). It is a sub-folder inside
the larger `workarea` git repo, which is a loose collection of unrelated hobby
scripts (bicycle gear calculator, weather/heating data, other GPX viewers, etc.).
`trackview` is **self-contained**: it has its own `README.md`, `requirements.txt`,
and `.venv`, and does not depend on anything in the parent repo.

## Setup

Uses Python 3.14 and a local virtualenv at `.venv/` (git-ignored).

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt      # contextily, matplotlib, gpxpy, numpy
```

Run the tool with the venv interpreter to avoid system-Python import errors:

```bash
.venv/bin/python trackview.py
```

## Commands

```bash
.venv/bin/python trackview.py                       # ./gpx -> ./output/tracks_overview.png
.venv/bin/python trackview.py --format pdf            # vector PDF instead of PNG
.venv/bin/python trackview.py --split                 # one map file per track (default: all in one)
.venv/bin/python trackview.py --style sat           # Esri satellite basemap
.venv/bin/python trackview.py --zoom 13             # override auto-chosen zoom
.venv/bin/python trackview.py --no-elev             # flat per-track colour, not elevation
.venv/bin/python trackview.py --gpx-dir DIR --out OUT
.venv/bin/python trackview.py --help                # full CLI
```

CLI flags (`argparse`, in `main()`): `--gpx-dir` (default `./gpx`), `--out`
(auto-named `output/tracks_overview.<format>` when omitted), `--format {png,pdf}`, `--style {topo,sat,terrain,osm}`, `--zoom` (int, else auto), `--no-elev`, `--split`
(one file per track, named from the GPX stem; the default renders all tracks
onto one combined map).

There is **no test suite, linter, formatter, or CI** in this project. To
validate a change, run the script (it needs network for the basemap) or at least
syntax-check with `.venv/bin/python -c "import ast; ast.parse(open('trackview.py').read())"`.

## Architecture

Everything lives in `trackview.py`. The pipeline runs top-to-bottom:

1. `load_tracks()` — parse each `*.gpx` with `gpxpy`, flatten all
   track→segment→point into one `(lat, lon, ele)` list per file.
2. `decimate()` — drop points closer than `DECIMATE_M` (5 m) apart to cut
   ~68k points/file down to a few thousand. First and last points are always kept.
3. `latlon_to_merc()` — project to Web Mercator (EPSG:3857) for plotting.
4. `render()` — fetch the raster basemap, overlay each track (white halo underlay
   + colour ramp), add start/stop markers, legend, colourbar, title, attribution,
   and save the PNG.
5. `main()` — CLI wiring and per-track summary printout.

Key non-obvious details:

- **Two different projection constants are used on purpose.** `PI_R`
  (`20037508.34` = π·R) scales the x/y Mercator coordinates; `EQUATOR`
  (`40075016.68` = 2π·R, the equatorial circumference) is used *only* for the
  zoom calculation in `choose_zoom()`. Do not "unify" them — the coordinate
  scaling must use π·R, not 2π·R.
- **Distance and elevation gain** (`_distance_and_gain`, and `decimate`) use an
  **equirectangular approximation** (local lat/lon → metre conversion with a
  mid-latitude cosine), not Haversine. Keep them consistent when changing one.
- **Basemap fallback** (`_load_basemap`): providers are tried in order
  (`--style` first, then the rest of `SOURCES`). It catches fetch exceptions
  *and* detects blank/rate-limited tiles by checking that the returned image's
  pixel variance exceeds `min_var`; on failure it sleeps 2 s and tries the next
  provider. A failed or blank tile is expected to trigger fallback, so this is
  intentionally not covered by tests.
- **Rendering is headless** — `matplotlib.use("Agg")` is set before importing
  `pyplot`. The figure is square (`FIGURE_IN = (11, 11)`) and `fit_aspect()`
  grows the bounding box to match the figure aspect so the map is never letter-boxed.
- **Elevation shading** is off when the total elevation range is ≤ 1 m or when
  `--no-elev` is passed; in that case tracks get flat distinct colours from a
  resampled `tab10` cmap instead of a `terrain` ramp + colourbar.
- The `gpx/` input and `output/` are git-ignored; GPX files here are Strava
  exports named `YYYY-MM-DD_<id>_<date>.gpx`.

## Basemap providers (`--style`)

`topo` (OpenTopoMap, default), `sat` (Esri World Imagery), `terrain`
(Esri World Terrain Base), `osm` (German OSM tile server). A proper `User-Agent`
is sent and attribution is printed on the image and console.

## Related work

The parent `workarea` has a separate GPX viewer, `gpx_viewer.py`
(Streamlit + Folium, interactive upload-based map) — a different approach from
this static-PNG renderer. They do not share code.
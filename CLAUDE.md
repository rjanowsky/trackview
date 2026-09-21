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
.venv/bin/python trackview.py --detail 13             # override auto-chosen detail
.venv/bin/python trackview.py --no-elev             # flat per-track colour, not elevation
.venv/bin/python trackview.py --color-by grade      # shade the route by slope (climbs red, descents blue, flat grey)
.venv/bin/python trackview.py --color-by grade --grade-cap 8      # pin the grade colour range to +/-8% (not auto)
.venv/bin/python trackview.py --color-by power      # shade the route by effort (fast/high = hot; needs --ext, else flat)
.venv/bin/python trackview.py --color-by speed       # shade the route by pace (fast = hot; needs --ext, else flat)
.venv/bin/python trackview.py --profile --split     # add an elevation + grade profile panel under each map
.venv/bin/python trackview.py --ext                 # avg power/speed/cadence/hr/temperature + calories burned (kcal)
.venv/bin/python trackview.py --no-map                # skip the map/image; just compute the stats + write stats/
.venv/bin/python trackview.py --since 2026-09-05       # only tracks on/after a date (from the .gpx filename)
.venv/bin/python trackview.py --until 2026-09-08       # only tracks on/before a date (from the .gpx filename)
.venv/bin/python trackview.py --csv                    # also write a CSV ride-log (header + rows, no totals) to stats/
.venv/bin/python trackview.py --csv --csv-delimiter ,   # comma-separated instead of the default ';'
.venv/bin/python trackview.py --sparse                   # quiet stdout: skip the per-track stats listing
.venv/bin/python trackview.py --no-scale                 # omit the map's lower-right scale bar (on by default)
.venv/bin/python trackview.py --heat                     # overlay a 2-D "time on route" density under the routes
.venv/bin/python trackview.py --labels                   # tag each route's start with name + distance (a combined map)
.venv/bin/python trackview.py --gain-noise 1.5           # ignore GPS vertical jitter when summing ascent
.venv/bin/python trackview.py --climbs 10                # also write a climb ranking to stats/
.venv/bin/python trackview.py --gpx-dir DIR --out OUT
.venv/bin/python trackview.py --help                # full CLI
```

CLI flags (`argparse`, in `main()`): `--gpx-dir` (default `./gpx`), `--out`
`--ext` (title shows the
calories-burned total in kcal plus an avg power/speed/cadence/hr/temperature line below it, when the
GPX carries `wahoo_to_gpx --ext` telemetry; calories = avg power x ride duration / ~25%
efficiency), `--split`
(one file per track; its title shows the ride date as `YYYY-MM-DD` for a
  Wahoo-style stem, else the name.  The default renders all tracks onto one
  combined map).  Ride duration (`Hh MMm`) is always on the title, between the
  distance and the elevation gain (total across the tracks when combined).
 `--color-by {elev,grade,flat,speed,power}` (default `elev`; `--no-elev` is a shorthand for `flat`)
   shades each route by the chosen metric (the `viridis` elevation ramp, a
   grey-centred diverging grade ramp with a robust percentile cap — `--grade-cap N`
   pins it and a few combined rides get their own colourbar — `speed`/`power` on the
   same effort ramp (`inferno`, fast/high = hot, needing the `--ext` telemetry, auto-
   collected and falling back to a flat colour when absent); or flat distinct colours); `--profile` adds an
  elevation + grade vs. distance panel under each map (needs `--split`, or a single track).
  `--since`/`--until` (each a `YYYY-MM-DD`) keep only the tracks whose ride date
  (read from the Wahoo-style filename stem) falls in the range — mirroring
  `wahoo_to_gpx --since/--until`; a filename with no date is skipped when a bound is set.

## Wahoo -> GPX (`wahoo_to_gpx.py`)

`gc/` holds Wahoo ELEMNT ride exports (`*.json`, one `{"RIDE": {...}}` per
ride, one `SAMPLES` row per second with `LAT/LON/ALT/WATTS/CAD/KPH/SLOPE/TEMP`).
`wahoo_to_gpx.py` turns each into a standard GPX 1.1 track in `gpx/` (the same
shape as the komoot tracks, so `trackview.py` renders them together):

```bash
.venv/bin/python wahoo_to_gpx.py                     # ./gc -> ./gpx
.venv/bin/python wahoo_to_gpx.py --ext                # also embed power/cad/hr/speed(km/h)/grade/temp
.venv/bin/python wahoo_to_gpx.py --since 2026-09-05            # only rides on/after a date
.venv/bin/python wahoo_to_gpx.py --until 2026-09-08            # only rides on/before a date
.venv/bin/python wahoo_to_gpx.py <file.json> --out-dir DIR
```

Non-obvious Wahoo quirks the converter handles (and why):
- the JSON has a **UTF-8 BOM** -> opened `utf-8-sig`;
- **`LAT`/`LON` are already decimal degrees** (no scale factor needed);
- rows with `LAT/LON == 0` are "no fix" (ride start/stop) -> dropped;
- `ALT == 0` is a **"no altitude" sentinel** (GPS altitude lags the position
  lock; real values here run ~12-120 m) -> filled from the neighbouring valid
  altitude so the `<ele>` series stays continuous;
- absolute time = `STARTTIME` (`"... UTC"`) + `SECS`, written with a `Z` suffix
  (via a tz-aware UTC `datetime`) to match the existing komoot tracks;
- distance/gain use the **same equirectangular approximation as `trackview.py`**
  (`_distance_and_gain`) — keep the two consistent;
- `gpxpy.parse()` (1.6.2) must be handed a **file object or string, not a path**
  (a path string is parsed *as* XML and fails).
- the two `--ext` flags are **paired**: `wahoo_to_gpx.py --ext` embeds
 `power`/`speed_kmh`/`cadence`/`heartrate`/`temperature` (and a `grade` tag the map does *not* use — see below) as un-namespaced `<trkpt><extensions>`
  children; `trackview.py --ext` reads them back (gpxpy flattens the `<extensions>` children onto `point.extensions`, bare tags) to print an avg power/speed/cadence/hr/temperature subtitle plus the calories-burned total on the main title line (kcal = avg power x ride duration / 4184 / ~25% efficiency); absent telemetry is skipped.
  Grade, by contrast, is *geometry-derived* (see Colouring modes below), so `--color-by grade` and `--profile` need no telemetry at all.

## Notes / testing

There is **no test suite, linter, formatter, or CI** in this project. To
validate a change, run the script (it needs network for the basemap) or at least
syntax-check with `.venv/bin/python -c "import ast; ast.parse(open('trackview.py').read())"`.

## Architecture

Everything lives in `trackview.py`. The pipeline runs top-to-bottom:

1. `main()` discovers `*.gpx` and applies the `--since`/`--until` date filter
   (by filename stem, via `_ride_date`/`_parse_argdate`); `load_tracks(paths)`
   then parses each remaining file with `gpxpy`, flattening all
   track→segment→point into one `(lat, lon, ele)` list per file.
2. `decimate()` — drop points closer than `DECIMATE_M` (5 m) apart to cut
   ~68k points/file down to a few thousand. First and last points are always kept.
3. `latlon_to_merc()` — project to Web Mercator (EPSG:3857) for plotting.
4. `render()` — fetch the raster basemap, overlay each track (white halo underlay
   + colour ramp), add start/stop markers, legend, colourbar, title, attribution,
   and save the PNG.  With `--profile` a single-track figure instead grows into a
   2-row `GridSpec` (`height_ratios=[3,1]`): the map on top and a `_draw_profile()`
   elevation + grade-vs-distance silhouette in a slim panel below.
5. `main()` — CLI wiring, per-track summary printout (`--sparse` skips it, leaving just
   the summary lines: where it reads, the track/point totals, files written, and any date-filter skips), and
   `write_stats()` which writes a ride-log table to `stats/` (one row per ride, each
   tagged with its device type, plus one `Summary` totals row per device type).  With
   `--csv`, `write_csv()` also writes the same columns to a `stats/` CSV — a header row
   plus one data row per ride, but *no* per-device Summary rows.

Key non-obvious details:

- **Two different projection constants are used on purpose.** `PI_R`
  (`20037508.34` = π·R) scales the x/y Mercator coordinates; `EQUATOR`
  (`40075016.68` = 2π·R, the equatorial circumference) is used *only* for the
  detail calculation in `choose_detail()`. Do not "unify" them — the coordinate
  scaling must use π·R, not 2π·R.
- **Distance and elevation gain** (`_distance_and_gain`, and `decimate`) use an
  **equirectangular approximation** (local lat/lon → metre conversion with a
  mid-latitude cosine), not Haversine. Keep them consistent when changing one.
- **Ascent noise, climbs, scale bar** (TODO items [15]/[10]/[7]):
   * `--gain-noise M` (default `0`) trims GPS vertical jitter from the ascent.
     `_distance_and_gain` tracks a *running climb's* top and commits its ascent
     (top − base) only when a descent exceeds `M` metres (a vertical dead-band), so
    centimetre fix-to-fix noise stops inflating the figure while real climbs/descents
    are untouched.   `M=0` reproduces the old "sum of every rising segment" exactly
    (verified: the 115-ride total is 44,533 m); the wahoo_to_gpx.py copy stays
    unchanged (default `0` keeps the two identical).
   * `--climbs [N]` (default `10`) writes `stats/trackview-<range>_climbs.txt`: the N
     most-significant *sustained* climbs across all rides — a maximal run of segments whose
     *smoothed* grade (`_moving_avg`, `CLIMB_SMOOTH`) stays ≥ `CLIMB_MIN_GR` (4 %) over ≥
     `CLIMB_MIN_LEN` (250 m), ranked by a "climb score" = gain × average grade.  Pure
     geometry, so it works with `--no-map`; `_ride_climbs`/`_all_climbs`/`write_climbs`.
   * A scale bar (`_draw_scale_bar`, `_nice_m`, `_fmt_len`) is drawn in every map's
     lower-right corner (`--no-scale` omits it): a "nice" 1/2/5×10ᵏ length of ~15 % of the
     visible width, in Web-Mercator metres (the `equal`-aspect axes makes a data-length line
     a true on-screen distance), with a white casing so it reads over a busy basemap.
- **Basemap fallback** (`_load_basemap`): providers are tried in order
  (`--style` first, then the rest of `SOURCES`). It catches fetch exceptions
  *and* detects blank/rate-limited tiles by checking that the returned image's
  pixel variance exceeds `min_var`; on failure it sleeps 2 s and tries the next
  provider. A failed or blank tile is expected to trigger fallback, so this is
  intentionally not covered by tests.
- **Rendering is headless** — `matplotlib.use("Agg")` is set before importing
  `pyplot`. The figure is square (`FIGURE_IN = (11, 11)`) and `fit_aspect()`
  grows the bounding box to match the figure aspect so the map is never letter-boxed.
- **Colouring modes** (`--color-by {elev,grade,flat,speed,power}`, default `elev`; `--no-elev` is a visible alias for `flat`): each track is shaded by a metric along its path.  Elevation uses the perceptually-uniform `viridis` ramp (`CMAPEL`, dark low end and bright high end both read on a pale basemap, unlike the old light `terrain`); grade uses a **grey-centred** diverging ramp (`CMAPGRADE`, `GRADE_STOPS`) — steep descents blue, steep climbs red, and the 0 % neutral a visible mid-**grey** rather than white, so a flat route stays visible.  The grade norm is **capped robustly** (the `GRADE_CAP_PCT` percentile of |grade|, clamped to `GRADE_CAP_FLOOR`/`GRADE_CAP_CEIL`) so a lone GPS-noise spike can't squash the ramp to its neutral centre, and `--grade-cap N` pins that range instead of the auto cap.   On a *combined* grade map a few rides (≤ `GRADE_CBAR_MAX`) each get their **own** colourbar at their own cap (via `_stack_grade_colorbars`/`_short_label`) so one steep ride can't desaturate the others; beyond that, or when a cap is pinned, a single shared colourbar is used and a line on stdout says so.   In `--profile`, the per-segment grade line is lightly smoothed (`_moving_avg`, `GRADE_SMOOTH`) to quiet GPS jitter.  Every metric-shaded route is under-laid with a subtle **dark outline** (a touch wider than the line) so it pops on the busy basemap; the flat mode keeps a white halo.  `--color-by flat`/`--no-elev` (or `elev` when the total elevation range is ≤ 1 m) gives one bold distinct colour per track instead.   `speed`/`power` shade the route by **per-segment telemetry** on the same perceptually-uniform effort ramp (`CMAPEED="inferno"`, fast/high = hot): each segment takes the average of its two endpoints and the norm is `_metric_norm` — a robust `[2 %, 98 %]` percentile range so a lone GPS spike can't squash it.  They need the per-point values that `load_tracks` now retains by carrying a per-point record through `decimate(carry=...)` (`d["speed_pts"]`/`d["power_pts"]`/`d["tsec"]`, aligned with `merc`/`ele`/`grade`); that collection is auto-enabled when `--color-by speed/power` or `--heat` is set even without `--ext` (which still gates the avg-telemetry title line and the ride-log columns), and a track without telemetry falls back to its flat colour with a note on stdout.  The active mode sets the colourbar and the title's `shaded by …` suffix.
- **Time-on-route density & ride labels.**  `--heat` (a map-only flag, ignored under `--no-map`) draws a 2-D "time on route" density *under* the route lines: `_draw_heat` builds a `HEAT_GRID`×`HEAT_GRID` (300×300) `np.histogram2d` of the routes' decimated points over the bbox, each cell weighted by the **time on the segments through it** (a slow climb / rest stop / traffic glows more than a fast pass) from `_dwell_times(d["tsec"], n)` — point j carries the time on the segment *leaving* it, the last point its incoming one; a ride with no usable timestamps falls back to a uniform point-count weight, so `--heat` works even without `--ext`.  It is drawn on a `YlOrRd` ramp at `HEAT_ALPHA` (0.55) with empty cells masked (basemap shows through) and the colour capped at `HEAT_CAP_PCT` (98 %), and carries a "Time on route" colourbar whose ticks are formatted as a duration by `_fmt_heat_time` (`N s` / `N m` / `Nh Mm`, a `FuncFormatter`); when a metric colourbar is already on the right edge that one is shown instead, with a note on stdout.  `--labels` (also map-only) tags each route's start marker on a *combined* map (`len(tracks) > 1`) with a halo'd `name      N km` line via `_short_label`, staggered vertically by the ride's index so co-located loop starts stay legible; a single track is left unlabelled (its name is in the title).
- **Stationary-trainer tracks are suppressed from the map only.** Before
   `render()`, `main()` drops any track whose `Device:` line matches
   `SUPPRESSED_RENDER_DEVICES` (currently `{"Kickr Snap"}` — a smart trainer logs a
   fixed location, not a route, so it would just clutter the basemap). The split is
   computed once: the image (combined and `--split`) is built from the remaining
   tracks, while `write_stats()`/`write_csv()` still use the full set, so a trainer
   ride is always listed in the ride-log/CSV. A `suppressing N 'Kickr Snap'` line is
   printed when any are dropped.
- The `gpx/` input, `output/` and `stats/` are git-ignored; GPX files here are
  Strava exports named `YYYY-MM-DD_<id>_<date>.gpx`.
- **Ride-log stats table** (`write_stats`): every run writes
    `stats/trackview-<first>_<last>.txt`, where `<first>`/`<last>` are the earliest
  and latest ride dates — `tracks[0]`/`tracks[-1]` via `_title_name` (the glob is
  date-sorted, so these are the first/last rides); one ride's date repeats for a
  single-track run.  Each ride row carries the ride stats plus its **device type**, the
  last column (from the GPX `Device:` line, parsed by `_device_type`; a track with none
  reads as `unknown`).  The table closes with one **`Summary`** totals/averages row **per
  device type** (`_device_groups` groups the rides; that device's name, shown last, in the
  Device column).  Columns mirror the two title lines; under `--ext` two more appear — a **Max grade (%)** (the ride's steepest segment, geometry-derived rather than read from the `grade` extension) and an **Avg temperature (°C)** (from the `temperature` extension) — alongside the calories-burned total and avg power/speed/cadence/hr.  A `-` marks a metric a ride does not carry.  `--no-map`
  skips the `render()`/basemap step (no image, no network fetch — the map-only flags `--out`/`--format`/`--style`/`--detail`/`--split`/`--no-elev`/`--color-by`/`--grade-cap`/`--profile`/`--heat`/`--labels`/`--no-scale` are then no-ops) but still runs this stats write, so a stats-only run is possible.
- **CSV ride-log** (`--csv`, `write_csv`): also writes
   `stats/trackview-<first>_<last>.csv` — the same columns as the `.txt` ride-log
   (incl. the Device column, shared via `_stats_columns`), but just a header row + one
   data row per ride, with **no** title/rules/per-device Summary rows (those totals live
   only in the `.txt`).  The field delimiter is `--csv-delimiter`
   (default `;`, the European/Excel default; e.g. `,`).  Numbers are decimal-
   normalised for the CSV (no column padding, no thousands grouping — the shared
   formatters keep both for the `.txt` table), so the stdlib `csv` module only ever
   quotes a field that genuinely contains the delimiter (e.g. a comma in a ride name).

## Basemap providers (`--style`)

`topo` (OpenTopoMap, default), `sat` (Esri World Imagery), `terrain`
(Esri World Terrain Base), `osm` (German OSM tile server). A proper `User-Agent`
is sent and attribution is printed on the image and console.

## Related work

The parent `workarea` has a separate GPX viewer, `gpx_viewer.py`
(Streamlit + Folium, interactive upload-based map) — a different approach from
this static-PNG renderer. They do not share code.


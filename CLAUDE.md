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
.venv/bin/python trackview.py --profile --split     # an elevation + grade + telemetry "ride card" under each map
.venv/bin/python trackview.py --ext                 # avg power/speed/cadence/hr/temperature + calories burned (kcal)
.venv/bin/python trackview.py --no-map                # skip the map/image; just compute the stats + write stats/
.venv/bin/python trackview.py --since 2026-09-05       # only tracks on/after a date (from the .gpx filename)
.venv/bin/python trackview.py --until 2026-09-08       # only tracks on/before a date (from the .gpx filename)
.venv/bin/python trackview.py --today                  # a "what did I ride today?" glance: --flat --since <today> (no-fetch with --list)
.venv/bin/python trackview.py --device "Wahoo ELEMNT BOLT"  # restrict to one device    (GPX <desc> "Device:")
.venv/bin/python trackview.py --sport Bike                  # restrict to one sport     (GPX <desc> "Sport:")
.venv/bin/python trackview.py --top 10 --by gain            # render/stat only the N highest-gain rides (or --by km/recent)
.venv/bin/python trackview.py --top 5                       # ... or the N most recent (--by default)
.venv/bin/python trackview.py --list                        # list the rides that survive every filter, then stop (no basemap, no image)
.venv/bin/python trackview.py --list --since 2026-09-01 --top 10 --by gain # preview a filter selection without fetching a basemap
.venv/bin/python trackview.py --csv                    # also write a CSV ride-log (header + rows, no totals) to stats/
.venv/bin/python trackview.py --csv --csv-delimiter ,   # comma-separated instead of the default ';'
.venv/bin/python trackview.py --sparse                   # quiet stdout: skip the per-track stats listing
.venv/bin/python trackview.py --no-scale                 # omit the map's lower-right scale bar (on by default)
.venv/bin/python trackview.py --no-cache                 # fetch tiles fresh each run (default: cache them under tiles/)
.venv/bin/python trackview.py --heat                     # overlay a 2-D "time on route" density under the routes
.venv/bin/python trackview.py --labels                   # tag each route's start with name + distance (a combined map)
.venv/bin/python trackview.py --gain-noise 1.5           # ignore GPS vertical jitter when summing ascent
.venv/bin/python trackview.py --climbs 10                # also write a climb ranking to stats/
.venv/bin/python trackview.py --trend                    # also write a per-ride training-trend chart over ride date to output/
.venv/bin/python trackview.py --calendar                 # a GitHub-style activity grid (km/day) over the year -> output/
.venv/bin/python trackview.py --calendar --calendar-by gain # colour each day by m gain (or 'rides') instead
.venv/bin/python trackview.py --summary                  # also write a year-in-review report (per year/month) -> stats/
.venv/bin/python trackview.py --html                     # a self-contained interactive Leaflet map (inline GeoJSON + a tile layer) -> output/
.venv/bin/python trackview.py --html --html-cdn          # reference Leaflet from a CDN instead of inlining it
.venv/bin/python trackview.py --gallery 6                   # tile the N most recent rides into one mosaic contact sheet -> output/ (bare --gallery = 9, a 3x3)
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
   collected and falling back to a flat colour when absent); or flat distinct colours); `--profile`
   renders a "ride card" — the elevation + grade silhouette (geometry-derived, no telemetry) plus
   a slim telemetry mini-panel per metric the ride carries (power/speed/HR/cadence, auto-
   collected) — under each map (needs `--split`, or a single track).
  `--since`/`--until` (each a `YYYY-MM-DD`) keep only the tracks whose ride date
  (read from the Wahoo-style filename stem) falls in the range — mirroring
  `wahoo_to_gpx --since/--until`; a filename with no date is skipped when a bound is set.
   `--device NAME`/`--sport NAME` narrow the rides to one device and/or sport — matched
   case-insensitively on the GPX `<desc>` "Device:"/"Sport:" line that `wahoo_to_gpx` stamps
    (e.g. `Wahoo ELEMNT BOLT`, `Bike`) — complementing the date filter for a mixed-device/sport
   folder.  Unlike the filename-based date filter these are read from the *parsed* `<desc>`, so
    the filter runs *after* `load_tracks` (see Key non-obvious details); a ride with no such
    line is skipped (never guessed), and when nothing matches the run stops.

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
  Grade, by contrast, is *geometry-derived* (see Colouring modes below), so `--color-by grade` and a `--profile` elevation + grade silhouette need no telemetry at all (the `--profile` telemetry mini-panels auto-collect it).

## Garmin -> GPX (`fit_to_gpx.py`)

`fit/` holds Garmin `.fit` ride exports (one binary file per ride; Connect names
them after the ride *and* a device serial, e.g.
`2026-09-21-061925-ELEMNT BOLT A8C5-660-0_2026_09_21_08_19_24.fit`).  A `.fit` is
a stream of typed
messages parsed by `fitparse` — a `file_id`, optional `device_info`, a `session`
(totals/sport) and one `record` per second carrying the point + telemetry.
`fit_to_gpx.py` gathers the `record` stream into the *same* GPX 1.1 track in
`gpx/` as `wahoo_to_gpx.py`, so `trackview.py` renders the Garmin rides
alongside the Wahoo and komoot ones:

```bash
.venv/bin/python fit_to_gpx.py                      # ./fit -> ./gpx
.venv/bin/python fit_to_gpx.py --ext                 # also embed power/cad/hr/speed(km/h)/grade/temp
.venv/bin/python fit_to_gpx.py --since 2026-09-05             # only rides on/after a date
.venv/bin/python fit_to_gpx.py --until 2026-09-08             # only rides on/before a date
.venv/bin/python fit_to_gpx.py <file.fit> --out-dir DIR
```

Non-obvious FIT/fitparse quirks the converter handles (and why):
- the **output is named after the ride start time**, the Wahoo-style
  `YYYY_MM_DD_HH_MM_SS.gpx` (from the `session`/`file_id`/first-record start time,
  *not* the long Garmin filename), so `trackview._ride_date` reads the date off
  the stem and the Garmin rides sort / filter / sheet exactly like the Wahoo ones
  (the original `.fit` name is kept in the GPX `<desc>` "Converted from …");
- the **device / sport are reworded to the Wahoo voice**: fitparse renders the
   FIT enum to machine words (`wahoo_fitness`, `cycling`), which the converter
   maps to the human words `wahoo_to_gpx` stamps (`Wahoo ELEMNT BOLT`, `Bike`), so a
   Garmin ride reads the same as a Wahoo one and `trackview --device` / `--sport`
   match across both (an unknown word passes through untouched);
- **position is stored in "semicircles"** (a Garmin unit, full circle = 2³¹),
  speed in m/s and distance in metres — all normalised by
  `StandardUnitsDataProcessor` (semicircles -> degrees, m/s -> km/h, m -> km), so
  no manual scale factors, matching the Wahoo export;
- **`ALT == -500 m` is the "no altitude" sentinel** (a raw `0` against the FIT
  altitude offset of 500; also an absent field) -> filled from the neighbouring
  valid altitude, the FIT analogue of Wahoo's `0 m` sentinel; `enhanced_altitude`
  (barometric) is preferred over the GPS `altitude` when present;
- records with `position_lat/long == 0/None` are "no fix" (ride start/stop) -> dropped;
- each record carries its own UTC `timestamp`, written with a `Z` suffix (a
  tz-aware UTC `datetime`) to match the existing tracks;
- a filename may be a **bare device serial with no date**, so the `--since`/
  `--until` ride date falls back to the file's `session`/`file_id` start time when
  the name is undated (a Wahoo/`komoot` stem is always dated, so it never does);
- distance/gain use the **same equirectangular approximation as `trackview.py`**
  (`_distance_and_gain`), copied verbatim so the two stay consistent;
- the `--ext` tags are **identical to `wahoo_to_gpx.py --ext`** (`power`/
  `speed_kmh`/`cadence`/`heartrate`/`grade`/`temperature` as un-namespaced
  `<trkpt><extensions>` children), so `trackview.py --ext` reads them back the
  same way (and the grade caveat above applies unchanged).

## Notes / testing

There is **no linter, formatter, or CI**, but there *is* an automated `pytest`
suite in `tests/` (configured by `pyproject.toml`: `testpaths = ["tests"]`, plus the
`network`/`slow` markers).  It is **pure by default** — no network, no figures — so
the whole thing runs offline in a fraction of a second:

```bash
.venv/bin/pytest                                 # the full suite (75 pass, 1 skip)
.venv/bin/pytest -m "not network and not slow"    # the pure subset — what CI should run
```

The modules map onto the TODO range — `test_parse_helpers.py` [25] (`_ride_date`/
`_parse_argdate`), `test_geometry.py` [26] (`_grade_cap`/`_moving_avg`/`_select_top`),
`test_filters.py` [27] (the `--since`/`--until` → `--device`/`--sport` → `--top --by`
composition, plus the `--today` fold), `test_load_tracks.py` [24] (in-memory `gpxpy`
rides, with and without `<extensions>` telemetry) and `test_dry_run.py` [28] (the
`--list` "writes nothing" contract), and `test_fit_to_gpx.py` [29] (a hand-built `.fit` parsed to a track: no-fix dropped, the `-500 m` altitude sentinel filled, semicircles -> degrees, the start-time output stem, the device/sport reword, and `--since`/`--until`).  `tests/conftest.py` supplies the shared
fixtures/helpers — `build_ride`, `write_ride`, `gpx_points`, `gpx_folder`,
`ride_paths`, `run_filters`, `run_main` (the last points `output/`/`stats/` at a
`tmp_path` so a `main()` run never writes into the repo).  The one heavy path,
`test_render_smoke.py` (a real basemap fetch + matplotlib figure render), sits behind
*both* markers and is **skipped** in the default run; opt in with
`TRACKVIEW_TEST_NETWORK=1 .venv/bin/pytest -m "network and slow"`.

When you can't run the suite, a quick fallback is to syntax-check:
`.venv/bin/python -c "import ast; ast.parse(open('trackview.py').read())"`.

## Architecture

Everything lives in `trackview.py`. The pipeline runs top-to-bottom:

1. `main()` discovers `*.gpx` (recursively into subfolders by default; `--flat` for one level) and applies the `--since`/`--until` date filter
   (by filename stem, via `_ride_date`/`_parse_argdate`); `load_tracks(paths)`
   then parses each remaining file with `gpxpy`, flattening all
   track→segment→point into one `(lat, lon, ele)` list per file.
    A `--device`/`--sport` filter then runs *after* `load_tracks` (its values live in the
   parsed `<desc>`, not the filename), narrowing the `tracks` list every downstream reader sees.
2. `decimate()` — drop points closer than `DECIMATE_M` (5 m) apart to cut
   ~68k points/file down to a few thousand. First and last points are always kept.
3. `latlon_to_merc()` — project to Web Mercator (EPSG:3857) for plotting.
4. `render()` — fetch the raster basemap, overlay each track (white halo underlay
   + colour ramp), add start/stop markers, legend, colourbar, title, attribution,
   and save the PNG.  With `--profile` a single-track (or `--split`) figure instead grows
   into a *ride card*: a `GridSpec(2 + n_prof, 1)` (`height_ratios=[3.0, 1.3] + [0.5]*n_prof`)
   with the map on top, a `_draw_profile()` elevation + grade-vs-distance silhouette, then one
   slim telemetry mini-panel per metric the ride carries (`_draw_profile_metric`, driven by
   `PROF_METRICS` — power/speed/HR/cadence in a fixed order + colour, gated by
   `_has_metric_pts`).   `--profile` auto-collects that telemetry (no `--ext` on the line), and the figure grows only
   with the metrics present.
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
    * `--trend` writes a per-ride *training-trend* chart to
     `output/trackview-<range>_trend.<format>` — one stacked panel per metric *over ride
     date* (distance, elevation gain, duration, and a calories-burned panel when a ride
     carries a power average): each ride placed on its Wahoo-filename date (`_ride_date`),
     sorted so a panel reads left-to-right in time, a filled line on a shared `mdates`
     date axis (`AutoDateLocator` + a `%b %Y` formatter), colour-cycled from `_TREND_COLORS`.
     A standalone figure (no basemap, no network), so it writes even under `--no-map`;
     undated rides are skipped (the title notes how many).    `_trend_panels`/`write_trend`.
   * A scale bar (`_draw_scale_bar`, `_nice_m`, `_fmt_len`) is drawn in every map's
     lower-right corner (`--no-scale` omits it): a "nice" 1/2/5×10ᵏ length of ~15 % of the
     visible width, in Web-Mercator metres (the `equal`-aspect axes makes a data-length line
     a true on-screen distance), with a white casing so it reads over a busy basemap.
- **Activity calendar & year-in-review** (TODO [13]/[14]) — both *standalone* outputs (no
   basemap, no network, so they write even under `--no-map`):
    * `--calendar` writes a GitHub-style *activity grid* to
     `output/trackview-<range>_calendar.<format>`: one 7 (weekday, Mon–Sun) × ISO-week block
     per calendar year that has rides, stacked top-to-bottom and each labelled with its year,
     every day a square coloured by that day's total on a sequential ramp with a pale "no-ride"
     end, so a busy stretch glows and a rest gap goes blank.  The metric is
     `--calendar-by {distance,gain,rides}` (default `distance`, km/day on `Greens`; `gain` m/day
     on `OrRd`, `rides` a count on `Blues`); `--year YYYY` restricts to one calendar year.  All
     days share one colour scale (0 .. the busiest day) so the stacked years compare, with a
     single colourbar in the right margin; the x-axis is labelled by *month* (a tick at the first
     week of each month, not by week number, so a partial year shows only the months it spans).
     Each ride is placed on its `_ride_date` (an undated ride is skipped, the title notes how
     many).   `_calendar_days`/`write_calendar` (with `_month_ticks` for the month x-axis).
    * `--summary` writes a per-year, per-month *year-in-review* aggregate of the ride-log to
     `stats/trackview-<range>_summary.txt`: the dated rides grouped by calendar year, and within
     each year by month, each with its ride count, total distance, gain and hours — plus, under
     `--ext` as the ride-log does, the group's point-weighted average power (`_metric_avg`, a `-`
     marks a group with none).  Each year is a block of monthly rows closed by a `TOTAL` row; a
     multi-year log closes with an `ALL years` grand total, and undated rides get a note.  Pure
     geometry, so it writes under `--no-map`; the avg-power column needs `--ext`.
     `_summary_groups`/`write_summary`.
- **Interactive HTML / Leaflet export** (`--html`, TODO [22]) writes a *self-contained, single-file*
   interactive map to `output/trackview-<range>_map.html` -- a *different* deliverable from the
   parent repo's `gpx_viewer.py` (a Streamlit + Folium upload app; no code shared).  Each ride is an
   *inline GeoJSON* LineString (`_tracks_geojson`/`_ride_feature`, from the decimated `d["ll"]`
   lat/lon `load_tracks` now keeps), coloured by its place in `STRONG_COLORS`, with a white-cased
   route, green/red start/stop markers, a click-for-stats popup and a clickable ride list, on a tile
   layer at the URL matching `--style`, fit to the data on load.  The Leaflet CSS + JS are *inlined*
   by default (`_load_leaflet`), so the one file opens from disk offline; the ~150 KB library is
   cached on disk under the git-ignored `lib/` (like the tile cache, via `_fetch_text`) so re-renders
   don't refetch, and `--html-cdn` references the library from a CDN instead (a smaller file that
   needs internet to *view*).  `--html` is *not* a map-only flag (a `--no-map` run still writes it):
   it fetches no basemap and needs no telemetry.  The embedded GeoJSON is JSON with `<` escaped (so a
   ride name can't close the `<script>`); ride names shown in the DOM are HTML-escaped client-side.
    `_leaflet_document`/`write_html`.
- **Gallery / contact sheet** (`--gallery [N]`, bare = 9; TODO [23]) tiles the N *most recent* rides of the already-filtered `tracks` into one mosaic at `output/trackview-<range>_gallery.<format>` (`write_gallery` -> `_gallery_grid` lays a near-square rows x cols grid, 3x3 for 9, 2x3 for 5; `_gallery_cell` draws each cell = that ride's own basemap + route via the shared `_load_basemap`, flat `STRONG_COLORS` per cell, white-cased, green/red start/stop, a name/distance/gain caption).  The rides are sorted newest-first (`_ride_date` ordinal) so the top-left cell is the latest; a route-less ride (< 2 points, e.g. a suppressed trainer ride) is dropped and an empty set writes nothing (a line on stdout).  It is a *map* output (a basemap per cell, so it honours `--style`/`--detail`/the tile cache and is skipped under `--no-map`, alongside the ride-log/CSV), the mosaic alternative to `--split` (which the `main()` render branch treats as mutually exclusive: `--gallery` takes precedence).
- **Basemap fallback** (`_load_basemap`): providers are tried in order
  (`--style` first, then the rest of `SOURCES`). It catches fetch exceptions
  *and* detects blank/rate-limited tiles by checking that the returned image's
  pixel variance exceeds `min_var`; on failure it sleeps 2 s and tries the next
  provider. A failed or blank tile is expected to trigger fallback, so this is
  intentionally not covered by tests.
- **On-disk tile cache** (`--no-cache` disables it): contextily already caches the
  tiles it downloads (a joblib `Memory` keyed by z/x/y per provider) but wipes its
  cache dir at process exit; `main()` points that cache at the git-ignored `tiles/`
  dir (`cx.set_cache_dir`, gated on `not args.no_cache`) before the render loop, so a
  re-render -- or a run with no network -- reuses the tiles already on disk instead of
  refetching every one, easing the rate-limit pressure the fallback above exists to
  absorb.  `--no-cache` leaves contextily's ephemeral per-session cache (the old
  behaviour); a map-only flag, ignored under `--no-map`.
- **Rendering is headless** — `matplotlib.use("Agg")` is set before importing
  `pyplot`. The figure is square (`FIGURE_IN = (11, 11)`) and `fit_aspect()`
  grows the bounding box to match the figure aspect so the map is never letter-boxed.
- **Colouring modes** (`--color-by {elev,grade,flat,speed,power}`, default `elev`; `--no-elev` is a visible alias for `flat`): each track is shaded by a metric along its path.  Elevation uses the perceptually-uniform `viridis` ramp (`CMAPEL`, dark low end and bright high end both read on a pale basemap, unlike the old light `terrain`); grade uses a **grey-centred** diverging ramp (`CMAPGRADE`, `GRADE_STOPS`) — steep descents blue, steep climbs red, and the 0 % neutral a visible mid-**grey** rather than white, so a flat route stays visible.  The grade norm is **capped robustly** (the `GRADE_CAP_PCT` percentile of |grade|, clamped to `GRADE_CAP_FLOOR`/`GRADE_CAP_CEIL`) so a lone GPS-noise spike can't squash the ramp to its neutral centre, and `--grade-cap N` pins that range instead of the auto cap.   On a *combined* grade map a few rides (≤ `GRADE_CBAR_MAX`) each get their **own** colourbar at their own cap (via `_stack_grade_colorbars`/`_short_label`) so one steep ride can't desaturate the others; beyond that, or when a cap is pinned, a single shared colourbar is used and a line on stdout says so.   In `--profile`, the per-segment grade line is lightly smoothed (`_moving_avg`, `GRADE_SMOOTH`) to quiet GPS jitter.  Every metric-shaded route is under-laid with a subtle **dark outline** (a touch wider than the line) so it pops on the busy basemap; the flat mode keeps a white halo.  `--color-by flat`/`--no-elev` (or `elev` when the total elevation range is ≤ 1 m) gives one bold distinct colour per track instead.   `speed`/`power` shade the route by **per-segment telemetry** on the same perceptually-uniform effort ramp (`CMAPEED="inferno"`, fast/high = hot): each segment takes the average of its two endpoints and the norm is `_metric_norm` — a robust `[2 %, 98 %]` percentile range so a lone GPS spike can't squash it.  They need the per-point values that `load_tracks` now retains by carrying a per-point record through `decimate(carry=...)` (`d["speed_pts"]`/`d["power_pts"]`/`d["tsec"]`, aligned with `merc`/`ele`/`grade`); that collection is auto-enabled when `--color-by speed/power`, `--heat`, `--profile` or `--trend` is set even without `--ext` (`--profile`/`--trend` use it only for the card's mini-panels / the trend's calories panel, not the `--ext` title line or ride-log columns), and a track without telemetry falls back to its flat colour with a note on stdout.  The active mode sets the colourbar and the title's `shaded by …` suffix.
- **Time-on-route density & ride labels.**  `--heat` (a map-only flag, ignored under `--no-map`) draws a 2-D "time on route" density *under* the route lines: `_draw_heat` builds a `HEAT_GRID`×`HEAT_GRID` (300×300) `np.histogram2d` of the routes' decimated points over the bbox, each cell weighted by the **time on the segments through it** (a slow climb / rest stop / traffic glows more than a fast pass) from `_dwell_times(d["tsec"], n)` — point j carries the time on the segment *leaving* it, the last point its incoming one; a ride with no usable timestamps falls back to a uniform point-count weight, so `--heat` works even without `--ext`.  It is drawn on a `YlOrRd` ramp at `HEAT_ALPHA` (0.55) with empty cells masked (basemap shows through) and the colour capped at `HEAT_CAP_PCT` (98 %), and carries a "Time on route" colourbar whose ticks are formatted as a duration by `_fmt_heat_time` (`N s` / `N m` / `Nh Mm`, a `FuncFormatter`); when a metric colourbar is already on the right edge that one is shown instead, with a note on stdout.  `--labels` (also map-only) tags each route's start marker on a *combined* map (`len(tracks) > 1`) with a halo'd `name      N km` line via `_short_label`, staggered vertically by the ride's index so co-located loop starts stay legible; a single track is left unlabelled (its name is in the title).
- **Stationary-trainer tracks are suppressed from the map only.** Before
   `render()`, `main()` drops any track whose `Device:` line matches
   `SUPPRESSED_RENDER_DEVICES` (currently `{"Kickr Snap"}` — a smart trainer logs a
   fixed location, not a route, so it would just clutter the basemap). The split is
   computed once: the image (combined and `--split`) is built from the remaining
   tracks, while `write_stats()`/`write_csv()` still use the full set, so a trainer
   ride is always listed in the ride-log/CSV. A `suppressing N 'Kickr Snap'` line is
   printed when any are dropped.
- **Device / sport filter** (`--device NAME`/`--sport NAME`, TODO [17]) narrow the rides to
   one device and/or sport — an exact, case-insensitive, whitespace-trimmed match on each ride's
  own GPX `<desc>` "Device:"/"Sport:" value (the lines `_device_type`/`_sport_type` parse, e.g.
    `Wahoo ELEMNT BOLT`/`Bike`, stamped by `wahoo_to_gpx`).  Because those values live in the
   *parsed* `<desc>` (not the filename, as the date filter's do), `main()` applies
    `_filter_by_meta(tracks, ...)` *after* `load_tracks`, and the narrowed list flows to every
   downstream reader — the map, the ride-log/CSV and the stats reports.  A ride carrying no such
     line is skipped (never guessed, as an undated ride under `--since`/`--until`); when nothing
    matches the distinct values the log *does* carry are printed (a typo is easy to fix) and the
    run stops.  They gate the stats too, so they are *not* in the map-only flag list (a `--no-map`
   run still honours them).
- **Top-N filter** (`--top N --by {km,gain,recent}`, default `recent`, TODO [18]) keeps only the
   `N` most-significant rides — a "best-of" map, or a way to keep a huge combined map legible —
   ranked by `dist_km` (`km`), `gain_m` (`gain`) or the Wahoo-filename ride date (`recent`).  As with
   `--device`/`--sport` (it runs *after* those too, so it selects the top `N` of whatever rides
   remain), `main()` applies `_select_top(tracks, N, by)` *after* `load_tracks` and the narrowed list
   flows to every downstream reader — the map, the ride-log/CSV and the stats reports.  `_select_top`
   re-sorts the survivors back into the original date-ascending order (the (recursive) glob is date-ascending, so the
   ride-log and the `trackview-<first>_<last>` filename still read as usual); a stable rank keeps ties
   in that order, a ride with no filename date ranks last under `recent` (but still wins on a pure value
   under `km`/`gain`), and `N` ≥ the ride count (or `N` ≤ 0) is a no-op.  It is *not* a map-only flag
   (a `--no-map` run still honours it).
- **Dry-run listing** (`--list`, TODO [20]) prints the rides that *would* be processed -- one
   `Date  Ride  Dist (km)  Gain (m)` line per ride that survives *every* filter (`--since`/`--until`,
   `--device`/`--sport`, `--top N --by`), closed by a `TOTAL` row -- then stops: it fetches no
  basemap and writes no image or stats/CSV/report, so a filter selection can be previewed cheaply.
  `main()` calls a new `_list_rides(tracks)` and `return`s *after* the `--top` filter (on the
  fully-filtered `tracks`) but *before* the basemap fetch, image and the stats/CSV/climbs/summary/
  trend/calendar writes; a ride with no filename date shows `undated`.  It prints its own listing
  (so it overrides `--sparse`) and is *not* a map-only flag (a `--no-map` run stops at `--list` too).
- **Today glance** (`--today`, TODO [21]) is the shorthand for `--flat --since <today>` — a one-flag
  "what did I ride today?" look.  `main()` folds it into the two existing knobs: it sets `args.flat = True`
  and `args.since = date.today().isoformat()` (a *runtime* date, never a baked-in constant), so every
  downstream reader — the date filter, `--list` and the stats path — sees the narrow selection transparently,
  and it composes with `--list` (a `--list --today` is a no-fetch dry-run of today's rides) and the stats
  path.  It is *not* a map-only flag (a `--no-map` run still honours it); it forces flat discovery, so
  today's ride must sit at the top level of the input dir (not a `year/` subfolder).
- The `gpx/` input, `output/`, `stats/`, `tiles/` (the on-disk basemap cache) and `lib/` (the cached Leaflet library, for `--html`) are git-ignored; GPX files here are
  Strava exports named `YYYY-MM-DD_<id>_<date>.gpx`.  Discovery recurses into subfolders by
  default (a `year/` layout — the real `gpx/` holds one folder per year); `--flat` restricts it
  to the input dir itself (the old single-level glob).
- **Ride-log stats table** (`write_stats`): every run writes
    `stats/trackview-<first>_<last>.txt`, where `<first>`/`<last>` are the earliest
  and latest ride dates — `tracks[0]`/`tracks[-1]` via `_title_name` (the (recursive)
  glob is date-ascending, so these are the first/last rides); one ride's date repeats for a
  single-track run.  Each ride row carries the ride stats plus its **device type**, the
  last column (from the GPX `Device:` line, parsed by `_device_type`; a track with none
  reads as `unknown`).  The table closes with one **`Summary`** totals/averages row **per
  device type** (`_device_groups` groups the rides; that device's name, shown last, in the
  Device column).  Columns mirror the two title lines; under `--ext` two more appear — a **Max grade (%)** (the ride's steepest segment, geometry-derived rather than read from the `grade` extension) and an **Avg temperature (°C)** (from the `temperature` extension) — alongside the calories-burned total and avg power/speed/cadence/hr.  A `-` marks a metric a ride does not carry.  `--no-map`
  skips the `render()`/basemap step (no image, no network fetch — the map-only flags `--out`/`--format`/`--style`/`--detail`/`--split`/`--gallery`/`--no-elev`/`--color-by`/`--grade-cap`/`--profile`/`--heat`/`--labels`/`--no-scale`/`--no-cache` are then no-ops) but still runs this stats write, so a stats-only run is possible.
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


# trackview -- API reference

`trackview` renders every GPX track in a folder onto a static map (PNG/PDF), with a
ride-log, a climb ranking, a training trend, an activity calendar and a self-contained
HTML/Leaflet map.  It has been broken up (PLAN.md Phases 1--3) into a small `trackview/`
package of single-purpose modules; the root `trackview.py` is now a thin launcher that
re-enters `trackview.cli:main`.

This reference is the **module map**: for each module, its role, the constants it holds,
and the functions it exposes.  The per-flag behaviour and the copy-paste command lines
live in the **Usage** and **Output** sections of `README.md` (the user-facing guide); this
file is the catalog of what each module *is* and *how the pieces fit together*.

## Two ways in

* **The command line** -- `python trackview.py [flags]`, or the installed `trackview`
  command (`pip install .`, `pyproject.toml` `[project.scripts]`).  Every flag and the
  outputs it drives are in `README.md` -> **Usage**.  This is the normal way to use the
  tool.
* **The programmatic surface** -- a handful of functions you could call from your own
  script if you want to drive the pipeline in code rather than through the CLI:
  `load_tracks` (read the rides), `render` / `write_gallery` (the figures), and the
  `write_*` reports (stats / climbs / summary / trend / calendar / html).  They share one
  in-memory ride-dict shape (the output of `load_tracks`), so the usual flow is
  `tracks = load_tracks(paths, ...)` then call the writers you want on `tracks`.

```python
from pathlib import Path
from trackview.load   import load_tracks
from trackview.mapfig import render
from trackview.stats  import write_stats

paths = sorted(Path("gpx").rglob("*.gpx"))
tracks = load_tracks(paths, decimate_m=5.0, with_ext=True)
if tracks:
    render(tracks, style="osm", out_path=Path("output/tracks_overview.png"), detail=None)
    write_stats(tracks, Path("stats/trackview-ride_log.txt"))
```

> **Naming note.**  The extraction carried the original monolith's helper names over
> verbatim, so most functions carry a leading `_`.  In this repo that underscore is a
> **house style, not Python's "private" signal**: the names *are* the cross-module API
> (every module imports the others' `_`-prefixed functions -- see the "Module map"
> dependency lines below), and there is no `__all__`.  Treat the module boundaries, not
> the leading `_`, as the interface.

## Module map

The modules are listed bottom-up (a module imports only those below it, so the dependency
tree is acyclic).  Each line after a module's role names the functions it exposes, in
definition order, with the first line of each function's docstring.

### `trackview.config` -- the centralised configuration

The shared paths and tunables every other module reads: `DATA_DIR` (the per-user
data dir: `$TRACKVIEW_HOME`, else `~/.trackview`), `GPX_DIR`, `OUTPUT_DIR`,
`STATS_DIR`, `TILE_CACHE_DIR` (the on-disk dirs, all under `DATA_DIR`), `DECIMATE_M`
(the default point thinning, metres) and `PI_R` (degrees->radians).  No functions.

### `trackview.geometry` -- geometry utilities

`PI_R` (re-exported constant).
* `latlon_to_merc(lat, lon)` -- WGS84 (lat, lon) -> Web-Mercator (x, y) in metres.
* `decimate(points, min_m, carry)` -- keep only points spaced >= `min_m` apart
  (equirectangular distance); returns the kept points and the carried-through values.
* `_distance_and_gain(points, noise_m)` -- total distance (km) and positive elevation
  gain (m); the gain ignores GPS vertical jitter below `noise_m`.
* `_grade_and_cumkm(points)` -- per-segment grade (%) and per-point cumulative distance
  (km).

### `trackview.metrics` -- metric / telemetry / calorie / formatting helpers

`GRADE_CAP_PCT`, `GRADE_CAP_FLOOR`, `GRADE_CAP_CEIL` (the grade-colour range),
`JOULES_PER_KCAL`, `METABOLIC_EFFICIENCY` (the calories-burned constants),
`_TELE_TAGS` (the per-point telemetry keys read from Wahoo `--ext` data).
* `_point_telemetry(point)` -- optional Wahoo telemetry off a trackpoint -> `{key: float}`
  (empty when the point carries none).
* `_metric_avg(tracks, key)` -- point-weighted average of a per-track `[sum, count]`
  metric across the tracks.
* `_metric_avg_track(t, key)` -- one ride's own average; `None` when it has no samples.
* `_max_grade(t)` -- a ride's steepest per-segment grade (%); `None` when it has none.
* `_max_grade_group(tracks)` -- the steepest grade across a group of rides.
* `_grade_cap(grades, grade_cap)` -- the `|grade|` colour-range cap: an explicit
  `--grade-cap` wins, else the `GRADE_CAP_PCT` percentile of `|grade|`, clamped to
  `[FLOOR, CEIL]`.
* `_track_calories(t)` -- this ride's "calories burned" (kcal): avg power (W) x ride
  duration (s) over `JOULES_PER_KCAL` and a ~25% efficiency; `None` without a power
  average or a ride span.
* `_calories_burned(tracks)` -- total "calories burned" (kcal) across the tracks.
* `_fmt_duration(total_s)` -- ride time as `Hh MMm` (`3h 05m`); `0m` under a minute.
* `_fmt_dur_or_dash(total_s)` -- as above, or a `-` for a track with no measured span.
* `_fmt_num(v, spec)` -- format a metric value, or a `-` when it is absent (`None`).

### `trackview.rendering` -- rendering helpers

`CMAPEED`, `GRADE_CBAR_MAX`, `SUPPRESSED_RENDER_DEVICES`, `GRADE_SMOOTH`, `HEAT_GRID`,
`HEAT_CAP_PCT`, `HEAT_ALPHA`, `DPI`, `STRONG_COLORS`, `PAD_FRAC`.
* `_metric_norm(vals, lo_pct, hi_pct)` -- a robust sequential colour norm for a telemetry
  metric (`--color-by speed/power`).
* `_moving_avg(arr, window)` -- centred moving average over a fixed odd window, skipping
  NaN (quiet the GPS jitter in a per-segment grade line).
* `_draw_profile(ax, t, x_label)` -- elevation + grade vs. cumulative distance for one
  track (grade on a twin axis).
* `_has_metric_pts(t, key)` -- `True` when a ride carries at least one value for a
  per-point telemetry array.
* `_draw_profile_metric(ax, t, key, label, color)` -- one telemetry mini-panel of the
  `--profile` "ride card".
* `_stack_grade_colorbars(fig, ax, cmap, norms, labels, unit)` -- one compact vertical
  colourbar per ride, stacked on the right of the map.
* `_nice_m(raw_m)` -- round a target length (m) up to the nearest 1/2/5 x 10^k for a tidy
  scale bar.
* `_fmt_len(m)` -- a scale-bar length: whole metres under a kilometre, else kilometres.
* `_draw_scale_bar(ax, bbox)` -- a `0 .. N km/m` scale bar in the map's lower-right
  corner.
* `_dwell_times(tsec, n)` -- per-point "time on route" (seconds): point `j` carries the
  time on the segment *leaving* it.
* `_fmt_heat_time(sec, pos)` -- a `--heat` colourbar tick: a time-on-route value (seconds)
  as `N s`, `N m` or `N h`.
* `_draw_heat(ax, tracks, bbox, grid, cap_pct, alpha)` -- a 2-D "time on route" density of
  the routes' decimated points, drawn *under* the route lines.

### `trackview.io` -- the basemap fetch and the HTML/Leaflet export

`USER_AGENT`, `SOURCES` (the tile providers, tried in order), `ATTRIBUTION`,
`LEAFLET_VER`, `LEAFLET_JS_CDN`, `LEAFLET_CSS_CDN`, `LEAFLET_DIR` (under
`config.DATA_DIR`), `LEAFLET_TIMEOUT`, `_APP_JS`, `EQUATOR`, `DETAIL_MIN`,
`DETAIL_MAX`.
* `_load_basemap(ax, bbox, order, detail, min_var, retries, backoff_s)` -- fall back
  through tile providers until one shows real tiles.
* `_html_escape(s)` -- escape the HTML-significant characters in a user-derived string.
* `_fetch_text(url, cache_path, timeout)` -- fetch `url` as text, caching the download
  under `cache_path`.
* `_load_leaflet(inline)` -- the Leaflet CSS + JS for the HTML head, as ready-to-inject
  elements (inlined, or CDN references).
* `_ride_feature(t, color)` -- one ride as a GeoJSON LineString feature.
* `_tracks_geojson(tracks)` -- the rides as a GeoJSON FeatureCollection.
* `_leaflet_document(gj, tile_url, attribution, title, css_html, js_html)` -- build the
  self-contained interactive-map HTML.
* `write_html(tracks, out_path, style, inline, title)` -- write a self-contained,
  single-file interactive Leaflet map to `out_path`.
* `choose_detail(bbox, target_px, dmin, dmax)` -- pick a tile detail level so the bbox
  spans roughly `target_px` pixels (clamped to `[dmin, dmax]`).
* `_gallery_grid(n)` -- rows x cols that fit `n` cells with as few empty slots as
  possible.
* `_gallery_cell(ax, t, idx, style, detail)` -- draw one mosaic cell: a single-ride
  basemap + its white-haloed, flat-coloured route, with a name/distance/gain caption.
* `write_gallery(tracks, out_path, style, n, detail)` -- tile the `n` most recent rides
  into one mosaic contact sheet.

### `trackview.load` -- the GPX reader

* `load_tracks(paths, decimate_m, with_ext=False, noise_m=0.0)` -- read every `.gpx` path
  (discovered and date-filtered by the caller), merge its segments into one polyline each,
  and -- over the pre-decimation samples -- accumulate the Wahoo `--ext` telemetry and the
  ride's first->last timestamp span (its duration, feeding the calories-burned estimate).
  This is the one entry into the pipeline: its ride-dict output is what every writer
  consumes.

### `trackview.helpers` -- metadata / filter / selection helpers

`_NAME_DATE_RE`, `_DEVICE_RE`, `_SPORT_RE`, `_UNSAFE_CHARS`, `_TOP_BY`, `_MONTH_ABBR`.
* `_title_name(name)` -- for a `--split` single-track title, show a Wahoo-style date stem
  when the name is one.
* `_ride_date(path)` -- the calendar date of a ride, read from the `.gpx` filename stem;
  `None` when the name carries no date.
* `_device_type(desc)` / `_sport_type(desc)` -- the device / sport embedded by
  `goldencheetah_to_gpx` as a `Device:` / `Sport:` line in the GPX `<desc>` (`None` when absent).
* `_device_label(device)` -- the ride-log "Device" cell text; `unknown` when the track
  carries no device.
* `_device_groups(tracks)` -- split the rides into `(device label, [rides])` groups in
  first-seen order.
* `_match_meta(t, device, sport)` -- `True` when a ride passes the active
  `--device/--sport` filter.
* `_filter_by_meta(tracks, device, sport)` -- keep only the rides passing the active
  `--device/--sport` filter.
* `_top_key(t, by)` -- a ride's `--top` ranking value on `by` (`km` / `gain` / `recent`).
* `_select_top(tracks, n, by)` -- keep only the top `n` rides ranked by `by`.
* `_list_rides(tracks)` -- the `--list` dry-run preview: one line per ride that survives
  every filter.
* `_parse_argdate(s, flag)` -- parse a `YYYY-MM-DD` CLI date, aborting with a clear error
  if malformed.
* `_safe_filename(name)` -- make a GPX file stem safe to use as an output filename.
* `_short_label(name, width)` -- a compact per-ride label for a stacked colourbar.

### `trackview.stats` -- the ride-log report

* `_stats_columns(show_ext)` -- the ride-log columns shared by `write_stats()` and
  `write_csv()` (each a `(header, key, ...)` tuple).
* `write_stats(tracks, out_path, show_ext)` -- write the ride-log table to `out_path`
  (a row per ride, plus a totals row).
* `write_csv(tracks, out_path, show_ext, delimiter)` -- write the same ride-log as CSV
  (a header row + one row per ride, no totals).

### `trackview.climbs` -- the climb-ranking report

`CLIMB_MIN_GR`, `CLIMB_MIN_LEN`, `CLIMB_SMOOTH`.
* `_ride_climbs(t, min_gr, min_len_m, smooth)` -- the sustained climbs in one ride:
  maximal runs of segments whose *smoothed* grade clears `min_gr` for at least
  `min_len_m`.
* `_all_climbs(tracks)` -- every climb across the tracks, ranked most-significant first
  (by score).
* `write_climbs(tracks, out_path, top_n, min_gr, min_len_m)` -- write the climb ranking to
  `out_path`.

### `trackview.summary` -- the year-in-review report

* `_summary_groups(tracks)` -- split the rides for the `--summary` report: dated rides
  grouped by year (and month); undated rides in their own group.
* `write_summary(tracks, out_path, show_ext)` -- write the year-in-review report to
  `out_path`.

### `trackview.calendar` -- the activity grid

`_CALENDAR_METRICS`.
* `_calendar_days(tracks, metric, year)` -- per-year day-totals for the grid:
  `{year: {(iso_week, iso_weekday): value}}`.
* `_month_ticks(year, weeks)` -- x-axis ticks for the grid, one per calendar month.
* `write_calendar(tracks, out_path, metric, year)` -- write the GitHub-style activity grid
  to `out_path` (one 7 x weeks block per year that has rides).

### `trackview.trend` -- the training-trend chart

`_TREND_COLORS`.
* `_trend_panels(tracks)` -- the chart's panels: one per metric over ride date (distance,
  elevation gain, duration, and a calories panel when a power average is available).
* `write_trend(tracks, out_path)` -- write the per-ride training-trend chart to
  `out_path`.

### `trackview.mapfig` -- the map / ride-card figure

`FIGURE_IN`, `CMAPEL`, `GRADE_STOPS`, `CMAPGRADE`, `PROF_METRICS`.
* `fit_aspect(bbox, aspect_wh)` -- grow the bbox (west, south, east, north) so it matches
  the figure aspect (so the basemap is never letter-boxed).
* `render(tracks, *, style, out_path, detail, color_by="elev", title=None,
  show_ext=False, split=False, profile=False, grade_cap=None, scale=True, heat=False,
  labels=False)` -- build and save the ride-map figure (plus its `--profile` ride card and
  `--heat` overlay); the top of the figure pipeline.

### `trackview.cli` -- the orchestrator

* `main()` -- parse the CLI and drive the whole pipeline.  This is the console entry point
  (`pyproject.toml` `[project.scripts]`, `trackview = "trackview.cli:main"`); it imports
  and dispatches to every writer above.

## Dependency direction

The tree is acyclic: `config` / `geometry` / `metrics` / `rendering` / `io` / `load` /
`helpers` are leaves (a module here imports only leaves *below* it), and the report
writers (`stats`, `climbs`, `summary`, `calendar`, `trend`) and the figure orchestrators
(`mapfig`, `cli`) sit on top.  `cli.main` is the single top -- it imports every writer --
and no module imports back up to it, which is why the `main`/`render` monolith could be
lifted out without a cycle.

## Where the user guide lives

Flag-by-flag behaviour, the `--style` base-map providers, the `tools/` helpers
(`goldencheetah_to_gpx`, `garmin_fit_reader`, `fit_to_gpx`) and the output formats are documented
in `README.md` (**Usage**, **Output**, **Base-map providers**, **Helper tools**).  This
`API.md` is the catalog; `README.md` is the how-to.

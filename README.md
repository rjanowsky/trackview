# trackview

Plot every GPX track in `./gpx` onto a static map image (PNG or PDF).

## What it does

1. Reads all `*.gpx` from the `gpx/` folder (`gpxpy`).
2. Decimates the points (default 5 m spacing) — keeps the route shape, cuts the
   point count for crisp, fast drawing.
3. Fetches a raster base map for the tracks' bounding box (`contextily`,
   OpenStreetMap by default — great for MTB/cycling).
4. Overlays each route, shaded by elevation, with a white halo, start/stop
   markers, an elevation colourbar, a legend and a title.
5. Writes `output/tracks_overview.png` by default (see **Output** for PDF and one-file-per-track).

## Setup

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

## Usage

```bash
python trackview.py                    # ./gpx -> ./output/tracks_overview.png
python trackview.py --format pdf           # vector PDF instead of PNG
python trackview.py --split                # one map file per track (default: all in one)
python trackview.py --style sat        # Esri satellite base map
python trackview.py --style terrain    # Esri shaded-relief
python trackview.py --detail 13          # override the auto-chosen detail
python trackview.py --no-elev          # flat per-track colour instead of elevation
python trackview.py --color-by grade        # shade the route by slope (climbs red, descents blue, flat grey)
python trackview.py --color-by grade --grade-cap 8   # pin the grade colour range to +/-8% instead of auto
python trackview.py --color-by power         # shade by effort (fast/high = hot; needs --ext, else flat)
python trackview.py --color-by speed         # shade by pace  (fast = hot;     needs --ext, else flat)
python trackview.py --profile --split        # an elevation + grade + telemetry "ride card" under each map
python trackview.py --ext                  # avg power/speed/cadence/hr/temperature + calories burned (kcal) in the title
python trackview.py --no-map             # skip the map image; just compute the stats + write the stats/ ride-log
python trackview.py --since 2026-09-08     # only tracks on/after a date (from the .gpx filename)
python trackview.py --until 2026-09-05     # only tracks on/before a date (from the .gpx filename)
python trackview.py --csv                 # also write a CSV ride-log (header + rows, no totals) to stats/
python trackview.py --csv --csv-delimiter ,   # comma-separated instead of the default ';'
python trackview.py --no-scale                # omit the map's lower-right scale bar (on by default)
python trackview.py --heat                   # overlay a 2-D "time on route" density under the routes (where you ride)
python trackview.py --labels                 # tag each route's start with name + distance (a combined map)
python trackview.py --gain-noise 1.5          # ignore GPS vertical jitter when summing ascent
python trackview.py --climbs 10               # also write a climb ranking to stats/
python trackview.py --trend                   # also write a per-ride training-trend chart (distance/gain/duration/calories) over ride date to output/
python trackview.py --calendar                 # a GitHub-style activity grid (km/day) over the year to output/
python trackview.py --calendar --calendar-by gain     # colour each day by m gain (or 'rides') instead of km
python trackview.py --calendar --year 2026   # restrict the grid to one calendar year
python trackview.py --summary                  # also write a year-in-review report (per year/month) to stats/
python trackview.py --sparse                 # quiet stdout: skip the per-track stats listing
```

## Output

- **Format** `--format {png,pdf}` (default `png`): PNG is a raster image; PDF is a
  vector file (crisp at any detail, small, good for print).
- **Combined vs split** `--split` writes one map file *per track*, named after its
  GPX file with spaces made filesystem-safe (e.g.
  `2026-09-07_3264766585_2026-09-07_11_45.png`). By default every track is drawn
  onto a single map.  In `--split` mode each map's title shows the ride date as
  `YYYY-MM-DD` (from a Wahoo-style filename stem, e.g. `2026_09_11_08_07_29`); any
  other name (e.g. a komoot title) is shown as-is.
- The file is `output/tracks_overview.<format>` unless overridden with `--out`;
  with `--split` the per-track files go to the same directory.  When `--out` is
  also given in `--split` mode its name is used as a *prefix* for the per-track
   files (e.g. `--out rides.png` → `rides_<ride>.png`); without `--out` they are
  just named after the GPX stem.
- **Shading / profile** `--color-by {elev,grade,flat,speed,power}` (default `elev`; `--no-elev` is a shorthand for `flat`) colours each route along its path: an elevation ramp (the perceptually-uniform `viridis`, dark low / bright high so both ends read on a pale basemap) by default, a **grey-centred** diverging grade ramp (steep descents blue, steep climbs red, 0% a visible mid-grey neutral) otherwise, or a flat distinct colour per track; and `speed`/`power` shade the route by telemetry on the same perceptually-uniform ramp (`inferno`, fast / high = hot) — each segment takes the average of its two endpoints and the range is a robust percentile (a lone GPS spike can't squash it), so they need the `--ext` telemetry (auto-collected when you ask for them) and a track without it falls back to its flat colour (a line on stdout says so).  The grade colour scale is capped at a high percentile of the data so a lone GPS-noise spike can't squash the ramp to its neutral centre, and every metric-shaded route is under-laid with a subtle dark outline so it pops on the busy basemap.  On a combined grade map a few rides (≤ 4) each get their *own* colourbar at their own cap, so a single steep ride can't desaturate the others; with more rides, or when you pin the range with `--grade-cap N`, a single shared colourbar is used (a line on stdout says so).  `--profile` renders a *ride card* beneath each map (it needs `--split`, or a single track): the elevation + grade silhouette (grade is computed from the track geometry and lightly smoothed, so it needs no telemetry) plus a slim mini-panel per telemetry metric the ride carries — power, speed, HR, cadence, each on its own strip and sharing the distance axis, in a fixed order and colour.  That telemetry is *auto-collected* (no `--ext` on the line); a metric the ride lacks (no HR strap, a plain komoot track) is skipped, and a ride with none falls back to elevation + grade only, with a line on stdout.
- **Scale bar** every map (except a `--no-map` run, or when `--no-scale`) carries a
  labelled `0 .. N km` scale bar in the lower-right corner — a static image has no zoom,
  so without it a distance can't be read off the picture.  The length is a "nice"
  1/2/5×10ᵏ of ~15 % of the visible width, drawn in Web-Mercator metres (the axes keeps an
  `equal` aspect, so a data-length line is a true on-screen distance) with a white casing
  so it stays legible over a busy basemap.
- **Time-on-route density** `--heat` overlays a 2-D density of *where you ride* under the route lines: a 300×300 histogram of the routes' decimated points over the map's bounding box, each cell weighted by the **time spent** on the segments through it (so a slow climb, a rest stop or a traffic queue glows more than a fast pass; a ride with no timestamps is weighted by point count instead), on a `YlOrRd` ramp at ~0.55 opacity with empty cells masked so the basemap shows through and the colour capped at a high percentile so one hot cell can't wash out the rest.  It carries a "Time on route" colourbar (ticks formatted as a duration, `N s` / `N m` / `Nh Mm`); when a metric colourbar is already on the right edge that one is shown instead, with a note on stdout.  A map-only flag, ignored with `--no-map`.
- **Ride labels** `--labels` tags each route's **start marker** on a *combined* map with a halo'd `name      N km` line (via `_short_label`), so a many-ride overview is identifiable without a legend key.  Loop rides often share one start, so the tags are staggered vertically by the ride's order to keep a handful of co-located starts legible; a single track is left unlabelled (its name is already in the title).  A map-only flag, ignored with `--no-map`.
- **Telemetry** `--ext` adds the calories-burned **total** (kcal) to the main title line and an average power / heart rate / speed / cadence / temperature line just below it, read from the `<extensions>` that `wahoo_to_gpx --ext` embeds.  The calories are estimated as average power times the ride's duration, divided by a ~25% efficiency (the rides carry no calorie field).  Tracks without telemetry (e.g. komoot) simply omit both.
- The ride **duration** (`Hh MMm`, e.g. `3h 42m`) is always on the title, between
  the distance and the elevation gain — the total across the tracks when combined.
- Every run also writes a **ride-log table** to `stats/trackview-<first>_<last>.txt` (`<first>`/`<last>` are the earliest and latest ride dates, `YYYY-MM-DD`): one row per ride with the same stats as the two title lines (distance, duration, gain — plus the calories-burned total and avg power / speed / cadence / hr / temperature when `--ext`, and a **max grade** column), plus its **device type** (from the GPX `Device:` line) as the last column, closing with a totals/averages **per device type** (device name in the Device column).  A `-` marks a metric a ride doesn't carry; a ride with no `Device:` line (e.g. a plain komoot track) reads as `unknown`.
- With `--csv`, the same columns (the ride stats plus a trailing device type) are also written to
  `stats/trackview-<first>_<last>.csv` — a header row plus one data row per ride, but
  **no** title or per-device Summary rows (header and data only).  The field delimiter
  is `--csv-delimiter` (default `;`, the European/Excel default; e.g. `,`).  Numbers are
  decimal-normalised for the CSV (no padding, no thousands grouping, unlike the `.txt`
  table); any field that genuinely contains the delimiter (e.g. a comma in a ride name)
  is quoted, keeping the file valid CSV.
- **Elevation-gain noise** `--gain-noise M` (default `0`, the raw ascent) trims GPS
  vertical jitter from the ascent: the gain is the sum of a *running* climb's rises — a
  descent ends the climb (resetting its base) only once it exceeds `M` metres, so
  centimetre-scale fix-to-fix noise stops inflating the figure while real climbs and
  descents are untouched.  It changes only the gain total (distance and duration are
  unaffected); `0` reproduces the old "sum of every rising segment" exactly.

- `--no-map` skips the basemap fetch and image entirely (no output image, no network) and just writes the ride-log table above — a stats-only run.  The map-only flags (`--out`/`--format`/`--style`/`--detail`/`--split`/`--no-elev`/`--color-by`/`--grade-cap`/`--profile`/`--heat`/`--labels`/`--no-scale`) are ignored when it is set.
- **Sparse output** `--sparse` quiets stdout: it skips the per-track stats listing (the
  one line per read ride) and prints only the summary lines — where it reads, the track
  count / point totals, the files written, and any `--since`/`--until` skips.  The
  ride-log and CSV files are unaffected.
- **Date filter** `--since`/`--until` (each a `YYYY-MM-DD`) keep only the tracks whose
  ride date falls in the range — read from the Wahoo-style filename stem (e.g.
  `2026_09_07_08_12_47` → `2026-09-07`), the same way `wahoo_to_gpx --since`/`--until`
  filters.  A track whose filename carries no date is skipped (never guessed) whenever a
  bound is active.
- **Climb ranking** `--climbs [N]` (default `10`) also writes
  `stats/trackview-<first>_<last>_climbs.txt`: the N most-significant *sustained* climbs
   across all the rides, a maximal run of segments whose smoothed grade stays ≥ 4 % over at
  least 250 m, ranked by a "climb score" (gain × average grade) so a long moderate climb can
  beat a short steep one.  Grade is pure geometry (no telemetry), so it works even with
   `--no-map`; each row gives the ride, where the climb sits (`from`/`to` km), its length,
  gain, average and steepest grade, and its score.
- **Training-trend chart** `--trend` writes a per-ride line chart of *distance, elevation
   gain, and duration* — plus a *calories-burned* panel when a ride carries a power average — *over
   ride date* to `output/trackview-<first>_<last>_trend.<format>`: all the rides on one shared
   time axis, so training volume and the span of the log read at a glance.  Each ride is placed
   on its Wahoo-filename date (`YYYY-MM-DD`) and the rides are sorted by it, so each panel reads
   left-to-right in time; a ride with no date in its filename can't be placed and is skipped (the
   title notes how many).  It is a standalone figure (no basemap, no network), so it writes even with
   `--no-map`, and it auto-collects the telemetry the calories panel needs.
- **Activity calendar** `--calendar` writes a GitHub-contribution-style *activity grid* to
   `output/trackview-<first>_<last>_calendar.<format>`: one 7 (weekday, Mon–Sun) × ISO-week block
   per calendar year that has rides, stacked top-to-bottom and each labelled with its year, every
   day a square coloured by that day's total on a sequential ramp with a pale "no ride" end, so a
   busy stretch glows and a rest gap goes blank.  A day that saw two rides sums them.  The metric
   is `--calendar-by {distance,gain,rides}` (default `distance`, km/day on a `Greens` ramp; `gain`
   is m/day on `OrRd`, `rides` is a ride count on `Blues`); `--year YYYY` restricts the grid to one
   calendar year.  Every day shares one colour scale (0 .. the busiest day) so the stacked years
   compare at a glance, with a single "metric/day" colourbar in the right margin.  The x-axis is
   labelled by *month* (a tick at the first week of each month, the GitHub way, not by week
   number), so a stretch of riding reads at a glance and a partial year shows only the months it
   spans.  Each ride is
   placed on its Wahoo-filename date (`YYYY-MM-DD`, the same `_ride_date()` the trend chart uses);
   a ride with no date can't be placed and is skipped (the title notes how many).  It is a
   standalone figure (no basemap, no network), so it writes even under `--no-map`.
- **Year-in-review summary** `--summary` writes a per-year, per-month aggregate of the ride-log to
   `stats/trackview-<first>_<last>_summary.txt`: the dated rides grouped by calendar year, and
   within each year by month, each shown with its ride count, total distance, total gain and total
   hours — and, under `--ext` as the ride-log does, the group's point-weighted average power (a `-`
   marks a group that carries none).  Each year is its own block of monthly rows closed by a `TOTAL`
   row; when the log spans several years an `ALL years` grand total closes the report, and any
   undated rides (no date in the filename, so unplaceable) get a note.  Pure geometry, so it writes
   even under `--no-map`; the avg-power column needs `--ext`.

## Base-map providers (`--style`)

| key         | source                                    |
| ----------- | ---------------------------------------- |
| `topo`      | OpenTopoMap — contours + relief           |
| `sat`       | Esri World Imagery (satellite)            |
| `terrain`   | Esri World Terrain Base                   |
| `osm`       | OpenStreetMap, German tiles (default)     |

Providers are tried in order; a failed or *blank* tile fetch (near-zero image
variance, e.g. rate-limiting) automatically falls back to the next one.

## Notes

- Base maps are fetched over the network at render time (a proper `User-Agent`
  is sent). Attribution is printed on the image and in the console.
- The projection is Web Mercator (EPSG:3857); the scaling constant is `π·R`
  (`20037508.34`), **not** the equatorial circumference `2·π·R`.



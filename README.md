# trackview

Plot every GPX track in your ride log (default: `~/.trackview/gpx`; relocate the
whole data dir with `$TRACKVIEW_HOME`) onto a static map image (PNG or PDF).

## What it does

1. Reads all `*.gpx` from the ride log's `gpx/` folder (default `~/.trackview/gpx`,
   see **Data location**) **and its subfolders** (`gpxpy`), so rides
   organised under a `year/` or `device/` layout are found too (`--flat` for a single level).
2. Decimates the points (default 5 m spacing) — keeps the route shape, cuts the
   point count for crisp, fast drawing.
3. Fetches a raster base map for the tracks' bounding box (`contextily`,
   OpenStreetMap by default — great for MTB/cycling).
4. Overlays each route, shaded by elevation, with a white halo, start/stop
   markers, an elevation colourbar, a legend and a title.
5. Writes `output/tracks_overview.png` by default (the data dir's `output/`, default
   `~/.trackview/output`; see **Output** for PDF and one-file-per-track).

## Data location

All input and output data lives under one **per-user data dir**, independent of where
the code is installed:

- **Default:** `~/.trackview` — a dot-prefixed home dir, so it stays out of the way
  and never collides with a `~/trackview` source checkout.
- **Override:** set `TRACKVIEW_HOME` to relocate it (an existing install, or a test
  pointing at a temp dir).  It is also the *multi-athlete* knob: give each rider a
  distinct home (`TRACKVIEW_HOME=~/.trackview-alice` vs. `~/.trackview-bob`) and each
  gets its own `gpx/`, `output/`, `stats/`, … from a single install, fully isolated.

Under it sit the folders the tool reads from and writes to: `gpx/` (the ride log it
plots), `gc/` and `fit/` (the two converters' inputs), and `output/`, `stats/`,
`tiles/`, `lib/` (the generated images, reports, the on-disk tile cache and the
cached Leaflet library).  Every one is created on demand: the outputs (`output/`,
`stats/`, `tiles/`, `lib/`) when first written, and the two converters' inputs
(`gc/`, `fit/`) on their first default run — so a fresh checkout needs no setup.
The paths named throughout this README (`gpx/`, `output/`, `stats/`, …) are
**relative to this data dir**, not the repo.

> **Why home, not the package?**  The tool plots *one athlete's* rides, so their data
> belongs in the user's home, not next to the code.  An older build anchored these dirs
> to the script's own location — which, once trackview is `pip install`ed, resolves to
> `site-packages/` (read-only, and the wrong place to write a ride log).  They now live
> under the data dir instead.
>
> **One-time migration:** if a *source checkout* still holds an old `gpx/` / `gc/` /
> `fit/`, either move them into the data dir, or point the old location at the tool for
> a while — e.g. run from inside that checkout with `TRACKVIEW_HOME=$PWD` (an existing
> install reads and writes its ride log there until the dirs are moved).

## Setup

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

The deps are also declared in `pyproject.toml` (PEP 621), kept in sync with
`requirements.txt` (the `fit` converter's `fitparse` is an optional extra there).  A
`pip install .` (or `pip install -e .`) additionally drops a `trackview` command onto the
PATH -- the installed counterpart to `python trackview.py` (the root launcher is a thin shim
that re-enters the same `main`).

## Testing

`pytest` (already in `.venv`) runs the pure suite -- no network, no figures, so it
is fast and offline:

```bash
.venv/bin/pytest                                  # the full suite
.venv/bin/pytest -m "not network and not slow"     # the pure subset (CI)
```

The two markers live in `pyproject.toml`: `network` (a basemap-tile / Leaflet-CDN
fetch) and `slow` (a matplotlib render).  The heavy path is behind both, so the
default run stays quick; run it with
`TRACKVIEW_TEST_NETWORK=1 .venv/bin/pytest -m "network and slow"`.

## Usage

```bash
python trackview.py --version          # print the trackview version and exit
python trackview.py                    # ride log -> output/ (both under ~/.trackview)
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
python trackview.py --today                 # a "what did I ride today?" glance: --flat --since <today> (a no-fetch glance with --list)
python trackview.py --device "Wahoo ELEMNT BOLT"       # restrict to one device   (GPX <desc> "Device:")
python trackview.py --sport Bike                       # restrict to one sport    (GPX <desc> "Sport:")
python trackview.py --top 10 --by gain                 # render/stat only the N highest-gain rides (or --by km/recent)
python trackview.py --top 5                            # ... or the N most recent (--by default)
python trackview.py --flat                             # look for *.gpx only in the input dir (default: recurse into subfolders, e.g. a year/ layout)
python trackview.py --list                                   # list the rides that survive every filter, then stop (no basemap, no image)
python trackview.py --list --since 2026-09-01 --top 10 --by gain # preview a filter selection without fetching a basemap
python trackview.py --csv                 # also write a CSV ride-log (header + rows, no totals) to stats/
python trackview.py --csv --csv-delimiter ,   # comma-separated instead of the default ';'
python trackview.py --no-scale                # omit the map's lower-right scale bar (on by default)
python trackview.py --no-cache                # fetch basemap tiles fresh each run (default: cache them on disk under tiles/)
python trackview.py --heat                   # overlay a 2-D "time on route" density under the routes (where you ride)
python trackview.py --labels                 # tag each route's start with name + distance (a combined map)
python trackview.py --gain-noise 1.5          # ignore GPS vertical jitter when summing ascent
python trackview.py --climbs 10               # also write a climb ranking to stats/
python trackview.py --trend                   # also write a per-ride training-trend chart (distance/gain/duration/calories) over ride date to output/
python trackview.py --calendar                 # a GitHub-style activity grid (km/day) over the year to output/
python trackview.py --calendar --calendar-by gain     # colour each day by m gain (or 'rides') instead of km
python trackview.py --calendar --year 2026   # restrict the grid to one calendar year
python trackview.py --summary                  # also write a year-in-review report (per year/month) to stats/
python trackview.py --html                     # a self-contained interactive Leaflet map (inline GeoJSON + a tile layer) to output/
python trackview.py --html --html-cdn          # reference Leaflet from a CDN instead of inlining it (a smaller file, needs internet to view)
python trackview.py --gallery 6                  # tile the N most recent rides into one mosaic contact sheet to output/ (bare --gallery = 9, a 3x3)
python trackview.py --sparse                 # quiet stdout: skip the per-track stats listing
```

## Directory Structure

```
trackview/            the importable package (the tool's internals, split into modules)
fit_to_gpx.py         Garmin .fit  -> GPX converter (top-level entry point, the `fit-to-gpx` command)
goldencheetah_to_gpx.py       GoldenCheetah JSON   -> GPX converter (top-level entry point, the `goldencheetah-to-gpx` command)
trackview.py          the root launcher: a thin shim that re-enters trackview.cli:main
pyproject.toml        build metadata, deps, the console entry points, ruff + pytest config
requirements.txt      the same runtime deps as a plain `pip install -r` list
tests/                the pytest suite (one module per feature; offline markers in pyproject.toml)
tools/                ad-hoc helpers: Garmin .fit diagnostics + a GPX trimmer (see Helper tools below)
samples/              sample rendered profiles (elevation/grade/power/speed strips), for the README
CHANGELOG.md          notable changes per release, in Keep a Changelog format (supersedes the git-ignored TODO.lst)
API.md                module-by-module reference -- the "module map"; per-flag usage lives in README.md
--
~/.trackview/         the per-user data dir ($TRACKVIEW_HOME to relocate); created on first use
  gpx/                GPX rides the tool renders (recurse into year/ subfolders)       [personal data]
  gc/                 GoldenCheetah ride exports (*.json, from a Wahoo ELEMNT BOLT)    [personal data]
  fit/                Garmin FIT ride exports (*.fit) that fit_to_gpx converts          [personal data]
  output/             generated images (the map, ride cards, trend, calendar, HTML)
  stats/              generated ride-log / CSV / climbs / summary reports
  tiles/              on-disk basemap-tile cache (keyed z/x/y, reused across runs)
  lib/                cached Leaflet CSS + JS the --html inlines for an offline map
```

The first block is the **source** that ships in the repo; the second is the
**per-user data dir** (`~/.trackview` by default, `$TRACKVIEW_HOME` to relocate, see
**Data location**) — the private ride data (`gpx/`, `gc/`, `fit/`) and the regenerable
output and cache (`output/`, `stats/`, `tiles/`, `lib/`).  It lives *outside* the repo,
so a clone holds only the source and nothing personal is ever committed; the data dirs
are created on first use.

- **`trackview/`** the package itself — the pipeline's internals split into
  focused modules: `config` (constants + `__version__`), `load` (GPX parse +
  decimation), `geometry` / `metrics` (grade, distance, telemetry math),
  `rendering` / `mapfig` (the matplotlib figures), the standalone outputs
  (`trend`, `summary`, `climbs`, `activitygrid`), `convert` (the helpers shared
  by the two converters), `io` / `helpers`, and `cli` (`main`, the entry point).
- **`trackview.py`** the launcher you run: `python trackview.py …`.  It is a thin
  shim over `trackview.cli:main`; the `pip install .` counterpart is the
  `trackview` console command, which re-enters that same `main`.
- **`goldencheetah_to_gpx.py`** / **`fit_to_gpx.py`** the two ingest converters:
  `gc/*.json` (GoldenCheetah) and `fit/*.fit` (Garmin) → `gpx/*.gpx`, so a ride from
  either source renders like any other.  Their console forms are the
  `goldencheetah-to-gpx` / `fit-to-gpx` commands.  The distance / altitude-fill /
  extension helpers they share live in `trackview.convert`.
- **`tests/`** the `pytest` suite — one module per feature
  (`test_geometry`, `test_filters`, `test_stats`, `test_trend`, …) plus a
  `conftest.py`.  The `network` / `slow` markers (in `pyproject.toml`) let the
  fast, offline subset run in CI.
- **`tools/`** three dependency-light helpers — two diagnostics for *inspecting*
  a Garmin `.fit` ride (the file/session/record layout and a stats summary) and
  `gpx_trim.py`, a pure-stdlib editor that trims `<trkpt>` off a ride's start /
  end.  *Not* the converter, that is `fit_to_gpx.py`.  See **Helper tools** below.
- **`gpx/`** (in the data dir) the input the tool renders: one `*.gpx` per ride,
  organised one subfolder per year (`2019`…`2026`); discovery recurses into them by
  default.
- **`gc/`** (in the data dir) the GoldenCheetah ingest input for
  `goldencheetah_to_gpx.py`: one `*.json` ride export per day
  (`{"RIDE": {…SAMPLES…}}`, re-saved by GoldenCheetah from a Wahoo ELEMNT BOLT
  `.fit`), one subfolder per year.
- **`fit/`** (in the data dir) the Garmin ingest input for `fit_to_gpx.py`: one
  `*.fit` binary ride per day, named `YYYY-MM-DD-…-ELEMNT BOLT …`.
- **`output/`** (in the data dir) the rendered images — `tracks_overview.<png|pdf>`
  and the `--trend` / `--calendar` / `--gallery` / `--html` figures.
- **`stats/`** (in the data dir) the text/CSV reports — the
  `trackview-<first>_<last>` ride-log (and `--csv`), plus the `--climbs`,
  `--summary` and other report variants.
- **`tiles/`** (in the data dir) the basemap-tile cache: downloaded tiles stored `z/x/y` per
  provider so a re-render or an offline run reuses them instead of refetching
  (`--no-cache` bypasses it).
- **`lib/`** (in the data dir) the cached Leaflet CSS + JS that `--html` inlines so
  the interactive map is a genuinely offline single file (`--html-cdn` skips the
  cache for a smaller, internet-dependent file).

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
- **Tile cache** basemap tiles are cached to disk under `tiles/` (git-ignored), keyed by z/x/y per provider, so a re-render — or an offline run — reuses the tiles already downloaded instead of refetching every one, which also eases the rate-limit pressure the `_load_basemap` fallback was there to absorb.  `--no-cache` fetches fresh each run instead (contextily's ephemeral per-session cache, the old behaviour); a map-only flag, ignored with `--no-map`.
- **Telemetry** `--ext` adds the calories-burned **total** (kcal) to the main title line and an average power / heart rate / speed / cadence / temperature line just below it, read from the `<extensions>` that `goldencheetah_to_gpx --ext` / `fit_to_gpx --ext` embed.  The calories are estimated as average power times the ride's duration, divided by a ~25% efficiency (the rides carry no calorie field).  Tracks without telemetry (e.g. komoot) simply omit both.
- The ride **duration** (`Hh MMm`, e.g. `3h 42m`) is always on the title, between
  the distance and the elevation gain — the total across the tracks when combined.
- Every run also writes a **ride-log table** to `stats/trackview-<first>_<last>.txt` (`<first>`/`<last>` are the earliest and latest ride dates, `YYYY-MM-DD`): one row per ride with the same stats as the two title lines (distance, duration, gain — plus the calories-burned total and avg power / speed / cadence / hr / temperature when `--ext`, and a **max grade** column), plus its **device type** (from the GPX `Device:` line) as the last column, closing with a totals/averages **per device type** (device name in the Device column).  A `-` marks a metric a ride doesn't carry; a ride with no `Device:` line (e.g. a plain komoot track) reads as `unknown`.  (The full set of statistics and the complete `stats/` layout — the `.txt`/`.csv` ride-log, `--climbs` and `--summary` — are gathered in **Statistics** below.)
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

- `--no-map` skips the basemap fetch and image entirely (no output image, no network) and just writes the ride-log table above — a stats-only run.  The map-only flags (`--out`/`--format`/`--style`/`--detail`/`--split`/`--gallery`/`--no-elev`/`--color-by`/`--grade-cap`/`--profile`/`--heat`/`--labels`/`--no-scale`/`--no-cache`) are ignored when it is set.
- **Sparse output** `--sparse` quiets stdout: it skips the per-track stats listing (the
  one line per read ride) and prints only the summary lines — where it reads, the track
  count / point totals, the files written, and any `--since`/`--until` skips.  The
  ride-log and CSV files are unaffected.
- **Input dir / recursion** the `--gpx-dir` input is searched **recursively by default**
  (subfolders are descended, so rides organised under a `year/` or `device/` layout are
  found too — the real `gpx/` holds one subfolder per year, `2019`…`2026`).  `--flat`
  restricts the search to the input dir itself (the old single-level glob).  Discovery stays
  date-ascending because the Wahoo filename embeds the ride date, so the ride-log and the
   `trackview-<first>_<last>` filename read as usual; it is *not* a map-only flag, so a
   `--no-map` run still recurses.
- **Date filter** `--since`/`--until` (each a `YYYY-MM-DD`) keep only the tracks whose
  ride date falls in the range — read from the Wahoo-style filename stem (e.g.
  `2026_09_07_08_12_47` → `2026-09-07`), the same way `goldencheetah_to_gpx` / `fit_to_gpx`
  name their output after the ride start (so a Garmin `.fit` ride sorts / filters
  just like a Wahoo one).  A track whose filename carries no date is skipped (never guessed) whenever a
  bound is active.
- **Today glance** `--today` is the shorthand for `--flat --since <today>`: a one-flag
  "what did I ride today?" look that switches to flat discovery (today's rides sit at the top
  level of the folder) and bounds `--since` to the current calendar day, so a daily glance needs
  no typed date.  It folds into those two flags, so it composes with `--list` (a `--list --today`
  is a no-fetch dry-run of today's rides) and the stats path, and is *not* a map-only flag (a
  `--no-map` run still honours it).  The date is `date.today()` at run time, never a baked-in constant.
- **Device / sport filter** `--device NAME` and `--sport NAME` keep only the rides whose
  GPX `<desc>` "Device:" / "Sport:" line (stamped by `goldencheetah_to_gpx` / `fit_to_gpx`, e.g. `Wahoo ELEMNT BOLT`,
   `Bike`) equals `NAME` (case-insensitive), narrowing a mixed-device or mixed-sport folder and
  complementing the `--since`/`--until` date filter.  A ride carrying no such line is skipped
   (never guessed), as an undated ride is under a date bound, and when nothing matches the distinct
  values the log *does* carry are printed so a typo is easy to fix.  They gate the ride-log/CSV and
   the stats reports as well as the map, so they are *not* map-only (a `--no-map` run still honours
  them).
- **Top-N filter** `--top N --by {km,gain,recent}` (default `recent`) keeps only the `N`
  most-significant rides — a "best-of" map, or a way to keep a huge combined map legible — ranked
  by distance (`km`), elevation gain (`gain`) or recency (`recent`, the default).  It runs *after*
  the `--since`/`--until`/`--device`/`--sport` filters (so it selects the top `N` of whatever rides
  remain), and narrows the `tracks` list the same way, so the map, the ride-log/CSV and the stats
  reports all see only the selected rides; the survivors are re-sorted back into date order (so the
  ride-log and the `trackview-<first>_<last>` filename read as usual), ties keep that order, and
  `N` ≥ the ride count (or `N` ≤ 0) is a no-op.  It is *not* a map-only flag (a `--no-map` run still
  honours it).
- **Dry-run listing** `--list` prints the rides that *would* be processed -- one
  `Date  Ride  Dist (km)  Gain (m)` line per ride that survives *every* filter
  (`--since`/`--until`, `--device`/`--sport`, `--top N --by`), closed by a `TOTAL`
  row -- then stops: it fetches no basemap and writes no image or stats/CSV/report,
  so a filter selection can be previewed cheaply.  It runs *after* the filters on the
  fully-filtered rides (so it shows exactly what a run would process), prints its own
  listing (so it overrides `--sparse`), and is *not* a map-only flag (a `--no-map` run
  stops at `--list` too); a ride with no date in its filename shows `undated`.
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
- **Interactive HTML map** `--html` writes a self-contained, single-file interactive Leaflet map to
   `output/trackview-<first>_<last>_map.html`: the rides as *inline GeoJSON* LineStrings (each a
   white-cased coloured route with green/red start/stop markers and a click-for-stats popup) on a
   tile layer at the URL matching `--style`, plus a clickable ride list, fit to the data on load —
   so it zooms/pans and is shareable with no server.  It complements the static PNG/PDF, and is a
   *different* deliverable from the parent repo's `gpx_viewer.py` (an interactive Streamlit + Folium
   app).  The Leaflet CSS + JS are *inlined* by default (a genuinely offline single file; the ~150 KB
   download is cached under the data dir's `lib/`, like the tile cache), so the file opens straight
   from disk; `--html-cdn` references the library from a CDN instead (a smaller file that needs
   internet to *view*).  A standalone output (no basemap fetch, no telemetry), so it writes even
   under `--no-map`; because it embeds every decimated point, pair it with `--top`/`--since` to keep
   a busy log to a handful of rides.
- **Gallery / contact sheet** `--gallery [N]` (bare `--gallery` = 9) tiles the N *most recent* rides of the already-filtered set into a single mosaic to `output/trackview-<first>_<last>_gallery.<format>` — a "recent rides" overview without opening N files, the *mosaic* alternative to `--split` (one image instead of N).  Each cell is that ride's own basemap + route (the flat per-track look of a `--split` cell) with a green start / red stop and a name / distance / gain caption, laid out in a near-square grid (3x3 for 9, 2x3 for 5, a 1xN row for a small N); the top-left cell is the latest ride.  It fetches a basemap per cell, so it honours `--style` / `--detail` / the tile cache and is skipped under `--no-map` (a line on stdout says so, and the ride-log/CSV are still written); a ride with no route (e.g. a suppressed trainer ride) is dropped from the sheet, and an empty set writes nothing.  `--out` names the single file; otherwise the dated auto name is used.

## Sample output

`samples/` holds a few rendered profile strips so you can see what a ride card
looks like without running trackview — the same `--profile` mini-panels
(elevation / grade / power / speed, each on its own strip, sharing the distance
axis), for two sample rides.  They are static JPEGs committed to the repo
(personal-data-free — no EXIF, no GPS), not a runtime output.

![sample ride profile strip](samples/Sample_1_grade.jpg)

> **A single ride, here — but it scales up.** The samples show one ride each.  In
> practice `trackview` lays **every** `.gpx` you hand it onto one image, so a week, a
> month or a whole season of rides can share the same map (or, with `--pdf`, one page
> each).

## Statistics

Beyond the rendered maps, every run reads the numbers off each ride and writes
them to `stats/` (a few reports go to `output/` as standalone figures).  This
section is the one place the *statistics* and the `stats/` layout live together;
the per-flag detail is in **Output** above.

### What trackview reads from a `.gpx`

`load_tracks` (in `trackview/load.py`) is the single reader.  For every `*.gpx`
it parses the file with `gpxpy`, merges the track segments into **one polyline**,
records the **first→last timestamp span** (the ride's `duration`), **decimates**
the points to one every `DECIMATE_M` metres (default 5 m — ~68 k points → a few
thousand), and, when telemetry is wanted, accumulates the **per-point telemetry**
`goldencheetah_to_gpx --ext` / `fit_to_gpx --ext` embed.  A file that is missing,
truncated or foreign is *skipped with a note*, not fatal — one bad file in a
mixed-vendor `gpx/` never aborts the run.

**Geometry (always, pure from lat/lon/elev)** —

- **Distance (km)** — equirectangular sum of segment lengths
  (`111320·cos(mid-lat)` E–W, `110540` N–S).
- **Gain (m)** — the sum of *positive* rises; a descent ends the climb only once
  it exceeds `--gain-noise` (`0` = the raw ascent).
- **Grade (%)** — per-segment rise ÷ horizontal run ×100.
- **Cumulative km** — running distance per point.
- **Duration** — `t_last − t_first` in seconds (always on the map title, `Hh MMm`).
- **Max grade** — the ride's steepest per-segment grade.

**Telemetry (only when a ride carries it, from `--ext`)** — `power`,
`speed_kmh`, `cadence`, `heartrate`, `temperature`, read from the
un-namespaced `<extensions>` children `gpxpy` flattens onto each trackpoint.
Each is kept as a point-weighted `[sum, count]` pair, so an average is the true
sum-over-count — **avg power (W) / avg speed (km/h) / avg cadence (rpm) / avg HR
(bpm) / avg temperature (°C)**.  **Calories (kcal)** is *estimated*, not measured:
`avg power (W) × duration (s) ÷ 4184 J/kcal ÷ 0.25 efficiency`, so it needs both a
power average and a duration.  A plain komoot track (no extensions) carries none —
those columns then read `-`.

**Ride metadata (off the `<desc>` line `goldencheetah_to_gpx` / `fit_to_gpx`
stamp, and the filename)** — **Device** (e.g. `Wahoo ELEMNT BOLT`) and **Sport**
(e.g. `Bike`), read case-insensitively; a ride missing a line falls into its own
`unknown` group.  The **ride date** is *not* from the GPX internals but from a
Wahoo-style filename stem `YYYY_MM_DD_HH_MM_SS` (a foreign name is *undated*) —
this is what the `--since`/`--until` filter and the output filenames key off.

**Climbs (geometry-only)** — sustained runs of *smoothed* grade (a 9-segment
moving average) staying `≥ 4.0 %` over `≥ 250 m` of horizontal run; each climb
carries gain, average grade, steepest grade and a **score = gain × average
grade** that ranks a long moderate climb against a short steep one.

### How the `stats/` reports are organised and named

Every report in a run shares **one dated label**, built once from the earliest
and latest ride (the glob is date-ascending):

```
trackview-<first>_<last>.<ext>      e.g. trackview-2026-09-01_2026-09-30.txt
```

`<first>`/`<last>` are the **calendar dates** of the first and last ride
(`YYYY-MM-DD` for a Wahoo stem, the ride title unchanged otherwise), made
filesystem-safe — so the *span of the run is the filename*, and every report from
one run lines up.  The `.txt` tables close with a **`Summary` totals row per
device type** (rides with no `Device:` line group under `unknown`); the `.csv`
omits those totals.  The four text reports that live in `stats/`:

| report | flag | file in `stats/` | shape |
| ------ | ---- | ---------------- | ----- |
| **Ride-log table** | always | `trackview-<first>_<last>.txt` | one row per ride + one **`Summary`** totals row per device; columns `Ride, Dist (km), Duration, Gain (m)` + `Device`, and under `--ext` also `Calories, Avg power, Avg speed, Avg cadence, Avg HR, Max grade, Avg temperature` |
| **CSV ride-log** | `--csv` | `trackview-<first>_<last>.csv` | the same columns, but **no** title/rules/`Summary` (totals live only in the `.txt`); decimal-normalised, `--csv-delimiter` (default `;`) |
| **Climb ranking** | `--climbs [N]` | `trackview-<first>_<last>_climbs.txt` | top `N` (default 10) by score; `#, Ride, From (km), To (km), Len (km), Gain (m), Avg %, Max %, Score`; the header self-describes the thresholds; a "no sustained climbs found." note when empty |
| **Year-in-review** | `--summary` | `trackview-<first>_<last>_summary.txt` | grouped **year → month**, each block `Month, Rides, Dist (km), Gain (m), Hours` (+ `Avg power (W)` under `--ext`) closed by a `TOTAL`, an `ALL years` grand total when > 1 year, plus an undated-rides note |

Two cross-cutting points:

- The **`.txt` totals come per device group** — the ride-log and summary print one
  `Summary`/`TOTAL` row *per device type*, so a mixed-device folder gets its own
  subtotal per device, not one lumped total.
- The `--summary` and `--climbs` reports are **pure geometry**, so they write
  even under `--no-map` (no basemap fetch).  The `--trend`, `--calendar` and
  `--html` outputs are *also* standalone (they write under `--no-map` too), but
  they are **figures**, so they land in `output/` (`trackview-<first>_<last>_trend.<fmt>`,
  `_calendar.<fmt>`, `_map.html`), not `stats/`.

## Base-map providers (`--style`)

| key         | source                                    |
| ----------- | ---------------------------------------- |
| `topo`      | OpenTopoMap — contours + relief           |
| `sat`       | Esri World Imagery (satellite)            |
| `terrain`   | Esri World Terrain Base                   |
| `osm`       | OpenStreetMap, German tiles (default)     |

Providers are tried in order; a failed or *blank* tile fetch (near-zero image
variance, e.g. rate-limiting) automatically falls back to the next one.

## Helper tools (`tools/`)

Three ad-hoc, dependency-light helpers under `tools/` — two *diagnostics* for
*inspecting* a Garmin `.fit` ride, and one small *editor* for trimming a GPX.
None of them is the converter that feeds the tool — that is `fit_to_gpx.py`
(Garmin `.fit` → GPX) / `goldencheetah_to_gpx.py` (GoldenCheetah JSON → GPX),
which turn the data dir's `fit/` / `gc/` into `gpx/`.

```bash
.venv/bin/python tools/garmin_fit_reader.py              # most recent data dir/fit/*.fit
.venv/bin/python tools/garmin_fit_reader.py <a.fit> ..   # explicit ride(s)
.venv/bin/python tools/garmin_fit_reader_standalone.py   # no fitparse needed
.venv/bin/python tools/gpx_trim.py ride.gpx --start 10 --end 500   # trim trackpoints
```

`garmin_fit_reader.py` (needs `fitparse`, already in `requirements.txt`) prints
the file/session/lap/record layout and a short stats summary and dumps the *full*
record stream to a sibling `<name>_records.json`.  `garmin_fit_reader_standalone.py`
is the dependency-free fallback: with no `fitparse` it reads only the FIT header,
a hex dump and the embedded strings, then points at the tools that can decode the
rest.  `gpx_trim.py` is a pure-stdlib editor that removes `N` `<trkpt>` elements
from the *start* and/or *end* of a `*.gpx` (preserving the file's XML namespaces);
by default it writes a sibling `<name>_trimmed.gpx` (or use `-o`).  The `.fit`
inputs and the dumped `_records.json` live in the data dir's `fit/` (personal
data and regenerable output); `gpx_trim.py` operates on a ride's GPX in place
(its `_trimmed` sibling is regenerable, like `output/`).

## Notes

- Base maps are fetched over the network at render time (a proper `User-Agent`
  is sent). Attribution is printed on the image and in the console.
- The projection is Web Mercator (EPSG:3857); the scaling constant is `π·R`
  (`20037508.34`), **not** the equatorial circumference `2·π·R`.



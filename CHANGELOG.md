# Changelog

All notable changes to **trackview** are recorded here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
(the version is the single `trackview.config.__version__` constant; `pyproject.toml`
stamps it dynamically, so the wheel/sdist version and `trackview --version` can never
drift).  Dates are the ones carried by the entries; "Added / Changed / Fixed /
Removed / Improved" follow the Keep a Changelog categories.  User-facing flags and
outputs are the headline; internal refactors and packaging work are noted too.

---

## [Unreleased]

### Added

- **README "Statistics" section.**  A new consolidated section (between "Sample
  output" and "Base-map providers") gathers the *statistics* trackview reads from
  each `.gpx` — the always-on geometry (distance, gain, grade, cumulative km,
  duration, max grade), the `--ext` telemetry (avg power / speed / cadence / HR /
  temperature, the estimated calories-burned, and the Device / Sport / ride-date
  metadata), and the geometry-only climb detection — together with *how the `stats/`
  reports are organised and named* (the single `trackview-<first>_<last>` dated
  label, and the four text reports: the ride-log `.txt`, the `--csv`, the
  `--climbs` ranking and the `--summary` year-in-review).  The per-flag "Output"
  prose cross-links to it; no flag or output behaviour changes.

- **README "Sample output" note.**  A one-line blockquote under the sample profile
  strip notes that the sample images each show a *single* ride, whereas `trackview`
  plots every `.gpx` you hand it onto one image — a week, a month or a whole season
  together — or one page each under `--pdf`.  Doc-only; no flag or output behaviour
  changes.

- **README "Data location" multi-athlete note.**  The `TRACKVIEW_HOME` "Override"
  bullet now names its third use — the *multi-athlete* knob: give each rider a
  distinct home (`TRACKVIEW_HOME=~/.trackview-alice` vs. `~/.trackview-bob`) so two
  or more athletes keep their own `gpx/`, `output/`, `stats/`, … from a single
  install.  Doc-only; the capability already existed via `TRACKVIEW_HOME`, this just
  surfaces it.  No flag or output behaviour changes.

- **README "Usage" converter pipeline.**  The "Usage" section now opens by stating
  that `trackview` plots the `gpx/` ride log and does *not* read a device's native
  files, so the user must *supply* the `gpx/` — via the two converters, which read the
  data dir's `gc/` / `fit/` (GoldenCheetah JSON / Garmin `.fit`) and write the *same*
  `gpx/` trackview then plots (`goldencheetah-to-gpx` / `fit-to-gpx`, with `--ext`,
  `--since` / `--until`, or an explicit file), cross-linking the `.fit` *inspection*
  helpers to **Helper tools**.  Doc-only; no flag or output behaviour changes.

---

## [1.0.3] — 2026-10-23

Cuts `1.0.2` → `1.0.3` on two additive, non-breaking additions: a third `tools/`
helper (`gpx_trim.py`, a dependency-free GPX trimmer) and a `samples/` folder of
public, personal-data-free render illustrations.  No flag or output changes, so
it is a non-breaking patch.

### Added

- **`tools/gpx_trim.py` — a dependency-free GPX trimmer.**  A pure-stdlib helper
  (no `trackview` import, no new dependency) that removes `N` `<trkpt>` elements
  from the *start* and/or *end* of a `*.gpx`, preserving the file's XML
  namespaces.  It writes a sibling `<name>_trimmed.gpx` by default (`-o` to name
  it), reuses the trimmed file for a round-trip, and is the third entry under
  `tools/` alongside the two FIT diagnostics.
- **`samples/` — public sample output.**  A small set of rendered `--profile`
  strips (elevation / grade / power / speed for two sample rides), committed as
  static JPEGs so a reader sees what a ride card looks like without running
  trackview.  They are personal-data-free (no EXIF, no GPS) and are *illustrative*
  — not a runtime output — so the README's "Sample output" section can link one
  directly.

### Changed

- **README / Helper tools / Directory Structure now cover `gpx_trim.py` and
  `samples/`.**  The "Helper tools (`tools/`)" section lists all three helpers and
  shows a `gpx_trim.py` usage line; the directory tree gains a `samples/` entry;
  a new "## Sample output" section links `samples/Sample_1_grade.jpg`.
- **`tools/gpx_trim.py` now carries its own docstring.**  The stale
  `gpx_trim_en.py` name in the usage examples was corrected to `gpx_trim.py`
  (the module's real filename).

---

## [1.0.2] — 2026-10-22

Cuts `1.0.1` → `1.0.2` on the per-user data-dir move below: the run-time data
no longer hangs off the script's own location (a `pip install` would otherwise
find a `fit/`/`gpx/` beside `site-packages`, a read-only place to write a ride
log), and the `tools/` FIT diagnostics follow the same data dir.  The move is
data-preserving (a same-volume rename), and the `--fit-dir`/`--gc-dir`
`--in-dir`/`--out-dir` flags stay unchanged, so it is a non-breaking patch.

### Changed

- **Ride data now lives under a per-user data dir, not the script's own
  location.**  All input and output now hangs off a single **data dir**
  (`trackview.config.DATA_DIR`): `~/.trackview` by default, or `$TRACKVIEW_HOME`
  when set.  The four run-time dirs — `gpx/` (the ride log), `output/` (rendered
  maps), `stats/` (the reports) and `tiles/` (the basemap cache) — plus the
  converters' `fit/` / `gc/` inputs and the `--html` `lib/` Leaflet cache, now sit
  *under* it.
  - **Why:** the tool plots *one athlete's* rides, so their data belongs in the
    user's home.  The dirs were previously anchored to the script's own
    location (`__file__`), which resolves to `site-packages/` once trackview is
    `pip install`ed — a read-only, wrong place to write a ride log.
  - `trackview.config` now imports `os` (still stdlib-only, so the build-time
    dynamic-version import stays dependency-free) to read `$TRACKVIEW_HOME`.
  - Both converters (`fit_to_gpx`, `goldencheetah_to_gpx`) keep `OUT_DIR ==
    GPX_DIR`, so the convert → render pipeline stays wired with no flag.
  - A converter's **default run now creates its input dir** (`fit/`, `gc/`) with
    its parents, so a first run leaves a clean, ready-to-fill `~/.trackview` to
    drop rides into, instead of a "nothing found in `~/.trackview/fit`" over a
    missing private dir.  Explicit files / `--in-dir` are unaffected.
  - **One-time migration** for an existing source checkout: move the old top-level
    `gpx/` / `gc/` / `fit/` / `output/` / `stats/` / `tiles/` / `lib/` into the
    data dir (a same-volume rename — no data is copied); or run from that checkout
    with `TRACKVIEW_HOME=$PWD` until they are moved.  A converter or trackview run
    then reads the moved dirs and the converter writes *into* them, so no
    top-level folder ever reappears.
- **The two `tools/` FIT diagnostics now read the data dir's `fit/`** —
  `tools/garmin_fit_reader.py` and `tools/garmin_fit_reader_standalone.py`, run
  with no argument, inspect the most recent `*.fit` in `DATA_DIR / "fit"`
  (`$TRACKVIEW_HOME` else `~/.trackview`, imported from `trackview.config`)
  instead of a `fit/` next to the script — so the diagnostic and `fit_to_gpx.py`
  can never disagree on where the rides live, and a `pip install`ed run no longer
  points at a `fit/` beside `site-packages`.  A `sys.path` bootstrap makes the
  import resolve whether the package is pip-installed or a source checkout.

---

## [1.0.1] — 2026-10-21

Cuts `1.0.0` → `1.0.1` on the JSON-converter rename below (a user-facing change to
a public command and module name, so the patch level is warranted) together with the
two doc/ignoring items that landed after the `1.0.0` tag.

*Changed*
- **Renamed the JSON → GPX converter `wahoo_to_gpx.py` → `goldencheetah_to_gpx.py`**
  (a breaking rename) — the `./gc/*.json` rides are re-saved by **GoldenCheetah**
  from a Wahoo ELEMNT BOLT `.fit` export, so the *source* of the JSON is
  GoldenCheetah even though the ride data originated on a Wahoo device.  The module,
  the `goldencheetah-to-gpx` console entry point, the test module, and every doc
  reference follow; the device stamped into the GPX `<desc>` stays `Wahoo ELEMNT
  BOLT`, as do the "Wahoo-style" filename and "Wahoo voice" references.
- **README gained a Directory Structure section** — maps the repo: the shipped
  source (`trackview/`, the `trackview.py` launcher, the two converter scripts,
  `tests/`, `tools/`, `pyproject.toml`, `requirements.txt`) vs. the git-ignored
  local/personal data (`gpx/`, `gc/`, `fit/`) and generated output/caches
  (`output/`, `stats/`, `tiles/`, `lib/`).
- **Git-ignored `CLAUDE.md` / `PLAN.md` / `TODO.lst`** — the two private working
  docs (the AI-assistant notes and the completed refactoring plan) are now
  git-ignored; `TODO.lst` (the project's changelog source) is ignored too, the
  record it stands in for living on in `CHANGELOG.md`.

---

## [1.0.0] — 2026-10-19

The first release.  Cuts the version `0.1.0` → `1.0.0` after a whole-repo
re-analysis found only polish (no behaviour gaps).

*Added*
- **`--version`** — a side-effect-free `trackview --version` (and the console
  entry point) that prints `trackview 1.0.0` and exits, reading the same
  `trackview.config.__version__` the build stamps, so the two can never disagree.
- **A linter + a CI gate** — `ruff` now lints the sources and a
  `.github/workflows/ci.yml` runs two fast, offline jobs: a *lint* job
  (`ruff check` over `trackview/`, the converter scripts, the root launcher,
  `tests/` and `tools/`, gating on `F` + `E9` only) and a *test* job
  (`pytest -m "not network and not slow"` across Python 3.10–3.13).  `ruff` is a
  `lint` extra, never a runtime dependency.
- **De-duplicated the two ride converters** — the shared surface
  (`_parse_argdate`, `_distance_and_gain`, `_fill_altitude`, `_add_extensions`,
  and the FIT-only reading cluster) now lives in one `trackview/convert.py`, with
  `fit_to_gpx.py` / `goldencheetah_to_gpx.py` as thin shims; `pyproject.toml` gained the
  `fit-to-gpx` / `goldencheetah-to-gpx` console entry points + `py-modules` so they ship.
- **Per-file error isolation in the GPX reader** — a corrupt or missing `*.gpx` in a
  mixed-vendor `gpx/` is skipped with a `skip (could not open)` /
  `skip (not a valid .gpx)` note and the run continues (mirroring the fit/wahoo
  converters), rather than being fatal.

*Changed*
- **Reconciled the duplicated `PI_R`** — the Web-Mercator scaling constant now lives
  only in `trackview/geometry.py` (its one consumer, `latlon_to_merc`); the orphaned
  `config.py` copy and its dead import are gone, and the test moved with the value.
- **Lint `tools/` in CI** — the lint job now covers the standalone `.fit` helpers
  too, so a stray unused import / empty f-string can't creep in there.
- **Cleaned `tools/garmin_fit_reader_standalone.py`** — dropped an unused `struct`
  import and an f-string with no placeholders (ruff-caught); the file still decodes
  a `.fit`.
- **Refreshed stale module docstrings** — six narrations that still described the
  Phase-1 module split as *in progress* were reworded to the final architecture
  (the monolith is gone; `_metric_norm` → `rendering.py`, the render cluster →
  `mapfig.py`, `GPX_DIR`/`TILE_CACHE_DIR` → `config.py`, `write_gallery` → `io.py`).
- **Documentation pass** — the last two undocumented module functions
  (`cli.main`, `mapfig.render`) gained docstrings, and a new top-level
  `API.md` catalogs the 13-module map, its constants and entry points.
- **Versioning folded into config** — `__version__ = "1.0.0"` in
  `trackview/config.py` is the single source of truth; `pyproject.toml` reads it
  dynamically (`[project].dynamic = ["version"]`) instead of holding a second copy.
- **Hygiene** — `.gitignore` gained `.coverage` / `htmlcov/` (a pytest-cov artifact).
- **Decision recorded** — Phase 2 of the refactoring plan (a `Track`/`Point`/
  `LineString`/`Visualization` class hierarchy) is *not* implemented: the functional
  design is the chosen final form, and a class migration would churn every signature
  for no new capability (YAGNI).

---

## [0.1.0] — 2026-10-18

Packaging + documentation baseline (the version at which the build system was
added).  The feature history below was delivered over 2026-09-17 → 2026-09-30;
this is the first *tagged* release, cut when the build system landed.

*Added*
- **A GoldenCheetah JSON → GPX converter (`goldencheetah_to_gpx.py`)** — turns the
  GoldenCheetah `gc/` `*.json` ride exports (the `{"RIDE": {...}}` shape, UTF-8 *with a BOM*, so
  read as `utf-8-sig`) into GPX 1.1 rides in `gpx/`: no-fix rows (`LAT/LON == 0`) at
  the start and end are dropped, the `ALT == 0` "no altitude" sentinel is
  forward/back-filled, absolute time is `STARTTIME` + `SECS` (UTC "Z"), and
  `LAT`/`LON`/`KPH` pass through untouched.  The output is named after the JSON stem
  (`YYYY_MM_DD_HH_MM_SS.gpx`) so `trackview` sorts / filters it like any ride;
  `--ext` embeds the six `power`/`speed_kmh`/`cadence`/`heartrate`/`grade`/
  `temperature` `<trkpt><extensions>` tags and `--since`/`--until` narrow by the
  stem date.  This converter is the reference the later Garmin FIT converter mirrors.
- **Build system (PEP 518/621)** — `pyproject.toml` (no `setup.py`) holds the
  metadata (`trackview`, `requires-python = ">=3.10"`, `readme = "README.md"`), the
  core runtime deps (`contextily` / `gpxpy` / `matplotlib` / `numpy`, mirrored from
  `requirements.txt`), two optional extras (`fit = fitparse`, used only by the
  top-level `fit_to_gpx.py`; `test = pytest`), and the console entry point
  `trackview = "trackview.cli:main"` (the `fit-to-gpx` / `goldencheetah-to-gpx` entry
  points joined it with the converter de-duplication below).  A
  `[tool.setuptools] packages = ["trackview"]`
  keeps flat-layout auto-discovery from sweeping the root `trackview.py` launcher or
  the data dirs into the build; `python -m build` produces a clean sdist +
  `trackview-0.1.0-py3-none-any.whl`.
- **A `tests/` suite** — a `conftest.py` (a `sys.path` shim, the `build_ride` /
  `write_ride` / `gpx_points` helpers, and synthetic-GPX + filter fixtures) plus
  one test module per feature; the heavy basemap-fetch / matplotlib-render paths sit
  behind `network` / `slow` markers registered in `pyproject.toml`, so the fast,
  offline subset runs in CI.
- **A Garmin `.fit` → GPX converter (`fit_to_gpx.py`)** — reads each `fit/*.fit`
  with `fitparse` into a GPX 1.1 track in `gpx/`, named after the ride *start time*
  (Wahoo-style `YYYY_MM_DD_HH_MM_SS`, not the long Connect device+serial name) so
  `trackview._ride_date` sorts / filters it like a Wahoo ride; the same flags
  (`--ext`, `--since`/`--until`, a positional file, `--out-dir`), the same
  `--ext` telemetry tags, and the same equirectangular `_distance_and_gain`.
  Handles the FIT quirks (semicircle positions, the `-500 m` altitude sentinel,
  no-fix records, a `session`/`file_id` start-time fallback) and rewords
  device/sport to the Wahoo voice (`wahoo_fitness` → `Wahoo ELEMNT BOLT`,
  `cycling` → `Bike`).
- **A GoldenCheetah JSON → GPX converter test** — `tests/test_goldencheetah_to_gpx.py` exercises
  `goldencheetah_to_gpx.py` the same way the FIT converter is: a hand-built BOM-prefixed
  ride JSON driven through `ride_to_gpx` / `main` (no-fix lead-in + trailing rows
  dropped, the `0 m` altitude sentinel back-filled, `LAT`/`LON`/`KPH` passed
  through, `--ext` embedding the six telemetry tags, `main` naming output after the
  JSON stem and composing `--since`/`--until`).
- **The ad-hoc FIT diagnostics (`tools/`)** — `garmin_fit_reader.py` (a
  `fitparse`-based diagnostic that prints the file/session/lap/record layout + a
  stats summary and dumps the *full* record stream to a sibling
  `<name>_records.json`) and `garmin_fit_reader_standalone.py` (a dependency-free
  fallback that reads only the FIT header, a hex dump and the embedded strings);
  both are now repo-aware (no-arg → the most recent `fit/*.fit`, explicit paths
  override).  Diagnostics, not the converter, so they stay out of the `tests/`
  suite; the `.fit` inputs and the dumped `*_records.json` are git-ignored.
- **A self-contained HTML / Leaflet map (`--html`)** — a single-file interactive
  Leaflet map to `output/trackview-<range>_map.html`: the rides as inline-GeoJSON
  LineStrings on a tile layer matching `--style`, with green/red start/stop markers,
  click-for-stats popups and a clickable ride list.  The Leaflet CSS + JS are
  *inlined* by default (a genuinely offline file, the ~150 KB library cached under
  the git-ignored `lib/`); `--html-cdn` references the library from a CDN instead
  (a smaller file that needs internet to *view*).  A standalone output (no basemap,
  no telemetry), so it writes even under `--no-map`; pair it with `--top`/`--since`
  to keep a busy log small.
- **A gallery / contact sheet (`--gallery [N]`)** — tiles the N *most recent* rides
  (bare `--gallery` = 9, a 3×3) into one mosaic at
  `output/trackview-<range>_gallery.<format>`: each cell is that ride's own basemap
  + route (white-cased coloured line, green/red markers, a name/distance/gain
  caption), newest in the top-left — the mosaic alternative to `--split`.
- **Recursive input discovery** — `main()` now `rglob`s `*.gpx` by default, so rides
  organised one subfolder per year (`gpx/2019`…`gpx/2026`) are all found (a flat
  glob found 0 of them); `--flat` restores the old single-level glob.  Discovery
  stays date-ascending (the Wahoo filename embeds the date) and composes with
  `--since`/`--until`/`--device`/`--sport`/`--top`.
- **A `--list` dry-run** — prints the rides that *would* be processed after every
  filter (one `Date  Ride  Dist (km)  Gain (m)` line each, closed by a `TOTAL` row)
  and stops: no basemap fetch, no image, no stats/CSV written.  Not a map-only flag
  (a `--no-map` run stops at `--list` too).
- **A `--today` glance** — a one-flag `--flat --since <today>` shortcut: "what did I
  ride today?" with no typed date (a *runtime* `date.today()`, never a baked-in
  constant).  Composes with `--list` (a no-fetch dry-run of today's rides) and the
  stats path; not a map-only flag.
- **Device / sport filters (`--device NAME` / `--sport NAME`)** — keep only the
  rides whose GPX `<desc>` "Device:" / "Sport:" line equals `NAME`
  (case-insensitive), complementing the `--since`/`--until` date filter for a
  mixed-device / mixed-sport folder; a non-match prints the distinct values the log
  *does* carry.  Not map-only (a `--no-map` run honours them).
- **A top-N filter (`--top N --by {km,gain,recent}`)** — keep only the N
  most-significant rides (a "best-of" map, or to keep a huge combined map legible),
  ranked by distance, elevation gain or recency; runs *after* the other filters and
  re-sorts the survivors back into date order.  Not map-only.
- **An on-disk tile cache** — contextily's per-session cache is re-pointed at a
  persistent, git-ignored `tiles/` (keyed `z/x/y` per provider), so a re-render or an
  offline run reuses the tiles already on disk instead of refetching every one;
  `--no-cache` restores the ephemeral per-session cache.
- **An activity calendar (`--calendar`)** — a GitHub-contribution-style activity grid
  to `output/trackview-<range>_calendar.<format>`: one 7 (weekday) × ISO-week block
  per calendar year, each day coloured by that day's total on a sequential ramp.
  `--calendar-by {distance,gain,rides}` (default `distance`) and `--year YYYY`
  restrict it; a standalone figure, so it writes even under `--no-map`.
- **A year-in-review summary (`--summary`)** — a per-year, per-month aggregate of the
  ride-log to `stats/trackview-<range>_summary.txt` (ride count, total distance,
  gain and hours per month, plus a point-weighted average power under `--ext`),
  closed by a `TOTAL` row and, across years, an `ALL years` grand total.
- **A training-trend chart (`--trend`)** — a per-ride line chart of distance,
  elevation gain, duration and (when a ride carries a power average) calories over
  ride date to `output/trackview-<range>_trend.<format>`: all the rides on one
  shared time axis; a standalone figure, so it writes even under `--no-map`.
- **A profile "ride card" (`--profile`)** — beneath each map (needs `--split`, or a
  single track): the elevation + grade silhouette plus one slim telemetry
  mini-panel per metric the ride carries (power, speed, HR, cadence), each on its
  own strip sharing the distance axis; a metric the ride lacks is skipped, and a
  telemetry-free ride falls back to elevation + grade.
- **A time-on-route density overlay (`--heat`)** — a 2-D "where you ride" density
  under the routes: a 300×300 histogram weighted by the time spent per segment
  (a slow climb / rest stop glows more than a fast pass), on a `YlOrRd` ramp; a
  map-only flag.
- **Ride labels on a combined map (`--labels`)** — tag each route's start marker
  with a halo'd `name      N km` line so a many-ride overview is identifiable
  without a legend key; a map-only flag.
- **`--color-by {speed,power}`** — shade the route by effort/pace (fast / high = hot,
  on a perceptually-uniform ramp); telemetry is auto-collected when these are set,
  and a ride without the data falls back to its flat colour.
- **A climb ranking (`--climbs [N]`)** — the N most-significant *sustained* climbs
  across all the rides to `stats/trackview-<range>_climbs.txt`: a maximal run of
  segments whose smoothed grade stays ≥ 4 % over ≥ 250 m, ranked by a climb score
  (gain × average grade).  Pure geometry, so it runs under `--no-map`.
- **A scale bar on every map** — a labelled `0 .. N km` bar in the lower-right
  corner (a "nice" 1/2/5×10ᵏ length of ~15 % of the width, Web-Mercator metres,
  white-cased); `--no-scale` omits it.
- **`--grade-cap N`** — pin the grade colour range to ±N % instead of the auto
  high-percentile cap.
- **Elevation-gain noise handling (`--gain-noise M`)** — trim GPS vertical jitter
  from the ascent: the gain is a *running climb*'s rises, a descent ending the climb
  only once it exceeds M metres, so centimetre-scale jitter stops inflating the
  figure while real climbs/descents are untouched.  `0` (the default) reproduces the
  classic "sum of every rising segment" exactly.
- **Per-track grade colouring on a combined map** — for a few rides (≤ 4) each gets
  its own colourbar at its own cap, so one steep ride can't desaturate the others;
  beyond that, or when `--grade-cap` is pinned, a single shared colourbar is used.
- **CSV ride-log (`--csv`)** — the same ride-log columns as a
  `stats/trackview-<range>.csv` (header + one row per ride, no title or per-device
  summary rows); `--csv-delimiter` sets the separator (default `;`).
- **Sparse output (`--sparse`)** — quiet stdout: skip the per-track stats listing,
  print only the summary lines (the ride-log / CSV files are unaffected).
- **`--out` honoured in `--split` mode** — `--out rides.png` prefixes the per-track
  files (`rides_<ride>.png`); without `--out` they are just named after the GPX stem.
- **Grade-line smoothing** — the profile panel runs a centred, NaN-skipping moving
  average over the grade before plotting, so the climb/descent silhouette reads
  cleanly instead of jitting on GPS noise.

*Changed*
- **Refactored the `trackview.py` monolith into a `trackview/` package** — the
  single-file script was split byte-for-byte, one module at a time, into a
  15-module package with no cross-module back-edges: `config` (the runtime
  constants + `__version__`), `geometry` (`latlon_to_merc`, `decimate`,
  `_distance_and_gain`, `_grade_and_cumkm`, `PI_R`), `helpers` (the Wahoo-stem
  date + device/sport readers, the filters and string helpers), `metrics`
  (per-point telemetry, the metric averages, the robust grade cap, the calorie
  estimate, the formatters), `rendering` (the colour / moving-average / figure
  leaves), `mapfig` (the render / ride-card / heat orchestration), `load`
  (`load_tracks`), `stats` (the ride-log / CSV), `climbs`, `trend`, `activitygrid`,
  `summary`, `convert` (the shared converter surface, added later) and `cli`
  (`main`).  `trackview/__init__.py` is an empty package init and the root
  `trackview.py` is now a thin CLI that re-enters `trackview.cli.main` (the old
  importlib re-export bridge that kept the package importable mid-split was deleted
  once every module had moved).  Every move kept the test suite green.
- **A clean `USER_AGENT`** — dropped the dead `user@example.com` placeholder; the
  tile fetches now carry a clean product string (with a marker for a real
  contact/URL).

---

## Legend / notes

The dated history above (2026-09-17 → 2026-10-21) was authored in the project's
`TODO.lst` — every entry `[done]`, dated, verified by the render / test suite.  This
changelog is that record, condensed into user-facing terms and collapsed by release;
`TODO.lst` remains the granular source of truth.  The "offline suite" counts the
TODO entries carried (final: 217 passed, 1 deselected).

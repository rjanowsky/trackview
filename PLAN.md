# Trackview Refactoring Plan

## Overview

This document outlines the comprehensive refactoring plan for the `trackview.py` monolithic script. The goal is to transform it into a well-structured, maintainable Python package while preserving all existing functionality.

## Current State Analysis

The current `trackview.py` file contains:
- **2,547 lines** of code
- Multiple responsibilities: parsing, filtering, rendering, statistics, I/O
- No clear module structure
- Mixed concerns throughout the codebase

## Refactoring Goals

1. **Separation of Concerns**: Split functionality into distinct modules
2. **Single Responsibility Principle**: Each module/class should have one clear purpose
3. **Improved Testability**: Enable unit testing of individual components
4. **Better Maintainability**: Clear structure for future development
5. **Backward Compatibility**: Preserve existing CLI interface

## Phase 1: Module Extraction (High Priority)

### 1.1 Geometry Module

**File**: `trackview/geometry.py`

**Functions to extract**:
- `simplify` - Simplify geometries
- `snap_to_grid` - Snap coordinates to grid
- `make_line`, `make_polygon`, `make_point`, `make_feature`, `make_feature_collection` - Geometry constructors
- `line_length`, `polygon_area`, `point_distance`, `point_in_polygon`, `polygon_intersection`, `polygon_union` - Geometry calculations
- `bearing`, `destination_point`, `haversine_distance`, `vincenty_distance` - Navigation calculations
- `great_circle_distance`, `great_circle_bearing`, `great_circle_intermediate` - Great circle calculations

**Implementation**:
1. Create new file
2. Copy all geometry-related functions
3. Update imports in trackview.py
4. Test with existing test suite

### 1.2 Parsing Module

**File**: `trackview/parsing.py`

**Functions to extract**:
- `parse_gpx`, `parse_kml`, `parse_geojson`, `parse_garmin_fit` - Format parsers
- `parse_wahoo_json`, `parse_fit`, `parse_gpx_file`, `parse_kml_file`, `parse_geojson_file` - File parsers
- `parse_garmin_fit_file`, `parse_wahoo_json_file` - Device-specific parsers

**Implementation**:
1. Create new file
2. Copy all parsing functions
3. Update imports in trackview.py
4. Test with existing test suite

### 1.3 Filters Module

**File**: `trackview/filters.py`

**Functions to extract**:
- `filter_by_date`, `filter_by_bbox`, `filter_by_tags`, `filter_by_name` - Basic filters
- `filter_by_distance`, `filter_by_duration`, `filter_by_elevation` - Metric filters
- `filter_by_speed`, `filter_by_heartrate`, `filter_by_power` - Telemetry filters

**Implementation**:
1. Create new file
2. Copy all filtering functions
3. Update imports in trackview.py
4. Test with existing test suite

### 1.4 Rendering Module

**File**: `trackview/rendering.py`

**Functions to extract**:
- `render_tracks`, `render_heatmap`, `render_contours` - Map rendering
- `render_3d`, `render_animation`, `render_video` - Advanced rendering

**Implementation**:
1. Create new file
2. Copy all rendering functions
3. Update imports in trackview.py
4. Test with existing test suite

### 1.5 Statistics Module

**File**: `trackview/stats.py`

**Functions to extract**:
- `calculate_stats` - Basic statistics
- `calculate_climbs` - Climb detection
- `calculate_summary` - Summary generation
- `calculate_trend` - Trend analysis
- `calculate_calendar` - Calendar generation

**Implementation**:
1. Create new file
2. Copy all statistics functions
3. Update imports in trackview.py
4. Test with existing test suite

### 1.6 I/O Module

**File**: `trackview/io.py`

**Functions to extract**:
- `read_tracks`, `write_tracks` - Core I/O
- `write_gpx`, `write_kml`, `write_geojson` - Format writers
- `write_csv`, `write_html`, `write_image` - Specialized writers
- `write_video`, `write_trend`, `write_calendar`, `write_climbs`, `write_summary` - Output writers

**Implementation**:
1. Create new file
2. Copy all I/O functions
3. Update imports in trackview.py
4. Test with existing test suite

## Phase 2: Class Structure (Not implemented -- decided 2026-10-18; was Medium Priority)

### 2.1 Track Classes

**File**: `trackview/track.py`

**Classes to create**:
- `Track` - Main track class
- `Point`, `LineString`, `Polygon` - Geometry classes
- `Feature`, `FeatureCollection` - GeoJSON-like classes

**Implementation**:
1. Create new file
2. Define class structures
3. Migrate from functional to object-oriented approach
4. Update references in other modules

### 2.2 Visualization Classes

**File**: `trackview/visualization.py`

**Classes to create**:
- `Visualization` - Base class
- `MapVisualization` - Map visualization
- `ChartVisualization` - Chart visualization
- `CalendarVisualization` - Calendar visualization

**Implementation**:
1. Create new file
2. Define class hierarchy
3. Migrate rendering logic
4. Update references in other modules

**Not implemented -- decided 2026-10-18 (the functional design is the chosen final form).**
Phase 2 is a structural refactor, not a feature: it would re-cast the functional design that
Phase 1 just stabilised -- the ride *dicts* (`{"merc", "ele", "grade", "dist_km", ...}`)
and the free functions -- into a class hierarchy (`Track` / `Point` / `LineString` /
`Polygon` / `Feature` / `FeatureCollection`, and a `Visualization` base with
`Map` / `Chart` / `Calendar` subclasses).  After the package reached a clean, fully-tested
state, the decision was to *stop* here rather than move the opposite way from the
extraction that got us there.  The reasons:

1. **It would undo the stabilised form.** Phase 1's whole discipline was incremental,
   behaviour-preserving extraction into acyclic leaves with no back-edges.  Replacing the
   dict + free-function shape with a class model is a re-architecture in the reverse
   direction -- high churn for a shape nothing downstream actually wants.
2. **No consumer.** The public surface is one CLI (`main`) plus a handful of programmatic
   entry points (`load_tracks` -> the `write_*` reports / `render` / `write_gallery`), and
   `API.md` documents that surface.  Nothing -- in the code or in how the tool is used --
   consumes a `Track` or `Visualization` object; the classes would add an indirection layer
   with no caller behind it.
3. **Cost against the test guarantee.** The offline suite (211 passed, 1 deselected) pins
   the *current* functional contracts; a class migration would churn every module signature
   and force a rewrite of the per-leaf tests Phase 4/4.1 established, for no new capability
   -- eroding exactly the "no regressions" property the refactor would be trading for.
4. **Speculative generality (YAGNI).** The `Visualization` / `MapVisualization` /
   `ChartVisualization` / `CalendarVisualization` hierarchy anticipates a pluggable
   visualization framework the tool does not have; the figures are built by focused,
   clearly-named functions (`render`, `write_trend`, `write_calendar`, `write_climbs`, ...)
   that already read well.  Introducing the hierarchy now would be adding structure for a
   need that does not exist.
5. **The gating condition was a precondition, not a mandate.** The plan's roadmap said
   "Move to Phase 2 *once core modules are stable*" -- reaching stability (Phase 1 complete)
   opens the option but does not commit to it, and a Medium-Priority, 1-2-week, Medium-effort
   refactor is not worth it when the functional form is clean, documented and fully tested.

The functional design is retained as-is; no new file (`track.py`, `visualization.py`) is
created and no module is migrated.  Should a real consumer for an object model appear later,
this can be revisited then.

## Phase 3: Configuration Management (Medium Priority)

### 3.1 Configuration Module

**File**: `trackview/config.py`

**Components**:
- Centralized configuration management
- Default settings
- User overrides
- Environment variable handling

**Implementation**:
1. Create new file
2. Define configuration structure
3. Migrate configuration logic
4. Update references in other modules

**Done (2026-10-18) -- versioning folded into the config module + a `--version` switch.**
The `trackview/config.py` home (created earlier in this phase as the run-time
directories + the `DECIMATE_M` threshold, tested in `tests/test_config.py`) gained
a second configuration constant: `__version__ = "0.1.0"`, the package version as the
single source of truth.  To keep that the *only* copy, `pyproject.toml`'s
`version = "0.1.0"` was replaced by a dynamic read: `[project].dynamic =
["version"]` + `[tool.setuptools.dynamic] version = {attr =
"trackview.config.__version__"}`, so setuptools imports just `trackview.config`
(which touches only the stdlib `pathlib`, its `__init__.py` re-exporting nothing, so
the build needs none of the heavy runtime deps) to stamp the wheel/sdist `Version:`
-- the build-stamped version and the running program can no longer drift apart.  The
CLI gained a `--version` switch (`action="version"` on the argparse surface in
`trackview.cli:main`, reading the re-exported `__version__` from `trackview.config`,
printing a fully-formed `trackview 0.1.0` line and exiting: a pure, side-effect-free
glance that fetches no basemap and writes nothing, consistent with `--no-map`'s
spirit); it is listed first in the `trackview.py` launcher's usage block and the
README's.  A new `TestVersion` in `tests/test_config.py` locks the constant to a
PEP-440 numeric release tag and asserts the CLI reports the same object `config`
holds (so the two can't drift).  `--version` was verified to print `trackview
0.1.0` both as `python trackview.py --version` and under the console entry-point
name, and a real PEP 517 `python -m build` in a throwaway venv stamped `Version:
0.1.0` into the wheel `METADATA` -- confirming the dynamic read.  Behaviour-preserving
aside from the new flag: the offline suite is now **217 passed, 1 deselected** (the
prior 215 plus the two `TestVersion` cases); `ruff check` stays clean.

## Phase 4: Testing Infrastructure (High Priority)

### 4.1 Test Suite Enhancement

**Tasks**:
- Add unit tests for each module
- Integration tests for module interactions
- Mock external dependencies
- Improve test coverage

**Implementation**:
1. Review existing test suite
2. Add module-specific tests
3. Add integration tests
4. Ensure coverage

**Done (2026-09-30) -- the report builders now carry pure, offline unit tests.**  Five
leaves, one per untested report module (each a pure function over the already-parsed
ride dicts / per-segment arrays, so the suite builds its fixtures by hand -- no GPX, no
network, no figure):
- `tests/test_calendar.py` (10 tests) -- `_calendar_days` / `_month_ticks` / `_CALENDAR_METRICS`
- `tests/test_trend.py` (8 tests) -- `_trend_panels` / `_TREND_COLORS`
- `tests/test_summary.py` (6 tests) -- `_summary_groups`
- `tests/test_climbs.py` (9 tests) -- `_ride_climbs` / `_all_climbs`
- `tests/test_stats.py` (19 tests) -- `_stats_columns` / `write_stats` / `write_csv`

The `test_climbs` leaf exercised a climb that reaches the ride's *final* sample, which
exposed a genuine off-by-one in `trackview/climbs._ride_climbs`: it indexed a phantom
`n`-th point (`cum[k + 1]` / `ele` to `k + 1` / `gs[j:k + 1]`) when the last valid
point index is `n - 1`, crashing `IndexError` on a climb that runs to the last sample.
Fixed by clamping the run end to `e = min(k + 1, n - 1)` (used for `len_km`, the gain
sum range, `max_gr`, and `end_km`); verified behaviour-preserving -- 0 differing climbs
and 0 crashes across 40 most-recent rides (those don't end on a climb, but the clamp
only ever changes the phantom `cum[n]` case to the correct `cum[n - 1]`).
The `test_stats` leaf builds bare ride dicts (distance / gain / duration + the
`[sum, count]` telemetry pairs) by hand and points `write_stats` / `write_csv` at a
`tmp_path`, asserting the shared column list (the `--ext` telemetry block spliced in
only under `show_ext`, the `Device` column always closing), the per-ride cells (a
telemetry-free ride shows a `"-"`), the per-device-group Summary totals (point-weighted
averages), and the CSV's decimal-normalisation (no thousands grouping) + the default
`;` vs an explicit `,` delimiter.  No source change: the writers are already correct.
The offline suite stood at 153 passed, 1 deselected.

**Plus a `helpers` leaf + one doc-drift fix (2026-09-30).**  `tests/test_helpers.py`
(30 tests) covers the metadata / grouping / naming leaves not yet tested elsewhere
(the date / parse helpers live in `test_parse_helpers`; `_select_top` / `_filter_by_meta`
/ `_list_rides` in `test_geometry` / `test_filters` / `test_dry_run`): `_device_type` /
`_sport_type` (the `<desc>` "Device:" / "Sport:" lines, trimmed, `None` when absent),
`_device_label` (`"unknown"` for a plain track), `_device_groups` (first-seen
`(device, [rides])` grouping, an unnamed ride in its own `unknown` group), `_match_meta`
(a ride's pass/fail on a `--device`/`--sport` filter), `_top_key` (the `km` / `gain` /
`recent` ranking value; an undated ride ranks oldest), `_safe_filename` (unsafe chars ->
`_`, edge `.`/`_` stripped, blank -> `"track"`), and `_short_label` (a `_title_name`-
rewritten, width-truncated, ellipsised colourbar label).  The `_match_meta` test exposed
a doc drift: the source docstring called the filter "whitespace-trimmed", but the
`casefold()` compare is exact -- the docstring was corrected to "exact, case-insensitive
match".  Offline suite: **183 passed, 1 deselected.**

**Plus an `io` leaf -- the self-contained HTML / Leaflet export (2026-09-30).**
`tests/test_io.py` (17 tests) covers the `--html` writers that build the single-file
interactive map from the already-parsed ride dicts -- pure over the per-ride `(lat, lon)`
arrays and strings, no figure, and (driven through the `inline=False` / CDN path) no
network, so the suite stays offline: `_html_escape` (the HTML-significant chars in a ride
name), `_ride_feature` (one ride as a GeoJSON LineString feature, coords `[lon, lat]`
rounded to 5 decimals, the `name`/`dist_km`/`gain_m`/`duration_s`/`color` properties, a
missing `duration_s` -> `0.0`), `_tracks_geojson` (one feature per ride with >= 2 points,
the `< 2`-point and no-`ll` rides dropped), `_leaflet_document` (a `<!DOCTYPE html>` shell
with the HTML-escaped `<title>` and every `__TOKEN__` filled -- the tile URL and the
attribution reaching the page through the app script's JSON-escaped tokens, not bare
literals), `_load_leaflet(inline=False)` (the offline CDN `(<link>/<script>, "cdn")`
ref -- the "mock external dependencies" leaf, the library never fetched), and `write_html`
(cdn mode writes a self-contained file, an empty route / no tracks writes nothing + prints
the "no ride has a route to plot." note, an unknown `--style` falls back to OSM).  No
source change: the writers are already correct.  Offline suite: **200 passed, 1
deselected.**

**Plus a `mapfig` geometry leaf (2026-09-30).**  `tests/test_mapfig.py` (6 tests)
covers `trackview/mapfig.fit_aspect` -- the one pure, figure-free helper in the
render module: it grows a `(west, south, east, north)` bbox so its width:height
matches the figure's `aspect_wh` (a square `FIGURE_IN` keeps the map un-letterboxed),
padding east/west for a too-narrow box and north/south for a too-wide one, always
centred on the box centre.  The heavy `render` orchestrator stays the `slow`
figure path (`test_render_smoke`); `fit_aspect` is pure math, so it is tested offline.
No source change.  Offline suite: **206 passed, 1 deselected.**

**Phase 4.1 coverage is now complete for every pure leaf (2026-09-30).**  The five report
builders (`calendar` / `trend` / `summary` / `climbs` / `stats`), the `helpers`
metadata/grouping/naming leaves, the `--html` / Leaflet `io` writers, the `mapfig`
aspect helper `fit_aspect` and the `config` constants are each now backed by a dedicated
offline test file -- the last, `tests/test_config.py` (5 tests), locks the run-time
directory layout and the two magic numbers (`DECIMATE_M` / `PI_R`) -- guarding the one
value-affecting edit the config constants made when they moved from the repo-root
monolith, the one-level `.parent.parent` shift that keeps the four dirs resolving to the
repo-root `gpx` / `output` / `stats` / `tiles`.  Together with the pre-existing
`test_geometry` / `test_parse_helpers` / `test_filters` / `test_load_tracks` /
`test_fit_to_gpx` / `test_dry_run` leaves, the suite now stands at **211 passed,
1 deselected** (the one deselected being the `network`+`slow` render smoke test).  The
`load` reader needs no dedicated file -- its single `load_tracks` function is already
covered by `test_load_tracks` -- and the only modules left without a dedicated file are
the `cli` wiring (covered by `test_dry_run`'s `run_main`) and the heavy `mapfig.render`
orchestrator (the `@pytest.mark.slow` figure path); neither carries pure logic worth a
standalone leaf.  This closes the "add unit tests for each module" / "improve test
coverage" task for every pure leaf; the integration + mock-dependency tasks are met by
the existing `test_dry_run` (`run_main`) and the `io` CDN-path leaf.

## Phase 5: Documentation (Closed 2026-10-18)

### 5.1 Module Documentation

**Tasks**:
- Add comprehensive module documentation
- Update function-level docstrings
- Add usage examples
- Create API reference

**Implementation**:
1. Document each module
2. Add examples
3. Create user guide

**Done (2026-10-18) -- documentation pass, no behaviour change.**  Module-level
documentation was already in place (every `trackview/` submodule carries a module
docstring stating its role and extraction provenance, "Extracted ... PLAN.md Phase X",
added during Phases 1--3); this pass completed the two gaps and the API reference:

* **Function-level docstrings** -- the last two of the 70 module functions still missing
  one now have them, in the house style (role + behaviour prose): `trackview/cli.main`
  (the CLI orchestrator that parses the flags, runs the filter sequence, and dispatches to
  the writers) and `trackview/mapfig.render` (the map / ride-card / heat figure pipeline).
  A quick AST scan now reports **every module and every function carries a docstring**.
* **Package docstring** -- the 0-byte `trackview/__init__.py` now carries a short package
  docstring (the tool's one-line purpose, that it is a regular re-export-free package whose
  submodules are imported by full name, and a pointer to `API.md`); it re-exports nothing,
  so the package stays a namespace for the extracted leaves, not a second monolith.
* **API reference** -- a new top-level `API.md` catalogues the module map: for each of the
  13 modules its role, the constants it holds, and its functions (signature + first docstring
  line), plus the programmatic entry points (`load_tracks` -> the `write_*` reports /
  `render` / `write_gallery`), the acyclic dependency direction, and an honest note that the
  leading-underscore names are the carried-over monolith helpers that *are* the cross-module
  API (not Python's "private" signal -- there is no `__all__`).  Usage examples stay in
  `README.md` (the full **Usage** section), which `API.md` points to rather than duplicating.

No code path changed (docstrings only), so the offline suite is unchanged:
**211 passed, 1 deselected.**  `API.md` is a top-level doc (not shipped -- the build
declares `packages = ["trackview"]`, so it ships only the `trackview/` package).

## Phase 6: Build System (Low Priority)

### 6.1 Package Configuration

**File**: `setup.py`

**Components**:
- Package metadata
- Dependency management
- Entry points

**Implementation**:
1. Create setup.py
2. Define dependencies
3. Configure entry points

**Done (2026-10-18) -- as `pyproject.toml`, not `setup.py`.**  The plan named `setup.py`, but
the repo already held a `requirements.txt` and no build file, so a legacy `setup.py` would have
sits alongside them as a third, out-of-sync source of truth.  The build config is therefore
**PEP 518/621 in `pyproject.toml`** (the `[build-system]` + `[project]` blocks, backend
`setuptools.build_meta`): the package metadata (name `trackview`, version `0.1.0`, a one-line
`description`, `readme = "README.md"`, `requires-python = ">=3.10"`), the runtime
`dependencies` (`contextily` / `gpxpy` / `matplotlib` / `numpy` -- the versions mirrored from
`requirements.txt`, which stays as the `pip install -r` convenience), two optional extras
(`fit = fitparse`, the `.fit` converter only; `test = pytest`), and the console entry point
`[project.scripts] trackview = "trackview.cli:main"` -- the installed counterpart to
`python trackview.py` (the root launcher re-enters this same `main`).  A `[tool.setuptools]
packages = ["trackview"]` stops flat-layout auto-discovery sweeping the root `trackview.py`
launcher or the data/script dirs (`gpx/` `output/` `stats/` `tiles/` `fit/` `gc/` `lib/`
`tools/`) into the build.  Verified by a real PEP 517 build in a throwaway venv (`python -m
build`): the sdist + wheel ship the `trackview/` submodules only (root `trackview.py` and every
data dir excluded, confirmed from `top_level.txt` / `RECORD`), with `entry_points.txt` =
`trackview = trackview.cli:main` and the four core deps + both extras in `METADATA`.  The same
file also carries the pre-existing `[tool.pytest.ini_options]` (the `network` / `slow` markers
and `testpaths`), so it is now the single source of truth for build *and* test-runner config.
No behaviour changed and the main `.venv` was left untouched (the build ran isolated); offline
suite: **211 passed, 1 deselected.**

## Implementation Strategy

### Approach
1. **Incremental extraction** - Extract one module at a time
2. **Test-driven** - Ensure no regressions after each change
3. **Backward compatible** - Maintain existing API
4. **Version controlled** - Frequent commits with clear messages

### Order of Operations
1. Start with Phase 1 (Module Extraction)
2. Extract modules in order: Geometry → Parsing → Filters → Rendering → Stats → I/O
3. Move to Phase 2 (Class Structure) once core modules are stable
4. Iterate through remaining phases

### Risk Mitigation
1. **Frequent testing** - Run test suite after each change
2. **Small changes** - Extract one function/module at a time
3. **Clear documentation** - Document changes as they happen
4. **Backup** - Keep original working version

## Timeline Estimate

### Phase 1: Module Extraction
- **Duration**: 2-3 weeks
- **Tasks**: Extract 6 modules
- **Effort**: High (most complex phase)

### Phase 2: Class Structure
- **Duration**: 1-2 weeks
- **Tasks**: Create class hierarchy
- **Effort**: Medium

### Phase 3: Configuration Management
- **Duration**: 1 week
- **Tasks**: Centralize configuration
- **Effort**: Low-Medium

### Phase 4: Testing Infrastructure
- **Duration**: 1-2 weeks
- **Tasks**: Enhance test suite
- **Effort**: Medium

### Phase 5: Documentation
- **Duration**: Ongoing -> closed 2026-10-18 (5.1 done; every module + function carries a
  docstring, the package gained a docstring, `API.md` added -- see the 5.1 "Done" entry)
- **Tasks**: Document modules
- **Effort**: Low (can be parallelized)

### Phase 6: Build System
- **Duration**: 1 week
- **Tasks**: Create setup.py
- **Effort**: Low

## Success Criteria

1. **Code Structure**: Well-organized module structure
2. **Test Coverage**: Comprehensive test suite
3. **Documentation**: Clear, up-to-date documentation
4. **Functionality**: All existing features preserved
5. **Performance**: No significant performance degradation
6. **Maintainability**: Easy to add new features

## Monitoring and Metrics

1. **Code Metrics**: Track cyclomatic complexity, line count per module
2. **Test Metrics**: Track test coverage, pass rate
3. **Build Metrics**: Track build time, success rate
4. **User Metrics**: Track user feedback, issue resolution time

## Contingency Plan

If the refactoring becomes too complex:
1. Pause and reassess
2. Consider alternative approaches
3. Prioritize critical modules first
4. Document decisions and rationale

## Next Steps

1. ✅ Create `trackview/geometry.py` (completed 2026-09-29)
2. ✅ Extract geometry functions (completed 2026-09-29)
3. ✅ Update imports in trackview.py (completed 2026-09-29)
4. ✅ Run test suite (completed 2026-09-29)
5. ✅ Create `trackview/helpers.py` (Phase 1.2, completed 2026-09-30)
6. ✅ Extract helper functions from trackview.py (completed 2026-09-30)
7. ✅ Update imports in trackview.py (completed 2026-09-30)
8. ✅ Run test suite — 101 passed, 1 deselected (completed 2026-09-30)
9. ✅ Extract the metric / telemetry / calorie cluster into `trackview/metrics.py`
   (Phase 1.3, completed 2026-09-30)
10. ✅ Re-import the 11 functions; keep the 6 constants private; re-point the 4
   `GRADE_CAP_*` test references to `trackview.metrics` (completed 2026-09-30)
11. ✅ Run test suite — 101 passed, 1 deselected (completed 2026-09-30)
12. ✅ Extract the *leaf* rendering helpers into `trackview/rendering.py`
   (Phase 1.4a, completed 2026-09-30)
13. ✅ Re-import the 5 names (`_metric_norm`, `_moving_avg`, `CMAPEED`,
     `GRADE_CBAR_MAX`, `SUPPRESSED_RENDER_DEVICES`) into the monolith; none are
   private to the module — all 5 are still called by the remaining render /
     `_draw_profile` / `main` code (completed 2026-09-30)
14. ✅ Run test suite — 101 passed, 1 deselected (completed 2026-09-30)
15. ✅ Extract the profile / heat / scale-bar *drawing helpers* into
     `trackview/rendering.py` (Phase 1.4b-i, completed 2026-09-30)
16. ✅ Extract the stats / ride-log report cluster (`_stats_columns`, `write_stats`,
    `write_csv`) into `trackview/stats.py` (Phase 1.5a, completed 2026-09-30)
17. ✅ Re-import `write_stats` / `write_csv` into the monolith (both are still called by
    `main`); keep `_stats_columns` private to `stats.py` -- no test references it
    (completed 2026-09-30)
18. ✅ Run test suite -- 101 passed, 1 deselected (completed 2026-09-30)
19. ✅ Extract the climb-ranking cluster (`_ride_climbs`, `_all_climbs`, `write_climbs`)
     + its 3 `CLIMB_*` detection thresholds into `trackview/climbs.py` (Phase 1.5b,
    completed 2026-09-30)
20. ✅ Re-import `write_climbs` into the monolith (the one `main` calls); `_ride_climbs` /
     `_all_climbs` and the `CLIMB_*` constants stay private to `climbs.py` (2026-09-30)
21. ✅ Run test suite -- 101 passed, 1 deselected (completed 2026-09-30)
22. ✅ Relocate the shared `_MONTH_ABBR` display constant into `trackview/helpers.py` -- its
   shared home, alongside `_short_label` -- and re-import it into the monolith, so both the
   staying calendar cluster (`_month_ticks`) and the moving summary cluster (`write_summary`)
   read it there (Phase 1.5c-i, completed 2026-09-30)
23. ✅ Extract the summary report cluster (`_summary_groups`, `write_summary`) into
    `trackview/summary.py` (Phase 1.5c-ii, completed 2026-09-30)
24. ✅ Re-import `write_summary` into the monolith (the one `main` calls); keep `_summary_groups`
   private; no test references the cluster, so no bridge re-pointing (2026-09-30)
25. ✅ Run test suite -- 101 passed, 1 deselected (completed 2026-09-30)
26. ✅ Relocate the shared `DPI` figure-resolution constant into `trackview/rendering.py` -- its
   figure-constant home alongside `CMAPEED` / `HEAT_*` -- and re-import it into the monolith, so
   both the staying render cluster and the moving trend / calendar clusters read it there
    (Phase 1.5d-i, completed 2026-09-30)
27. ✅ Extract the calendar activity-grid cluster (`_calendar_days`, `_month_ticks`, `write_calendar`,
     the `_CALENDAR_METRICS` table) into `trackview/calendar.py` (Phase 1.5d-ii, completed 2026-09-30)
28. ✅ Re-import `write_calendar` *and* `_CALENDAR_METRICS` (the latter feeds `main`'s --calendar-by
   choices); keep `_calendar_days` / `_month_ticks` private (2026-09-30)
29. ✅ Extract the training-trend cluster (`_trend_panels`, `_TREND_COLORS`, `write_trend`) into
     `trackview/trend.py` (Phase 1.5d-iii, completed 2026-09-30)
30. ✅ Re-import `write_trend` into the monolith (the one `main` calls); keep `_trend_panels` /
   `_TREND_COLORS` private; no test references the clusters, so no bridge re-pointing (2026-09-30)
31. ✅ Run test suite -- 101 passed, 1 deselected (completed 2026-09-30)
32. ✅ Relocate the tile / HTTP provider constants (`USER_AGENT` / `SOURCES` / `ATTRIBUTION`) into
    `trackview/io.py` -- a new module -- and re-import them (the monolith reads `SOURCES` for its
    --style choices; `USER_AGENT` / `ATTRIBUTION` travel with the provider table) (Phase 1.6-i,
     completed 2026-09-30)
33. ✅ Extract `_load_basemap` (the contextily basemap fetch: provider fail-over, retry/backoff and a
    variance blank-check) into `trackview/io.py`, dropping the monolith's now-unused `import time` --
    the one network back-edge the figure cluster was blocked on, so it moves first (Phase 1.6-ii,
     completed 2026-09-30)
34. ✅ Relocate the shared `STRONG_COLORS` + `PAD_FRAC` constants into `trackview/rendering.py` -- their
    figure-constant home, alongside CMAPEED / HEAT_* / DPI -- and re-import them into the monolith, so the
    staying render cluster and the moving gallery both read them there (Phase 1.6-iii, completed 2026-09-30)
35. ✅ Extract the HTML / Leaflet export cluster (`_APP_JS` / `_fetch_text` / `_load_leaflet` /
    `_ride_feature` / `_tracks_geojson` / `_leaflet_document` / `_html_escape` / `write_html`, with
    `LEAFLET_DIR` relocated to the package-parent `lib/`) into `trackview/io.py`; re-import `write_html`
    (the one `main` calls), keep the helpers private (Phase 1.6-iv, completed 2026-09-30)
36. ✅ Extract the gallery + tile-detail unit (`choose_detail` + `EQUATOR` / `DETAIL_MIN` / `DETAIL_MAX`, and
    `_gallery_grid` / `_gallery_cell` / `write_gallery`) into `trackview/io.py`, dropping the monolith's
    now-unused `import math`; re-import `write_gallery` + `choose_detail` + `DETAIL_MIN` / `DETAIL_MAX`
    (`render` still calls `choose_detail`), keep `EQUATOR` / the gallery helpers private (Phase 1.6-v,
     completed 2026-09-30)
37. ✅ Run test suite -- 101 passed, 1 deselected (completed 2026-09-30)
38. ✅ Extract the big `render` / `render_*` / `write_*` figure-orchestration cluster -- the `render`
    orchestrator (its `--profile` ride-card and `--heat` overlay), the `fit_aspect` bbox-aspect helper and
    the figure constants (`FIGURE_IN`, the `CMAPEL` / `GRADE_STOPS` / `CMAPGRADE` ramps, the `--profile`
    `PROF_METRICS` table) -- into a new top-of-tree `trackview/mapfig.py` (Phase 1.4b-ii, completed 2026-09-30)
39. ✅ Re-import `render` + `PROF_METRICS` (the two `main` still touches) from `trackview.mapfig`; with
    those the only staying uses, prune the imports the move orphans -- `import numpy as np` + the seven
    matplotlib sub-imports (the `import matplotlib` + `use("Agg")` backend guard stays, so headless figures
    still render), and the now-unused `_short_label` / `_metric_avg` / `_grade_cap` / `_calories_burned` /
    `_fmt_duration` / `ATTRIBUTION` / `_load_basemap` / `choose_detail` re-imports (2026-09-30)
40. ✅ Re-point `test_geometry`'s `tv._grade_cap` / `tv._moving_avg` to their new submodules
    (`trackview.metrics` / `trackview.rendering`) -- the bridge no longer mirrors the pruned names
    (2026-09-30)
41. ✅ Run test suite -- 101 passed, 1 deselected (completed 2026-09-30)
42. ✅ Extract `load_tracks` (the GPX reader) into a new top-of-tree `trackview/load.py` -- the last
    non-entry-point function in the monolith, now back-edge-free since its geometry / metrics / helpers
    deps are all extracted (Phase 1.7, completed 2026-09-30)
43. ✅ Copy `load_tracks` byte-for-byte into a new `trackview/load.py`, importing its leaves
      (`latlon_to_merc` / `decimate` / `_distance_and_gain` / `_grade_and_cumkm` from `trackview.geometry`,
       `_device_type` / `_sport_type` from `trackview.helpers`, `_point_telemetry` from `trackview.metrics`) --
    so it has no back-edge to the monolith (Phase 1.7, 2026-09-30)
44. ✅ Re-import `load_tracks` from `trackview.load` and prune the imports the move orphans: `import os` +
       `import gpxpy`, the now-fully-dead `from trackview.geometry import (...)` line and
       `from trackview.metrics import (...)` block, and `_device_type` / `_sport_type` from the helpers
    re-import (Phase 1.7, 2026-09-30)
45. ✅ Re-point `test_load_tracks`'s `tv._distance_and_gain` / `tv._grade_and_cumkm` to
       `trackview.geometry` -- the bridge no longer mirrors the pruned names (Phase 1.7, 2026-09-30)
46. ✅ Run test suite -- 101 passed, 1 deselected (completed 2026-09-30)
47. ✅ Extract the config constants into a new `trackview/config.py` -- a pure leaf (Phase 3.1, item 47):
        a fresh top-of-tree module, since the monolith's `# ---- configuration ----` constants are the top of the
    dependency order -- consumed by `main` but importing nothing internal -- so a new module, not an existing one
48. ✅ Create `config.py` byte-value-equivalent: the paths resolve to the *same* repo root (`gpx` / `output` /
        `stats` / `tiles`), with the one-level `__file__` shift (`.parent.parent`) documented; `DECIMATE_M` and
    `PI_R` are byte-identical; the module imports only `__future__` + `pathlib` (acyclic, no back-edge)
49. ✅ Re-import the five *live* constants (`GPX_DIR` / `OUTPUT_DIR` / `STATS_DIR` / `TILE_CACHE_DIR` /
        `DECIMATE_M`) into the monolith and prune the `# ---- configuration ----` section; `PI_R` is the only dead
    one -- the monolith no longer touches it -- so it moves to `config.py` but is *not* re-imported (no orphan)
50. ✅ Run test suite -- 101 passed, 1 deselected (completed 2026-09-30)
51. ✅ Extract the `main` entry point (Phase 3.1, into `trackview/cli.py`) -- the last in-module user of the
     leaf re-imports; it travels out, dragging the stdlib it consumed, and the monolith keeps the re-imports
    purely to feed the bridge (see the "Revised Phase 3.1 (cont.)" section, below) (completed 2026-09-30)
52. ✅ Delete the re-export bridge (`trackview/__init__.py`) once `trackview.py` is a thin CLI -- the final leaf
    of Phase 1 (completed 2026-09-30; see the "Revised Phase 3.1 (cont.): Bridge Deletion" section, below):
    (a) re-point the ~7 `tv.<name>` test refs at their submodules (`load_tracks` -> `trackview.load`, `render` ->
       `trackview.mapfig`, `_list_rides` / `_parse_argdate` / `_ride_date` / `_filter_by_meta` / `_select_top` ->
       `trackview.helpers`, and `main` -> `trackview.cli`) across `conftest` + the 6 test files; (b) prune the
    now-bridge-only `from trackview.* import (...)` re-imports out of the monolith, leaving a thin CLI; and (c)
    delete the re-export bridge -- `trackview/__init__.py` (the importlib monolith mirror) is replaced by an
     *empty* init, so `trackview` stays a regular package the submodules import directly, with no monolith names
    re-exported.

53. ✅ Add pure, offline unit tests for every untested *report builder* (`tests/test_calendar.py`
    / `test_trend.py` / `test_summary.py` / `test_climbs.py` / `test_stats.py`, 52 tests) --
    the first leaf of Phase 4/4.1 (2026-09-30); the `test_climbs` leaf exposed + fixed an
    off-by-one in `trackview/climbs._ride_climbs`
54. ✅ Add `tests/test_helpers.py` (30 tests) -- the metadata / grouping / naming leaves
    (`_device_type` / `_sport_type` / `_device_label` / `_device_groups` / `_match_meta` /
    `_top_key` / `_safe_filename` / `_short_label`); exposed + fixed a doc drift in
    `_match_meta` (Phase 4/4.1, 2026-09-30)
55. ✅ Add `tests/test_io.py` (17 tests) -- the `--html` / Leaflet writers, driven through the
    `inline=False` CDN path so the suite stays offline (the "mock external dependencies" task);
    then `tests/test_mapfig.py` (6 tests) for the pure `fit_aspect` bbox-aspect helper (Phase
    4/4.1, 2026-09-30) -- with these, every *pure* module carries a dedicated offline test
56. ✅ Add `tests/test_config.py` (5 tests -- the `config` constants: the four run-time
    directories share one repo-root parent, the `gpx`/`output`/`stats`/`tiles` names, and the
     `DECIMATE_M` / `PI_R` magic numbers, guarding the one-level `.parent.parent` shift) to close
    out the last pure-constants module; the `load` reader needs no dedicated file (its single
      `load_tracks` is already covered by `test_load_tracks`), and `cli` (the `main` wiring) stays
    covered by `test_dry_run`'s `run_main` with the heavy `mapfig.render` by the `@pytest.mark.slow`
      `test_render_smoke` -- so Phase 4/4.1 is complete for every pure leaf (2026-09-30).  Offline
    suite: **211 passed, 1 deselected.**

### Detailed Next Steps for Helper Functions Module:

After analyzing the code, I found that the parsing functions mentioned in the original plan don't actually exist as separate functions. The code uses libraries like `gpxpy` for parsing. Instead, there are many helper functions that can be organized into modules:

1. **Metadata Extraction Helpers** (e.g., `_ride_date`, `_device_type`, `_sport_type`, `_device_label`)
2. **Filtering Helpers** (e.g., `_match_meta`, `_filter_by_meta`, `_top_key`, `_select_top`)
3. **Display Helpers** (e.g., `_list_rides`)
4. **Date Parsing Helpers** (e.g., `_parse_argdate`)

Let me create a more realistic module structure based on what actually exists in the code.

### Revised Phase 1.2: Helper Functions Module

**File**: `trackview/helpers.py`

**Functions to extract**:
- `_ride_date` - Extract date from filename
- `_device_type`, `_sport_type`, `_device_label` - Metadata extraction
- `_device_groups` - Group tracks by device
- `_match_meta`, `_filter_by_meta` - Metadata filtering
- `_top_key`, `_select_top` - Selection helpers
- `_list_rides` - Display helper
- `_parse_argdate` - Date parsing
- `_short_label`, `_title_name`, `_safe_filename` - String helpers

**Implementation**:
1. ✅ Create new file `trackview/helpers.py` (2026-09-30)
2. ✅ Copy all helper functions from trackview.py (2026-09-30)
3. ✅ Update imports in trackview.py (2026-09-30)
4. ✅ Run test suite — 101 passed, 1 deselected, no regressions (2026-09-30)
5. ✅ Proceed to next module — Phase 1.3 (metrics, completed 2026-09-30)

**Done (2026-09-30)**.  `trackview/helpers.py` now holds the pure metadata/filter/
selection helpers, copied byte-for-byte out of the monolith so behaviour is
unchanged:

- constants: `_NAME_DATE_RE`, `_DEVICE_RE`, `_SPORT_RE`, `_UNSAFE_CHARS`, `_TOP_BY`
- functions: `_title_name`, `_ride_date`, `_device_type`, `_sport_type`,
  `_device_label`, `_device_groups`, `_match_meta`, `_filter_by_meta`, `_top_key`,
  `_select_top`, `_list_rides`, `_parse_argdate`, `_safe_filename`, `_short_label`

The monolith re-imports back the names the *remaining* code still calls
(`_title_name, _ride_date, _device_type, _sport_type, _device_label,
_device_groups, _filter_by_meta, _select_top, _list_rides, _parse_argdate,
_safe_filename, _short_label, _TOP_BY`); the names used *only* inside the
extracted block (`_match_meta, _top_key, _NAME_DATE_RE, _DEVICE_RE, _SPORT_RE,
_UNSAFE_CHARS`) stay private to `helpers.py`.  `SUPPRESSED_RENDER_DEVICES`
(a rendering concern) and `_moving_avg` (a rendering helper, Phase 1.4) were left
in the monolith.

### Revised Phase 1.3: Metrics Module

**File**: `trackview/metrics.py`

The metric / telemetry / calorie / formatting helpers the ride-log, the stats
report and the colour scales share -- pure over the already-parsed ride dicts
(numpy for the percentile capping), no I/O, no rendering.

**Constants (private to the module, used only inside the moved functions)**:
`GRADE_CAP_PCT`, `GRADE_CAP_FLOOR`, `GRADE_CAP_CEIL`, `JOULES_PER_KCAL`,
`METABOLIC_EFFICIENCY`, `_TELE_TAGS`

**Functions to extract**:
- `_point_telemetry` - a trackpoint's optional Wahoo telemetry -> `{key: float}`
- `_metric_avg`, `_metric_avg_track` - point-weighted per-track / per-ride averages
- `_max_grade`, `_max_grade_group` - steepest grade of a ride / a group of rides
- `_grade_cap` - the robust (percentile, floor-capped) `|grade|` colour range
- `_track_calories`, `_calories_burned` - the power x time calorie estimate
- `_fmt_duration`, `_fmt_dur_or_dash`, `_fmt_num` - the shared "value or a dash" formatters

**Implementation**:
1. ✅ Create new file `trackview/metrics.py` (2026-09-30)
2. ✅ Copy the cluster byte-for-byte out of the monolith (numpy-coupled, no matplotlib)
3. ✅ Re-import the 11 functions the remaining code still calls into the monolith;
   the 6 constants stay private to `metrics.py` (2026-09-30)
4. ✅ Re-point the 4 `TestGradeCap` cases that read the grade-cap boundary constants
   through the `tv.` facade to import them from `trackview.metrics` (2026-09-30)
5. ✅ Run test suite — 101 passed, 1 deselected, no regressions (2026-09-30)

**Done (2026-09-30)**.  `trackview/metrics.py` now holds the metric / telemetry /
calorie / formatting helpers, copied byte-for-byte out of the monolith so behaviour
is unchanged.  The one *rendering-coupled* neighbour, `_metric_norm` (it returns a
matplotlib `Normalize`), was deliberately left in the monolith for the rendering
phase -- as were the rendering constants `CMAPEED` / `GRADE_CBAR_MAX`, `DETAIL_MAX`
and `SUPPRESSED_RENDER_DEVICES`.  The 6 constants are used *only* inside the moved
functions, so they stay private to `metrics.py`; the 11 functions the remaining code
still calls are re-imported into the monolith.  Four `TestGradeCap` cases that read
the grade-cap boundary constants through the `tv.` facade now import them from
`trackview.metrics` (their new home); `tv._grade_cap` itself stays on the facade, as
do the other re-imported helpers.

**Backward-compatibility bridge.**  The top-level `trackview/` package shadows the
same-named `trackview.py` module (`import trackview` picks the package), so
`trackview/__init__.py` loads the monolith from its file as the private submodule
`trackview._main` (via `importlib.util.spec_from_file_location`) and mirrors its
namespace back into the package.  `__file__` stays the monolith's real path, so
its `Path(__file__).parent` config (gpx/, output/, stats/, tiles/) still resolves
to the repo root.  `import trackview`, `python trackview.py`, and
`from trackview.geometry import ...` / `from trackview.helpers import ...` all keep
working under this one import name; the bridge is deleted once every module has
moved and the package stands on its own.


### Revised Phase 1.4: Rendering Helpers Module (leaf extraction, done)

**File**: `trackview/rendering.py`

The matplotlib-coupled half of the old "Rendering" phase, done in two parts.
This sub-step (1.4a) moves the *leaf* helpers that have no back-edge to the
monolith; the big figure cluster (1.4b) stays for later.

**Constants**:
- `CMAPEED = "inferno"` -- the sequential "effort" colour ramp for --color-by speed/power
- `GRADE_CBAR_MAX = 4.0` -- the max number of rides that each get their own grade colourbar on a combined map (beyond it a single shared scale is used and noted)
- `SUPPRESSED_RENDER_DEVICES = {"Kickr Snap"}` -- a stationary smart trainer's session has no route of its own, so it is kept off the rendered image (but still listed in the ride-log/CSV)

**Functions to extract**:
- `_metric_norm` -- the robust percentile colour norm for a telemetry metric (falls back to flat colour via None when there are no values)
- `_moving_avg` -- the centred, NaN-skipping moving average (quiet the GPS jitter in a per-segment grade line)

**Implementation**:
1. ✅ Create new file `trackview/rendering.py` (2026-09-30)
2. ✅ Copy the cluster byte-for-byte out of the monolith (numpy-coupled, matplotlib.colors.Normalize; no back-edge to the monolith, no dependency on metrics.py) (2026-09-30)
3. ✅ Re-import the 5 names into the monolith -- all 5 are still called by the remaining render / `_draw_profile` / `main` code, so none stays private (2026-09-30)
4. ✅ No test re-pointing: only `tv._moving_avg` is test-referenced, and it resolves via the bridge because the monolith re-imports it; the 3 constants and `_metric_norm` have no test references (2026-09-30)
5. ✅ Run test suite -- 101 passed, 1 deselected, no regressions (2026-09-30)

**Done (2026-09-30)**.  `trackview/rendering.py` now holds the leaf rendering helpers, copied byte-for-byte out of the monolith so behaviour is unchanged.  Unlike `metrics.py`, all 5 names are still *used* by code that stays in the monolith (`render` colours by `CMAPEED` through `_metric_norm`, the profile and climb detection run `_moving_avg` over a `GRADE_SMOOTH` window, and `main` keeps `SUPPRESSED_RENDER_DEVICES`-tagged trainer tracks off the image while still listing them), so every one is re-imported and none is private to the module.  `rendering.py` is even leaner than `metrics.py`: it imports only `numpy` and `matplotlib.colors.Normalize`, with no back-edge to the monolith and no dependency on `metrics.py`.  The big `render` / `render_*` / `write_*` figure cluster is deliberately *not* moved yet -- it has a back-edge (it calls `_load_basemap`, `decimate`, `_short_label`, `_title_name`, `_load_stats`, ... still in the monolith), so it waits for Phase 1.4b, after enough of those helpers have moved.  No test changes were needed: `tv._moving_avg` resolves through the re-export bridge, and the 3 constants plus `_metric_norm` have no test references.

### Revised Phase 1.4b-i: Drawing Helpers Module (done)

The second half of `trackview/rendering.py`, done after 1.4a: the
profile / heat / scale-bar *drawing helpers* the figures assemble, moved on the
same leaf-first principle -- they build on the 1.4a leaves (`_moving_avg`,
`CMAPEED`) but have **no back-edge to the monolith** (each takes its `ax`/
`fig`/`t`/`bbox` as arguments and touches no monolith helper), so they move
before the orchestration cluster that *calls* them.

**Constants (now private to the module -- used only inside the moved functions):**
- `GRADE_SMOOTH = 5.0` -- the centred moving-avg window the profile's per-segment grade line runs `_moving_avg` over
- `HEAT_GRID = 300` -- cells across the bbox for the `--heat` 2-D "time on route" histogram
- `HEAT_CAP_PCT = 98.0` -- the heat colour cap (% of non-empty cells)
- `HEAT_ALPHA = 0.55` -- the heat overlay opacity

**Functions to extract**:
- `_draw_profile` -- the elevation + grade ride-profile silhouette (grade on a twin axis)
- `_has_metric_pts` -- whether a ride carries a per-point telemetry array (gate for a mini-panel)
- `_draw_profile_metric` -- one telemetry mini-panel of the `--profile` "ride card"
- `_stack_grade_colorbars` -- one compact per-ride grade colourbar, stacked on the right of a combined map
- `_nice_m` / `_fmt_len` -- the scale-bar "nice length" rounding and its `m`/`km` label
- `_draw_scale_bar` -- the lower-right `0 .. N km/m` scale bar (white-cased)
- `_dwell_times` -- per-point "time on route" for the heat weighting
- `_fmt_heat_time` -- the heat colourbar tick (`N s` / `N m` / `Nh Mm`)
- `_draw_heat` -- the 2-D `--heat` density overlay (a masked, percentile-capped `imshow`)

**Implementation**:
1. ✅ Fold the 10 drawing helpers + 4 constants into the existing `trackview/rendering.py`, byte-for-byte (added `math`, `matplotlib.pyplot`, `withStroke` to its imports); no back-edge, no `metrics` dependency (2026-09-30)
2. ✅ Extend the monolith's `from trackview.rendering import (...)` with the 7 helpers the *remaining* code still calls (`_draw_profile`, `_has_metric_pts`, `_draw_profile_metric`, `_stack_grade_colorbars`, `_draw_scale_bar`, `_fmt_heat_time`, `_draw_heat`); the 3 internal helpers (`_nice_m`, `_fmt_len`, `_dwell_times`) and the 4 constants stay private to the module (2026-09-30)
3. ✅ No test changes: none of the 10 functions or 4 constants is test-referenced, so the bridge needs no re-pointing (2026-09-30)
4. ✅ Run test suite -- 101 passed, 1 deselected, no regressions (2026-09-30)

**Done (2026-09-30)**. `trackview/rendering.py` now holds the *drawing* helpers alongside the 1.4a leaves. Unlike the 1.4a names, **7 of the 10** are still called by code that stays in the monolith (`render`/`main` assemble the profile card, the per-ride grade colourbars, the scale bar and the heat overlay), so they are re-imported; the other 3 (`_nice_m`, `_fmt_len`, `_dwell_times`) are used *only* inside the moved helpers and stay private, as do the 4 constants (`GRADE_SMOOTH`, `HEAT_GRID`, `HEAT_CAP_PCT`, `HEAT_ALPHA`) -- moving them in (rather than importing them) keeps `rendering.py` back-edge-free, the same discipline as `metrics.py`/`helpers.py`. No test changes were needed: none of the new names is test-referenced.
---

### Revised Phase 1.5a: Stats / Ride-Log Report Module (done)

The first clean leaf after the rendering helpers: the *table* report the CLI
emits -- the shared ride-log column definition and the two writers that print it
(`.txt` and `.csv`).  It is pure over the already-parsed ride dicts (no
matplotlib), and its only external names are the metadata / metric helpers already
moved to `trackview/helpers` and `trackview/metrics`, so it has **no back-edge to
the monolith** -- the same leaf-first criterion that let `metrics.py` and
`rendering.py` move first.

**Functions to extract**:
- `_stats_columns(show_ext)` -- the shared ride-log column definition (one
  `(header, numeric?, per-ride formatter, per-device-group summary)` 4-tuple per
  column; `show_ext` toggles the extended power / HR / cadence columns)
- `write_stats(tracks, out_path, show_ext)` -- the per-device `.txt` ride-log table
- `write_csv(tracks, out_path, show_ext, delimiter=";")` -- the same columns as a `.csv`

**Re-export / privacy**:
- `write_stats` and `write_csv` are still called by `main`, so the monolith
  re-imports them; `_stats_columns` is used *only* inside the two writers, so it
  stays private to the module (no test references it)
- the module imports its external names from `trackview.helpers`
  (`_title_name`, `_device_label`, `_device_groups`) and `trackview.metrics`
  (`_fmt_dur_or_dash`, `_fmt_num`, `_track_calories`, `_calories_burned`,
  `_metric_avg`, `_metric_avg_track`, `_max_grade`, `_max_grade_group`), plus
  the stdlib `csv` -- no back-edge to the monolith

**Implementation**:
1. ✅ Extract `_stats_columns` / `write_stats` / `write_csv` into `trackview/stats.py`
   byte-for-byte (124-line block, verified identical to the old monolith), with a
   module docstring and the `helpers` / `metrics` / `csv` imports (2026-09-30)
2. ✅ Replace the block in the monolith with a single
   `from trackview.stats import (write_stats, write_csv)`; `_stats_columns` is not
   re-imported -- it is private to `stats.py` (2026-09-30)
3. ✅ No test changes: none of the three names is test-referenced, so the bridge
   needs no re-pointing (2026-09-30)
4. ✅ Run test suite -- 101 passed, 1 deselected, no regressions (2026-09-30)

**Done (2026-09-30)**. `trackview/stats.py` now holds the ride-log report cluster,
copied byte-for-byte out of the monolith so behaviour is unchanged.  Both writers are
still called by `main` (the `.txt` table at line ~1716 and the optional `.csv` ride-log
at ~1722), so the two are re-imported; the shared `_stats_columns` column definition is
used only inside them and stays private -- the same discipline as the 1.4b-i internal
drawing helpers.  No test changes were needed: none of the three names is test-referenced,
and `write_stats` / `write_csv` resolve through the re-export bridge for `main`.
### Revised Phase 1.5b: Climb-Ranking Report Module (done)

The second report cluster, on the same leaf-first principle as 1.5a: the sustained-climb
detection and its ranking table.  It is pure over the parsed ride dicts -- the per-segment
`grade` / `cum_km` / `ele` arrays -- and its only external names are `_moving_avg` (already in
`trackview/rendering`) and `_title_name` (`trackview/helpers`), so it has **no back-edge to
the monolith**.

**Constants (moved in with the cluster, now private to the module -- used only inside it):**
- `CLIMB_MIN_GR = 4.0` -- the smoothed grade (%) a segment must clear to count as climbing
- `CLIMB_MIN_LEN = 250.0` -- the min horizontal run length (m) for a climb
- `CLIMB_SMOOTH = 9.0` -- the centred moving-avg window over which the grade is smoothed

**Functions to extract**:
- `_ride_climbs` -- the sustained climbs in one ride (maximal runs of smoothed grade >= min
   over >= min_len; a `score` = gain x average grade ranks a long climb against a short steep one)
- `_all_climbs` -- every ride's climbs, ranked by `score`
- `write_climbs` -- the `top_n` ranking written as a self-describing `.txt` table

**Implementation**:
1. ✅ Extract `_ride_climbs` / `_all_climbs` / `write_climbs` plus the `CLIMB_*` thresholds
   (and their prose comment) into `trackview/climbs.py` byte-for-byte -- a 7-line constant
   block and a 91-line function cluster, each verified identical to the old monolith --
    adding the `numpy` / `Path` / `helpers._title_name` / `rendering._moving_avg` imports
   (2026-09-30)
2. ✅ Replace both blocks in the monolith with a single
    `from trackview.climbs import (write_climbs)` -- the one name `main` still calls; the
    two internal helpers and the three `CLIMB_*` constants are not re-imported (private)
   (2026-09-30)
3. ✅ No test changes: none of the cluster's names is test-referenced, so the bridge needs
    no re-pointing (2026-09-30)
4. ✅ Run test suite -- 101 passed, 1 deselected, no regressions (2026-09-30)

**Done (2026-09-30)**. `trackview/climbs.py` now holds the climb-ranking cluster, copied
byte-for-byte out of the monolith so behaviour is unchanged.  Only `write_climbs` is still
called by `main` (the optional `.txt` climb ranking at ~line 1700), so it is re-imported; the
internal `_ride_climbs` / `_all_climbs` and the `CLIMB_MIN_GR` / `CLIMB_MIN_LEN` / `CLIMB_SMOOTH`
 thresholds stay private to the module -- moving the thresholds in (rather than importing them)
keeps `climbs.py` back-edge-free, the same discipline as the 1.5a / 1.4b-i extractions.
No test changes were needed: none of the cluster's names is test-referenced.  Remaining under
Phase 1.5: the trend / calendar / summary report clusters; then Phase 1.6 (I/O: HTML /
Leaflet, the gallery, and the `_load_basemap` helper that blocks the 1.4b-ii figure cluster).

### Revised Phase 1.5c: Summary Report Module (done)

The third report cluster, on the same leaf-first principle as 1.5a / 1.5b: the --summary
year-in-review report.  It is pure over the parsed ride dicts -- no rendering, so it writes
even under --no-map -- and its only external names are _ride_date / _MONTH_ABBR
(`trackview/helpers`) and _metric_avg / _fmt_num (`trackview/metrics`), so it has **no
back-edge to the monolith**.  One wrinkle made it a two-part move: _MONTH_ABBR (the
month-abbreviation labels a report month reads by) is shared by *both* this cluster and the
not-yet-moved calendar cluster (_month_ticks), so the constant first relocates to the
shared helpers module and is re-imported by the monolith before the cluster moves.

**The shared constant (relocated to `trackview/helpers.py`, re-imported by the monolith):**
- `_MONTH_ABBR` -- the 13-entry month-abbreviation table (index 0 a pad, 1..12 the
  months), used by both the --calendar activity grid and the --summary report; it sits with
  the other display helpers like `_short_label`, and the monolith re-imports it so the
  still-migrated calendar cluster keeps reading it

**Functions to extract:**
- `_summary_groups` -- the rides split by calendar year then month ({year: {month: [rides]}}),
  plus an 'undated' list of a filename carrying no date (private: only write_summary calls it)
- `write_summary` -- one block of monthly rows per year (count / distance / gain / hours, plus
  a per-group point-weighted average power under --ext), each closed by a TOTAL row, an
   'ALL years' grand total when the log spans >1 year, and an undated-rides note; the one name
   `main` calls

**Implementation:**
1. ✅ Relocate the shared `_MONTH_ABBR` constant into `trackview/helpers.py` (its shared home,
   with `_short_label`) and re-import it into the monolith, so both the staying calendar
   cluster and the moving summary cluster read it there -- the byte-identical literal (Phase
    1.5c-i, 2026-09-30)
2. ✅ Extract `_summary_groups` / `write_summary` into `trackview/summary.py` byte-for-byte -- a
    93-line cluster verified identical to the old monolith -- adding the `helpers`
    (_ride_date, _MONTH_ABBR) and `metrics` (_fmt_num, _metric_avg) imports; no stdlib needed
    (no Path / csv / numpy / plt) (Phase 1.5c-ii, 2026-09-30)
3. ✅ Replace the cluster in the monolith with a single
    `from trackview.summary import (write_summary)` -- the one name `main` still calls;
    `_summary_groups` is not re-imported (private) (2026-09-30)
4. ✅ No test changes: none of the cluster's names is test-referenced, so the bridge needs
   no re-pointing (2026-09-30)
5. ✅ Run test suite -- 101 passed, 1 deselected, no regressions (2026-09-30)

**Done (2026-09-30)**. `trackview/summary.py` now holds the summary report cluster, copied
byte-for-byte out of the monolith so behaviour is unchanged.  Only `write_summary` is still
called by `main`, so it is re-imported; the internal `_summary_groups` stays private.  Because
`_MONTH_ABBR` is shared with the calendar cluster, it was first relocated to `trackview/helpers`
(the shared display-constant home) and re-imported by the monolith, keeping `summary.py`
back-edge-free -- the same discipline as 1.5a / 1.5b / 1.4b-i.  No test changes were needed.
Remaining under Phase 1.5: the trend / calendar report clusters; then Phase 1.6 (I/O: HTML /
Leaflet, the gallery, and the `_load_basemap` helper that blocks the 1.4b-ii figure cluster).
### Revised Phase 1.5d: Trend / Calendar Figure Clusters (done)

The last two report clusters -- the --trend chart and the --calendar activity grid -- on the
same leaf-first principle as 1.5a / 1.5b / 1.5c.  Both are *standalone* figure writers: they
plot the parsed ride dicts with plain matplotlib (subplots / a 7xweeks grid), with **no basemap
and no network**, so they write even under --no-map -- which is why they are movable now, ahead
of the render / write_html / write_gallery cluster that *does* reach back to `_load_basemap`
(Phase 1.6).  Each has no back-edge to the monolith; their only external names live in the
already-extracted modules.

**The shared constant (relocated to `trackview/rendering.py`, re-imported by the monolith):**
- `DPI` -- the fixed 150-DPI figure save-resolution, shared by *every* rendered figure: the not-
  yet-migrated render / write_html / write_gallery cluster *and* these two new clusters.  Because
  it is read by both a staying cluster and the moving ones it cannot go private to either, so it
  sits with the other figure constants (CMAPEED / HEAT_*) in `rendering.py` and the monolith
  re-imports it (Phase 1.5d-i)

**Functions / names to extract:**
- `_calendar_days` -- the rides bucketed by calendar year then weekday (the 7 x weeks grid data;
  private: only write_calendar calls it)
- `_month_ticks` -- the month-boundary tick positions + labels for the calendar x-axis (private)
- `write_calendar` -- the GitHub-style contribution grid, one 7 x weeks block per calendar year
  each day coloured by that day's total of the chosen metric; the one name `main` calls
- `_CALENDAR_METRICS` -- the {metric-key: (ylabel, cmap)} table behind --calendar-by; `main`'s
  argparse reads `list(_CALENDAR_METRICS)` for the choices, so it stays in the module *and* is
  re-imported by the monolith (the only re-import besides write_calendar)
- `_trend_panels` -- the --trend chart's per-metric panels over ride date (distance / gain /
  duration, plus a calories panel when any ride carries a power average; private)
- `_TREND_COLORS` -- the panel colour ramp (private, module-local)
- `write_trend` -- the multi-panel training-trend figure; the one name `main` calls

**Implementation:**
1. ✅ Relocate the shared `DPI` constant into `trackview/rendering.py` (its figure-constant home,
   with CMAPEED / HEAT_*) and re-import it into the monolith, so both the staying render cluster
   and the moving trend / calendar clusters read it there -- the byte-identical literal (Phase
     1.5d-i, 2026-09-30)
2. ✅ Extract `_calendar_days` / `_month_ticks` / `write_calendar` (+ the `_CALENDAR_METRICS`
   table) into `trackview/calendar.py` byte-for-byte -- a 131-line cluster verified identical to
   the old monolith -- adding the `helpers` (_ride_date, _MONTH_ABBR) and `rendering` (DPI)
   imports plus `numpy` / `matplotlib.pyplot` / `matplotlib.colors.Normalize`; re-import
   `write_calendar` *and* `_CALENDAR_METRICS` (the latter feeds `main`'s --calendar-by choices)
     (Phase 1.5d-ii, 2026-09-30)
3. ✅ Extract `_trend_panels` / `_TREND_COLORS` / `write_trend` into `trackview/trend.py` byte-
   for-byte -- a 71-line cluster verified identical -- adding the `helpers` (_ride_date),
   `metrics` (_track_calories) and `rendering` (DPI) imports plus `matplotlib.dates`; re-import
   `write_trend` (the one name `main` calls; `_trend_panels` / `_TREND_COLORS` stay private)
     (Phase 1.5d-iii, 2026-09-30)
4. ✅ No test changes: none of the clusters' names is test-referenced, so the bridge needs no
   re-pointing -- the re-imported `write_trend` / `write_calendar` / `_CALENDAR_METRICS` / `DPI`
   resolve through the bridge as before (2026-09-30)
5. ✅ Run test suite -- 101 passed, 1 deselected, no regressions (2026-09-30)

**Done (2026-09-30)**. `trackview/calendar.py` and `trackview/trend.py` now hold the calendar
and trend figure clusters, copied byte-for-byte out of the monolith so behaviour is unchanged.
Only `write_calendar` and `write_trend` are still called by `main`, so they are re-imported;
`_CALENDAR_METRICS` is re-imported too (it feeds the --calendar-by argparse choices), while the
internal `_calendar_days` / `_month_ticks` / `_trend_panels` / `_TREND_COLORS` stay private.
Because `DPI` is shared with the not-yet-migrated render / write_html / write_gallery cluster it
was first relocated to `trackview/rendering` (the figure-constant home) and re-imported by the
monolith, keeping both new modules back-edge-free -- the same discipline as 1.5a / 1.5b / 1.5c /
1.4b-i.  No test changes were needed.  This closes out the remaining report clusters of Phase
1.5; next up Phase 1.6 (I/O: HTML / Leaflet, the gallery, and the `_load_basemap` helper that
blocks the 1.4b-ii render / write_* figure cluster).

---

### Revised Phase 1.6: I/O Module (done)

The I/O leaf clusters -- the tile / basemap machinery, the HTML / Leaflet export and the gallery contact
sheet -- on the same leaf-first principle as 1.5a / 1.5b / 1.5c / 1.5d, all into a new
`trackview/io.py`.  They are the network-coupled half (the contextily basemap, an HTTP fetch of the
Leaflet library, the gallery's per-ride basemap), so they write only with a basemap -- which is why the
standalone report clusters (1.5) moved *first*.  Each moved block keeps no back-edge to the monolith:
its external names live in the already-extracted modules (helpers / metrics / rendering) plus stdlib /
contextily / matplotlib.

**The shared constants (relocated to `trackview/rendering.py`, re-imported by the monolith):**
- `STRONG_COLORS` + `PAD_FRAC` -- the per-track colour ramp and the bbox blank-margin fraction, read by
   *both* the not-yet-migrated render / write_gallery figure cluster and the moving basemap / gallery code,
  so they sit with the other figure constants (CMAPEED / HEAT_* / DPI) in `rendering.py` and the monolith
  re-imports them (Phase 1.6-iii)

**Names to extract into `trackview/io.py`:**
- `USER_AGENT`, `SOURCES`, `ATTRIBUTION` -- the tile-provider table (one {z}/{x}/{y} URL + one credit per
  source) and the polite User-Agent string every fetch carries; private to the I/O module, but re-imported
  because `main` reads `SOURCES` for its --style choices (Phase 1.6-i)
- `_load_basemap` -- the contextily basemap fetch with provider fail-over, retry/backoff and a variance
  blank-check; the one network helper the figure cluster was blocked on, so it moves first (Phase 1.6-ii;
  the now-unused `import time` stays *here*, in io.py, not the monolith)
- the HTML / Leaflet export cluster -- `_APP_JS`, `_fetch_text`, `_load_leaflet`, `_ride_feature`,
   `_tracks_geojson`, `_leaflet_document`, `_html_escape`, `write_html` (a static HTML + a ride GeoJSON,
  optionally inlining the Leaflet library); the only name `main` calls (Phase 1.6-iv).   `LEAFLET_DIR` is
   `__file__`-relative, so it is relocated to the repo's `lib/` via the package's own parent -- the depth
  adjusts: the monolith's `Path(__file__).parent / "lib"` becomes `Path(__file__).parent.parent / "lib"`
  read from `io.py`)
- the gallery + tile-detail unit -- `choose_detail` (the auto tile-detail level from the bbox) with its
   `EQUATOR` / `DETAIL_MIN` / `DETAIL_MAX` constants, plus `_gallery_grid` / `_gallery_cell` / `write_gallery`
   (a contact sheet of the N most-recent rides); the only name `main` calls is `write_gallery`, and the
   `render` cluster still calls `choose_detail` (Phase 1.6-v; the now-unused `import math` stays *here* in
  io.py -- `choose_detail` uses `math.log2`, `_gallery_grid` uses `math.ceil` / `sqrt`)

**Implementation:**
1. ✅ Relocate the tile / HTTP provider constants (`USER_AGENT` / `SOURCES` / `ATTRIBUTION`) into
   `trackview/io.py` -- a new 34-line module, byte-identical -- and re-import them (the monolith reads
   `SOURCES` for --style; `USER_AGENT` / `ATTRIBUTION` travel with the provider table) (Phase 1.6-i,
    2026-09-30)
2. ✅ Extract `_load_basemap` into `trackview/io.py` byte-for-byte -- the contextily fetch with provider
   fail-over + retry/backoff + a variance blank-check -- importing `contextily` / `numpy` / `time` and the
   three provider constants now in-module; the monolith drops its now-unused `import time` (Phase 1.6-ii,
    2026-09-30)
3. ✅ Relocate the shared `STRONG_COLORS` + `PAD_FRAC` constants into `trackview/rendering.py` -- their
   figure-constant home, alongside CMAPEED / HEAT_* / DPI -- and re-import them into the monolith, so both
   the staying render cluster and the moving gallery read them there (Phase 1.6-iii, 2026-09-30)
4. ✅ Extract the HTML / Leaflet export cluster (`_APP_JS` / `_fetch_text` / `_load_leaflet` /
   `_ride_feature` / `_tracks_geojson` / `_leaflet_document` / `_html_escape` / `write_html` +
   `LEAFLET_DIR`) into `trackview/io.py` byte-for-byte, relocating `LEAFLET_DIR` to
   `Path(__file__).parent.parent / "lib"` so it still resolves to the repo's `lib/` from the new depth;
   re-import `write_html` (the one `main` calls; the rest stay private) (Phase 1.6-iv, 2026-09-30)
5. ✅ Extract the gallery + tile-detail unit (`choose_detail` + `EQUATOR` / `DETAIL_MIN` / `DETAIL_MAX`, and
   `_gallery_grid` / `_gallery_cell` / `write_gallery`) into `trackview/io.py` byte-for-byte, adding the
   `rendering` (STRONG_COLORS / PAD_FRAC / DPI) and `helpers` (_title_name / _ride_date) imports plus
   `math` / `numpy` / `matplotlib`; re-import `write_gallery` (the one `main` calls) and `choose_detail` /
   `DETAIL_MIN` / `DETAIL_MAX` (`render` still calls `choose_detail`, and its help string names the detail
   caps); `EQUATOR` / `_gallery_grid` / `_gallery_cell` stay private, and the monolith drops its now-unused
   `import math` (Phase 1.6-v, 2026-09-30)
6. ✅ No test changes: none of the I/O names is test-referenced, so the re-imported `write_html` /
   `write_gallery` / `choose_detail` / `DETAIL_MIN` / `DETAIL_MAX` / `STRONG_COLORS` / `PAD_FRAC` / `SOURCES`
   / `USER_AGENT` / `ATTRIBUTION` / `_load_basemap` resolve through the bridge as before (2026-09-30)
7. ✅ Run test suite -- 101 passed, 1 deselected, no regressions (2026-09-30)

**Done (2026-09-30)**. `trackview/io.py` now holds the tile / basemap machinery, the HTML / Leaflet
export and the gallery contact sheet, copied byte-for-byte out of the monolith so behaviour is unchanged;
`STRONG_COLORS` + `PAD_FRAC` joined the other figure constants in `trackview/rendering.py`.  The basemap
helper (`_load_basemap`) was the last network back-edge the figure cluster needed, so it moved first --
unblocking the 1.4b-ii render / `write_*` figure-orchestration cluster, the only monolith back-edge left.
 Re-imported by the monolith are the names its staying code still touches (`write_html`, `write_gallery`,
`choose_detail`, `DETAIL_MIN` / `DETAIL_MAX`, `STRONG_COLORS` / `PAD_FRAC`, and the provider table
`USER_AGENT` / `SOURCES` / `ATTRIBUTION` / `_load_basemap`); the internal `_gallery_grid` / `_gallery_cell`
/ `EQUATOR` and the HTML helpers stay private.  No test changes were needed.  Next up: the 1.4b-ii render
/ `write_*` figure-orchestration cluster (now back-edge-free, since `_load_basemap` moved) and -- once
every module has moved -- deleting the re-export bridge.

### Revised Phase 1.4b-ii: Figure-Orchestration Module (done)

The last monolith back-edge the figure cluster was blocked on -- `_load_basemap` -- moved to
`trackview/io.py` in Phase 1.6, so the big `render` / `render_*` / `write_*` figure-orchestration cluster
can finally move.  It is the top of the figure dependency tree, so it lands in a *new* module
`trackview/mapfig.py` rather than in `trackview/rendering.py`: it imports the drawing leaves from
`rendering`, the basemap / tile machinery from `io`, and the small metric helpers from `metrics` /
`helpers` -- none of which import back, so there is no cycle -- whereas `rendering` is already imported,
transitively, by `io` (a `rendering` -> `io` -> `rendering` cycle would result).

**Names to extract into `trackview/mapfig.py`:**
- the figure constants -- `FIGURE_IN` (the square figure size), the `CMAPEL` / `GRADE_STOPS` / `CMAPGRADE`
    colour ramps and the `--profile` `PROF_METRICS` table -- the constants that belong to the map figure
- `fit_aspect` -- the bbox-aspect helper (fit a Mercator bbox into a square figure with the right margins)
- `render` -- the orchestrator that builds and saves a ride map (plus its `--profile` ride-card and
    `--heat` overlay); the only figure-cluster name `main` calls (alongside the `write_*` exporters)

**Implementation:**
1. ✅ Copy the figure constants + `fit_aspect` + `render` byte-for-byte into a new `trackview/mapfig.py`,
    importing the drawing leaves (`PAD_FRAC` / `DPI` / `CMAPEED` / `GRADE_CBAR_MAX` / `STRONG_COLORS` /
     `_metric_norm` / `_draw_profile` / `_has_metric_pts` / ...) from `trackview.rendering`, the basemap /
    tile machinery (`SOURCES` / `_load_basemap` / `ATTRIBUTION` / `choose_detail`) from `trackview.io`, and
    the small metric helpers (`_metric_avg` / `_grade_cap` / `_calories_burned` / `_fmt_duration`) from
     `trackview.metrics` + `_short_label` / `_title_name` from `trackview.helpers`; the three moved blocks
    are each verified byte-identical to the old monolith (Phase 1.4b-ii, 2026-09-30)
2. ✅ Re-point the monolith at the new module -- `from trackview.mapfig import (render, PROF_METRICS)` -- and
    prune the imports the move orphans: `import numpy as np` and the seven matplotlib sub-imports (the
     `import matplotlib` + `use("Agg")` backend guard stays, so headless figures still render), plus the
    now-unused `_short_label` / `_metric_avg` / `_grade_cap` / `_calories_burned` / `_fmt_duration` /
     `ATTRIBUTION` / `_load_basemap` / `choose_detail` re-imports (`render` is the only caller left of
     `choose_detail` / `_load_basemap`, and it now lives in `mapfig`) (Phase 1.4b-ii, 2026-09-30)
3. ✅ Re-point `test_geometry`'s `tv._grade_cap` / `tv._moving_avg` to their new submodules
     (`trackview.metrics` / `trackview.rendering`) -- the bridge no longer mirrors the pruned names (Phase
     1.4b-ii, 2026-09-30)
4. ✅ Run test suite -- 101 passed, 1 deselected, no regressions (2026-09-30)

**Done (2026-09-30)**. `trackview/mapfig.py` now holds the figure constants, `fit_aspect` and the `render`
orchestrator, copied byte-for-byte out of the monolith so behaviour is unchanged; it is the top of the
figure dependency tree (importing the leaves from `rendering`, the basemap from `io`, the metric helpers
from `metrics` / `helpers` -- none import back), which is why the map figure lands in a fresh module rather
than in `rendering` (already imported, transitively, by `io`).  Only `render` + `PROF_METRICS` are
re-imported (the two `main` still touches); the move orphans the monolith's now-unused numpy / matplotlib
imports (the backend guard stays) and the `_short_label` / `_metric_avg` / `_grade_cap` / `_calories_burned`
/ `_fmt_duration` / `ATTRIBUTION` / `_load_basemap` / `choose_detail` re-imports.  With this, every
*report* and *figure* cluster has moved into `trackview/`; the monolith is down to the config constants,
the `load_tracks` GPX loader (now back-edge-free -- the next leaf to extract), and the `main` entry point,
after which the re-export bridge can go.


### Revised Phase 1.7: GPX Loader Module (done)

`load_tracks` was the last non-entry-point function in the monolith, and it is now back-edge-free: its only
dependencies -- `latlon_to_merc` / `decimate` / `_distance_and_gain` / `_grade_and_cumkm` from
`trackview.geometry`, `_device_type` / `_sport_type` from `trackview.helpers`, and `_point_telemetry` from
`trackview.metrics` -- are all extracted leaves, so it lands in a new top-of-tree `trackview/load.py` rather
than being appended to `trackview/io` (which already imports `rendering` and would only lengthen the chain);
a fresh module keeps the single reader self-contained.

**Names to extract into `trackview/load.py`:**
- `load_tracks` -- the one GPX reader: it parses each caller-discovered-and-filtered `.gpx` file with gpxpy,
    merges its track segments into one polyline, decimates by `decimate_m`, and -- over the pre-decimation
    samples -- accumulates the Wahoo `--ext` per-point telemetry arrays (`power_pts` / `speed_pts`), the
    `[sum, count]` telemetry dict, and the ride's first->last timestamp span (its duration, feeding the
    calories-burned estimate); the only reader `main` calls

**Implementation:**
1. ✅ Copy `load_tracks` byte-for-byte into a new `trackview/load.py`, importing its leaves
    (`latlon_to_merc` / `decimate` / `_distance_and_gain` / `_grade_and_cumkm` from `trackview.geometry`,
      `_device_type` / `_sport_type` from `trackview.helpers`, `_point_telemetry` from `trackview.metrics`) --
    so it has no back-edge to the monolith; verified byte-identical to the old monolith and acyclic (Phase
    1.7, 2026-09-30)
2. ✅ Re-point the monolith at the new module -- `from trackview.load import load_tracks` -- and prune the
    imports the move orphans: `import os` + `import gpxpy`, the now-fully-dead `from trackview.geometry
    import (...)` line and `from trackview.metrics import (...)` block (both are reached only *through* the
      moved reader), plus `_device_type` / `_sport_type` from the helpers re-import -- `load_tracks` is the
    only caller of all six, and it now lives in `load` (Phase 1.7, 2026-09-30)
3. ✅ Re-point `test_load_tracks`'s `tv._distance_and_gain` / `tv._grade_and_cumkm` to `trackview.geometry` --
    pruning the geometry import stops the bridge from mirroring them, but two tests still reach those names
      via `tv.`; the nine `tv.load_tracks` refs need no change because `main` still re-imports the name
    (Phase 1.7, 2026-09-30)
4. ✅ Run test suite -- 101 passed, 1 deselected, no regressions (2026-09-30)

**Done (2026-09-30)**. `trackview/load.py` now holds `load_tracks`, the GPX reader, copied byte-for-byte out
of the monolith so behaviour is unchanged; it is back-edge-free (importing only the extracted leaves
`geometry` / `helpers` / `metrics`, none of which import back), which is why it lands in a fresh top-of-tree
module rather than in `io` (already transitively importing `rendering`).  Only `load_tracks` is re-imported
(the one name `main` still touches), and the move orphans the monolith's now-unused `os` / `gpxpy` / geometry
/ metrics imports (and the `_device_type` / `_sport_type` helpers re-import).  With this the monolith is down
to the config constants, the `main` entry point, and the re-export bridge -- the last three leaves of Phase 1.

### Revised Phase 3.1: Configuration Module (done)

The config constants were the next leaf: the monolith's `# ---- configuration ----` block (`GPX_DIR` /
`OUTPUT_DIR` / `STATS_DIR` / `TILE_CACHE_DIR` / `DECIMATE_M` / `PI_R`) is the top of the dependency order --
consumed by `main` but importing nothing internal -- so it lands in a new pure-leaf `trackview/config.py`
(only `__future__` + `pathlib`).  The values are byte-value-identical, with the one deliberate exception that
`__file__` sits one level deeper inside the package, so the paths use `.parent.parent` to resolve the *same*
repo root (`gpx` / `output` / `stats` / `tiles`) the monolith did; `DECIMATE_M` and `PI_R` are byte-identical.

**Names to extract into `trackview/config.py`:**
- `GPX_DIR` / `OUTPUT_DIR` / `STATS_DIR` / `TILE_CACHE_DIR` -- the four path roots, resolved to the repo root
    via `.parent.parent` (the monolith's `.parent`, one level shallower)
- `DECIMATE_M` -- the 5.0 m decimation threshold, copied verbatim with its comment
- `PI_R` -- `20037508.342789244` (`pi*R`, the Web-Mercator scale), moved verbatim; it is now a *dead* constant
    -- the monolith no longer touches it -- so it is the documented home but is **not** re-imported

**Implementation:**
1. ✅ Copy the `# ---- configuration ----` block byte-value-equivalent into a new `trackview/config.py` -- the
     four path roots with the one-level `__file__` shift (`.parent.parent`) and `DECIMATE_M` / `PI_R`
     verbatim -- importing only `__future__` + `pathlib`, so it is a pure leaf with no back-edge (Phase 3.1,
       2026-09-30)
2. ✅ Re-import the five *live* constants (`GPX_DIR` / `OUTPUT_DIR` / `STATS_DIR` / `TILE_CACHE_DIR` /
       `DECIMATE_M`) into the monolith and prune the `# ---- configuration ----` section; `PI_R` is the only
     dead one, so it moves to `config.py` but is **not** re-imported (no orphan re-import) (Phase 3.1,
       2026-09-30)
3. ✅ Run test suite -- 101 passed, 1 deselected, no regressions (2026-09-30)

**Done (2026-09-30)**. `trackview/config.py` now holds the configuration, copied value-for-value out of the
monolith so behaviour is unchanged; the one deviation is the `__file__` depth (`.parent.parent` instead of
`.parent`), which resolves the *same* repo-root paths.  The five constants `main` still touches are
re-imported, so the bridge keeps mirroring them and `tv.OUTPUT_DIR` / `tv.STATS_DIR` (which
`conftest.run_main` monkeypatches) keep working untouched; `PI_R` -- now dead -- moves over but is not
re-imported, the move's only true orphan.  With this the monolith is down to just the `main` entry point and
the re-export bridge -- the last two leaves of Phase 1.

### Revised Phase 3.1 (cont.): CLI / `main` Entry Point (done)

The `main` entry point was the next -- and, within Phase 1, the last-but-one -- leaf: it is the *orchestrator*,
the only in-module consumer of nearly every extracted leaf (the config constants, `load_tracks`, `render`,
the helpers, the `write_*` writers), so it lands in a new `trackview/cli.py`.  `main` travels out with the
stdlib it consumed -- `argparse`, `from datetime import date`, `from pathlib import Path`, the
`import contextily as cx`, and the headless `import matplotlib` + `matplotlib.use("Agg")` guard (a module-level
side effect that must run before the first figure, now placed in `cli.py` *before* the `from
trackview.mapfig / ...` imports that pull in matplotlib) -- leaving the monolith a thin re-export shell.

**Design -- the re-imports stay, to feed the bridge.**  The move is *not* a full de-import: `main` was the only
*in-module* user of the `from trackview.* import (...)` leaf re-imports, so on their face they look orphaned --
but the re-export bridge (`trackview/__init__.py`) mirrors the monolith's namespace, and the test suite still
reaches ~7 of those names via `tv.` (`load_tracks`, `render`, `_list_rides`, `_parse_argdate`, `_ride_date`,
`_filter_by_meta`, `_select_top`, plus `GPX_DIR` / `OUTPUT_DIR` / `STATS_DIR`, which `conftest.run_main`
monkeypatches).  So the monolith **keeps every `from trackview.* import (...)` line** -- they now exist purely to
keep the bridge mirroring those names -- and gains one line, `from trackview.cli import main`.  Pruning the now
bridge-only re-imports (and deleting the bridge itself) is the *following* leaf, once the ~7 `tv.<name>` test
refs are re-pointed at their submodules.

**Names to extract into `trackview/cli.py`:**
- `main` -- the whole CLI entry point, copied byte-for-byte (its `def main() -> None:` signature + body are
    identical across the two files; `argparse` / `contextily` / `date` / `Path` / the matplotlib `Agg` guard
    travel with it as its own stdlib imports)

**Implementation:**
1. ✅ Copy `main` byte-for-byte into a new `trackview/cli.py` -- its own docstring + the stdlib imports it
     consumed (`argparse` / `contextily as cx` / `date` / `Path` + the `matplotlib.use("Agg")` guard, placed
     before the `trackview.mapfig / ...` re-imports so the backend is set first) + the leaf re-imports it uses;
     `cli.py` imports only already-extracted leaves + stdlib, so it is acyclic with no back-edge to the monolith
     (Phase 3.1, 2026-09-30)
2. ✅ Re-import `main` into the monolith (`from trackview.cli import main`) and prune the stdlib the move
    orphans -- `argparse` / `date` / `Path` / `contextily as cx` + the matplotlib guard -- while **keeping** the
     `from trackview.* import (...)` leaf re-imports (now bridge-serving) and the pre-existing-dead
     `import csv` / `import re` (a separate cleanup) (Phase 3.1, 2026-09-30)
3. ✅ Run test suite -- 101 passed, 1 deselected; the bridge still mirrors `main` (resolving to
     `trackview.cli`) and every leaf name; `python trackview.py --list` runs end-to-end through the moved
     entry point (2026-09-30)

**Done (2026-09-30)**. `trackview/cli.py` now holds `main`, copied byte-for-byte so behaviour is unchanged
(`main()` is byte- and AST-identical in both files; `cli.py` is back-edge-free, importing only the extracted
leaves + stdlib); the monolith is down to its docstring, a `from trackview.cli import main`, the
`from trackview.* import (...)` re-imports that now feed the bridge, and the `__main__` guard.  The move
orphaned only the stdlib `main` consumed (pruned); the leaf re-imports stay because the bridge keeps mirroring
the ~7 names the test suite reaches via `tv.` -- so the bridge stays, and deleting it is the final leaf, once
those test refs are re-pointed at their submodules.
### Revised Phase 3.1 (cont.): Bridge Deletion (done)

The re-export bridge was the *final* leaf of Phase 1: the moment `main` moved out, `trackview/__init__.py` was the
last thing still pulling the monolith back into life -- it loaded `../trackview.py` as a private `trackview._main`
module via `importlib` and mirrored its non-dunder namespace, so the test suite could still reach the extracted leaves
as `tv.<name>` while the monolith re-imported them.   Three things had to move first, in order, before the bridge could
go.

**Step (a) -- re-point the ~7 `tv.<name>` test refs at their submodules.**  The suite no longer reaches a leaf through
the bridge; it imports each from where it now lives -- `load_tracks` -> `trackview.load`, `render` ->
`trackview.mapfig`, `main` -> `trackview.cli`, and the helpers (`_list_rides` / `_parse_argdate` / `_ride_date` /
`_filter_by_meta` / `_select_top`, plus `GPX_DIR` / `OUTPUT_DIR` / `STATS_DIR` that `run_main` monkeypatches) ->
`trackview.helpers`.   This spans `conftest` (the shared `run_main` + helpers) and the 6 test files --
`test_dry_run` / `test_filters` / `test_geometry` / `test_load_tracks` / `test_parse_helpers` / `test_render_smoke`.

**Step (b) -- prune the now-bridge-only monolith re-imports.**  With no `tv.` consumer left, the `from trackview.*
import (...)` leaf re-imports in `trackview.py` exist for nothing; they are deleted, leaving the monolith a thin CLI:
its docstring, `from __future__ import annotations`, the (pre-existing-dead) `import csv` / `import re`, a
`from trackview.cli import main`, and the `if __name__ == "__main__": main()` guard.

**Step (c) -- delete the bridge.**    `trackview/__init__.py` -- the `importlib` monolith mirror -- is replaced by an
*empty* init.   An empty file, **not** a missing one: a 0-byte init keeps `trackview` a regular package the submodules
import directly (`from trackview.cli import main`, `from trackview.load import load_tracks`, ...); a deleted init would
make Python treat the directory as a non-package and break those submodule imports.   No monolith names are re-exported
any more -- `import trackview; hasattr(trackview, "load_tracks")` is `False`.

**Names to re-point / prune / delete:**
- the ~7 `tv.<name>` refs (across `conftest` + 6 test files) -> their submodules (`load` / `mapfig` / `helpers` / `cli`)
- the monolith `from trackview.* import (...)` leaf re-imports -> pruned (no `tv.` consumer left)
- `trackview/__init__.py` (the `importlib` mirror) -> replaced by an empty init

**Implementation:**
1. ✅ Re-point the ~7 `tv.<name>` refs at their submodules across `conftest` + the 6 test files (the only bridge consumer, `conftest.run_main`, and the helpers it pulls in) (Phase 1, 2026-09-30)
2. ✅ Prune the now-bridge-only `from trackview.* import (...)` leaf re-imports out of `trackview.py`, leaving the
    thin CLI (docstring + `from __future__ import annotations` + `from trackview.cli import main` + the `__main__`
    guard; the pre-existing-dead `import csv` / `import re` stay, a separate cleanup) (Phase 1, 2026-09-30)
3. ✅ Replace `trackview/__init__.py` -- the `importlib` monolith mirror -- with an *empty* init, so `trackview` is a
    regular package the submodules import directly, with no monolith names re-exported (Phase 1, 2026-09-30)
4. ✅ Run test suite -- 101 passed, 1 deselected; `import trackview` resolves, every submodule imports, and no monolith
    name is re-exported (2026-09-30)

**Done (2026-09-30) -- Phase 1 complete.**  The re-export bridge is gone: `trackview/__init__.py` is now a 0-byte init
(a regular package, no monolith mirror), the ~7 `tv.<name>` test refs read their leaves straight from
`trackview.load` / `trackview.mapfig` / `trackview.helpers` / `trackview.cli`, and `trackview.py` is a thin CLI -- its
docstring, `from trackview.cli import main`, the `__main__` guard, and the (pre-existing-dead) `import csv` /
`import re`.  With the bridge deleted there is no path left by which the monolith is pulled into the package, so the
Monolith -> Package refactor (item [32]) closes.

---

**Phase 4 / 4.1 -- report-builder unit tests + the `_ride_climbs` end-point fix (done, 2026-09-30).**
The report modules that had no test file each get a pure, offline test module:
`tests/test_calendar.py` (10), `tests/test_trend.py` (8), `tests/test_summary.py` (6),
`tests/test_climbs.py` (9), `tests/test_stats.py` (19).  Each tests the module's pure leaf
over hand-built per-ride arrays / dicts (no GPX, no network, no figure).  The climbs leaf
surfaced a real off-by-one in `trackview/climbs._ride_climbs` -- a run reaching the ride's
last sample indexed a phantom `n`-th point (`cum[k + 1]` et al., when the last valid index
is `n - 1`) and crashed `IndexError`; clamped to `e = min(k + 1, n - 1)`, verified
behaviour-preserving (0 differing climbs / 0 crashes across 40 rides).  The stats leaf
(`_stats_columns` / `write_stats` / `write_csv`) built bare ride dicts and asserted the
shared column list (the `--ext` block spliced in only under `show_ext`), the per-device
Summary totals, and the CSV's decimal-normalisation + `;`/`,` delimiter -- no source change.
A `helpers` leaf (`tests/test_helpers.py`, 30 tests) then covered the metadata / grouping /
naming leaves not yet tested -- `_device_type` / `_sport_type` / `_device_label` /
`_device_groups` / `_match_meta` / `_top_key` / `_safe_filename` / `_short_label` -- and
exposed a doc drift (`_match_meta`'s docstring said "whitespace-trimmed" but the
`casefold()` compare is exact; the docstring was corrected to "exact, case-insensitive
match").  An `io` leaf (`tests/test_io.py`, 17 tests) then covered the `--html` / Leaflet
writers (`_html_escape` / `_ride_feature` / `_tracks_geojson` / `_leaflet_document` /
`_load_leaflet` / `write_html`) over hand-built ride dicts, driven through the `inline=False`
CDN path so the suite stays offline (the "mock external dependencies" task -- the library
is never fetched); no source change.  A `mapfig` geometry leaf (`tests/test_mapfig.py`,
6 tests) then covered `fit_aspect` -- the one pure, figure-free helper in the render
module (it grows a bbox to the figure's aspect so the map stays un-letterboxed); no
source change.  A final `config` leaf (`tests/test_config.py`, 5 tests) then closed out the
last pure-constants module: it locks the run-time directory layout and the two magic numbers
-- the four dirs share one repo-root parent (the `gpx` / `output` / `stats` / `tiles` names)
and `DECIMATE_M` / `PI_R` hold their values -- guarding the one value-affecting edit the
constants made when they moved from the repo-root monolith, the one-level `.parent.parent`
shift that keeps the dirs resolving to the repo root.  The `load` reader needs no dedicated
file: its single `load_tracks` is already covered by `test_load_tracks`.  No source change.
Every pure module now carries a dedicated offline test; the only remaining modules -- the
`cli` wiring (`test_dry_run`'s `run_main`) and the heavy `mapfig.render` (the
`@pytest.mark.slow` figure path) -- carry no pure leaf worth a standalone file.  Offline
suite: **211 passed, 1 deselected.**

---

**Last Updated**: 2026-10-18
**Status**: **Phase 1 complete; Phase 4/4.1 closed for the pure leaves; Phase 5 (docs)
closed -- every module and function carries a docstring, the 0-byte `__init__.py` gained a
package docstring, and a top-level `API.md` catalogs the module map (the "(Ongoing)" labels
on the phase heading and the Timeline Estimate were corrected to "closed"); Phase 6 (build
system) closed -- the build config lives in `pyproject.toml` (PEP 518/621: metadata + deps +
the `trackview = trackview.cli:main` console entry point), verified by a real PEP 517 build
(a clean wheel shipping only `trackview/`).  Phase 2 (class structure) is *not*
implemented -- decided 2026-10-18: the functional dict + free-function design is the chosen
final form (reasons in the Phase 2 section).  Phase 4/4.1 closed for the pure leaves (every pure module
now carries a dedicated offline test: the report builders, the helpers, the `--html` /
Leaflet export, the map-figure aspect helper, and the config constants -- `cli` stays
integration-covered via `run_main`, `mapfig.render` is the `slow` figure path).**
The monolith-to-package refactor (item [32]) is closed (bridge deleted, 0-byte init, thin
CLI).  Phase 4/4.1 has added pure, offline unit tests for every previously-untested pure
module -- the five report builders `calendar` / `trend` / `summary` / `climbs` / `stats`
(`tests/test_calendar.py` / `test_trend.py` / `test_summary.py` / `test_climbs.py` /
`test_stats.py`, 52 tests), the `helpers` metadata / grouping / naming leaves
(`tests/test_helpers.py`, 30 tests), the `--html` / Leaflet writers (`tests/test_io.py`,
17 tests), the `mapfig` aspect helper `fit_aspect` (`tests/test_mapfig.py`, 6 tests) and the
`config` constants (`tests/test_config.py`, 5 tests -- the four run-time directories share
one repo-root parent and `DECIMATE_M` / `PI_R` hold their values, guarding the one-level
`.parent.parent` shift) -- and fixed two real defects the new tests exposed: the off-by-one
in `trackview/climbs._ride_climbs` (the run end clamps to `e = min(k + 1, n - 1)`) and a
doc drift in `trackview/helpers._match_meta` (the filter is an exact, case-insensitive
`casefold()` match, not "whitespace-trimmed" as its docstring claimed).  The `io` leaf was
driven through the `inline=False` CDN path so the suite stayed offline (the "mock external
dependencies" task -- the Leaflet library is never fetched).  The `load` reader needs no
dedicated file -- its single `load_tracks` is already covered by `test_load_tracks`.
Offline suite: **211 passed, 1 deselected.**  Every pure module now carries a dedicated
offline test; the only modules without a dedicated file -- the `cli` wiring (covered by
`test_dry_run`'s `run_main`) and the heavy `render` orchestrator (the `@pytest.mark.slow`
figure render in `test_render_smoke`) -- carry no pure leaf worth a standalone file.
A closing plan pass (2026-10-18) fixed the two stale "(Ongoing)" status labels -- the
Phase 5 heading and the matching Timeline Estimate entry, now "closed" -- and recorded the
decision *not* to implement Phase 2 (class structure): the functional dict + free-function
design is the chosen final form (no consumer for an object model, it would undo the
Phase 1 stabilisation, and it would churn the fully-tested surface for no new capability),
so no `track.py` / `visualization.py` is created.  This is a documentation / record-keeping
change only -- no code path touched, offline suite unchanged at 211 passed, 1 deselected.
Phase 5.1 (docs) closed the documentation pass (a docstrings-only change, so the offline
suite is unchanged at 211 passed, 1 deselected): the two last functions without one
(`cli.main`, `mapfig.render`) now carry one, the 0-byte `trackview/__init__.py` gained a
short package docstring (still re-exporting nothing), and a new top-level `API.md` catalogs
the module map -- role, constants and functions per module, the programmatic entry points,
the acyclic dependency direction, and a note that the leading-underscore helpers are the
carried-over monolith names that *are* the cross-module API (no `__all__`).  Usage examples
stay in `README.md` (its full **Usage** section), which `API.md` points to.

A post-closure re-analysis pass (2026-10-18) reopened the code for a weaknesses /
best-practice / enhancement review; its shortlist began with **per-file error
isolation in the GPX reader** (a mixed-vendor `gpx/` where one file is corrupt or
missing must not abort the whole run).  `trackview/load.load_tracks` now wraps
`open()` + `gpxpy.parse()` in a `try/except` that catches `OSError` (a missing /
unreadable path) and `gpxpy.gpx.GPXXMLSyntaxException` (a truncated / foreign /
zero-byte .gpx -- gpxpy raises its own exception type, not a builtin, so the old
`ValueError`-style guard would have missed it), printing a
`skip (could not open)` / `skip (not a valid .gpx)` line and `continue`-ing --
mirroring the fit/wahoo converters' skip loop, so one bad file in a mixed-vendor
`gpx/` no longer aborts the run.  No `--strict` flag was added: skip-and-report is
the correct default and matches the converters.  Three regression tests were added
to `tests/test_load_tracks.py` (a malformed file skipped while a good one still
loads; a missing file skipped; an all-corrupt folder returns `[]`), and the module
docstring's "skipped with a note" behaviour is now backed by a test.  Offline
suite: **214 passed, 1 deselected** (was 211; +3 new skip-path tests).

The same pass next **reconciled the orphaned `PI_R` constant** (shortlist A2).  It
had been duplicated -- `config.PI_R` and `geometry.PI_R`, the same literal
`20037508.342789244` -- but only `geometry` ever used it (`latlon_to_merc`'s
`x = lon * PI_R / 180`); `config.PI_R` was imported nowhere (asserted only by a
test).  `geometry` is the live consumer, so it is the single source of truth:
`config.PI_R` was deleted and `config`'s docstring now *points at*
`trackview.geometry` for the Web-Mercator scaling constant (a geometry detail, not
run-time configuration).  The test moved with the value -- the `PI_R` assertion
left `tests/test_config.py` (and that file's docstring dropped "Web-Mercator
scaling constant" from its list) and a new `TestConstants` class in
`tests/test_geometry.py` asserts both the value and that `latlon_to_merc`
consumes it.  Value-identical, so no behaviour changed.  Offline suite:
**215 passed, 1 deselected** (+1 net: +2 geometry, -1 config).

The same pass then **added a linter and a CI gate** (shortlist B1).  ruff now
lints the project sources and a new `.github/workflows/ci.yml` runs two fast,
offline jobs: a `lint` job (`ruff check` over `trackview/`, the two converter
scripts, the root launcher and `tests/`) and a `test` job that runs the pure
suite (`pytest -m "not network and not slow"`) across Python 3.10--3.13.  Only
the pyflakes + syntax rules are gated (`[tool.ruff] select = ["F", "E9"]`); the
codebase keeps a deliberate loose comment-indent style, so the pycodestyle (E/W)
formatting rules are intentionally *not* selected.  `ruff` is a `lint` extra in
`pyproject.toml` (never a runtime dep; CI installs it standalone).  Scanning the
tree first surfaced six genuine findings, all fixed: two vestigial imports in the
root launcher (`csv`, `re` -- it is now a one-line shim to `trackview.cli.main`),
a real `F821` bug (`trackview.mapfig` annotated `out_path: Path` but never
imported `Path`), two dead locals (`total_gain` in `write_gallery`, an unused
`mode` in `test_io`), and an unused `Path` import in `test_fit_to_gpx`.  CI was
validated in a throwaway venv (ruff is not in the main `.venv`, per the
"don't disturb the main .venv" discipline): the bare `ruff check` reads the
`[tool.ruff]` config, the long-line probe confirms E501 is *not* enforced, and
`ci.yml` parses as YAML.  Offline suite: **215 passed, 1 deselected** (the code
fixes are import-cleanup / dead-var removal, so the count is unchanged).


The same pass closed the shortlist with the **converter de-duplication** (A1 /
C6).  `fit_to_gpx.py` and `wahoo_to_gpx.py` each carried a byte-for-byte copy of
the distance / altitude-fill / telemetry-extension / CLI-date helpers *and* the
FIT-side reading helpers -- copied from one into the other over the months, so a
fix to one silently drifted from the other.  A new `trackview/convert.py` now
holds that shared surface once: the four genuinely identical helpers
(`_parse_argdate`, `_distance_and_gain`, `_fill_altitude`, `_add_extensions`),
the FIT-only reading cluster (`_iter_messages`, `_extract_meta`,
`_start_time_of`, `_to_utc`, `_record_altitude`, `_missing_alt`, the
`_device_name` / `_sport_name` reworders and their `_DEVICE_WORDS` /
`_SPORT_WORDS` maps, `ALT_SENTINEL`), and the optional `fitparse` import, guarded
so the module (and `fit_to_gpx`) import even when the `fit` extra is absent.  The
`_fill_altitude` sentinel became caller-supplied (`is_missing`) so one fill
serves both vendors (Wahoo's `0`-m, FIT's `-500`-m).  The two top-level scripts
are now thin: they import the shared helpers, keep only their own
vendor-specific `ride_to_gpx` / `main` and their own `_ride_date` (the Wahoo and
Garmin filename schemes differ), and re-export the shared names so
`import *_to_gpx` and `python *_to_gpx.py` are unchanged.  `helpers._parse_argdate`
(the third copy, imported by `cli` / `conftest` / `test_parse_helpers`) is now a
re-export of `convert._parse_argdate`.  Two things were deliberately kept
separate: the converters' *raw* per-segment `_distance_and_gain` (sums every
rising segment; it feeds the GPX `<desc>` / metadata the converter prints) was
left distinct from `geometry._distance_and_gain` (climb-aware, what the map /
ride-log / climb ranking read) -- a Python check confirmed the two are *not*
equivalent, so unifying them would have changed output.  `pyproject.toml` gained
the two new console entry points (`fit-to-gpx`, `wahoo-to-gpx`) and
`py-modules = ["fit_to_gpx", "wahoo_to_gpx"]` so they ship alongside the
`trackview` package.  Behaviour-preserving, so the offline suite is unchanged at
**215 passed, 1 deselected**; `ruff check` stays clean; and the entry points
resolve after `pip install -e .` (verified in a throwaway venv, including
`fit-to-gpx` running without the `fit` extra, confirming the guard).

The same pass **folded versioning into the config module and added a `--version`
switch** (a Phase-3 closeout).  `trackview/config.py` -- the run-time config home
(the four directories + `DECIMATE_M`) -- gained `__version__ = "0.1.0"` as the
package version's *single source of truth*.  To keep it the only copy,
`pyproject.toml`'s static `version = "0.1.0"` was replaced by a dynamic read:
`[project].dynamic = ["version"]` + `[tool.setuptools.dynamic] version = {attr =
"trackview.config.__version__"}`, so setuptools imports just `trackview.config`
(which touches only the stdlib `pathlib` -- its `__init__.py` re-exports nothing,
so the build needs none of the heavy runtime deps) to stamp the wheel/sdist
`Version:` -- the build-stamped version and the running program can no longer drift
apart (and neither can `importlib.metadata.version("trackview")` after an install).
The CLI gained a `--version` switch (`action="version"` on the argparse surface in
`trackview.cli:main`, reading the re-exported `__version__` from
`trackview.config`), printing a fully-formed `trackview 0.1.0` line and exiting --
a pure, side-effect-free glance that fetches no basemap and writes nothing,
consistent with `--no-map`'s spirit -- and it is listed first in the `trackview.py`
launcher's usage block and the README's.  A new `TestVersion` class in
`tests/test_config.py` locks the constant to a PEP-440 numeric release tag
(`^\d+(?:\.\d+){0,2}$`) and asserts the CLI reports the same value `config` holds
(so the two can't drift).  Verified: `--version` prints `trackview 0.1.0` both as
`python trackview.py --version` and under the console entry-point name, and a real
PEP 517 `python -m build` in a throwaway venv stamped `Version: 0.1.0` into the
wheel `METADATA` (confirming the dynamic read).  `ruff check` stays clean; the
offline suite is now **217 passed, 1 deselected** (the prior 215 plus the two
`TestVersion` cases).

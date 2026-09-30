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

## Phase 2: Class Structure (Medium Priority)

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

## Phase 5: Documentation (Ongoing)

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
- **Duration**: Ongoing
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
19. 🧳 Next sub-step (Phase 1.4b-ii): the big `render` / `render_*` / `write_*`
    figure *orchestration* cluster -- matplotlib-coupled.  Its only real monolith back-edge
    is `_load_basemap` (the network / contextily basemap plus the config constants); the
    earlier plan's `decimate` / `_load_stats` references are stale -- `decimate` already
    lives in `trackview/geometry.py` (re-imported) and there is no `_load_stats`, so the
    cluster waits for Phase 1.6 to move the basemap helper
20. 🧳 Then Phase 1.5b (the climb / trend / calendar / summary report clusters --
    `_ride_climbs` / `_all_climbs` / `write_climbs`, `_trend_panels` / `write_trend`,
    `_calendar_days` / `_month_ticks` / `write_calendar`, `_summary_groups` /
    `write_summary`) and Phase 1.6 (I/O: HTML / Leaflet, the gallery, and the basemap helper)

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
---

**Last Updated**: 2026-09-30
**Status**: Phase 1.5a (stats / ride-log report module) complete -- 101 tests green; next up Phase 1.4b-ii (the render/write_* orchestration cluster, blocked on the `_load_basemap` basemap helper) and Phase 1.5b (climb / trend / calendar / summary clusters)

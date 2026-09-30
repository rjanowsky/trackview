#!/usr/bin/env python3
"""
trackview - render every GPX track in ./gpx onto a static map image (PNG or PDF).

Pipeline:
    parse GPX (gpxpy) -> decimate points -> fetch raster base map (contextily)
     -> overlay tracks coloured by elevation (matplotlib) -> save PNG or PDF.

Usage:
    python trackview.py                # ./gpx -> ./output/tracks_overview.png
    python trackview.py --format pdf      # write a vector PDF instead of PNG
    python trackview.py --split           # one map file per track (default: all in one)
    python trackview.py --profile --split    # an elevation + grade + telemetry ride card under each map
    python trackview.py --gallery 6                 # tile the N most recent rides into one mosaic contact sheet -> output/ (bare --gallery = 9, a 3x3)
    python trackview.py --style sat    # Esri satellite base map
    python trackview.py --detail 15      # override the auto-chosen detail
    python trackview.py --no-elev      # flat colour instead of elevation shading
    python trackview.py --color-by grade       # shade the route by slope (climbs hot, descents cold)
    python trackview.py --color-by power        # shade by effort (fast/high = hot; needs --ext)
    python trackview.py --heat                   # overlay a 2-D "time on route" density under the routes
    python trackview.py --labels                 # label each route by name + distance (a combined map)
    python trackview.py --ext          # add avg power/speed/cadence/hr/temperature + calories burned (kcal) to the title
    python trackview.py --no-map            # skip the map; just compute the stats + write the stats/ file
    python trackview.py --since 2026-09-08    # only tracks on/after a date (from the .gpx filename)
    python trackview.py --until 2026-09-05    # only tracks on/before a date (from the .gpx filename)
    python trackview.py --today                # a "what did I ride today?" glance: --flat --since <today> (with --list it is a no-fetch glance)
    python trackview.py --device "Wahoo ELEMNT BOLT"    # restrict to one device  (GPX <desc>)
    python trackview.py --sport Bike                    # restrict to one sport    (GPX <desc>)
    python trackview.py --top 10 --by gain              # render/stat only the N highest-gain rides (or --by km/recent)
    python trackview.py --top 5                         # ... or the N most recent (--by default)
    python trackview.py --csv                # also write a CSV ride-log (header + rows, no totals) to stats/
    python trackview.py --csv --csv-delimiter ,    # comma-separated instead of the default ';'
    python trackview.py --sparse               # quiet stdout: skip the per-track stats listing
    python trackview.py --gain-noise 1.5       # ignore GPS vertical jitter (a dip must exceed 1.5 m) when summing ascent
    python trackview.py --climbs 10            # also write a climb ranking (top N by gain x avg grade) to stats/
    python trackview.py --trend                  # a per-ride training-trend chart over ride date -> output/
    python trackview.py --calendar              # a GitHub-style activity grid (km/day) over the year -> output/
    python trackview.py --calendar --calendar-by gain # colour each day by m gain (or 'rides') instead of km
    python trackview.py --calendar --year 2026  # restrict the grid to one calendar year
    python trackview.py --summary               # a year-in-review report (per year/month) -> stats/
    python trackview.py --html                    # a self-contained interactive Leaflet map (inline GeoJSON + a tile layer) -> output/
    python trackview.py --html --html-cdn         # reference Leaflet from a CDN instead of inlining it (a smaller file, needs internet to view)
    python trackview.py --no-scale             # omit the map's lower-right scale bar (on by default)
    python trackview.py --no-cache             # fetch tiles fresh each run (default: cache them under tiles/)
    python trackview.py --flat                 # look for *.gpx only in the input dir (default: recurse into subfolders, e.g. a year/ layout)
    python trackview.py --list                  # list the rides that survive every filter, then stop (no basemap, no image)
    python trackview.py --list --since 2026-09-01 --top 10 --by gain      # preview a filter selection without fetching a basemap
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import time
import urllib.request
from datetime import date
from pathlib import Path

import numpy as np
import gpxpy
import contextily as cx
import matplotlib
matplotlib.use("Agg")                        # headless, no GUI needed
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.colors import Normalize, LinearSegmentedColormap
from matplotlib.lines import Line2D
from matplotlib.patheffects import withStroke as _with_stroke
from matplotlib.ticker import FuncFormatter
import matplotlib.dates as mdates

from trackview.geometry import latlon_to_merc, decimate, _distance_and_gain, _grade_and_cumkm
from trackview.helpers import (_title_name, _ride_date, _device_type, _sport_type,
                               _device_label, _device_groups, _filter_by_meta,
                               _select_top, _list_rides, _parse_argdate,
                               _safe_filename, _short_label, _TOP_BY)

# ------------------------------- configuration -------------------------------
GPX_DIR     = Path(__file__).resolve().parent / "gpx"
OUTPUT_DIR  = Path(__file__).resolve().parent / "output"
STATS_DIR   = Path(__file__).resolve().parent / "stats"
# Basemap tiles are cached to disk under here (contextily's on-disk tile cache,
# keyed by z/x/y per provider), so re-renders and offline runs reuse the downloaded
# tiles instead of refetching them; --no-cache disables it, tiles/ is git-ignored.
TILE_CACHE_DIR = Path(__file__).resolve().parent / "tiles"

DECIMATE_M  = 5.0       # drop track points closer than this (m): keeps the shape,
                        # cuts ~68k points to a few thousand for crisp, fast drawing
PAD_FRAC    = 0.10      # blank margin around the tracks (fraction of bbox)
DPI         = 150
FIGURE_IN   = (11, 11)  # square, so the map image is never letter-boxed
# Colour ramps.  Elevation uses viridis (perceptually uniform: a dark low
# end and a bright high end both read on a pale basemap, unlike the old
# light "terrain").  Grade uses a grey-centred diverging ramp: steep
# descents run blue, steep climbs red, and the 0 % neutral is a visible
# mid-grey (not white), so a flat route stays readable on the map.
CMAPEL = "viridis" # colour ramp for elevation
GRADE_STOPS = [
     "#08306b", "#2171b5", "#6baed6",   # steep -> gentle descent (blue)
     "#9a9a9a",                          # 0 % neutral (grey, stays visible)
     "#f6a895", "#d73027", "#7f0000",    # gentle -> steep climb (red)
]
CMAPGRADE = LinearSegmentedColormap.from_list("grade", GRADE_STOPS)
# A sequential "effort" ramp for the telemetry colourings (--color-by speed/power):
# low = cold/dark, high = hot/bright, perceptually uniform so a rider reads pacing
# and effort at a glance (fast / high power at the hot end).  Paired with the same
# dark under-lay as the grade shading so even the cold low end pops on a pale basemap.
CMAPEED = "inferno"
# The grade norm is capped robustly (a high percentile of |grade|, clamped
# to a floor/ceiling) so a lone GPS-noise spike (e.g. a spurious 20 % blip)
# can't squash the whole ramp to its neutral centre and leave the route
# nearly colourless.  The colourbar shows the capped range.
GRADE_CAP_PCT    = 98.0     # % of segments inside the (capped) colour range
GRADE_CAP_FLOOR = 3.0      # min range: an all-flat ride still shows colour
GRADE_CAP_CEIL   = 15.0     # max range: steeper is rare, clamp the rest
GRADE_CBAR_MAX = 4.0      # max rides that each get their own grade colourbar on a
                              # combined map; beyond it a single shared scale is used (and noted)
GRADE_SMOOTH   = 5.0       # centred moving-average window (segments) for the profile's
                              # per-segment grade line: GPS jitter makes it noisy otherwise
# A "climb" (see _ride_climbs) is a sustained run of segments whose *smoothed* grade stays
# above CLIMB_MIN_GR over at least CLIMB_MIN_LEN of horizontal run; the grade is smoothed
# over CLIMB_SMOOTH segments (as the profile is) so GPS jitter can't break a run.  A climb's
# 'score' (gain x its average grade) ranks a long moderate climb against a short steep one.
CLIMB_MIN_GR    = 4.0         # smoothed grade (%) a segment must clear to count as "climbing"
CLIMB_MIN_LEN    = 250.0      # min horizontal length (m) of a run to count as a climb
CLIMB_SMOOTH     = 9.0        # centred moving-avg window (segments) for the climb grade scan
# The --heat density overlay: a 2-D "time on route" histogram of the routes' points,
# drawn under the lines.  Empty cells are masked to zero (the basemap shows through)
# and the colour is capped at a high percentile, so a single hot cell (a spot ridden
# many times, or a rest stop) can't wash out the rest of the map.
HEAT_GRID         = 300            # cells across the bbox (a HEAT_GRID x HEAT_GRID histogram)
HEAT_CAP_PCT      = 98.0           # colour cap: % of non-empty cells inside the (capped) range
HEAT_ALPHA        = 0.55           # overlay opacity (the route lines stay readable on top)
# The --profile "ride card" adds a slim telemetry mini-panel below the elevation + grade
# silhouette, one per metric the ride carries (its per-point array, aligned with cum_km),
# each on its own strip and colour so a single figure reads like a full ride card.  Order
# and colour are fixed so a card looks the same every time; a panel is skipped when the ride
# carries no value for that metric (a komoot track, or a ride with no HR strap).
PROF_METRICS = [
         ("power_pts",    "Power (W)",      "#d73027"),
         ("speed_pts",    "Speed (km/h)",   "#1f78b4"),
         ("hr_pts",       "HR (bpm)",       "#2a9d8f"),
         ("cadence_pts", "Cadence (rpm)",  "#8c564b"),
]
# Bold, saturated hues used per track when NOT shaded by elevation, so several
# routes stay distinct against a busy basemap (paired with the white halo).
STRONG_COLORS = [
      "#e41a1c",   # red
      "#377eb8",   # blue
      "#4daf4a",   # green
      "#ff7f0e",   # orange
      "#984ea3",   # purple
      "#17becf",   # cyan
      "#a65628",   # brown
      "#f781bf",   # pink
      "#ffff33",   # yellow
      "#999999",   # grey
]
USER_AGENT    = "trackview/1.0 (static GPX->map renderer)"
 # A contact/URL can be appended here (e.g. " ...; contact: you@...") so a
 # a tile provider can reach out about rate-limiting; left blank on purpose
 # rather than ship a dead placeholder address nobody will read.

# Base-map tile providers, tried in order until one loads. OpenStreetMap is the
# default; the others are fallbacks (OpenTopoMap's contours suit MTB/cycling).
SOURCES = {
    "topo":   "https://a.tile.opentopomap.org/{z}/{x}/{y}.png",
    "sat":    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    "terrain":"https://server.arcgisonline.com/ArcGIS/rest/services/World_Terrain_Base/MapServer/tile/{z}/{y}/{x}",
    "osm":    "https://tile.openstreetmap.de/{z}/{x}/{y}.png",
}
ATTRIBUTION = {
    "topo":   "© OpenTopoMap (CC-BY-SA)",
    "sat":    "© Esri, Maxar, Earthstar Geographics",
    "terrain":"© Esri, USGS, NOAA",
    "osm":    "© OpenStreetMap contributors",
}

PI_R      = 20037508.342789244     # pi*R: scales the Web-Mercator x/y projection
EQUATOR   = 40075016.686            # 2*pi*R: equatorial circumference, used for detail
DETAIL_MIN = 10                      # auto-chosen detail never drops below this level
DETAIL_MAX = 16                      # auto-chosen detail never rises past this level
JOULES_PER_KCAL = 4184.0        # 1 dietary "kcal" (as on food labels) = 4184 J
METABOLIC_EFFICIENCY = 0.25     # only ~25% of food energy -> pedal work; rest is heat


# --------------------------------- helpers -----------------------------------


# Wahoo telemetry embedded under <trkpt><extensions> by `wahoo_to_gpx --ext`,
# mapped to the short key trackview averages.  Un-namespaced on purpose (see
# wahoo_to_gpx.py); gpxpy flattens the <extensions> children straight onto a
# trackpoint's .extensions list, so each element's bare .tag is the metric.
_TELE_TAGS = {"power": "power", "speed_kmh": "speed", "cadence": "cadence",
              "heartrate": "hr", "temperature": "temp"}


def _point_telemetry(point) -> dict:
    """Optional Wahoo telemetry off a trackpoint -> {key: float}.  Empty when
    the point carries no extensions (e.g. a plain komoot track)."""
    out = {}
    for ext in point.extensions:
        key = _TELE_TAGS.get(ext.tag)
        if key and ext.text:
            try:
                out[key] = float(ext.text)
            except ValueError:
                pass
    return out


def _metric_avg(tracks, key) -> float | None:
    """Point-weighted average of a per-track [sum, count] metric across the
    tracks being drawn.  None when no track carries that metric."""
    s = c = 0.0
    for t in tracks:
        m = t.get(key)
        if m:
            s += m[0]
            c += m[1]
    return s / c if c else None


def _metric_avg_track(t, key) -> float | None:
    """One ride's own average for a per-track [sum, count] metric; None when it has no samples."""
    m = t.get(key)
    if m and m[1]:
        return m[0] / m[1]
    return None


def _max_grade(t) -> float | None:
    """A ride's steepest per-segment grade (%); None when it has no graded segment."""
    gs = [g for g in t.get("grade", []) if g is not None]
    return max(gs) if gs else None


def _max_grade_group(tracks) -> float | None:
    """The steepest grade (%) across a group of rides (their per-ride maxima)."""
    gs = [v for v in (_max_grade(t) for t in tracks) if v is not None]
    return max(gs) if gs else None


def _grade_cap(grades, grade_cap: float | None) -> float:
    """|grade| colour-range cap: an explicit --grade-cap wins, else the GRADE_CAP_PCT percentile of |grade| clamped to [FLOOR, CEIL] (a GPS-noise spike can't squash the ramp, an all-flat ride still shows colour)."""
    if grade_cap and grade_cap > 0:
        return float(grade_cap)
    a = np.array([abs(g) for g in grades], dtype=float)
    cap = float(np.percentile(a, GRADE_CAP_PCT)) if a.size else GRADE_CAP_FLOOR
    return min(max(cap, GRADE_CAP_FLOOR), GRADE_CAP_CEIL)


def _metric_norm(vals, lo_pct: float = 2.0, hi_pct: float = 98.0):
    """A robust sequential colour norm for a telemetry metric (--color-by speed/power):
    the [lo_pct, hi_pct] percentiles of the per-segment values, so a lone outlier (a GPS
    speed spike, a one-off sprint) can't squash the ramp the way an un-capped min/max would.
    Returns None when there are no values (the caller then falls back to flat colour)."""
    if not vals:
        return None
    a = np.asarray(vals, dtype=float)
    lo = float(np.percentile(a, lo_pct))
    hi = float(np.percentile(a, hi_pct))
    if hi <= lo:
        hi = lo + 1.0
    return Normalize(vmin=lo, vmax=hi, clip=True)


def _track_calories(t) -> float | None:
    """This ride's 'calories burned' (kcal): avg power (W) x ride duration (s) over 4184 J/kcal and a ~25% efficiency; None without a power average or a ride span."""
    p = t.get("power")                            # [sum, count] power samples
    dur = t.get("duration_s", 0.0)
    if p and p[1] and dur:
        return (p[0] / p[1]) * dur / JOULES_PER_KCAL / METABOLIC_EFFICIENCY
    return None


def _calories_burned(tracks) -> float | None:
    """Total "calories burned" (kcal) across the tracks, estimated from average
    power (W) x ride duration (s): the mechanical work in kcal, then divided by a
    ~25% muscular efficiency (only ~1 in 4 kcal of food energy becomes pedal work).
    Summed per track; None when no track has both a power average and a measured
    duration (e.g. a plain komoot track without Wahoo telemetry)."""
    total = 0.0
    have = False
    for t in tracks:
        p = t.get("power")                        # [sum, count] power samples
        dur = t.get("duration_s", 0.0)
        if p and p[1] and dur:
            total += (p[0] / p[1]) * dur / JOULES_PER_KCAL / METABOLIC_EFFICIENCY
            have = True
    return total if have else None


def _fmt_duration(total_s: float) -> str:
    """Ride time as 'Hh MMm' (e.g. 3h 05m); '0m' for a ride under a minute."""
    h, rem = divmod(int(round(total_s)), 3600)
    m = rem // 60
    return f"{h}h {m:02d}m"


def _fmt_dur_or_dash(total_s: float) -> str:
    """Ride time as 'Hh MMm', or a '-' for a track with no measured span."""
    return _fmt_duration(total_s) if total_s > 0 else "-"


def _fmt_num(v, spec: str) -> str:
    """Format a metric value, or a "-" when it is absent (None)."""
    return "-" if v is None else f"{v:{spec}}"


# A "Kickr Snap" is a stationary smart trainer: its session has no route of its
# own, so its points would just clutter the basemap.  Keep such tracks off the
# rendered image, matched case-sensitively against the trimmed 'Device:' line -
# they are still listed in the ride-log/CSV (a trainer ride is still a ride).
SUPPRESSED_RENDER_DEVICES = {"Kickr Snap"}


def load_tracks(paths, decimate_m: float, with_ext: bool = False,
                noise_m: float = 0.0) -> list[dict]:
    """Read every .gpx path (discovered and date-filtered by the caller);
    merge its segments into one polyline each.
    Always record each ride's first->last timestamp span: its duration, shown on the
    title and feeding the calories-burned estimate.  With with_ext, also collect the
    Wahoo telemetry embedded by `wahoo_to_gpx --ext` (power/speed/cadence/hr) per
    point, accumulated over every sample (pre-decimation) so the caller can show an
    accurate average.  With noise_m > 0 each ride's gain ignores GPS vertical jitter
    below noise_m (see _distance_and_gain); 0 (the default) sums every rising segment."""
    tracks = []
    for path in sorted(paths):
        with open(path, "rb") as fh:
            gpx = gpxpy.parse(fh)
        raw = []                            # (lat, lon, ele) for every point
        tele = {k: [0.0, 0] for k in ("power", "speed", "cadence", "hr", "temp")} if with_ext else None
        records = [] if with_ext else None     # per-point {time, speed, power}, carried through decimation
        t_first = t_last = None               # ride span (1st -> last timestamp) for calories
        for trk in gpx.tracks:
            for seg in trk.segments:
                for pt in seg.points:
                    raw.append((pt.latitude, pt.longitude, pt.elevation))
                    st = pt.time              # ride span -> duration (+ calories when --ext)
                    if st is not None:
                        t_first = st if t_first is None or st < t_first else t_first
                        t_last   = st if t_last  is None or st > t_last  else t_last
                    if with_ext:
                          # a per-point record: the timestamp plus any telemetry on the point
                        rec = {"t": st}
                        for key, val in _point_telemetry(pt).items():
                            rec[key] = val
                            tele[key][0] += val
                            tele[key][1] += 1
                        records.append(rec)
        if not raw:
            print(f"  skip (no points): {os.path.basename(path)}")
            continue
        dist_km, gain_m = _distance_and_gain(raw, noise_m)
        dec, dec_records = decimate(raw, decimate_m, carry=records)
        merc = [latlon_to_merc(la, lo) for (la, lo, _e) in dec]
        ele = [e for (_la, _lo, e) in dec]
        ll = [(la, lo) for (la, lo, _e) in dec]            # decimated WGS84 lat/lon,
                                                          # the --html GeoJSON export's source
        grade, cum_km = _grade_and_cumkm(dec)
        name = (gpx.name or (gpx.tracks[0].name if gpx.tracks
                              and gpx.tracks[0].name else None)
                 or Path(path).stem)
        device = _device_type(gpx.description)           # "Device: <name>" line, if any
        sport  = _sport_type(gpx.description)            # "Sport: <name>" line, if any
        d = {"path": path, "name": name, "device": device, "sport": sport,
              "n": len(raw), "ndec": len(dec),
              "merc": merc, "ele": ele, "ll": ll,
              "dist_km": dist_km, "gain_m": gain_m,
              "grade": grade, "cum_km": cum_km,
              "duration_s": (t_last - t_first).total_seconds() if t_first else 0.0}
        if tele is not None:
            d.update(tele)                    # per-metric [sum, count] pairs
        if records is not None:
            # per-decimated-point arrays, aligned with merc/ele/grade
            d["tsec"] = [r.get("t") for r in dec_records]
            d["speed_pts"] = [r.get("speed") for r in dec_records]
            d["power_pts"] = [r.get("power") for r in dec_records]
            d["cadence_pts"] = [r.get("cadence") for r in dec_records]
            d["hr_pts"] = [r.get("hr") for r in dec_records]
        tracks.append(d)
    return tracks




def choose_detail(bbox, target_px: float = 1600.0, dmin: int = DETAIL_MIN, dmax: int = DETAIL_MAX) -> int:
    """Pick a tile detail level so the bbox spans roughly target_px pixels."""
    w_m = bbox[2] - bbox[0]
    d = math.log2(EQUATOR * target_px / (256.0 * w_m))
    return int(round(min(dmax, max(dmin, d))))


def fit_aspect(bbox, aspect_wh: float) -> tuple:
    """Grow the bbox (west,south,east,north) so it matches the figure aspect."""
    w, s, e, n = bbox
    bw, bh = e - w, n - s
    if bw / aspect_wh < bh:               # too narrow -> pad east/west
        dw = (bh * aspect_wh - bw) / 2
        return (w - dw, s, e + dw, n)
    dh = (bw / aspect_wh - bh) / 2        # too wide   -> pad north/south
    return (w, s - dh, e, n + dh)


# --------------------------------- rendering ----------------------------------
def _moving_avg(arr, window: int) -> "np.ndarray":
    """Centred moving average over a fixed (odd) window, skipping NaN so a gap just shortens the window (quiet the GPS jitter in a per-segment grade line)."""
    w = max(1, int(window))
    half = w // 2
    out = np.full(len(arr), np.nan)
    for i in range(len(arr)):
        seg = arr[max(0, i - half): i + half + 1]
        good = seg[np.isfinite(seg)]
        if good.size:
            out[i] = good.mean()
    return out

def _draw_profile(ax, t, x_label: bool = True) -> None:
    """Elevation + grade vs. cumulative distance for one track (grade on a twin
      axis): the classic ride-profile silhouette drawn under the map; the distance
      x-label is shown on this panel only when it is the bottom one (x_label)."""
    km = np.array(t.get("cum_km") or [0.0], dtype=float)
    ele = t.get("ele") or []
    if km.size < 2:
        return
    el = np.array([(e if e is not None else np.nan) for e in ele], dtype=float)
    ax.plot(km, el, color="#444", lw=1.1, zorder=2)
    base = np.nanmin(el) if np.isfinite(el).any() else 0.0
    ax.fill_between(km, base, el, color="#444", alpha=0.18, zorder=1)
    ax.set_ylabel("Elevation (m)", fontsize=9)
    if x_label:
        ax.set_xlabel("Distance (km)", fontsize=9)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(km[0], km[-1])
        # grade on a right-hand axis (per-segment, so one fewer point than the
        # profile).  A raw per-segment grade jitters on GPS noise, so it is a light
        # centred moving average over GRADE_SMOOTH segments before it is plotted.
    gr = t.get("grade") or []
    garr = np.array([(g if g is not None else np.nan) for g in gr], dtype=float)
    if garr.size and np.isfinite(garr).any():
        gs = _moving_avg(garr, GRADE_SMOOTH)
        pairs = [(x, g) for x, g in zip(km[:-1], gs) if np.isfinite(g)]
        if pairs:
            gx, gg = zip(*pairs)
            axg = ax.twinx()
            axg.plot(gx, gg, color="#c0392b", lw=0.9, alpha=0.85)
            axg.set_ylabel("Grade (%)", fontsize=9, color="#c0392b")




def _has_metric_pts(t, key) -> bool:
    """True when a ride carries at least one value for a per-point telemetry array
    (power/speed/hr/cadence, aligned with cum_km): the --profile card draws a mini-panel
    for a metric only then, so a ride missing it (no HR strap, a plain komoot track) skips it."""
    return any(v is not None for v in (t.get(key) or []))


def _draw_profile_metric(ax, t, key, label, color) -> None:
    """One telemetry mini-panel of the --profile "ride card": the ride's per-point
    `key` (power/speed/hr/cadence, aligned with cum_km) as a light filled line vs. distance,
    on its own strip and colour, so a single figure reads like a full ride card.  The raw
    per-point values are plotted (a card should show real effort -- a sprint's peak power
    -- not a smoothed trace); the distance x-label is left to the bottom panel the caller
    draws.  A no-op when the ride carries no value for the metric."""
    km = np.array(t.get("cum_km") or [0.0], dtype=float)
    arr = t.get(key) or []
    y = np.array([(v if v is not None else np.nan) for v in arr], dtype=float)
    if y.size == 0 or not np.isfinite(y).any():
        return
    ax.plot(km, y, color=color, lw=0.9, alpha=0.9, zorder=2)
    ax.fill_between(km, 0.0, y, color=color, alpha=0.12, zorder=1)
    ax.set_ylabel(label, fontsize=8, color=color)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(km[0], km[-1])
    ax.tick_params(axis="y", labelsize=7, colors=color)
def _stack_grade_colorbars(fig, ax, cmap, norms, labels, unit="Grade (%)"):
    """One compact vertical colourbar per ride, stacked on the right of the map, each labelled with its ride and a 3-tick range -- a combined grade map shows every ride's own cap."""
    ap = ax.get_position()
    n = len(norms)
    left = ap.x1 + 0.012
    width = min(0.02, ap.width * 0.03)
    step = (ap.y1 - ap.y0) / n
    fig.text(left + width / 2, ap.y1 + 0.018, unit, ha="center", va="bottom",
             fontsize=8, color="#555")
    for k, (norm, lab) in enumerate(zip(norms, labels)):
        y0 = ap.y0 + k * step + step * 0.15
        h = step * 0.70
        cax = fig.add_axes([left, y0, width, h])
        sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
        sm.set_array([])
        cb = fig.colorbar(sm, cax=cax, orientation="vertical",
                          ticks=[-norm.vmax, 0.0, norm.vmax])
        cb.outline.set_visible(False)
        cb.ax.tick_params(labelsize=6)
        cb.ax.set_yticklabels([f"{norm.vmin:.0f}", "0", f"{norm.vmax:.0f}"])
        cb.ax.set_title(lab, fontsize=6, pad=3)


def _nice_m(raw_m: float) -> float:
    """Round a target length (m) up to the nearest 1/2/5 x 10^k for a tidy scale bar."""
    if raw_m <= 0 or not math.isfinite(raw_m):
        return 0.0
    mag = 10.0 ** math.floor(math.log10(raw_m))
    for m in (1.0, 2.0, 5.0, 10.0):
        if m * mag >= raw_m:
            return m * mag
    return 10.0 * mag


def _fmt_len(m: float) -> str:
    """A scale-bar length: whole metres ('N m') under a kilometre, else kilometres
    (one decimal under 10 km)."""
    if m < 1000.0:
        return f"{m:.0f} m"
    km = m / 1000.0
    return f"{km:.0f} km" if km >= 10.0 else f"{km:.1f} km"


def _draw_scale_bar(ax, bbox) -> None:
    """A '0 .. N km/m' scale bar in the map's lower-right corner.  The axes is in
    Web-Mercator metres with an 'equal' aspect, so a line of length nice_m in data units
    is exactly that many metres on screen; a 'nice' length (a fraction of the visible width)
    is picked, with end caps, a white casing (so it reads on a busy basemap) and a distance
    label above it.  Skipped when the box has no width (a single point)."""
    w_m = bbox[2] - bbox[0]
    n_m = bbox[3] - bbox[1]
    if w_m <= 0 or n_m <= 0:
        return
    nice = _nice_m(w_m * 0.15)
    if nice <= 0:
        return
    bx1 = bbox[2] - w_m * 0.04           # 4% in from the right edge, clear of the colourbar
    bx0 = bx1 - nice
    by     = bbox[1] + n_m * 0.06         # 6% up from the bottom, clear of the corner text
    cap = nice * 0.06
    # a white casing under the bar and its end caps, then the dark bar on top, so it stays
    # visible over a busy basemap (the same halo trick as the route lines)
    ax.plot([bx0, bx1], [by, by], color="white", linewidth=4.0, solid_capstyle="butt",
             zorder=8)
    ax.plot([bx0, bx1], [by, by], color="#222", linewidth=2.2, solid_capstyle="butt",
             zorder=9)
    for x in (bx0, bx1):
        ax.plot([x, x], [by, by + cap], color="white", linewidth=4.0, solid_capstyle="butt",
                 zorder=8)
        ax.plot([x, x], [by, by + cap], color="#222", linewidth=2.2, solid_capstyle="butt",
                 zorder=9)
    ax.text((bx0 + bx1) / 2, by + cap * 1.8, _fmt_len(nice), ha="center", va="bottom",
             fontsize=8, color="#222", zorder=9,
             path_effects=[_with_stroke(linewidth=2.5, foreground="white")])


def _dwell_times(tsec, n: int):
    """Per-point 'time on route' (seconds): point j carries the time on the segment *leaving*
    it (j -> j+1); the final point takes its incoming segment.  A point with no timestamp (a GPS
    gap) adds 0 for that segment.  None when the ride has no usable timestamps, so the caller
    can fall back to weighting by point count."""
    if not tsec or all(x is None for x in tsec):
        return None
    seg = [ (tsec[j + 1] - tsec[j]).total_seconds()
            if tsec[j] is not None and tsec[j + 1] is not None else 0.0
            for j in range(n - 1) ]
    dwell = seg + ([seg[-1]] if seg else [])      # the last point reuses its incoming segment
    return [max(0.0, d) for d in dwell]


def _fmt_heat_time(sec, pos=0.0) -> str:
    """A --heat colourbar tick: a time-on-route value (seconds), shown as 'N s', 'N m', or
    'Nh Mm' -- the total time can span many hours across all the rides."""
    sec = int(round(sec))
    if sec < 60:
        return f"{sec} s"
    m = sec // 60
    if m < 60:
        return f"{m} m"
    h, m = divmod(m, 60)
    return f"{h} h" if m == 0 else f"{h} h {m} m"


def _draw_heat(ax, tracks, bbox, grid: int = HEAT_GRID, cap_pct: float = HEAT_CAP_PCT,
               alpha: float = HEAT_ALPHA):
    """A 2-D 'time on route' density of the routes' decimated points, drawn *under* the route
    lines: a grid x grid histogram over the bbox, each cell weighted by the time spent on the
    segments through it (so overlapping and slow routes -- climbs, rest stops, traffic -- glow
    most; a ride with no timestamps is weighted by point count).  The colour is capped at a high
    percentile so one hot cell can't wash out the rest, and empty cells are masked so the basemap
    shows through.  Returns the AxesImage (for a colourbar), or None when there is nothing to plot."""
    import matplotlib.colors as mcolors
    w, s, e, n = bbox
    if e <= w or n <= s:
        return None
    xs, ys, wts = [], [], []
    for t in tracks:
        merc = t.get("merc") or []
        if len(merc) < 2:
            continue
        dwell = _dwell_times(t.get("tsec"), len(merc))
        for j, (x, y) in enumerate(merc):
            xs.append(x)
            ys.append(y)
            wts.append(1.0 if dwell is None else dwell[j])
    if not xs:
        return None
    H, _xe, _ye = np.histogram2d(xs, ys, bins=grid,
                                 range=[[w, e], [s, n]], weights=wts)
    H = np.ma.masked_equal(H, 0.0)             # empty cells: let the basemap show through
    vals = H.compressed()
    cap = float(np.percentile(vals, cap_pct)) if vals.size else 0.0
    norm = mcolors.Normalize(vmin=0.0, vmax=max(cap, 1e-9), clip=True)
    # imshow(aspect="auto") makes the (square) grid fill the view *and* flips the
    # axes aspect to "auto" as a side effect.  Do NOT "restore" the map's equal aspect
    # afterwards: switching the axes back to "equal" after the image was laid out at
    # "auto" invalidates the image's transform, so the overlay was never drawn (the
    # --heat output was byte-identical to no --heat).  The restore is also pointless
    # here: the bbox is already aspect-fit to the figure, so the view limits are
    # unchanged by the flip (equal and auto agree), and the route lines + scale bar
    # (data-coordinate artists, placed by those view limits, not the aspect string)
    # stay undistorted.
    im = ax.imshow(H, extent=[w, s, e, n], origin="lower", aspect="auto",
                   cmap="YlOrRd", norm=norm, alpha=alpha, zorder=3,
                   interpolation="bilinear")
    return im


def render(tracks, *, style: str, out_path: Path, detail: int | None,
           color_by: str = "elev", title: str | None = None,
           show_ext: bool = False, split: bool = False, profile: bool = False,
           grade_cap: float | None = None, scale: bool = True,
           heat: bool = False, labels: bool = False) -> None:
    if not tracks:
        print("No tracks to render.")
        return

    all_merc = np.array([pt for t in tracks for pt in t["merc"]], dtype=float)
    w0, s0, e0, n0 = (all_merc[:, 0].min(), all_merc[:, 1].min(),
                      all_merc[:, 0].max(), all_merc[:, 1].max())
    dx, dy = (e0 - w0) * PAD_FRAC, (n0 - s0) * PAD_FRAC
    raw_bbox = (w0 - dx, s0 - dy, e0 + dx, n0 + dy)

    elev = [e for t in tracks for e in t["ele"] if e is not None]
    elev_min, elev_max = (min(elev), max(elev)) if elev else (0.0, 1.0)

    if profile and len(tracks) == 1:
         # a "ride card": the elevation + grade silhouette plus one slim telemetry
         # mini-panel (power/speed/hr/cadence) per metric the ride carries, each its own
         # strip below the map.  The layout is data-driven, so the figure grows only when
         # telemetry is present; a plain ride (no --ext) keeps just the elevation + grade panel.
        t0 = tracks[0]
        prof_metrics = [m for m in PROF_METRICS if _has_metric_pts(t0, m[0])]
        n_prof = len(prof_metrics)
        fig_h = FIGURE_IN[1] * (1.25 + 0.22 * n_prof)
        fig = plt.figure(figsize=(FIGURE_IN[0], fig_h), dpi=DPI)
        gs = fig.add_gridspec(2 + n_prof, 1,
                              height_ratios=[3.0, 1.3] + [0.5] * n_prof, hspace=0.13)
        ax = fig.add_subplot(gs[0])
         # a tall ride-card figure would letter-box the near-square basemap (white side-
         # bars), so refit the map's bbox to the map axes' own (narrower) aspect
        fig.canvas.draw()
        pos = ax.get_position()
        map_aspect = (pos.width * FIGURE_IN[0]) / (pos.height * fig_h)
        bbox = fit_aspect(raw_bbox, map_aspect)
        if detail is None:
            detail = choose_detail(bbox)
        ax_prof = fig.add_subplot(gs[1])
        _draw_profile(ax_prof, t0, x_label=False)
        last = ax_prof
        for k, (key, label, color) in enumerate(prof_metrics):
            axm = fig.add_subplot(gs[2 + k])
            _draw_profile_metric(axm, t0, key, label, color)
            last = axm
        last.set_xlabel("Distance (km)", fontsize=9)
    else:
        bbox = fit_aspect(raw_bbox, FIGURE_IN[0] / FIGURE_IN[1])
        if detail is None:
            detail = choose_detail(bbox)
        fig, ax = plt.subplots(figsize=FIGURE_IN, dpi=DPI)
        ax_prof = None

    # --- base map (tried in fallback order) ---
    ordered = [style] + [k for k in SOURCES if k != style]
    loaded = _load_basemap(ax, bbox, ordered, detail)
    attr = ATTRIBUTION.get(loaded, "© OpenStreetMap contributors")

    # --- heat overlay: a 2-D "time on route" density, drawn under the route lines ---
    heat_im = _draw_heat(ax, tracks, bbox) if heat else None

    # --- overlay tracks ---
         # colouring mode: 'elev' shades by elevation, 'grade' by per-segment slope on a
         # diverging ramp (steep climbs hot, descents cold), 'flat' = one bold hue per
         # track.  Each mode precomputes a shared norm + cmap across all the tracks.
    per_track_norms = None
    if color_by == "grade":
         # Per-ride colouring (each route on its own cap) makes sense only when the
         # cap is *auto* -- an explicit --grade-cap means one shared scale.  It is
         # used for a combined multi-track map so a single steep ride can't
         # desaturate the others; a single or --split map is already per-track.  A
         # few rides get their own colourbar; beyond GRADE_CBAR_MAX we fall back to
         # one shared scale and say so.
        grades_all = [g for t in tracks for g in t.get("grade", []) if g is not None]
        have_metric = bool(grades_all)
        cmap, cbar_label = CMAPGRADE, "Grade (%)"
        per_track = (grade_cap is None and len(tracks) > 1
                     and len(tracks) <= GRADE_CBAR_MAX)
        if per_track:
            per_track_norms = []
            for t in tracks:
                cap = _grade_cap([x for x in t.get("grade", []) if x is not None], grade_cap)
                per_track_norms.append(Normalize(vmin=-cap, vmax=cap, clip=True))
            norm = None
        else:
            gcap = _grade_cap(grades_all, grade_cap)
            norm = Normalize(vmin=-gcap, vmax=gcap, clip=True)
            if grade_cap is None and len(tracks) > GRADE_CBAR_MAX and grades_all:
                print(f"      grade: {len(tracks)} tracks share one colour scale "
                         f"(more than {int(GRADE_CBAR_MAX)}); use --split or --grade-cap "
                         f"for a per-ride / fixed range")
    elif color_by == "elev":
        norm = Normalize(vmin=elev_min, vmax=elev_max)
        cmap, cbar_label = CMAPEL, "Elevation (m)"
        have_metric = (elev_max - elev_min) > 1.0
    elif color_by in ("speed", "power"):
          # per-segment telemetry shading: each segment takes the average of its two
          # endpoint values (both must be present).  The norm is a robust percentile
          # range so one spike can't squash the ramp; absent per-point telemetry
          # (e.g. no --ext / a non-Wahoo ride) there are no values and the route
          # falls back to its flat per-track colour (have_metric stays False).
        key = "speed_pts" if color_by == "speed" else "power_pts"
        vals = [ (t[key][j] + t[key][j + 1]) / 2 for t in tracks
                 for j in range(len(t.get(key, [])) - 1)
                 if t[key][j] is not None and t[key][j + 1] is not None ]
        norm = _metric_norm(vals)
        cmap = CMAPEED
        cbar_label = "Speed (km/h)" if color_by == "speed" else "Power (W)"
        have_metric = norm is not None
    else:
        norm = cmap = cbar_label = None
        have_metric = False
    if color_by in ("speed", "power") and not have_metric:
        print(f"      --color-by {color_by}: no per-point {color_by} telemetry "
                "(need wahoo_to_gpx --ext); drawing a flat per-track colour instead")
    for i, t in enumerate(tracks):
        seg = np.array([[t["merc"][j], t["merc"][j + 1]]
                        for j in range(len(t["merc"]) - 1)])
             # Underlay that makes the route pop on the busy basemap: a subtle
             # dark outline for metric shading (a touch wider than the line,
             # so even the grey 0 % grade neutral is visible) and the white
             # halo for the bold flat per-track colours.  Either way it covers
             # the whole track, so a metric-less gap just shows the underlay.
        if have_metric:
            halo = LineCollection(seg, colors="#333", linewidths=4.6, alpha=0.5)
        else:
            halo = LineCollection(seg, colors="white", linewidths=4.6, alpha=0.9)
        halo.set_zorder(4)
        ax.add_collection(halo)
        if have_metric:
                 # shade only the segments that carry the metric on this end
            if color_by == "grade":
                gr = t.get("grade", [])
                ok = [j for j in range(len(gr)) if gr[j] is not None]
                mc = [gr[j] for j in ok]
            elif color_by in ("speed", "power"):
                arr = t.get("speed_pts" if color_by == "speed" else "power_pts", [])
                ok = [j for j in range(len(arr) - 1)
                      if arr[j] is not None and arr[j + 1] is not None]
                mc = [(arr[j] + arr[j + 1]) / 2 for j in ok]
            else:
                     # elevation: a segment needs it on both ends (some GPX omit it)
                ok = [j for j in range(len(t["ele"]) - 1)
                      if t["ele"][j] is not None and t["ele"][j + 1] is not None]
                mc = [(t["ele"][j] + t["ele"][j + 1]) / 2 for j in ok]
            seg_m = [[t["merc"][j], t["merc"][j + 1]] for j in ok]
            norm_i = per_track_norms[i] if per_track_norms is not None else norm
            lc = LineCollection(seg_m, cmap=cmap, norm=norm_i,
                                linewidths=3.2, alpha=0.98)
            lc.set_array(mc)
        else:
               # bold, distinct colour per track so routes stand out on the basemap
            color = STRONG_COLORS[i % len(STRONG_COLORS)]
            lc = LineCollection(seg, colors=[color], linewidths=3.2, alpha=0.95)
        lc.set_zorder(5)
        ax.add_collection(lc)

        x0, y0 = t["merc"][0]
        x1, y1 = t["merc"][-1]
        ax.scatter([x0], [y0], s=70, color="lime", edgecolors="k",
                   linewidths=0.6, zorder=7)
        ax.scatter([x1], [y1], s=70, color="red", edgecolors="k",
                   linewidths=0.6, zorder=7)
        if labels and len(tracks) > 1:
               # a halo'd 'name  N km' near the start marker, so a many-ride map
               # reads without a legend key (a single ride's name is in the title).  Loop
               # rides often share one start, so stagger each label by its index to keep a
               # handful of co-located starts legible.
            lab = f"{_short_label(t['name'])}      {t['dist_km']:,.0f} km"
            ax.annotate(lab, (x0, y0), xytext=(7.0, 7.0 + (i % 12) * 3.0),
                        textcoords="offset points", fontsize=8, color="#111", zorder=8,
                        path_effects=[_with_stroke(linewidth=2.5, foreground="white")])

     # one more start-marker for the overall route start, drawn after every
     # track so it sits on top of all the per-track lines, halos and markers
    sx, sy = tracks[0]["merc"][0]
    ax.scatter([sx], [sy], s=70, color="lime", edgecolors="k",
               linewidths=0.6, zorder=8)

    ax.axis("off")

    # colourbar + legend + attribution
    if have_metric:
        if per_track_norms is not None:
           # one compact colourbar per ride, stacked on the right, each labelled with
           # its ride -- a combined grade map, so every ride shows its own cap
            _stack_grade_colorbars(fig, ax, cmap, per_track_norms,
                                   [_short_label(t["name"]) for t in tracks])
        else:
            sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
            sm.set_array([])
            cb = fig.colorbar(sm, ax=ax, fraction=0.03, pad=0.02, location="right")
            cb.set_label(cbar_label, fontsize=10)
    elif heat_im is not None:
           # a 'time on route' colourbar, its ticks formatted as a duration
        cb = fig.colorbar(heat_im, ax=ax, fraction=0.03, pad=0.02, location="right")
        cb.set_label("Time on route", fontsize=10)
        cb.formatter = FuncFormatter(_fmt_heat_time)
        cb.update_ticks()
    if heat_im is not None and have_metric:
        print("      heat: a metric colourbar is shown instead of the "
                 "'Time on route' one (both are right-edge bars)")

    total_km = sum(t["dist_km"] for t in tracks)
    total_gain = sum(t["gain_m"] for t in tracks)
    total_dur = sum(t.get("duration_s", 0.0) for t in tracks)
     # Duration and "calories burned" are totals (like distance/gain), so they join
     # the main title line, not the "avg" subtitle.  Calories needs --ext power and
     # is omitted when absent.
    sep = "     -     "
    dur_seg = f"{sep}{_fmt_duration(total_dur)}" if total_dur > 0 else ""
    cal = _calories_burned(tracks) if show_ext else None
    cal_seg = f"{sep}{cal:,.0f} kcal" if cal is not None else ""
    if color_by == "grade":
        suffix = "     -  shaded by grade" if have_metric else ""
    elif color_by == "elev":
        suffix = "     -  shaded by elevation" if have_metric else ""
    elif color_by in ("speed", "power"):
        suffix = f"     -  shaded by {color_by}" if have_metric else ""
    else:
        suffix = ""
    head = _title_name(tracks[0]["name"]) if (split and len(tracks) == 1) else None
    if title is not None:
        suptitle = title
    elif len(tracks) == 1:
        name = head or tracks[0]["name"]
        suptitle = (f"{name}{sep}{total_km:,.0f} km{dur_seg}"
                    f"{sep}▲ {total_gain:,.0f} m{cal_seg}{suffix}")
    else:
        suptitle = (f"{len(tracks)} tracks{sep}{total_km:,.0f} km{dur_seg}"
                    f"{sep}▲ {total_gain:,.0f} m{cal_seg}{suffix}")
    if show_ext:
        # average power/speed/cadence/hr for a separate, smaller header line below the
        # title (point-weighted across the tracks drawn here; only metrics present).
        tele = []
        for label, key, unit, fmt in (
             ("power", "power", "W", "5.0f"),
             ("speed", "speed", "km/h", "4.1f"),
             ("cadence", "cadence", "rpm", "3.0f"),
             ("hr", "hr", "bpm", "3.0f")):
            avg = _metric_avg(tracks, key)
            if avg is not None:
                tele.append(f"{label} {avg:{fmt}} {unit}")
    fig.suptitle(suptitle, fontsize=13, fontweight="bold", y=0.985)
    if show_ext and tele:
        # second line: a smaller font, a little lower -> reads as a subtitle
        fig.text(0.5, 0.95, "avg       " + "       ".join(tele), ha="center",
                 va="top", fontsize=10)

    handles = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor="lime",
               markeredgecolor="k", markersize=9, label="Start"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="red",
               markeredgecolor="k", markersize=9, label="Stop"),
    ]
    ax.legend(handles=handles, loc="lower left", framealpha=0.85, fontsize=9)

    # a scale bar in the lower-right: the axes is in metres with an 'equal' aspect, so a
    # data-length line reads as a true distance on the (otherwise scale-less) static map
    if scale:
        _draw_scale_bar(ax, bbox)

    fig.text(0.006, 0.004, attr, fontsize=7, color="#555")
    fig.text(0.994, 0.004, f"detail {detail}", fontsize=7, color="#555", ha="right")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=DPI, facecolor="white")
    plt.close(fig)
    print(f"  wrote {out_path}    ({out_path.stat().st_size // 1024} KB)")


def _stats_columns(show_ext: bool) -> list:
    """The ride-log columns shared by write_stats() and write_csv(): each is a
    (header, numeric?, per-ride formatter, per-device-group summary) tuple.  The
    per-ride formatter turns one ride into its cell; the summary formatter turns a
    group of rides (all one device type) into that device's totals cell, so the
    ride-log can print one totals row per device.  The Ride/Device columns carry a
    fixed summary label instead of a number.  The calories-burned and avg
    power/speed/cadence/hr columns appear only under --ext; a per-ride cell of
    "-" still marks a metric that ride lacks (e.g. a plain komoot track)."""
    # (column header, numeric?, per-ride formatter, per-device-group summary)
    cols = [
          ("Ride", False,
          lambda t: _title_name(t["name"]),
          lambda g: "Summary"),
          ("Dist (km)", True,
          lambda t: f"{t['dist_km']:,.1f}",
          lambda g: f"{sum(t['dist_km'] for t in g):,.0f}"),
          ("Duration", False,
          lambda t: _fmt_dur_or_dash(t.get("duration_s", 0.0)),
          lambda g: _fmt_dur_or_dash(sum(t.get("duration_s", 0.0) for t in g))),
          ("Gain (m)", True,
          lambda t: f"{t['gain_m']:,.0f}",
          lambda g: f"{sum(t['gain_m'] for t in g):,.0f}"),
    ]
    if show_ext:
        cols += [
              ("Calories (kcal)", True,
              lambda t: _fmt_num(_track_calories(t), ",.0f"),
              lambda g: _fmt_num(_calories_burned(g), ",.0f")),
              ("Avg power (W)", True,
              lambda t: _fmt_num(_metric_avg_track(t, "power"), "5.0f"),
              lambda g: _fmt_num(_metric_avg(g, "power"), "5.0f")),
              ("Avg speed (km/h)", True,
              lambda t: _fmt_num(_metric_avg_track(t, "speed"), "4.1f"),
              lambda g: _fmt_num(_metric_avg(g, "speed"), "4.1f")),
              ("Avg cadence (rpm)", True,
              lambda t: _fmt_num(_metric_avg_track(t, "cadence"), "3.0f"),
              lambda g: _fmt_num(_metric_avg(g, "cadence"), "3.0f")),
              ("Avg HR (bpm)", True,
              lambda t: _fmt_num(_metric_avg_track(t, "hr"), "3.0f"),
              lambda g: _fmt_num(_metric_avg(g, "hr"), "3.0f")),
              ("Max grade (%)", True,
              lambda t: _fmt_num(_max_grade(t), ".1f"),
              lambda g: _fmt_num(_max_grade_group(g), ".1f")),
              ("Avg temperature (°C)", True,
              lambda t: _fmt_num(_metric_avg_track(t, "temp"), ".0f"),
              lambda g: _fmt_num(_metric_avg(g, "temp"), ".0f")),
        ]
     # the Device column closes the ride-log (both .txt and .csv); its cell
     # on each per-device Summary row is that group's device label, shown last
    cols += [
          ("Device", False,
          lambda t: _device_label(t.get("device")),
          lambda g: _device_label(g[0].get("device"))),
    ]
    return cols


def write_stats(tracks, out_path: Path, show_ext: bool) -> None:
    """Write one ride-log table to out_path: a row per ride carrying the two title
    headers' stats plus a Device column (distance, duration, gain; and calories +
    avg power/speed/cadence/hr under --ext).  A "-" marks a metric a ride does not
    carry (e.g. a plain komoot track, no telemetry).  The table closes with one
    Summary totals row per device type - "Summary" in the Ride column, that
    device's totals in the numeric columns, its name in the last (Device) column."""
    cols = _stats_columns(show_ext)
    rows = [[c[2](t) for c in cols] for t in tracks]
    groups = _device_groups(tracks)
    # one Summary totals row per device type ("Summary" + device + that device's totals)
    summary_rows = [[c[3](g) for c in cols] for _lbl, g in groups]

    # each column is as wide as its widest cell (header, a ride row, a summary cell)
    widths = []
    for i, c in enumerate(cols):
        cells = [c[0]] + [r[i] for r in rows] + [sr[i] for sr in summary_rows]
        widths.append(max(len(x) for x in cells))

    def fmt_row(cells):
        out = []
        for i, (cell, c) in enumerate(zip(cells, cols)):
            out.append(cell.rjust(widths[i]) if c[1] else cell.ljust(widths[i]))
        return "       ".join(out)

    head = [c[0] for c in cols]
    rule = "       ".join("-" * w for w in widths)
    n = len(tracks)
    lines = [f"trackview - {n} ride{'s' if n != 1 else ''}", "",
             fmt_row(head), rule]
    lines += [fmt_row(r) for r in rows]
    lines.append(rule)
    for sr in summary_rows:
        lines.append(fmt_row(sr))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  wrote {out_path}")


def write_csv(tracks, out_path: Path, show_ext: bool, delimiter: str = ";") -> None:
    """Write a CSV ride-log to out_path: just a header row and one data row per
    ride - the same columns as the stats ride-log (including a Device column),
    but no title/rules/totals: the per-device totals live only in the .txt.
    Numeric fields are decimal-normalised for the CSV (no column
    padding, no thousands grouping), unlike the .txt table; a field that contains
    `delimiter` (default ';', the European/Excel default) is still quoted by the csv
    module, and a "-" still marks a metric a ride lacks."""
    cols = _stats_columns(show_ext)
    head = [c[0] for c in cols]

      # the shared per-ride formatters are tuned for the .txt table (column padding +
      # a thousands comma); the CSV wants bare decimals, so drop the padding and the
      # grouping comma from the numeric cells only, keeping the "-" marker for a ride
      # that lacks a metric (ride names / the duration string are left as-is).
    def clean(cell: str, numeric: bool) -> str:
        return cell if (not numeric or cell == "-") else cell.replace(",", "").strip()

    rows = [[clean(c[2](t), c[1]) for c in cols] for t in tracks]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter=delimiter, lineterminator="\n")
        w.writerow(head)
        w.writerows(rows)
    print(f"  wrote {out_path}")


def _ride_climbs(t, min_gr=CLIMB_MIN_GR, min_len_m=CLIMB_MIN_LEN,
                 smooth=CLIMB_SMOOTH) -> list[dict]:
    """Sustained climbs in one ride: maximal runs of segments whose *smoothed* grade
    stays >= min_gr and whose horizontal length reaches min_len_m.  Raw GPS grade jitters
    (as the profile's), so a centred moving average over `smooth` segments (as in
    _draw_profile) is run first; a run's gain is the positive elevation rise across it, its
    average grade the distance-weighted slope (gain / length), its max grade the steepest
    smoothed segment, and a 'score' (gain x average grade) ranks a long climb against a short
    steep one.   [] when the ride carries no grade (some tracks omit elevation)."""
    gr = t.get("grade") or []
    cum = t.get("cum_km") or []
    ele = t.get("ele") or []
    if len(gr) < 1 or len(cum) < 2 or len(ele) < 2:
        return []
    garr = np.array([(g if g is not None else np.nan) for g in gr], dtype=float)
    if not np.isfinite(garr).any():
        return []
    gs = _moving_avg(garr, smooth)
    n = len(gr)
    climbs = []
    j = 0
    while j < n:
        if not np.isfinite(gs[j]) or gs[j] < min_gr:
            j += 1
            continue
        k = j
        while k + 1 < n and np.isfinite(gs[k + 1]) and gs[k + 1] >= min_gr:
            k += 1
             # run [j, k] spans points j..k+1: length from the cumulative km, the gain from
             # the positive elevation rise across it (the ascent of that climb)
        len_km = cum[k + 1] - cum[j]
        if len_km * 1000.0 >= min_len_m:
            gain_m = sum(max(0.0, (ele[j + 1] or 0.0) - (ele[j] or 0.0))
                         for j2 in range(j, k + 1))
            avg_gr = 100.0 * gain_m / (len_km * 1000.0) if len_km > 0 else 0.0
            max_gr = float(np.nanmax(gs[j:k + 1]))
            climbs.append({
                  "ride": t["name"], "device": t.get("device"),
                  "start_km": cum[j], "end_km": cum[k + 1], "len_km": len_km,
                  "gain_m": gain_m, "avg_gr": avg_gr, "max_gr": max_gr,
                  "score": gain_m * avg_gr,
             })
        j = k + 1
    return climbs


def _all_climbs(tracks) -> list[dict]:
    """Every climb across the tracks, ranked most-significant first (by score)."""
    allc = []
    for t in tracks:
        allc.extend(_ride_climbs(t))
    allc.sort(key=lambda c: c["score"], reverse=True)
    return allc


def write_climbs(tracks, out_path: Path, top_n: int,
                 min_gr: float = CLIMB_MIN_GR, min_len_m: float = CLIMB_MIN_LEN) -> None:
    """Write a climb ranking to out_path: the top_n most-significant sustained climbs
    (runs of smoothed grade >= min_gr over at least min_len_m of horizontal run, found by
    _ride_climbs), one row each - the ride, where it sits (start->end km), its length, gain,
    average and steepest grade, and a 'score' (gain x average grade).  The header names the
    detection thresholds so the list is self-describing; an empty run writes a note."""
    climbs = _all_climbs(tracks)[:top_n]
    lines = [f"trackview - top {len(climbs)} climb"
             f"{'s' if len(climbs) != 1 else ''}  "
             f"(grade >= {min_gr:.0f}%, run >= {min_len_m:.0f} m)",
              ""]
    if not climbs:
        lines.append("  no sustained climbs found.")
    else:
        head = ["#", "Ride", "From (km)", "To (km)", "Len (km)", "Gain (m)",
                 "Avg %", "Max %", "Score"]
        align = [True, False, True, True, True, True, True, True, True]
        rows = [[str(i), _title_name(c["ride"]), f"{c['start_km']:.1f}",
                  f"{c['end_km']:.1f}", f"{c['len_km']:.1f}", f"{c['gain_m']:,.0f}",
                  f"{c['avg_gr']:.1f}", f"{c['max_gr']:.1f}", f"{c['score']:,.0f}"]
                 for i, c in enumerate(climbs, 1)]
        widths = [max(len(head[i]), *(len(r[i]) for r in rows)) for i in range(len(head))]
        sep = "         "
        def fmt(cells):
            out = []
            for i, (cell, a) in enumerate(zip(cells, align)):
                out.append(cell.rjust(widths[i]) if a else cell.ljust(widths[i]))
            return sep.join(out)
        rule = sep.join("-" * w for w in widths)
        lines.append(fmt(head))
        lines.append(rule)
        lines += [fmt(r) for r in rows]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  wrote {out_path}")
def _trend_panels(tracks) -> tuple[list, int]:
    """The --trend chart's panels: one per metric over ride date -- distance, elevation
    gain and ride duration for every ride (each placed on its Wahoo-filename date),
    plus a calories-burned panel when any ride carries a power average.  A ride with no
    date in its filename can't be placed in time, so it is skipped (and counted).  Each
    panel is (y-label, [dates], [values]); the rides are sorted by date so a panel reads
    left-to-right in time."""
    dated = []
    skipped = 0
    for t in tracks:
        rd = _ride_date(t["path"])
        if rd is None:
            skipped += 1
            continue
        dated.append((rd, t))
    dated.sort(key=lambda pair: pair[0])
    dates = [d for d, _ in dated]
    panels = [
          ("Distance (km)", dates, [t["dist_km"] for _, t in dated]),
          ("Elevation gain (m)", dates, [t["gain_m"] for _, t in dated]),
          ("Duration (h)", dates, [t.get("duration_s", 0.0) / 3600.0 for _, t in dated]),
    ]
    cals = []
    for d, t in dated:
        cal = _track_calories(t)
        if cal is not None:
            cals.append((d, cal))
    if cals:
        panels.append(("Calories (kcal)", [d for d, _ in cals], [v for _, v in cals]))
    return panels, skipped


_TREND_COLORS = ["#1f78b4", "#2ca02c", "#ff7f0e", "#984ea3"]


def write_trend(tracks, out_path: Path) -> None:
    """Write a per-ride 'training trend' chart to out_path: one panel per metric
    (distance, gain, duration, and a calories-burned panel when any ride carries a power
    average) plotted over ride date, so training volume and the span of the log read at a
    glance.  A standalone chart (no basemap, no network), so it writes even under --no-map;
    rides with no date in the filename are skipped (they can't be placed in time)."""
    panels, skipped = _trend_panels(tracks)
    if not panels or not panels[0][1]:
        print("          --trend: no dated rides to chart.")
        return
    n = len(panels)
    fig, axes = plt.subplots(n, 1, figsize=(11, 1.6 + 1.1 * n), dpi=DPI,
                             sharex=True, squeeze=False)
    for k, (label, xs, ys) in enumerate(panels):
        ax = axes[k][0]
        c = _TREND_COLORS[k % len(_TREND_COLORS)]
        ax.plot(xs, ys, color=c, lw=1.0, alpha=0.9, marker="o", ms=3.0)
        ax.fill_between(xs, 0.0, ys, color=c, alpha=0.10)
        ax.set_ylabel(label, fontsize=9, color=c)
        ax.grid(True, alpha=0.3)
        ax.tick_params(axis="y", labelsize=8)
        ax.tick_params(axis="x", labelsize=8)
    axes[-1][0].xaxis.set_major_locator(mdates.AutoDateLocator())
    axes[-1][0].xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    first_d, last_d = panels[0][1][0], panels[0][1][-1]
    n_rides = len(panels[0][1])
    title = (f"trackview - training trend       {n_rides} ride{'s' if n_rides != 1 else ''}"
             f"       {first_d:%Y-%m-%d} .. {last_d:%Y-%m-%d}")
    if skipped:
        title += f"       ({skipped} undated ride{'s' if skipped != 1 else ''} skipped)"
    fig.suptitle(title, fontsize=12, fontweight="bold", y=0.985)
    fig.subplots_adjust(hspace=0.45, top=0.93, bottom=0.05)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=DPI, facecolor="white")
    plt.close(fig)
    print(f"  wrote {out_path}       ({out_path.stat().st_size // 1024} KB)")


# The --calendar "activity grid" (a GitHub-style contribution calendar): one 7 (weekday) x
# weeks block per calendar year, each day a square coloured by that day's total of the chosen
# metric.  A metric is (a human label, a sequential colourmap whose *light* end is the "no
# ride" colour), so a busy stretch glows and a rest gap stays pale -- a year (or the whole
# log) at a glance.  The dict order fixes the --calendar-by choices.  The x-axis is labelled
# by month (_month_ticks: a tick at the first week of each month, not by week number), so a
# partial year shows only the months it spans.
_CALENDAR_METRICS = {
    "distance": ("km / day",      "Greens"),
    "gain":     ("m gain / day",  "OrRd"),
    "rides":    ("rides / day",   "Blues"),
}
_MONTH_ABBR = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _calendar_days(tracks, metric="distance", year=None):
    """Per-year day-totals for the --calendar grid: {year: {(iso_week, iso_weekday): value}}.
    Each dated ride adds its `metric` value to the day it was ridden -- distance (km) or gain
    (m), or 1.0 for a ride count -- so a day that saw two rides sums them; the (week, weekday)
    is the ride's ISO week/weekday (week 1..53, Monday=1).  `year`, when given, keeps only that
    one calendar year; else every year that has a dated ride is returned.  A ride with no date
    in its filename can't be placed on the grid, so it is skipped (and counted)."""
    by_year = {}
    skipped = 0
    for t in tracks:
        rd = _ride_date(t["path"])
        if rd is None:
            skipped += 1
            continue
        if year is not None and rd.year != year:
            continue
        if metric == "gain":
            val = t["gain_m"]
        elif metric == "rides":
            val = 1.0
        else:
            val = t["dist_km"]
        iso = rd.isocalendar()
        key = (iso[1], iso[2])
        cell = by_year.setdefault(rd.year, {})
        cell[key] = cell.get(key, 0.0) + val
    return by_year, skipped


def _month_ticks(year, weeks):
    """X-axis ticks for the --calendar grid, one per calendar month: a tick at the week
    that holds the 1st of the month, a GitHub-style month label in place of a week number.
    A month whose 1st falls outside this year's ISO weeks is left off -- a year that begins
    mid-ISO-year skips the January that sits in the previous ISO week, and a month past the
    log's last ride (past `weeks`) never starts -- so a partial year shows only the months
    it actually spans."""
    ticks, labels, seen = [], [], set()
    for m in range(1, 13):
        iso = date(year, m, 1).isocalendar()
        if iso[0] != year:                 # 1st landed in the adjacent ISO year's week
            continue
        w = iso[1]
        if not 1 <= w <= weeks or w in seen:
            continue
        seen.add(w)
        ticks.append(w - 1)
        labels.append(_MONTH_ABBR[m])
    return ticks, labels


def write_calendar(tracks, out_path, metric="distance", year=None):
    """Write a GitHub-style activity grid to out_path: one 7 (weekday) x weeks block per
    calendar year that has rides (stacked top-to-bottom, each labelled with its year), each day
    a square coloured by its total of `metric` (--calendar-by) on a sequential ramp with a pale
    "no ride" end, so busy stretches glow and rest gaps go blank.  The days share one colour
    scale (0 .. the busiest day) so the years compare at a glance.  A standalone figure (no
    basemap, no network), so it writes even under --no-map; undated rides can't be placed and
    are skipped (the title notes how many)."""
    by_year, skipped = _calendar_days(tracks, metric, year)
    if not by_year:
        what = f" in {year}" if year is not None else ""
        print(f"      --calendar: no dated ride to plot{what}.")
        return
    label, cmap = _CALENDAR_METRICS[metric]
    years = sorted(by_year)
    # a common week-width, so a partial year's empty leading/trailing weeks stay pale and
    # the stacked year-blocks line up column-for-column
    weeks = 1
    for cells in by_year.values():
        weeks = max(weeks, max((w for (w, _wd) in cells), default=1))
    vmax = max((v for cells in by_year.values() for v in cells.values()), default=0.0)
    norm = Normalize(vmin=0.0, vmax=max(vmax, 1e-9), clip=True)
    fig, axes = plt.subplots(len(years), 1,
                             figsize=(12.0, 1.7 + 1.5 * len(years)), dpi=DPI,
                             squeeze=False)
    weekday = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    for k, y in enumerate(years):
        ax = axes[k][0]
        arr = np.zeros((7, weeks))
        for (w, wd), val in by_year[y].items():
            if 1 <= w <= weeks and 1 <= wd <= 7:
                arr[wd - 1, w - 1] = val
        im = ax.imshow(arr, cmap=cmap, norm=norm, aspect="auto",
                       origin="upper", interpolation="nearest")
        ax.set_yticks(range(7))
        ax.set_yticklabels(weekday, fontsize=7)
        mticks, mlabels = _month_ticks(y, weeks)
        ax.set_xticks(mticks)
        ax.set_xticklabels(mlabels, fontsize=7)
        # thin white gaps between the squares (the contribution-grid look)
        ax.set_xticks(np.arange(-0.5, weeks, 1), minor=True)
        ax.set_yticks(np.arange(-0.5, 7, 1), minor=True)
        ax.grid(which="minor", color="white", linewidth=0.6, zorder=0)
        ax.tick_params(which="both", length=0)
        # label each year only when stacking more than one (a single block's year is in
        # the suptitle, so we don't print it twice)
        if len(years) > 1:
            ax.set_title(f"{y}", fontsize=11, fontweight="bold",
                         loc="left", x=0.0, pad=5)
    span = years[0] if len(years) == 1 else f"{years[0]}..{years[-1]}"
    title = f"trackview - activity {span}   ({label})"
    if skipped:
        title += f"   ({skipped} undated ride{'s' if skipped != 1 else ''} skipped)"
    fig.suptitle(title, fontsize=12, fontweight="bold", y=0.97)
    fig.subplots_adjust(hspace=0.6, left=0.06, right=0.89, top=0.88, bottom=0.09)
     # one colourbar in the reserved right margin (a single shared 0..busiest-day
     # scale, so the stacked years compare at a glance); its vertical extent is read
     # off the grid itself so the bar lines up with the squares, not the figure edges
    top_ax = axes[0][0].get_position()
    bot_ax = axes[-1][0].get_position()
    cax = fig.add_axes([0.925, bot_ax.y0, 0.013, top_ax.y1 - bot_ax.y0])
    cbar = fig.colorbar(im, cax=cax)
    cbar.set_label(label, fontsize=9)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=DPI, facecolor="white")
    plt.close(fig)
    print(f"  wrote {out_path}")


def _summary_groups(tracks):
    """Split the rides for the --summary year-in-review report: dated rides grouped by
    calendar year then month ({year: {month: [rides]}}), plus an 'undated' list of rides
    whose filename carries no date and so can't be placed by year/month."""
    by_year = {}
    undated = []
    for t in tracks:
        rd = _ride_date(t["path"])
        if rd is None:
            undated.append(t)
        else:
            by_year.setdefault(rd.year, {}).setdefault(rd.month, []).append(t)
    return by_year, undated


def write_summary(tracks, out_path, show_ext: bool = False) -> None:
    """Write a year-in-review report to out_path: the rides grouped by calendar year, and
    within each year by month, each shown with its ride count, total distance, total gain and
    total hours -- and, under --ext as the ride-log does, the group's point-weighted average
    power (a '-' marks a group that carries none).  Each year is its own block of monthly rows
    closed by a TOTAL row; when the log spans several years an 'ALL years' grand total closes
    the report, and any undated rides (no date in the filename, so unplaceable) get a note.
    Pure geometry, so it writes even under --no-map; the avg-power column needs --ext."""
    by_year, undated = _summary_groups(tracks)
    n = len(tracks)
    header = ["Month", "Rides", "Dist (km)", "Gain (m)", "Hours"]
    numeric = [False, True, True, True, True]
    if show_ext:
        header.append("Avg power (W)")
        numeric.append(True)

    def cells(group, label):
        dist = sum(t["dist_km"] for t in group)
        gain = sum(t["gain_m"] for t in group)
        hours = sum(t.get("duration_s", 0.0) for t in group) / 3600.0
        row = [label, f"{len(group):,}", f"{dist:,.0f}", f"{gain:,.0f}",
               f"{hours:,.1f}"]
        if show_ext:
            row.append(_fmt_num(_metric_avg(group, "power"), ",.0f"))
        return row

    def flat(by_year_):
        return [t for y in by_year_.values() for ms in y.values() for t in ms]

    year_rows = {}
    for y in sorted(by_year):
        months = by_year[y]
        rows = [cells(months[m], _MONTH_ABBR[m]) for m in sorted(months)]
        rows.append(cells(flat({y: months}), "TOTAL"))
        year_rows[y] = rows
    grand = None
    if len(by_year) > 1:
        grand = cells(flat(by_year), "ALL years")

    # every row that will print sizes the columns, so the year blocks align
    all_rows = [r for y in sorted(year_rows) for r in year_rows[y]]
    if grand is not None:
        all_rows.append(grand)
    widths = [max(len(header[i]), *[len(r[i]) for r in all_rows])
              for i in range(len(header))]

    def fmt(row):
        return "          ".join(
              (c.rjust(widths[i]) if numeric[i] else c.ljust(widths[i]))
              for i, c in enumerate(row))

    head = "          ".join(
          (h.rjust(widths[i]) if numeric[i] else h.ljust(widths[i]))
          for i, h in enumerate(header))
    rule = "          ".join("-" * w for w in widths)
    lines = [f"trackview - year-in-review   {n} ride{'s' if n != 1 else ''}",
             ""]
    for y in sorted(year_rows):
        lines.append("")
        lines.append(f"{y}")
        lines.append(head)
        lines.append(rule)
        lines += [fmt(r) for r in year_rows[y]]
    if undated:
        ud = sum(t["dist_km"] for t in undated)
        ug = sum(t["gain_m"] for t in undated)
        lines.append("")
        lines.append(f"   {len(undated)} undated ride"
                     f"{'s' if len(undated) != 1 else ''} "
                     f"(no date in the filename, unplaced by year/month): "
                     f"{ud:,.1f} km, {ug:,.0f} m")
    if grand is not None:
        lines.append("")
        lines.append(rule)
        lines.append(fmt(grand))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  wrote {out_path}")


# ---- Self-contained HTML / Leaflet export (TODO [22]) --------------------------
# A single, self-contained .html that draws the rides as inline GeoJSON on a
# Leaflet map: a tile layer (a URL matching --style, that the browser fetches to
# view) plus the routes embedded as GeoJSON LineStrings, start/stop markers,
# popups and a clickable ride list.  No server: the file opens from disk
# (file://) and zooms/pans, complementing the static PNG/PDF.  It is a different
# deliverable from the parent repo's interactive gpx_viewer.py (a Streamlit +
# Folium upload app) -- this is a static, dependency-light, single file.
#
# The Leaflet CSS + JS are inlined by default, so the output is genuinely offline
# and shareable as one file; the download is cached on disk under lib/
# (git-ignored, like the tile cache) so re-renders don't refetch, and a run with
# no network and no cache falls back to a CDN reference (the file then needs
# internet to *view*, but not to generate).   --html-cdn forces the CDN reference.

LEAFLET_VER      = "1.9.4"
LEAFLET_JS_CDN   = f"https://unpkg.com/leaflet@{LEAFLET_VER}/dist/leaflet.js"
LEAFLET_CSS_CDN  = f"https://unpkg.com/leaflet@{LEAFLET_VER}/dist/leaflet.css"
LEAFLET_DIR      = Path(__file__).resolve().parent / "lib"          # cached library (git-ignored)
LEAFLET_TIMEOUT  = 15.0


def _html_escape(s: str) -> str:
    """Escape the HTML-significant characters in a user-derived string (a ride
    name) before it is written into the document's static <title> tag; the ride
    list and popups escape on the client side (the app script's esc())."""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _fetch_text(url: str, cache_path, timeout: float = LEAFLET_TIMEOUT):
    """Fetch `url` as text, caching the download under `cache_path` (so a
    re-render -- or an offline run -- reuses it, as the tile cache does for the
    basemap).  Returns the text, or None when neither a cache nor a fetch
    succeeds (offline with nothing cached), so the caller can fall back to a CDN
    reference instead of hard-failing."""
    if cache_path is not None and cache_path.exists():
        if cache_path.stat().st_size > 0:
            return cache_path.read_text(encoding="utf-8", errors="replace")
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            data = r.read()
    except Exception as exc:                                # offline / unreachable / rate-limited
        print(f"         --html: could not fetch {url} ({type(exc).__name__}); "
                    "falling back to a CDN reference")
        return None
    text = data.decode("utf-8", "replace")
    if cache_path is not None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(text, encoding="utf-8")
    return text


def _load_leaflet(inline: bool = True):
    """The Leaflet CSS + JS for the HTML head, as ready-to-inject head elements.
    When `inline`, the library text is embedded in the .html (a genuinely offline,
    single-file output) using the on-disk cache or a one-time CDN fetch; when it
    can't be obtained (offline, nothing cached) we fall back to a CDN
    <link>/<script> reference so generation still succeeds.  Returns a
    (css_html, js_html, mode) triple, mode being 'inline' or 'cdn'."""
    if inline:
        js = _fetch_text(LEAFLET_JS_CDN, LEAFLET_DIR / "leaflet.js")
        css = _fetch_text(LEAFLET_CSS_CDN, LEAFLET_DIR / "leaflet.css")
        if js and css:
            # keep an (unlikely) embedded closing tag from ending the inlined block
            js = js.replace("</script", "<\\/script")
            css = css.replace("</style", "<\\/style")
            return f"<style>\n{css}\n</style>", f"<script>\n{js}\n</script>", "inline"
    css = f'<link rel="stylesheet" href="{LEAFLET_CSS_CDN}"/>'
    js = f'<script src="{LEAFLET_JS_CDN}"></script>'
    return css, js, "cdn"


def _ride_feature(t, color) -> dict:
    """One ride as a GeoJSON LineString feature: its decimated WGS84 points
    (rounded to ~11 cm, 5 decimals) as [lon, lat] coordinates -- GeoJSON's
    order, the mirror of the (lat, lon) kept on the ride dict -- with the ride's
    name / distance / gain / duration / colour in the properties the map's popups
    and ride list read."""
    coords = [[round(lo, 5), round(la, 5)] for (la, lo) in t.get("ll") or []]
    return {
        "type": "Feature",
        "properties": {
            "name": _title_name(t["name"]),
            "dist_km": round(t["dist_km"], 1),
            "gain_m": round(t["gain_m"]),
            "duration_s": round(t.get("duration_s", 0.0), 1),
            "color": color,
        },
        "geometry": {"type": "LineString", "coordinates": coords},
    }


def _tracks_geojson(tracks) -> dict:
    """The rides as a GeoJSON FeatureCollection: one LineString feature per ride
    that has at least two decimated points, each coloured by its place in
    STRONG_COLORS (so a many-ride overview stays distinct, as the static map's
    flat mode).  A route with fewer than two points contributes nothing."""
    feats = []
    for i, t in enumerate(tracks):
        if len(t.get("ll") or []) < 2:
            continue
        feats.append(_ride_feature(t, STRONG_COLORS[i % len(STRONG_COLORS)]))
    return {"type": "FeatureCollection", "features": feats}


# The app script: builds the Leaflet map from the embedded GeoJSON -- a tile
# layer at the supplied URL, one white-cased coloured route + start/stop markers
# + a popup per ride, a clickable ride list, fit to the data on load.  The four
# __TOKEN__ placeholders are filled by _leaflet_document.
_APP_JS = r"""
(function () {
  var RIDE_DATA = __DATA__;
  var TILE_URL   = __TILE__;
  var ATTRIB     = __ATTR__;
  var TITLE      = __TITLE__;

  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) {
      return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c];
    });
  }
  function fmtDur(s) {
    var h = Math.floor(s / 3600), m = Math.round((s % 3600) / 60);
    return h > 0 ? (h + 'h ' + String(m).padStart(2, '0') + 'm') : (m + 'm');
  }

  var map = L.map('map', { zoomControl: true });
  L.tileLayer(TILE_URL, { attribution: ATTRIB, maxZoom: 19 }).addTo(map);

  document.getElementById('title').innerHTML = '<b>' + esc(TITLE) + '</b>';

  var totalBounds = L.latLngBounds([]);
  var sidebar = document.getElementById('rides');
  var tot = { dist: 0, gain: 0, n: 0 };

  RIDE_DATA.features.forEach(function (f) {
    var p = f.properties;
    var ll = f.geometry.coordinates.map(function (c) { return [c[1], c[0]]; });
    if (!ll.length) return;
    var color = p.color;
    L.polyline(ll, { color: '#ffffff', weight: 6, opacity: 0.85 }).addTo(map);
    var line = L.polyline(ll, { color: color, weight: 3.5, opacity: 0.95 });
    line.addTo(map);
    L.circleMarker(ll[0], { radius: 5, color: '#000', weight: 1,
                            fillColor: '#2ecc40', fillOpacity: 1 }).addTo(map);
    L.circleMarker(ll[ll.length - 1], { radius: 5, color: '#000', weight: 1,
                            fillColor: '#e41a1c', fillOpacity: 1 }).addTo(map);

    var dur = p.duration_s > 0 ? fmtDur(p.duration_s) : '--';
    line.bindPopup('<b>' + esc(p.name) + '</b><br>'
          + p.dist_km.toFixed(1) + ' km &nbsp; + ' + p.gain_m + ' m &nbsp; ' + dur);

    var row = document.createElement('div');
    row.className = 'ride';
    row.innerHTML = '<span class="dot" style="background:' + color + '"></span>'
          + esc(p.name) + ' <span class="muted">' + p.dist_km.toFixed(1) + ' km</span>';
    row.onclick = function () { map.fitBounds(ll, { padding: [30, 30] }); line.openPopup(); };
    sidebar.appendChild(row);

    totalBounds.extend(ll);
    tot.dist += p.dist_km;
    tot.gain += p.gain_m;
    tot.n += 1;
  });

  var sum = document.createElement('div');
  sum.className = 'total';
  sum.innerHTML = '<b>TOTAL</b> &nbsp; ' + tot.n + ' ride'
        + (tot.n === 1 ? '' : 's') + ' &nbsp; ' + tot.dist.toFixed(1)
        + ' km &nbsp; + ' + Math.round(tot.gain) + ' m';
  sidebar.appendChild(sum);

  if (totalBounds.isValid()) map.fitBounds(totalBounds, { padding: [30, 30] });
})();
"""


def _leaflet_document(gj, tile_url, attribution, title, css_html, js_html) -> str:
    """Build the self-contained interactive-map HTML: a Leaflet map (the CSS +
    JS supplied as `css_html`/`js_html` -- inlined or a CDN reference) with the
    rides as inline GeoJSON (`gj`), a tile layer at `tile_url` (attributed), a
    white-cased coloured route + start/stop markers + a popup per ride, a
    clickable ride list, fit to the data on load.  The GeoJSON is embedded as a
    JSON blob with '<' escaped (so a ride name can never close the <script>), and
    the ride names shown in the DOM are HTML-escaped client-side.  Pure -- no I/O;
    the caller writes the returned string to disk."""
    data = json.dumps(gj, separators=(",", ":")).replace("<", "\\u003c")
    js = (_APP_JS
          .replace("__DATA__", data)
          .replace("__TILE__", json.dumps(tile_url))
          .replace("__ATTR__", json.dumps(attribution))
          .replace("__TITLE__", json.dumps(title)))
    style = (
        "html,body{margin:0;height:100%;"
        "font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;}\n"
        "#map{position:absolute;inset:0;}\n"
        "#panel{position:absolute;top:12px;right:12px;z-index:1000;width:250px;"
        "max-height:80%;overflow:auto;background:rgba(255,255,255,0.92);"
        "border-radius:8px;box-shadow:0 1px 4px rgba(0,0,0,0.3);padding:8px 10px;font-size:13px;}\n"
        "#title{font-size:14px;margin-bottom:6px;border-bottom:1px solid #ddd;padding-bottom:6px;}\n"
        ".ride{cursor:pointer;padding:2px 0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}\n"
        ".ride:hover{background:#eef;}\n"
        ".dot{display:inline-block;width:10px;height:10px;border-radius:50%;"
        "margin-right:6px;vertical-align:middle;}\n"
        ".muted{color:#666;}\n"
        ".total{margin-top:6px;padding-top:6px;border-top:1px solid #ddd;}\n"
        "#legend{margin-top:8px;font-size:11px;color:#555;}\n"
    )
    doc = (
        f'<!DOCTYPE html>\n<html lang="en">\n<head>\n'
        '<meta charset="utf-8"/>\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0"/>\n'
        f'<title>{_html_escape(title)}</title>\n'
        f'{css_html}\n'
        f"<style>\n{style}</style>\n"
        f'{js_html}\n'
        '</head>\n<body>\n'
        '<div id="map"></div>\n'
        '<div id="panel">\n'
        '<div id="title"></div>\n<div id="rides"></div>\n'
        '<div id="legend"><span style="color:#2ecc40">&#9679;</span> start &nbsp; '
        '<span style="color:#e41a1c">&#9679;</span> stop</div>\n'
        '</div>\n'
        f'<script>\n{js}\n</script>\n'
        '</body>\n</html>\n'
    )
    return doc


def write_html(tracks, out_path, style: str = "osm",
               inline: bool = True, title=None):
    """Write a self-contained, single-file interactive Leaflet map to out_path:
    the rides as inline GeoJSON on a tile layer (a URL matching `style`, fetched
    by the browser to view), with a white-cased route, start/stop markers, popups
    and a clickable ride list -- so a shareable, zoomable overview complements the
    static PNG/PDF.  The Leaflet CSS + JS are inlined by default (a genuinely
    offline single file, the download cached under lib/ like the tile cache),
    falling back to a CDN reference when the library can't be fetched or is not
    cached (then --html-cdn, or a network, is needed to *view* it).  A ride with
    fewer than two decimated points contributes no route.  Standalone -- no
    basemap fetch, no telemetry -- so it writes even under --no-map."""
    gj = _tracks_geojson(tracks)
    n = len(gj["features"])
    if not n:
        print("         --html: no ride has a route to plot.")
        return
    tile_url = SOURCES.get(style, SOURCES["osm"])
    attrib = ATTRIBUTION.get(style, ATTRIBUTION["osm"])
    if title is None:
        first = _title_name(tracks[0]["name"])
        last = _title_name(tracks[-1]["name"])
        total_km = sum(t["dist_km"] for t in tracks)
        title = (f"trackview - {n} ride{'s' if n != 1 else ''} "
                 f"({first} .. {last}, {total_km:,.0f} km)")
    css_html, js_html, mode = _load_leaflet(inline)
    html = _leaflet_document(gj, tile_url, attrib, title, css_html, js_html)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    how = ("inlined, offline single file" if mode == "inline"
              else "via CDN (needs internet to view)")
    print(f"  wrote {out_path}      ({out_path.stat().st_size // 1024} KB, leaflet {how})")


def _load_basemap(ax, bbox, order, detail, min_var: float = 1.0,
                  retries: int = 3, backoff_s: float = 2.0) -> str:
    """Fall back through tile providers until one shows real tiles.
    A transient fetch failure (a reset or closed connection, common when many
    tiles are pulled at once) is retried a few times with growing backoff; a
    blank fetch (near-zero pixel variance) or an empty response then moves on to
    the next provider, each after a short, polite delay."""
    for key in order:
        ax.clear()
        ax.set_xlim(bbox[0], bbox[2])
        ax.set_ylim(bbox[1], bbox[3])
        ax.set_aspect("equal")
        loaded = False
        for attempt in range(1, retries + 1):
            try:
                cx.add_basemap(ax, zoom=detail, source=SOURCES[key],    # contextily's kwarg is "zoom" (tile level)
                               headers={"User-Agent": USER_AGENT},
                               reset_extent=False)
                loaded = True
                break
            except Exception as exc:                # pragma: no cover
                if attempt < retries:
                    delay = backoff_s * (2 ** (attempt - 1))
                    print(f"  base-map '{key}' attempt {attempt}/{retries} failed "
                          f"({type(exc).__name__}); retrying in {delay:.0f}s")
                    time.sleep(delay)
                else:
                    print(f"  base-map '{key}' failed after {retries} attempts: "
                          f"{type(exc).__name__}: {exc}")
        if not loaded:
            time.sleep(2)
            continue                               # give up on this provider, try the next
        if ax.images:
            arr = np.asarray(ax.images[0].get_array()).astype(float)
            var = float(arr.var())
            if var < min_var:
                print(f"  base-map '{key}' returned blank tiles, trying next")
                time.sleep(2)
                continue
        else:
            print(f"  base-map '{key}' added no image, trying next")
            time.sleep(2)
            continue
        return key
    raise RuntimeError("all base-map sources failed")


def _gallery_grid(n: int) -> tuple:
    """Rows x cols that fit `n` cells with as few empty slots as possible -- a near-
    square mosaic (a 3x3 for the 9 rides the bare --gallery draws, a 2x3 for 5, a
     3x4 for 12, etc.).  The empty trailing slots of a ragged last row are just left
     blank on the sheet."""
    cols = math.ceil(math.sqrt(n))
    rows = math.ceil(n / cols)
    return rows, cols


def _gallery_cell(ax, t, idx, style, detail):
    """Draw one mosaic cell: a single-ride basemap + its white-haloed, flat-coloured
    route with green/red start/stop markers and a name/distance/gain caption above it
     -- the flat per-track look of a --split map, shrunk to a thumbnail.  The tile
    detail (zoom) is auto per cell from the ride's own extent unless `detail` pins it,
    so each ride zooms to itself rather than the whole set.  Returns the basemap
    provider actually loaded, so the figure can attribute every source it used."""
    merc = np.asarray(t["merc"], dtype=float)
    w, s, e, n = (merc[:, 0].min(), merc[:, 1].min(),
                  merc[:, 0].max(), merc[:, 1].max())
    dx, dy = (e - w) * PAD_FRAC, (n - s) * PAD_FRAC
    bbox = (w - dx, s - dy, e + dx, n + dy)
    if detail is None:
        detail = choose_detail(bbox)
    ordered = [style] + [k for k in SOURCES if k != style]
    loaded = _load_basemap(ax, bbox, ordered, detail)

    seg = np.array([[merc[j], merc[j + 1]] for j in range(len(merc) - 1)])
    halo = LineCollection(seg, colors="white", linewidths=3.0, alpha=0.9)
    halo.set_zorder(4)
    ax.add_collection(halo)
    lc = LineCollection(seg, colors=[STRONG_COLORS[idx % len(STRONG_COLORS)]],
                        linewidths=2.2, alpha=0.95)
    lc.set_zorder(5)
    ax.add_collection(lc)
    x0, y0 = merc[0]
    x1, y1 = merc[-1]
    ax.scatter([x0], [y0], s=40, color="lime", edgecolors="k",
               linewidths=0.5, zorder=7)
    ax.scatter([x1], [y1], s=40, color="red", edgecolors="k",
               linewidths=0.5, zorder=7)
    ax.axis("off")
    cap = (f"{_title_name(t['name'])}      "
           f"{t['dist_km']:,.0f} km      ▲ {t['gain_m']:,.0f} m")
    ax.set_title(cap, fontsize=9, pad=3)
    return loaded


def write_gallery(tracks, out_path, style="osm", n=9, detail=None):
    """Tile the `n` most recent rides into one mosaic contact sheet -- a 'recent
    rides' overview without opening N files, the mosaic alternative to --split (one
    image instead of N).  Each cell is a single-ride basemap + route with a caption
    (see _gallery_cell); the rides are the most recent (by filename date) of the
    already --since/--until/--device/--sport/--top-filtered tracks, shown newest-first
    so the top-left cell is the latest ride, and a ride with no date in its name ranks
    last so it drops out of a 'most recent' view first.  A ride with no route (< 2
    points, e.g. a suppressed trainer ride that slipped through) is skipped like the
    map, and an empty set is a no-op -- a line on stdout, nothing written.  A map
    output (a basemap per cell), so it fetches tiles and is skipped under --no-map."""
    def _recency(t):
        rd = _ride_date(t["path"])
        return rd.toordinal() if rd is not None else -1
    routed = [t for t in sorted(tracks, key=_recency, reverse=True)
              if len(t.get("merc") or []) >= 2]
    cells = routed if not n or n >= len(routed) else routed[:n]
    if not cells:
        print("      --gallery: no ride has a route to tile.")
        return
    rows, cols = _gallery_grid(len(cells))
    cell = 3.3                       # inches per cell; a 3x3 -> ~10x11 in, the base size
    fig = plt.figure(figsize=(cols * cell, rows * cell + 0.9), dpi=DPI)
    gs = fig.add_gridspec(rows, cols, hspace=0.24, wspace=0.20,
                          left=0.01, right=0.99, top=0.90, bottom=0.04)
    loaded_keys = []
    for k, t in enumerate(cells):
        r, c = divmod(k, cols)
        ax = fig.add_subplot(gs[r, c])
        loaded_keys.append(_gallery_cell(ax, t, k, style, detail))

    total_km = sum(t["dist_km"] for t in cells)
    total_gain = sum(t["gain_m"] for t in cells)
    if len(cells) > 1:
        span = (f"{_title_name(cells[-1]['name'])} .. "
                f"{_title_name(cells[0]['name'])}")
        title = f"trackview - {len(cells)} most recent rides   ({span})"
    else:
        name = _title_name(cells[0]["name"]) or cells[0]["name"]
        title = f"trackview - {name}   ({total_km:,.0f} km)"
    fig.suptitle(title, fontsize=13, fontweight="bold", y=0.985)

    # one attribution line, a distinct entry per basemap provider actually loaded
    used = "    ·    ".join(
        ATTRIBUTION.get(k, "© OpenStreetMap contributors")
        for k in dict.fromkeys(loaded_keys))
    fig.text(0.006, 0.005, used, fontsize=7, color="#555")
    if detail is not None:
        fig.text(0.994, 0.005, f"detail {detail}", fontsize=7,
                 color="#555", ha="right")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=DPI, facecolor="white")
    plt.close(fig)
    print(f"  wrote {out_path}    ({out_path.stat().st_size // 1024} KB)")


# --------------------------------- entry point --------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(
        description="Render GPX tracks from a folder onto a static map image "
                     "(PNG or PDF).")
    ap.add_argument("--gpx-dir", default=str(GPX_DIR))
    ap.add_argument("--flat", action="store_true",
                    help="look for *.gpx only in --gpx-dir itself, not its subfolders "
                         "(default: recurse into subfolders, so rides organised under a "
                         "year/ or device/ layout are found too)")
    ap.add_argument("--since", metavar="YYYY-MM-DD", default=None,
                    help="only render tracks on/after this date (local, read from the "
                             ".gpx filename); default: no lower bound")
    ap.add_argument("--until", metavar="YYYY-MM-DD", default=None,
                    help="only render tracks on/before this date (local, read from the "
                             ".gpx filename); default: no upper bound")
    ap.add_argument("--today", action="store_true",
                    help="shorthand for '--flat --since <today>': a 'what did I ride "
                             "today?' glance that switches to flat discovery and bounds "
                             "--since to the current calendar day (date.today() at run "
                             "time, never a baked-in constant); it folds into those two "
                             "flags, so it composes with --list, --until and the stats "
                             "path, and is not a map-only flag (a --no-map run honours it)")
    ap.add_argument("--device", metavar="NAME", default=None,
                    help="only render/list rides whose GPX <desc> 'Device:' line is NAME "
                              "(case-insensitive; a ride with no such line is skipped, as an "
                              "undated ride under --since/--until); complements the date "
                              "filter for a mixed-device folder")
    ap.add_argument("--sport", metavar="NAME", default=None,
                    help="only render/list rides whose GPX <desc> 'Sport:' line is NAME "
                              "(case-insensitive; a ride with no such line is skipped); "
                              "complements the date filter for a mixed-sport folder")
    ap.add_argument("--top", type=int, metavar="N", default=None,
                    help="render/stat only the N rides ranked by --by -- a 'best-of' map, "
                              "or a way to keep a huge combined map legible; applied after "
                              "the --since/--until and --device/--sport filters; default: no limit")
    ap.add_argument("--by", choices=list(_TOP_BY), default="recent",
                    help="what --top ranks the rides by: 'km' (the longest), 'gain' (the "
                              "highest elevation gain) or 'recent' (the most recent, the "
                              "default); ties keep date order")

    ap.add_argument("--list", action="store_true",
                    help="print the rides that survive every filter (--since/--until/"
                                 "--device/--sport/--top) -- their name, date, distance "
                                 "and gain -- then stop: a dry-run that fetches no "
                                 "basemap and writes no image or stats, so a filter "
                                 "selection can be previewed cheaply (overrides --sparse)")

    ap.add_argument("--out", default=None,
                    help="output file for the combined map "
                         "(default: output/tracks_overview.<format>)")
    ap.add_argument("--format", choices=["png", "pdf"], default="png",
                    help="image format for the auto-named / split outputs")
    ap.add_argument("--style", choices=list(SOURCES), default="osm")
    ap.add_argument("--detail", type=int, default=None,
                    help=f"basemap detail level: higher = closer / more detail, lower = "
                             f"wider / less detail.  Default: auto-chosen so the track's "
                             f"bbox fills the image, clamped to levels {DETAIL_MIN}-{DETAIL_MAX} "
                             f"(pass an int to override the auto choice)")
    ap.add_argument("--no-elev", action="store_true", help="flat colour, not elevation")
    ap.add_argument("--color-by", choices=["elev", "grade", "flat", "speed", "power"],
                    default="elev",
                    help="what shades the route line: 'elev' (default, the elevation "
                               "ramp), 'grade' (a diverging ramp, steep climbs hot and "
                               "descents cold), 'speed'/'power' (a telemetry ramp, fast/high = hot; needs "
                               "wahoo_to_gpx --ext, else flat), or 'flat' (one distinct colour per track); "
                               "--no-elev is shorthand for 'flat'")
    ap.add_argument("--grade-cap", type=float, default=None, metavar="N",
                    help="pin the grade colour range to +/-N%% (overrides the auto "
                              "percentile cap); a few rides then get their own "
                              "colourbar, beyond which one shared scale is used")
    ap.add_argument("--split", action="store_true",
                    help="one map file per track (default: all tracks in one file)")
    ap.add_argument("--profile", action="store_true",
                    help="add a 'ride card' below the map: an elevation + grade vs. "
                            "distance panel plus a slim mini-panel each for power, "
                            "speed, HR and cadence when the ride carries telemetry "
                            "(auto-collected -- no --ext on the line needed); needs "
                            "--split, or a single track -- one card per ride)")
    ap.add_argument("--gallery", type=int, nargs="?", const=9, metavar="N",
                    default=None,
                    help="instead of one combined (or --split) map, tile the N most "
                               "recent rides into a single mosaic contact sheet -- a "
                               "'recent rides' overview without opening N files; N "
                               "defaults to 9 (a 3x3).  Each cell is that ride's own "
                               "basemap + route (the flat per-track look of a --split "
                               "cell) with a name/distance/gain caption.  A map output, "
                               "so it fetches tiles and is skipped under --no-map; --split "
                               "is ignored when --gallery is set (it is the mosaic instead)")
    ap.add_argument("--ext", action="store_true",
                    help="add the calories-burned total (kcal) to the title and an avg "
                           "power/speed/cadence/hr line below it, from wahoo_to_gpx --ext telemetry (calories = avg power x ride duration / efficiency; ignored when absent)")
    ap.add_argument("--no-map", action="store_true",
                    help="skip map/image generation (no basemap fetch or output "
                            "image); just compute the stats and write the ride-log to "
                            "stats/.   The map-only flags --out/--format/--style/--detail/"
                            "--split/--gallery/--no-elev/--color-by/--grade-cap/--profile/--heat/"
                             "--labels/--no-scale/--no-cache are then ignored)")
    ap.add_argument("--csv", action="store_true",
                    help="also write a CSV ride-log to stats/ (a header row + one row "
                              "per ride, the same columns as the ride-log but no totals "
                              "row); its field delimiter is --csv-delimiter")
    ap.add_argument("--csv-delimiter", default=";",
                    help="field delimiter for the --csv file (default ';', the "
                              "European/Excel default); e.g. ',' for comma-separated")
    ap.add_argument("--sparse", action="store_true",
                    help="quiet stdout: skip the per-track stats listing (one line per "
                             "read ride); print only the summary lines - where it reads, "
                             "the track count, and the files written (plus any date-filter "
                              "skips when --since/--until is active)")
    ap.add_argument("--no-scale", action="store_true",
                    help="omit the map's scale bar (a 'N km' bar in the lower-right, "
                               "on by default); a map-only flag, ignored with --no-map")
    ap.add_argument("--no-cache", action="store_true",
                    help="fetch basemap tiles fresh each run (default: cache them on disk "
                                 "under tiles/, keyed by z/x/y, so re-renders and offline runs reuse "
                                 "them; a map-only flag, ignored with --no-map")
    ap.add_argument("--heat", action="store_true",
                    help="overlay a 2-D 'time on route' density under the routes (a "
                                "YlOrRd heatmap, brighter where you spend the most time or "
                                "ride most; weighted by point timestamps when --ext, else by "
                                "point count); a map-only flag, ignored with --no-map")
    ap.add_argument("--labels", action="store_true",
                    help="label each route with its name + distance near its start marker "
                                "(a halo'd tag, for a combined multi-ride map); ignored when "
                                "one track (the name is already in its title); a map-only flag, "
                                "ignored with --no-map")

    ap.add_argument("--gain-noise", type=float, default=0.0, metavar="M",
                    help="ignore GPS vertical jitter when summing ascent: a descent must "
                               "exceed M metres (default 0 = raw, every rising segment) "
                               "before it ends the climb in progress")
    ap.add_argument("--climbs", nargs="?", const=10, type=int, default=None, metavar="N",
                    help="also write a climb ranking (top N by gain x avg grade, default "
                               "10) to stats/trackview-<range>_climbs.txt; grade is "
                               "geometry-derived, so it works even with --no-map")
    ap.add_argument("--trend", action="store_true",
                    help="also write a per-ride training-trend chart over ride date -- "
                                 "distance, gain, duration, and a calories-burned panel when a "
                                 "power average is available -- to "
                                 "output/trackview-<range>_trend.<format>; a standalone figure "
                                 "(no basemap), so it writes even with --no-map")
    ap.add_argument("--calendar", action="store_true",
                    help="also write a GitHub-style activity grid -- one square per calendar "
                          "day, coloured by that day's total of --calendar-by, one 7xweeks block "
                          "per year that has rides -- to "
                          "output/trackview-<range>_calendar.<format>; a standalone figure "
                          "(no basemap), so it writes even with --no-map")
    ap.add_argument("--calendar-by", choices=list(_CALENDAR_METRICS), default="distance",
                    help="what colours each day of the --calendar grid: 'distance' (default, km "
                          "ridden that day), 'gain' (metres of ascent) or 'rides' (how many "
                          "rides that day)")
    ap.add_argument("--year", type=int, default=None, metavar="YYYY",
                    help="restrict --calendar to a single calendar year (default: every year "
                          "that has rides, stacked one block each)")
    ap.add_argument("--summary", action="store_true",
                    help="also write a year-in-review report to "
                          "stats/trackview-<range>_summary.txt: the rides grouped by year (and "
                          "month) with their ride count, total distance, gain and hours, plus "
                          "avg power under --ext; pure geometry, so it works even with --no-map")
    ap.add_argument("--html", action="store_true",
                    help="also write a self-contained, single-file interactive "
                            "Leaflet map -- the rides as inline GeoJSON on a tile "
                            "layer (matching --style), with start/stop markers, popups "
                            "and a clickable ride list -- to "
                            "output/trackview-<range>_map.html; zoomable and shareable "
                            "with no server, a complement to the static PNG/PDF.  The "
                            "Leaflet library is inlined (a genuinely offline single "
                            "file, cached under lib/); a standalone output, so it "
                            "writes even with --no-map")
    ap.add_argument("--html-cdn", action="store_true",
                    help="reference Leaflet from a CDN instead of inlining it into the "
                            "--html file: a smaller .html that needs internet to view "
                            "(default: inline it for a genuinely offline single file)")
    args = ap.parse_args()

    if args.csv and not args.csv_delimiter:
        raise SystemExit("error: --csv-delimiter must be a non-empty character")

      # --today is the shorthand for '--flat --since <today>' -- a one-flag "what did I
      # ride today?" glance.  It folds into the two existing knobs -- flat discovery
      # (today's rides sit at the top level of the folder) and a --since bound at the
      # current calendar day -- so every downstream reader (the date filter, --list, the
      # stats path) sees the narrow selection transparently, and it composes with --list
      # (a no-fetch dry-run of today's rides) and --no-map.  The date is date.today() at
      # run time, never a baked-in constant.
    if args.today:
        args.flat = True
        args.since = date.today().isoformat()
        print(f"        --today: flat discovery + since {args.since} (today's rides)")

    gpx_dir = Path(args.gpx_dir)
       # By default the search recurses into subfolders (rglob), so rides organised
       # under a year/ or device/ layout are found too; --flat restricts it to
       # --gpx-dir itself (the old single-level glob).  Either way the (recursive)
       # glob stays date-ascending, because the Wahoo filename embeds the ride date,
       # so the ride-log and the trackview-<first>_<last> filename read as usual.
    recurse = not args.flat
    print(f"trackview - reading *.gpx{' recursively' if recurse else ''} from {gpx_dir}")
    paths = sorted(gpx_dir.rglob("*.gpx") if recurse else gpx_dir.glob("*.gpx"))

     # date filter: Wahoo-style .gpx names carry the ride start date (local) in the
     # stem, so --since/--until select by that (mirrors wahoo_to_gpx.py).  A name with
     # no date is skipped (never guessed) when a bound is active.
    lo = _parse_argdate(args.since, "--since") if args.since else None
    hi = _parse_argdate(args.until, "--until") if args.until else None
    if lo or hi:
        lo_s = lo.isoformat() if lo else "any"
        hi_s = hi.isoformat() if hi else "any"
        kept, out_of_range, undated = [], [], []
        for p in paths:
            rd = _ride_date(p)
            if rd is None:
                undated.append(p)
            elif (lo and rd < lo) or (hi and rd > hi):
                out_of_range.append(p)
            else:
                kept.append(p)
        paths = kept
        for p in undated:
            print(f"  skip (date not in filename): {p.name}")
        n_total = len(kept) + len(out_of_range) + len(undated)
        if out_of_range:
            print(f"    --since/--until: {len(kept)}/{n_total} track(s) in range "
                  f"{lo_s}..{hi_s}")
        if not paths:
            print(f"No tracks within {lo_s}..{hi_s} - nothing to render.")
            return

    color_by = "flat" if args.no_elev else args.color_by
        # Per-point telemetry (power/speed/hr/cadence) is auto-collected for the
        # features that need it: --color-by speed/power shade by it, --profile's
        # ride card plots it, --heat's density wants point timestamps, and --trend's
        # calories panel needs a power average.  The map-only ones (speed/power,
        # profile, heat) collect only when a map is drawn; --trend is standalone (a
        # --no-map run still charts it), so it always collects.     --ext additionally
        # gates the avg-telemetry title line and the ride-log columns.
    want_ext = args.ext or args.trend or (not args.no_map
                  and (color_by in ("speed", "power") or args.heat or args.profile))
    tracks = load_tracks(paths, DECIMATE_M, with_ext=want_ext, noise_m=args.gain_noise)
    if not tracks:
        print(f"No *.gpx found in {gpx_dir}"
              f"{' (or its subfolders)' if recurse else ''} - nothing to render.")
        return

      # --device/--sport narrow the rides to one device and/or sport (each matched on
      # its own parsed <desc> 'Device:'/'Sport:' line, case-insensitively), complementing
      # the --since/--until date filter for a mixed-device/sport folder.  Filtering the
      # `tracks` list here means every downstream reader - the map, the ride-log/CSV and
      # the stats/ reports - sees only the kept rides; a ride missing the line an active
      # filter names is skipped, and when nothing matches we stop (nothing to render).
    if args.device or args.sport:
        tracks = _filter_by_meta(tracks, args.device, args.sport)
        if not tracks:
            print("      no track matches the --device/--sport filter - nothing to render.")
            return

      # --top N --by {km,gain,recent} keep only the N most-significant rides -- a
      # 'best-of' map, or a way to keep a huge combined map legible -- ranked by distance
      # ('km'), elevation gain ('gain') or recency ('recent', the default).  It runs
      # *after* every other filter (the --since/--until range and the --device/--sport
      # filter above), so it selects the top N of whatever rides remain; filtering the
      # `tracks` list here means the map, the ride-log/CSV and the stats/ reports all see
      # only the selected rides, which _select_top re-sorts back into date order so the
      # ride-log and the stats filename read as usual.
    if args.top is not None:
        kept = _select_top(tracks, args.top, args.by)
        if len(kept) < len(tracks):
            print(f"         --top {args.top} --by {args.by}: {len(kept)}/{len(tracks)} "
                  f"ride(s) kept (the {args.top} {_TOP_BY[args.by]})")
        tracks = kept

    if args.list:
        # --list is a dry-run preview: list the rides that survive every filter
        # and stop -- no basemap fetch, no image and no stats/CSV/report write, so
        # a --since/--until/--device/--sport/--top selection can be previewed
        # cheaply; it prints its own listing, so it is not gated on --sparse.
        _list_rides(tracks)
        return

    print(f"   {len(tracks)} track(s), "
          f"{sum(t['n'] for t in tracks):,} pts -> "
          f"{sum(t['ndec'] for t in tracks):,} after {DECIMATE_M:.0f} m decimation")
    if not args.sparse:
        for t in tracks:
            print(f"     - {t['name']:<20s} {t['dist_km']:6.1f} km     "
                  f"+{t['gain_m']:6.0f} m     {t['n']:>6,} -> {t['ndec']:>5,} pts")

    if args.no_map:
        print("      --no-map: skipping map generation (stats + ride-log only)")
    else:
        out_dir = Path(args.out).parent if args.out is not None else OUTPUT_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        split_prefix = (f"{_safe_filename(Path(args.out).stem)}_" if args.out else "")

         # Basemap tiles are cached to disk under tiles/ (contextily's on-disk tile
         # cache, keyed by z/x/y per provider), so re-renders and offline runs reuse
         # them instead of refetching every tile; --no-cache fetches fresh instead
         # (contextily's ephemeral per-session cache, the old behaviour).
        if not args.no_cache:
            TILE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cx.set_cache_dir(str(TILE_CACHE_DIR))
            if not args.sparse:
                print(f"       tile cache: {TILE_CACHE_DIR} "
                          "(re-renders reuse downloaded tiles; --no-cache fetches fresh)")

        # a stationary-trainer 'Kickr Snap' session has no route of its own, so
        # it would just clutter the basemap; keep such tracks off the image while
        # the ride-log/CSV still list them (a trainer ride is still a ride)
        suppressed = [t for t in tracks if t.get("device") in SUPPRESSED_RENDER_DEVICES]
        render_tracks = [t for t in tracks if t.get("device") not in SUPPRESSED_RENDER_DEVICES]
        if suppressed:
            print(f"      suppressing {len(suppressed)} 'Kickr Snap' track(s) from the map "
                  f"(still in the ride-log)")

        profile = args.profile
        if profile and not args.split and len(render_tracks) != 1:
            print("        --profile draws one distance profile, so it needs --split "
                    "(or a single track); skipping the profile panel")
            profile = False
        elif profile and not any(_has_metric_pts(t, m[0])
                                         for t in render_tracks for m in PROF_METRICS):
                  # --profile auto-collects the per-point telemetry the ride card's
                  # mini-panels plot; with none (e.g. a plain komoot track, no --ext)
                  # the card falls back to elevation + grade only
            print("          --profile: no ride carries per-point telemetry "
                              "(need wahoo_to_gpx --ext); each card shows elevation + grade only")

        if not render_tracks:
            print("      no tracks left to render after suppression.")
        elif args.gallery is not None:
             # a mosaic of the N most recent rides -- the --split alternative (one
             # image instead of N files); --out names the single file, else the
             # dated auto name in output/
            glabel = _safe_filename(f"{_title_name(render_tracks[0]['name'])}_"
                                   f"{_title_name(render_tracks[-1]['name'])}")
            out_path = (Path(args.out) if args.out is not None
                        else out_dir / f"trackview-{glabel}_gallery.{args.format}")
            print(f"       --gallery: {args.gallery} most recent ride(s) -> '{out_path.name}'")
            write_gallery(render_tracks, out_path, style=args.style,
                          n=args.gallery, detail=args.detail)
        elif args.split:
            if args.out:
                print(f"        --split + --out: each file -> '{split_prefix}<ride>.{args.format}' in {out_dir}")
            for t in render_tracks:
                out_path = out_dir / f"{split_prefix}{_safe_filename(Path(t['path']).stem)}.{args.format}"
                render([t], style=args.style, out_path=out_path, detail=args.detail,
                       color_by=color_by, show_ext=args.ext, split=True,
                       profile=profile, grade_cap=args.grade_cap,
                       scale=not args.no_scale,
                       heat=args.heat, labels=args.labels)
        else:
            out_path = (Path(args.out) if args.out is not None
                        else out_dir / f"tracks_overview.{args.format}")
            render(render_tracks, style=args.style, out_path=out_path, detail=args.detail,
                   color_by=color_by, show_ext=args.ext, profile=profile,
                   grade_cap=args.grade_cap, scale=not args.no_scale,
                   heat=args.heat, labels=args.labels)

     # a per-run ride-log -> ./stats/trackview-<first>_<last ride date>.txt, holding
     # the two title headers' stats as a table, one row per ride, plus a totals row
    first = _title_name(tracks[0]["name"])        # earliest ride (the glob is date-ascending)
    last   = _title_name(tracks[-1]["name"])       # latest ride
    label  = _safe_filename(f"{first}_{last}")
    stats_path = STATS_DIR / f"trackview-{label}.txt"
    write_stats(tracks, stats_path, show_ext=args.ext)

     # --csv: the same ride-log as CSV (header + one row per ride, no totals row),
     # written next to the .txt; the field delimiter is --csv-delimiter (default ';')
    if args.csv:
        csv_path = STATS_DIR / f"trackview-{label}.csv"
        write_csv(tracks, csv_path, show_ext=args.ext, delimiter=args.csv_delimiter)

       # --climbs: a climb ranking -> ./stats/trackview-<first>_<last ride date>_climbs.txt,
       # the top N most-significant sustained climbs (gain x avg grade); pure geometry, so
       # it works even with --no-map
    if args.climbs is not None:
        climbs_path = STATS_DIR / f"trackview-{label}_climbs.txt"
        write_climbs(tracks, climbs_path, top_n=args.climbs)

      # --summary: a year-in-review report -> ./stats/trackview-<first>_<last ride
      # date>_summary.txt, the rides grouped by year (and month) with their ride
      # count, total distance, gain and hours (plus avg power under --ext, as the
      # ride-log does); pure geometry, so it works even with --no-map.
    if args.summary:
        summary_path = STATS_DIR / f"trackview-{label}_summary.txt"
        write_summary(tracks, summary_path, show_ext=args.ext)

        # --trend: a per-ride training-trend chart over ride date (distance, gain,
        # duration, plus a calories-burned panel when any ride carries a power
        # average); a standalone figure (no basemap), so it writes even under
        # --no-map, alongside the stats/ ride-log.    --trend auto-collects the
        # telemetry the calories panel needs (see want_ext above).
    if args.trend:
        trend_path = OUTPUT_DIR / f"trackview-{label}_trend.{args.format}"
        write_trend(tracks, trend_path)

       # --calendar: a GitHub-style activity grid -> ./output/trackview-<first>_<last
       # ride date>_calendar.<format>, one square per calendar day coloured by
       # --calendar-by, one 7xweeks block per year that has rides; a standalone figure
       # (no basemap), so it writes even under --no-map, alongside the --trend chart.
    if args.calendar:
        cal_path = OUTPUT_DIR / f"trackview-{label}_calendar.{args.format}"
        write_calendar(tracks, cal_path, metric=args.calendar_by, year=args.year)

        # --html: a self-contained, single-file interactive Leaflet map ->
        # ./output/trackview-<first>_<last ride date>_map.html: the rides as inline
        # GeoJSON on a tile layer (matching --style), start/stop markers, popups and a
        # clickable ride list.  A standalone output (no basemap fetch, no telemetry),
        # so it writes even under --no-map; the Leaflet library is inlined by default
        # (a genuinely offline single file, cached under lib/) and --html-cdn references
        # it from a CDN instead.
    if args.html:
        html_path = OUTPUT_DIR / f"trackview-{label}_map.html"
        write_html(tracks, html_path, style=args.style, inline=not args.html_cdn)


if __name__ == "__main__":
    main()

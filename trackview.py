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
    python trackview.py --profile --split    # add an elevation + grade profile under each map
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
    python trackview.py --csv                # also write a CSV ride-log (header + rows, no totals) to stats/
    python trackview.py --csv --csv-delimiter ,    # comma-separated instead of the default ';'
    python trackview.py --sparse               # quiet stdout: skip the per-track stats listing
    python trackview.py --gain-noise 1.5       # ignore GPS vertical jitter (a dip must exceed 1.5 m) when summing ascent
    python trackview.py --climbs 10            # also write a climb ranking (top N by gain x avg grade) to stats/
    python trackview.py --no-scale             # omit the map's lower-right scale bar (on by default)
"""
from __future__ import annotations

import argparse
import csv
import math
import os
import re
import time
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

# ------------------------------- configuration -------------------------------
GPX_DIR     = Path(__file__).resolve().parent / "gpx"
OUTPUT_DIR  = Path(__file__).resolve().parent / "output"
STATS_DIR   = Path(__file__).resolve().parent / "stats"

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
def latlon_to_merc(lat: float, lon: float) -> tuple[float, float]:
    """WGS84 (lat, lon) -> Web-Mercator (x, y) in metres."""
    x = lon * PI_R / 180.0
    y = math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)) * PI_R / math.pi
    return x, y


def decimate(points, min_m: float, carry=None):
    """Keep only points spaced >= min_m apart (equirectangular distance).  Returns the kept
    points; when `carry` (a parallel sequence, one entry per point -- e.g. the per-point
    telemetry) is given, its kept entries are returned too, aligned with the kept points."""
    if len(points) < 2:
        return points, (carry if carry is not None else None)
    n = len(points)
    keep = [0]
    last_lat, last_lon = points[0][0], points[0][1]
    min_m2 = min_m * min_m
    for i in range(1, n):
        lat, lon = points[i][0], points[i][1]
        lat_mid = math.radians((lat + last_lat) / 2.0)
        dx = (lon - last_lon) * 111320.0 * math.cos(lat_mid)
        dy = (lat - last_lat) * 110540.0
        if dx * dx + dy * dy >= min_m2:
            keep.append(i)
            last_lat, last_lon = lat, lon
    keep.append(n - 1)                     # always keep the last point
    out = [points[i] for i in keep]
    if carry is not None:
        return out, [carry[i] for i in keep]
    return out, None


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


_NAME_DATE_RE = re.compile(r"^(\d{4})_(\d{2})_(\d{2})(?=_|$)")
# `wahoo_to_gpx` stamps a "Device: <name>" line into the GPX <desc> (e.g.
# "Wahoo ELEMNT BOLT", "Kickr Snap"); a plain komoot track has no such line.
_DEVICE_RE = re.compile(r"(?im)^\s*Device:\s*(.+)$")


def _title_name(name: str) -> str:
    """For a --split single-track title, show a Wahoo-style date stem
    (e.g. 2026_09_11_08_07_29) as just its calendar date (2026-09-11); any other
    name (a descriptive komoot title) passes through unchanged."""
    m = _NAME_DATE_RE.match(name)
    if not m:
        return name
    try:
        return date(int(m[1]), int(m[2]), int(m[3])).isoformat()
    except ValueError:
        return name


def _ride_date(path: Path) -> date | None:
    """Calendar date of a ride, read from the .gpx filename stem
    (YYYY_MM_DD_HH_MM_SS, local time) - no GPX parse needed.  None when the
    name isn't Wahoo-shaped, so a date filter can skip it rather than guess."""
    m = _NAME_DATE_RE.match(path.stem)
    if not m:
        return None
    try:
        return date(int(m[1]), int(m[2]), int(m[3]))
    except ValueError:
        return None


def _device_type(desc: str | None) -> str | None:
    """Device type embedded by `wahoo_to_gpx` as a 'Device: <name>' line in the
    GPX <desc> (e.g. 'Wahoo ELEMNT BOLT', 'Kickr Snap'); None when the track
    carries no such line (e.g. a plain komoot track)."""
    m = _DEVICE_RE.search(desc) if desc else None
    return m.group(1).strip() if m else None


def _device_label(device: str | None) -> str:
    """Cell text for the ride-log 'Device' column; 'unknown' when the track
    carries no Device line (e.g. a plain komoot track)."""
    return device or "unknown"


def _device_groups(tracks) -> list[tuple[str, list]]:
    """Split the rides into (device label, [rides]) groups in first-seen order
    (the glob is date-sorted), so the ride-log can print one totals row per
    device type.  A ride with no device line falls in its own 'unknown' group."""
    order: list[str] = []
    groups: dict[str, list] = {}
    for t in tracks:
        label = _device_label(t.get("device"))
        if label not in groups:
            groups[label] = []
            order.append(label)
        groups[label].append(t)
    return [(lbl, groups[lbl]) for lbl in order]


# A "Kickr Snap" is a stationary smart trainer: its session has no route of its
# own, so its points would just clutter the basemap.  Keep such tracks off the
# rendered image, matched case-sensitively against the trimmed 'Device:' line -
# they are still listed in the ride-log/CSV (a trainer ride is still a ride).
SUPPRESSED_RENDER_DEVICES = {"Kickr Snap"}


def _parse_argdate(s: str, flag: str) -> date:
    """Parse a 'YYYY-MM-DD' CLI date, aborting with a clear error if malformed."""
    try:
        return date.fromisoformat(s)
    except ValueError:
        raise SystemExit(f"error: {flag} {s!r} is not a YYYY-MM-DD date")


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
        grade, cum_km = _grade_and_cumkm(dec)
        name = (gpx.name or (gpx.tracks[0].name if gpx.tracks
                              and gpx.tracks[0].name else None)
                 or Path(path).stem)
        device = _device_type(gpx.description)           # "Device: <name>" line, if any
        d = {"path": path, "name": name, "device": device, "merc": merc, "ele": ele,
              "n": len(raw), "ndec": len(dec),
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
        tracks.append(d)
    return tracks


def _distance_and_gain(points, noise_m: float = 0.0) -> tuple[float, float]:
    """Total distance (km) and positive elevation gain (m).  The gain is the sum of the
    rises; a descent ends the climb in progress (resetting its base) only once it exceeds
    noise_m metres, so a few cm of GPS vertical jitter can't be counted as fresh ascent on
    the way back up.  noise_m = 0 counts every rising segment - the raw ascent."""
    dist = 0.0
    gain = 0.0
    base = last = None                        # base/last (m) of the climb in progress
    for i in range(1, len(points)):
        la0, lo0, e0 = points[i - 1]
        la1, lo1, e1 = points[i]
        lat_mid = math.radians((la0 + la1) / 2.0)
        dx = (lo1 - lo0) * 111320.0 * math.cos(lat_mid)
        dy = (la1 - la0) * 110540.0
        dist += math.hypot(dx, dy)
        if e0 is None or e1 is None:          # some GPX points omit elevation
            base = last = None
            continue
        if base is None:
            base = last = e0
        if e1 > last:
            last = e1                         # track the top of the climb
        elif last - e1 >= noise_m:            # a descent past the band ends the climb
            gain += last - base
            base = e1
            last = e1
    if base is not None:
        gain += last - base                   # commit the climb still open at the end
    return dist / 1000.0, gain


def _grade_and_cumkm(points) -> tuple[list, list]:
    """Per-segment grade (%) and per-point cumulative distance (km) of an
      equirectangular (lat, lon, ele) track.  A segment's grade is its rise over
      its horizontal run, x100; a segment with a missing end-elevation or a zero
      run is None.  Cumulative distance is the running metre total over every
      segment, reported in km at each point."""
    grades = []
    cum = [0.0]
    dist = 0.0
    for i in range(1, len(points)):
        la0, lo0, e0 = points[i - 1]
        la1, lo1, e1 = points[i]
        lat_mid = math.radians((la0 + la1) / 2.0)
        dx = (lo1 - lo0) * 111320.0 * math.cos(lat_mid)
        dy = (la1 - la0) * 110540.0
        run = math.hypot(dx, dy)
        dist += run
        cum.append(dist / 1000.0)
        if e0 is not None and e1 is not None and run > 0.0:
            grades.append((e1 - e0) / run * 100.0)
        else:
            grades.append(None)
    return grades, cum


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


_UNSAFE_CHARS = re.compile(r'[<>:"/\\|?*\s]+')


def _safe_filename(name: str) -> str:
    """Make a GPX file stem safe to use as an output filename."""
    cleaned = _UNSAFE_CHARS.sub("_", name).strip("._")
    return cleaned or "track"


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

def _draw_profile(ax, t) -> None:
    """Elevation + grade vs. cumulative distance for one track (grade on a twin
      axis): the classic ride-profile silhouette drawn under the map."""
    km = np.array(t.get("cum_km") or [0.0], dtype=float)
    ele = t.get("ele") or []
    if km.size < 2:
        return
    el = np.array([(e if e is not None else np.nan) for e in ele], dtype=float)
    ax.plot(km, el, color="#444", lw=1.1, zorder=2)
    base = np.nanmin(el) if np.isfinite(el).any() else 0.0
    ax.fill_between(km, base, el, color="#444", alpha=0.18, zorder=1)
    ax.set_ylabel("Elevation (m)", fontsize=9)
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


def _short_label(name, width=16) -> str:
    """Compact per-ride label for a stacked colourbar: _title_name, truncated with an ellipsis so the bar stays narrow."""
    s = _title_name(name) or str(name)
    return s if len(s) <= width else s[: width - 1] + "…"

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
    # imshow(aspect="auto") flips the *axes* to auto; restore the map's equal aspect
    # so the routes and the scale bar (a true on-screen distance) stay undistorted.
    prev_aspect = ax.get_aspect()
    im = ax.imshow(H, extent=[w, s, e, n], origin="lower", aspect="auto",
                   cmap="YlOrRd", norm=norm, alpha=alpha, zorder=3,
                   interpolation="bilinear")
    ax.set_aspect(prev_aspect)
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
    bbox = fit_aspect((w0 - dx, s0 - dy, e0 + dx, n0 + dy), FIGURE_IN[0] / FIGURE_IN[1])
    if detail is None:
        detail = choose_detail(bbox)

    elev = [e for t in tracks for e in t["ele"] if e is not None]
    elev_min, elev_max = (min(elev), max(elev)) if elev else (0.0, 1.0)

    if profile and len(tracks) == 1:
         # a distance profile (elevation + grade) rides in a slim panel below the map
        fig = plt.figure(figsize=(FIGURE_IN[0], FIGURE_IN[1] * 1.35), dpi=DPI)
        gs = fig.add_gridspec(2, 1, height_ratios=[3, 1], hspace=0.12)
        ax = fig.add_subplot(gs[0])
        ax_prof = fig.add_subplot(gs[1])
        _draw_profile(ax_prof, tracks[0])
    else:
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


# --------------------------------- entry point --------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(
        description="Render GPX tracks from a folder onto a static map image "
                     "(PNG or PDF).")
    ap.add_argument("--gpx-dir", default=str(GPX_DIR))
    ap.add_argument("--since", metavar="YYYY-MM-DD", default=None,
                    help="only render tracks on/after this date (local, read from the "
                             ".gpx filename); default: no lower bound")
    ap.add_argument("--until", metavar="YYYY-MM-DD", default=None,
                    help="only render tracks on/before this date (local, read from the "
                             ".gpx filename); default: no upper bound")
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
                    help="add an elevation + grade vs. distance profile panel below "
                            "the map (needs --split, or a single track: one profile "
                            "per ride)")
    ap.add_argument("--ext", action="store_true",
                    help="add the calories-burned total (kcal) to the title and an avg "
                           "power/speed/cadence/hr line below it, from wahoo_to_gpx --ext telemetry (calories = avg power x ride duration / efficiency; ignored when absent)")
    ap.add_argument("--no-map", action="store_true",
                    help="skip map/image generation (no basemap fetch or output "
                            "image); just compute the stats and write the ride-log to "
                            "stats/.   The map-only flags --out/--format/--style/--detail/"
                            "--split/--no-elev/--color-by/--grade-cap/--profile/--heat/"
                             "--labels/--no-scale are then ignored)")
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
    args = ap.parse_args()

    if args.csv and not args.csv_delimiter:
        raise SystemExit("error: --csv-delimiter must be a non-empty character")

    gpx_dir = Path(args.gpx_dir)
    print(f"trackview - reading *.gpx from {gpx_dir}")
    paths = sorted(gpx_dir.glob("*.gpx"))

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
     # --color-by speed/power need per-point telemetry; --heat wants point
      # timestamps -- both auto-enable the per-point collection (with_ext),
      # unless --no-map (a stats-only run ignores the map-only flags)
    want_ext = args.ext or (not args.no_map
                  and (color_by in ("speed", "power") or args.heat))
    tracks = load_tracks(paths, DECIMATE_M, with_ext=want_ext, noise_m=args.gain_noise)
    if not tracks:
        print("No *.gpx files found - nothing to render.")
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

        if not render_tracks:
            print("      no tracks left to render after suppression.")
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
    first = _title_name(tracks[0]["name"])        # earliest ride (glob is date-sorted)
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

if __name__ == "__main__":
    main()

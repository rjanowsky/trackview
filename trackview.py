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
    python trackview.py --style sat    # Esri satellite base map
    python trackview.py --zoom 15      # override the auto-chosen zoom
    python trackview.py --no-elev      # flat colour instead of elevation shading
    python trackview.py --ext          # add avg power/speed/cadence/hr + calories burned (kcal) to the title
"""
from __future__ import annotations

import argparse
import glob
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
from matplotlib.colors import Normalize
from matplotlib.lines import Line2D

# ------------------------------- configuration -------------------------------
GPX_DIR     = Path(__file__).resolve().parent / "gpx"
OUTPUT_DIR  = Path(__file__).resolve().parent / "output"

DECIMATE_M  = 5.0       # drop track points closer than this (m): keeps the shape,
                        # cuts ~68k points to a few thousand for crisp, fast drawing
PAD_FRAC    = 0.10      # blank margin around the tracks (fraction of bbox)
DPI         = 150
FIGURE_IN   = (11, 11)  # square, so the map image is never letter-boxed
CMAPEL      = "terrain" # colour ramp for elevation
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
USER_AGENT  = "trackview/1.0 (static GPX->map renderer; contact: user@example.com)"

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
EQUATOR   = 40075016.686            # 2*pi*R: equatorial circumference, used for zoom
JOULES_PER_KCAL = 4184.0        # 1 dietary "kcal" (as on food labels) = 4184 J
METABOLIC_EFFICIENCY = 0.25     # only ~25% of food energy -> pedal work; rest is heat


# --------------------------------- helpers -----------------------------------
def latlon_to_merc(lat: float, lon: float) -> tuple[float, float]:
    """WGS84 (lat, lon) -> Web-Mercator (x, y) in metres."""
    x = lon * PI_R / 180.0
    y = math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)) * PI_R / math.pi
    return x, y


def decimate(points, min_m: float):
    """Keep only points spaced >= min_m apart (equirectangular distance)."""
    if len(points) < 2:
        return points
    out = [points[0]]
    last_lat, last_lon = points[0][0], points[0][1]
    min_m2 = min_m * min_m
    for p in points[1:]:
        lat, lon = p[0], p[1]
        lat_mid = math.radians((lat + last_lat) / 2.0)
        dx = (lon - last_lon) * 111320.0 * math.cos(lat_mid)
        dy = (lat - last_lat) * 110540.0
        if dx * dx + dy * dy >= min_m2:
            out.append(p)
            last_lat, last_lon = lat, lon
    out.append(points[-1])               # always keep the last point
    return out


# Wahoo telemetry embedded under <trkpt><extensions> by `wahoo_to_gpx --ext`,
# mapped to the short key trackview averages.  Un-namespaced on purpose (see
# wahoo_to_gpx.py); gpxpy flattens the <extensions> children straight onto a
# trackpoint's .extensions list, so each element's bare .tag is the metric.
_TELE_TAGS = {"power": "power", "speed_kmh": "speed", "cadence": "cadence", "heartrate": "hr"}


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


_NAME_DATE_RE = re.compile(r"^(\d{4})_(\d{2})_(\d{2})(?=_|$)")


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


def load_tracks(gpx_dir: Path, decimate_m: float, with_ext: bool = False) -> list[dict]:
    """Read every *.gpx in gpx_dir; merge its segments into one polyline each.
    Always record each ride's first->last timestamp span: its duration, shown on the
    title and feeding the calories-burned estimate.  With with_ext, also collect the
    Wahoo telemetry embedded by `wahoo_to_gpx --ext` (power/speed/cadence/hr) per
    point, accumulated over every sample (pre-decimation) so the caller can show an
    accurate average."""
    tracks = []
    for path in sorted(glob.glob(str(gpx_dir / "*.gpx"))):
        with open(path, "rb") as fh:
            gpx = gpxpy.parse(fh)
        raw = []                            # (lat, lon, ele) for every point
        tele = {k: [0.0, 0] for k in ("power", "speed", "cadence", "hr")} if with_ext else None
        t_first = t_last = None               # ride span (1st -> last timestamp) for calories
        for trk in gpx.tracks:
            for seg in trk.segments:
                for pt in seg.points:
                    raw.append((pt.latitude, pt.longitude, pt.elevation))
                    st = pt.time              # ride span -> duration (+ calories when --ext)
                    if st is not None:
                        t_first = st if t_first is None or st < t_first else t_first
                        t_last   = st if t_last  is None or st > t_last  else t_last
                    if tele is not None:
                        for key, val in _point_telemetry(pt).items():
                            tele[key][0] += val
                            tele[key][1] += 1
        if not raw:
            print(f"  skip (no points): {os.path.basename(path)}")
            continue
        dist_km, gain_m = _distance_and_gain(raw)
        dec = decimate(raw, decimate_m)
        merc = [latlon_to_merc(la, lo) for (la, lo, _e) in dec]
        ele = [e for (_la, _lo, e) in dec]
        name = (gpx.name or (gpx.tracks[0].name if gpx.tracks
                              and gpx.tracks[0].name else None)
                 or Path(path).stem)
        d = {"path": path, "name": name, "merc": merc, "ele": ele,
              "n": len(raw), "ndec": len(dec),
              "dist_km": dist_km, "gain_m": gain_m,
              "duration_s": (t_last - t_first).total_seconds() if t_first else 0.0}
        if tele is not None:
            d.update(tele)                    # per-metric [sum, count] pairs
        tracks.append(d)
    return tracks


def _distance_and_gain(points) -> tuple[float, float]:
    """Total distance (km) and positive elevation gain (m)."""
    dist = 0.0
    gain = 0.0
    for i in range(1, len(points)):
        la0, lo0, e0 = points[i - 1]
        la1, lo1, e1 = points[i]
        lat_mid = math.radians((la0 + la1) / 2.0)
        dx = (lo1 - lo0) * 111320.0 * math.cos(lat_mid)
        dy = (la1 - la0) * 110540.0
        dist += math.hypot(dx, dy)
        gain += max(0.0, e1 - e0)
    return dist / 1000.0, gain


def choose_zoom(bbox, target_px: float = 1600.0, zmin: int = 10, zmax: int = 16) -> int:
    """Pick a tile zoom so the bbox spans roughly target_px pixels."""
    w_m = bbox[2] - bbox[0]
    z = math.log2(EQUATOR * target_px / (256.0 * w_m))
    return int(round(min(zmax, max(zmin, z))))


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
def render(tracks, *, style: str, out_path: Path, zoom: int | None,
           color_by_elev: bool, title: str | None = None,
           show_ext: bool = False, split: bool = False) -> None:
    if not tracks:
        print("No tracks to render.")
        return

    all_merc = np.array([pt for t in tracks for pt in t["merc"]], dtype=float)
    w0, s0, e0, n0 = (all_merc[:, 0].min(), all_merc[:, 1].min(),
                      all_merc[:, 0].max(), all_merc[:, 1].max())
    dx, dy = (e0 - w0) * PAD_FRAC, (n0 - s0) * PAD_FRAC
    bbox = fit_aspect((w0 - dx, s0 - dy, e0 + dx, n0 + dy), FIGURE_IN[0] / FIGURE_IN[1])
    if zoom is None:
        zoom = choose_zoom(bbox)

    elev = [e for t in tracks for e in t["ele"]]
    elev_min, elev_max = (min(elev), max(elev)) if elev else (0.0, 1.0)
    have_elev = (elev_max - elev_min) > 1.0 and color_by_elev

    fig, ax = plt.subplots(figsize=FIGURE_IN, dpi=DPI)

    # --- base map (tried in fallback order) ---
    ordered = [style] + [k for k in SOURCES if k != style]
    loaded = _load_basemap(ax, bbox, ordered, zoom)
    attr = ATTRIBUTION.get(loaded, "© OpenStreetMap contributors")

    # --- overlay tracks ---
    norm = Normalize(vmin=elev_min, vmax=elev_max)
    for i, t in enumerate(tracks):
        seg = np.array([[t["merc"][j], t["merc"][j + 1]]
                        for j in range(len(t["merc"]) - 1)])
        # white halo underlay makes the routes pop on the busy terrain map
        halo = LineCollection(seg, colors="white", linewidths=4.6, alpha=0.9)
        halo.set_zorder(4)
        ax.add_collection(halo)
        if have_elev:
            ec = [(t["ele"][j] + t["ele"][j + 1]) / 2 for j in range(len(t["ele"]) - 1)]
            lc = LineCollection(seg, cmap=CMAPEL, norm=norm, linewidths=2.4, alpha=0.95)
            lc.set_array(ec)
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

     # one more start-marker for the overall route start, drawn after every
     # track so it sits on top of all the per-track lines, halos and markers
    sx, sy = tracks[0]["merc"][0]
    ax.scatter([sx], [sy], s=70, color="lime", edgecolors="k",
               linewidths=0.6, zorder=8)

    ax.axis("off")

    # colourbar + legend + attribution
    if have_elev:
        sm = plt.cm.ScalarMappable(cmap=CMAPEL, norm=norm)
        sm.set_array([])
        cb = fig.colorbar(sm, ax=ax, fraction=0.03, pad=0.02, location="right")
        cb.set_label("Elevation (m)", fontsize=10)

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
    suffix = "     -  shaded by elevation" if have_elev else ""
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

    fig.text(0.006, 0.004, attr, fontsize=7, color="#555")
    fig.text(0.994, 0.004, f"zoom {zoom}", fontsize=7, color="#555", ha="right")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=DPI, facecolor="white")
    plt.close(fig)
    print(f"  wrote {out_path}    ({out_path.stat().st_size // 1024} KB)")


def _load_basemap(ax, bbox, order, zoom, min_var: float = 1.0) -> str:
    """Fall back through tile providers until one shows real tiles.
    A failed or blank fetch (near-zero pixel variance) triggers the
    next provider after a short, polite delay."""
    for key in order:
        ax.clear()
        ax.set_xlim(bbox[0], bbox[2])
        ax.set_ylim(bbox[1], bbox[3])
        ax.set_aspect("equal")
        try:
            cx.add_basemap(ax, zoom=zoom, source=SOURCES[key],
                           headers={"User-Agent": USER_AGENT},
                           reset_extent=False)
        except Exception as exc:                      # pragma: no cover
            print(f"  base-map '{key}' failed: {type(exc).__name__}: {exc}")
            time.sleep(2)
            continue
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
    ap.add_argument("--out", default=None,
                    help="output file for the combined map "
                         "(default: output/tracks_overview.<format>)")
    ap.add_argument("--format", choices=["png", "pdf"], default="png",
                    help="image format for the auto-named / split outputs")
    ap.add_argument("--style", choices=list(SOURCES), default="osm")
    ap.add_argument("--zoom", type=int, default=None, help="override auto zoom")
    ap.add_argument("--no-elev", action="store_true", help="flat colour, not elevation")
    ap.add_argument("--split", action="store_true",
                    help="one map file per track (default: all tracks in one file)")
    ap.add_argument("--ext", action="store_true",
                    help="add the calories-burned total (kcal) to the title and an avg "
                           "power/speed/cadence/hr line below it, from wahoo_to_gpx --ext telemetry (calories = avg power x ride duration / efficiency; ignored when absent)")
    args = ap.parse_args()

    gpx_dir = Path(args.gpx_dir)
    print(f"trackview - reading *.gpx from {gpx_dir}")
    tracks = load_tracks(gpx_dir, DECIMATE_M, with_ext=args.ext)
    if not tracks:
        print("No *.gpx files found - nothing to render.")
        return

    print(f"   {len(tracks)} track(s), "
          f"{sum(t['n'] for t in tracks):,} pts -> "
          f"{sum(t['ndec'] for t in tracks):,} after {DECIMATE_M:.0f} m decimation")
    for t in tracks:
        print(f"    - {t['name']:<20s} {t['dist_km']:6.1f} km    "
              f"+{t['gain_m']:6.0f} m    {t['n']:>6,} -> {t['ndec']:>5,} pts")

    color_by_elev = not args.no_elev
    out_dir = Path(args.out).parent if args.out is not None else OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.split:
        for t in tracks:
            out_path = out_dir / f"{_safe_filename(Path(t['path']).stem)}.{args.format}"
            render([t], style=args.style, out_path=out_path, zoom=args.zoom,
                   color_by_elev=color_by_elev, show_ext=args.ext, split=True)
    else:
        out_path = (Path(args.out) if args.out is not None
                    else out_dir / f"tracks_overview.{args.format}")
        render(tracks, style=args.style, out_path=out_path, zoom=args.zoom,
               color_by_elev=color_by_elev, show_ext=args.ext)


if __name__ == "__main__":
    main()

"""Rendering helpers for trackview.

Extracted from the trackview monolith (see PLAN.md, Phase 1.4) -- the
matplotlib-coupled half of the old "Rendering" phase, moved in leaf-first
sub-steps.  So far this holds the *leaf* helpers the map and profile figures
build on: the colour-ramp / heat / device constants, the robust colour norm
(``_metric_norm``) and the centred moving average (``_moving_avg``), plus the
profile / heat / scale-bar drawing helpers (``_draw_profile``,
``_draw_profile_metric``, ``_stack_grade_colorbars``, ``_draw_scale_bar``,
``_draw_heat`` and their small ``_nice_m`` / ``_fmt_len`` / ``_dwell_times`` /
``_fmt_heat_time`` / ``_has_metric_pts`` helpers).  The big ``render`` /
``render_*`` / ``write_*`` figure cluster that *orchestrates* them still has a
back-edge to the monolith (``_load_basemap``, ``decimate``, ...) and stays put
for the next sub-step; these leaves have no such edge, so they move first.
"""
from __future__ import annotations

import math

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize
from matplotlib.patheffects import withStroke as _with_stroke


# --- constants ---------------------------------------------------------------
# A sequential "effort" ramp for the telemetry colourings (--color-by speed/power):
# low = cold/dark, high = hot/bright, perceptually uniform so a rider reads pacing
# and effort at a glance (fast / high power at the hot end).  Paired with the same
# dark under-lay as the grade shading so even the cold low end pops on a pale basemap.
CMAPEED = "inferno"
GRADE_CBAR_MAX = 4.0      # max rides that each get their own grade colourbar on a
                              # combined map; beyond it a single shared scale is used (and noted)

# A "Kickr Snap" is a stationary smart trainer: its session has no route of its
# own, so its points would just clutter the basemap.  Keep such tracks off the
# rendered image, matched case-sensitively against the trimmed 'Device:' line -
# they are still listed in the ride-log/CSV (a trainer ride is still a ride).
SUPPRESSED_RENDER_DEVICES = {"Kickr Snap"}


GRADE_SMOOTH   = 5.0       # centred moving-average window (segments) for the profile's
                              # per-segment grade line: GPS jitter makes it noisy otherwise
# The --heat density overlay: a 2-D "time on route" histogram of the routes' points,
# drawn under the lines.  Empty cells are masked to zero (the basemap shows through)
# and the colour is capped at a high percentile, so a single hot cell (a spot ridden
# many times, or a rest stop) can't wash out the rest of the map.
HEAT_GRID         = 300            # cells across the bbox (a HEAT_GRID x HEAT_GRID histogram)
HEAT_CAP_PCT      = 98.0           # colour cap: % of non-empty cells inside the (capped) range
HEAT_ALPHA        = 0.55           # overlay opacity (the route lines stay readable on top)

# The figure save-resolution (a fixed 150 DPI for every rendered figure -- the
# map, the ride-profile, and the trend / calendar charts).  Shared by the not-yet-
# migrated render / write_html / write_gallery clusters too, so it lives here and the
# monolith re-imports it.
DPI          = 150


# --- functions ---------------------------------------------------------------
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


# --- drawing helpers (the profile / heat / scale-bar artists) ---------------
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

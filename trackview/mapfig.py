"""The render / write_* figure-orchestration cluster (the old monolith's "rendering"
phase), extracted in PLAN.md Phase 1.4b-ii.

It holds the figure constants that belong to the map figure (`FIGURE_IN`, the
`CMAPEL` / `GRADE_STOPS` / `CMAPGRADE` colour ramps, the `--profile` card's
`PROF_METRICS`), the bbox-aspect helper (`fit_aspect`) and the big `render`
orchestrator that builds and saves a ride map (plus its `--profile` card and
`--heat` overlay).  This is the top of the dependency tree: it imports the
drawing leaves from `trackview.rendering`, the basemap / tile machinery from
`trackview.io`, and the small metric helpers from `trackview.metrics` /
`trackview.helpers` -- none of which import back, so there is no cycle -- which
is why the map figure moves here rather than into `rendering` (that module is
already imported, transitively, by `io`).
"""
from __future__ import annotations

import numpy as np
import matplotlib
matplotlib.use("Agg")                           # headless, no GUI needed
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.colors import Normalize, LinearSegmentedColormap
from matplotlib.lines import Line2D
from matplotlib.patheffects import withStroke as _with_stroke
from matplotlib.ticker import FuncFormatter

from trackview.rendering import (PAD_FRAC, DPI, CMAPEED, GRADE_CBAR_MAX,
                                 STRONG_COLORS, _metric_norm,
                                 _draw_profile, _draw_profile_metric,
                                 _has_metric_pts, _stack_grade_colorbars,
                                 _draw_scale_bar, _fmt_heat_time, _draw_heat)
from trackview.io import (SOURCES, _load_basemap, ATTRIBUTION, choose_detail)
from trackview.metrics import (_metric_avg, _grade_cap, _calories_burned, _fmt_duration)
from trackview.helpers import (_short_label, _title_name)


# ------------------------------- figure constants ----------------------------

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


def fit_aspect(bbox, aspect_wh: float) -> tuple:
    """Grow the bbox (west,south,east,north) so it matches the figure aspect."""
    w, s, e, n = bbox
    bw, bh = e - w, n - s
    if bw / aspect_wh < bh:               # too narrow -> pad east/west
        dw = (bh * aspect_wh - bw) / 2
        return (w - dw, s, e + dw, n)
    dh = (bw / aspect_wh - bh) / 2        # too wide   -> pad north/south
    return (w, s - dh, e, n + dh)


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

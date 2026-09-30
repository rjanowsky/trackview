"""Per-ride 'training trend' chart for trackview.

Extracted from the trackview monolith (see PLAN.md, Phase 1.5d) -- the
--trend figure: one panel per metric (distance, elevation gain, ride
duration, and a calories-burned panel when any ride carries a power
average) plotted over ride date, so training volume and the span of the
log read at a glance.  A standalone chart (no basemap, no network), so it
writes even under --no-map.  It is pure over the parsed ride dicts (each
track's filename date and its dist_km / gain_m / duration_s / power
average); its only external names are _ride_date (`trackview/helpers`),
_track_calories (`trackview/metrics`) and the DPI figure-resolution
constant (`trackview/rendering`), so it has no back-edge to the monolith.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from trackview.helpers import _ride_date
from trackview.metrics import _track_calories
from trackview.rendering import DPI


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

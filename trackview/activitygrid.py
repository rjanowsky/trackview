"""Activity-grid (GitHub-style contribution calendar) figure for trackview.

Extracted from the trackview monolith (see PLAN.md, Phase 1.5d) -- the
--calendar "activity grid": one 7 (weekday) x weeks block per calendar year,
each day a square coloured by that day's total of the chosen metric, written
even under --no-map (a standalone figure, no basemap, no network).  It is pure
over the parsed ride dicts (each track's filename date and its dist_km / gain_m
or a ride count); its only external names are _ride_date / _MONTH_ABBR
(`trackview/helpers`) and the DPI figure-resolution constant (`trackview/rendering`),
so it has no back-edge to the monolith.

The module was named `calendar`, but that shadows the stdlib `calendar` module for
any `sys.path[0]`-style import (a theoretical footgun no entry point triggers, since
nothing in the package imports the stdlib calendar).  It is now `activitygrid` --
the figure's own name -- so the stdlib module can never be shadowed.
"""
from __future__ import annotations

from datetime import date

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize

from trackview.helpers import _ride_date, _MONTH_ABBR
from trackview.rendering import DPI


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

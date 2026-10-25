#!/usr/bin/env python3
"""
A "year-in-review" dashboard for a trackview ride log (a local, personal helper).

Reads a trackview *per-ride* stats table -- the "trackview - N rides" report the
tool writes to $TRACKVIEW_HOME/stats/ (~/.trackview/stats/) -- and renders a
single, shareable PNG "one picture of my whole life riding":

    1  The trophy shelf -- the top ride by distance / gain / avg power /
       time on the bike, and the biggest climb (max grade) ever logged
    2  The top N rides by distance -- a ranked horizontal-bar list
       (N via --top, default 10; the "best rides" leaderboard)
    3  Cumulative distance over time            (rising curve + total)
    4  Ride calendar -- a contribution grid,
       rows = calendar month, columns = day-of-month, cells = distance ridden
       that day (the GitHub heatmap habit, a year at a glance)
    5  Monthly distance vs. climbing gain, by year (seasonality / progress)

Only *matplotlib* is needed (already a trackview dependency); the ride log is
a fixed-width, 12-column table, so it is parsed with a small stdlib reader
rather than pulling in pandas.  This is a tools/ helper: its rendered PNG is a
regenerable, personal output, so by default it lands in trackview's output/
dir ($TRACKVIEW_HOME/output/, i.e. ~/.trackview/output/ -- the same place the
tool's maps go, and git-ignored), like the .fit inputs and the *_records.json
dumps.  --out names a specific file anywhere.

The per-ride columns trackview writes are:
    Ride date | Dist (km) | Duration | Gain (m) | Calories (kcal)
    | Avg power (W) | Avg speed (km/h) | Avg cadence (rpm) | Avg HR (bpm)
    | Max grade (%) | Avg temperature (C) | Device
Power / HR / temperature / grade only exist from ~2024 on; earlier rows carry a
'-' and are read as "missing", not zero, so the power panels skip them.

Usage:
    python3 tools/ride_dashboard.py                          # most recent log, -> output/
    python3 tools/ride_dashboard.py <log.txt>                # a specific log
    python3 tools/ride_dashboard.py --out report.png         # where to write it
    python3 tools/ride_dashboard.py --top 5                  # 5 rows in the top-N panel
    python3 tools/ride_dashboard.py --title "Rides 2019-2026"
"""

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

# run as `python tools/..py`, sys.path[0] is tools/, not the repo root -- so the
# trackview package (for its per-user data-dir config) is not importable.  Add it.
if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import matplotlib
matplotlib.use("Agg")                       # headless: write a PNG, open no window
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap

import trackview.config as cfg              # the per-user data root (GPX/STATS dirs)

# the 12 columns a per-ride table reports, in order.
_COLS = ("date", "dist", "dur", "gain", "cal", "power", "speed",
         "cad", "hr", "grade", "temp", "device")
MONTHS = "J F M A M J J A S O N D".split()
GREENS = LinearSegmentedColormap.from_list("greens",
    ["#f7fcf5", "#c7e9c0", "#74c476", "#238b45", "#00441b"])


# ------------------------------- parsing -------------------------------------
def _f(tok):
    """A numeric token -> float, or None for the '-' / '' placeholders trackview
    prints for a metric a pre-power-meter ride never recorded."""
    return None if tok in ("-", "", None) else float(tok)


def _split_row(line):
    """Split a table line into its columns on 2+ spaces (the fixed-width gap).

    This keeps multi-word fields whole -- "1h 43m" (Duration) and "Wahoo ELEMNT
    BOLT" (Device) -- which a naive whitespace split would break.  Returns None
    for non-data lines (title / header / '----------' / 'Summary').
    """
    if not re.match(r"^\d{4}-\d{2}-\d{2}", line):
        return None
    cols = [c.strip() for c in re.split(r"\s{2,}", line.strip())]
    return cols + [""] * (len(_COLS) - len(cols))   # pad short (older) rows


def parse_rides(path):
    """Parse a per-ride table into a list of dict rides.

    A *ride* row is any line starting with a YYYY-MM-DD date -- this skips the
    title, the header, the '----------' separators, and the trailing 'Summary'
    line.  Durations "2h 05m" / "45m" become hours; a missing metric becomes
    None.
    """
    rides = []
    for line in Path(path).read_text().splitlines():
        cols = _split_row(line)
        if cols is None:
            continue
        row = dict(zip(_COLS, cols))
        row["y"] = int(row["date"][:4]); row["mo"] = int(row["date"][5:7]); row["d"] = int(row["date"][8:10])
        row["dist"] = _f(row["dist"]); row["gain"] = _f(row["gain"])
        row["power"] = _f(row["power"]); row["grade"] = _f(row["grade"])
        row["hours"] = _hours(row["dur"])
        rides.append(row)
    return rides


def _hours(tok):
    """'2h 05m' / '45m' -> 125.0 / 0.75 (hours); '-' / None -> 0.0."""
    if tok in ("-", "", None):
        return 0.0
    parts = tok.split()
    hours = sum(float(p[:-1]) for p in parts if p.lower().endswith("h"))
    mins = sum(float(p[:-1]) / 60.0 for p in parts if p.lower().endswith("m"))
    return hours + mins


def _dur(r):
    """A ride's time on the bike as 'Hh Mm' (its original duration token when
    present, else rebuilt from its hours), for a leaderboard row label."""
    tok = r.get("dur")
    if tok not in (None, "", "-"):
        return tok
    h = r.get("hours") or 0.0
    return f"{int(h)}h {int(round((h - int(h)) * 60))}m"


# ------------------------------- aggregation ---------------------------------
def cumulative(rides):
    """Rides sorted by date, each carrying a running total distance in km."""
    out, cum = [], 0.0
    for x in sorted(rides, key=lambda r: r["date"]):
        cum += x["dist"] or 0.0
        x["cum"] = cum
        out.append(x)
    return out


def monthly(rides):
    """{(year, month): {dist, gain, hours, rides}} -- the seasonality table."""
    agg = defaultdict(lambda: {"dist": 0.0, "gain": 0.0, "hours": 0.0, "rides": 0})
    for x in rides:
        k = (x["y"], x["mo"])
        agg[k]["dist"] += x["dist"] or 0.0
        agg[k]["gain"] += x["gain"] or 0.0
        agg[k]["hours"] += x["hours"] or 0.0
        agg[k]["rides"] += 1
    return agg


# A per-ride "max grade" above this is physically implausible on a road bike --
# early GPS-era logs report single-point spikes (e.g. 800%+ from a noisy
# altitude sample).  The "steepest climb" trophy caps here so it shows a genuine
# climb, not that noise.
MAX_GRADE = 30.0


def top_rides(rides):
    """The 'trophy shelf': the single best ride by distance, gain, avg power,
    time on the bike, and max grade (missing metrics ignored)."""
    def best(key):
        vals = [r for r in rides if r.get(key) is not None]
        return max(vals, key=lambda r: r[key]) if vals else None
    # steepest: the highest *plausible* per-ride grade (capped at MAX_GRADE); None
    # if no logged grade clears it (all noise) -- the card then reads "no data".
    sane = [r for r in rides if r.get("grade") and r["grade"] <= MAX_GRADE]
    return {"dist": best("dist"), "gain": best("gain"), "power": best("power"),
            "time": max(rides, key=lambda r: r["hours"]) if rides else None,
            "grade": max(sane, key=lambda r: r["grade"]) if sane else None}


# ------------------------------- rendering -----------------------------------
def render(rides, out, title=None, top_n=10):
    """Draw the five-panel dashboard to `out` (a PNG path); returns `out`.

    `top_n` sizes the "top rides by distance" leaderboard (the bottom panel).
    """
    cumulative(rides)
    agg = monthly(rides)
    tops = top_rides(rides)

    years = sorted({x["y"] for x in rides})
    total_km = sum(x["dist"] or 0.0 for x in rides)
    total_gain = sum(x["gain"] or 0.0 for x in rides)
    total_h = sum(x["hours"] or 0.0 for x in rides)
    head = title or f"trackview - year in review   {len(rides)} rides - " \
                   f"{total_km:,.0f} km - {total_gain:,.0f} m gain - " \
                   f"{total_h:,.0f} h   ({years[0]}-{years[-1]})"

    fig, axes = plt.subplots(5, 1, figsize=(13, 19),
                             gridspec_kw={"height_ratios": [1, 2, 3, 3, 3]})
    fig.suptitle(head, fontsize=15, fontweight="bold")

    # 1 -- the trophy shelf ---------------------------------------------------
    ax = axes[0]
    ax.axis("off")
    cards = [
        ("Longest ride",        _fmt(tops["dist"], "dist")),
        ("Most climbing",       _fmt(tops["gain"], "gain")),
        ("Strongest power",     _fmt(tops["power"], "power")),
        ("Longest on the bike", _fmt(tops["time"], "time")),
        ("Steepest climb",      _fmt(tops["grade"], "grade")),
    ]
    ncol = len(cards)
    for i, (label, body) in enumerate(cards):
        x = i / ncol + 0.5 / ncol
        ax.text(x, 0.62, label, ha="center", va="center", fontsize=9, color="#666")
        ax.text(x, 0.30, body, ha="center", va="center", fontsize=11, fontweight="bold")
    ax.set_title("1  Best rides on record", fontweight="bold")

    # 2 -- top N rides by distance (a ranked leaderboard) --------------------
    ax = axes[1]
    top = sorted(rides, key=lambda x: x["dist"] or 0.0, reverse=True)[:top_n]
    # barh's index 0 sits at the *bottom*, so put the highest rank (#1) at index
    # 0 and read it top-down: reverse the sorted list, then reverse the labels
    # back so the axis reads #1 at top ... #N at bottom.
    rows = list(enumerate(reversed(top)))
    labels = [f"#{i + 1}  {r['date']}  ({_dur(r)})"
              for i, r in enumerate(top)]
    ys = [i for i, _ in rows]
    dists = [r["dist"] or 0.0 for _, r in rows]
    bars = ax.barh(ys, dists, color="#2b6cb0", edgecolor="#fff")
    ax.set_yticks(ys)
    ax.set_yticklabels(reversed(labels), fontsize=8)
    ax.set_xlabel("distance (km)")
    ax.set_title(f"2  Top {top_n} rides by distance", fontweight="bold")
    ax.grid(axis="x", alpha=0.3)
    # The value labels sit just past each bar's end (ha="left"), so the x-limit
    # must clear the *longest* label -- a 3-digit ride (e.g. "103.6") overruns a
    # ~1.12x limit and clips at the figure edge.  A modest padding in *data* units
    # (5% of the top ride, >=10 km) leaves room for the label and keeps the bars
    # comparable, without an auto axis that would clip on a tight span.
    top_dist = dists[0] if dists else 1.0
    ax.set_xlim(0, top_dist * 1.05 + 10.0)
    for b, r in zip(bars, [r for _, r in rows]):
        ax.text(b.get_width(), b.get_y() + b.get_height() / 2,
                f"{r['dist']:.1f}", va="center", ha="left", fontsize=7)

    # 3 -- cumulative distance ------------------------------------------------
    ax = axes[2]
    pts = sorted(rides, key=lambda x: x["date"])
    import datetime as _dt
    xs = [mdates.date2num(_dt.date.fromisoformat(r["date"])) for r in pts]
    ax.plot(xs, [x["cum"] for x in pts], lw=1.4, color="#2b6cb0")
    ax.axhline(total_km, ls="--", lw=1, color="#999", label=f"total {total_km:,.0f} km")
    ax.set_title("3  Cumulative distance", fontweight="bold"); ax.set_ylabel("km (cumulative)")
    ax.legend(loc="upper left"); ax.grid(alpha=0.3)
    # A plain, fixed one-year-per-tick axis (2014 ... 2026).  The alternative,
    # ConciseDateFormatter, collapses labels on a century rollover (2000->00,
    # 2010->10, 2020->20) so a tight span reads as a scrambled '14 26 08 23 04 16'
    # -- cryptic, and its decade ticks land unevenly.  Explicit year labels are
    # unambiguous; skip the tick every few years if the span ever runs long.
    yrs = list(range(years[0], years[-1] + 1))
    step = 1 if len(yrs) <= 12 else max(1, len(yrs) // 12)
    ticks = [mdates.date2num(_dt.date(y, 1, 1)) for y in yrs[::step]]
    ax.set_xticks(ticks)
    ax.set_xticklabels([str(yrs[i]) for i in range(0, len(yrs), step)])

    # 4 -- ride calendar (contribution grid) ---------------------------------
    ax = axes[3]
    grid = np.zeros((12, 32))                       # [month][day-1] = distance that day
    for x in rides:
        grid[x["mo"] - 1, x["d"] - 1] += x["dist"] or 0.0
    nz = grid[grid > 0]
    # Cap the colour scale so the grid reads day-to-day intensity, not one
    # outlier.  median * 3 (the original cap) can pin every active day at the
    # darkest green -- a low cap washes the grid flat and shows no structure --
    # so the cap keys off the *total* distance on a calendar day (this grid
    # sums multi-ride days), and a high quantile of the riding days captures the
    # strong days a rider remembers, while a floor keeps a quiet season from
    # under-scaling the grid.
    if nz.size:
        vmax = max(float(np.quantile(nz, 0.9)), 15.0)
    else:
        vmax = 15.0
    ax.imshow(grid, aspect="auto", cmap=GREENS, origin="upper", vmin=0, vmax=vmax)
    ax.set_yticks(range(12)); ax.set_yticklabels(MONTHS)
    ax.set_xticks(range(0, 31, 2)); ax.set_xticklabels([str(d + 1) for d in range(0, 31, 2)])
    ax.set_xlabel("day of month"); ax.set_title("4  Ride calendar (colour = distance that day)", fontweight="bold")
    sm = fig.colorbar(plt.cm.ScalarMappable(cmap=GREENS,
                   norm=matplotlib.colors.Normalize(0, vmax)), ax=ax,
                   fraction=0.02, pad=0.01)
    sm.set_label("km / day")

    # 5 -- monthly distance vs. gain by year ---------------------------------
    ax = axes[4]
    mo_order = list(range(1, 13))
    for y in years:
        ds = [agg[(y, m)]["dist"] for m in mo_order]
        gs = [agg[(y, m)]["gain"] / 1000.0 for m in mo_order]   # gain in 1000 m
        ax.plot(mo_order, ds, "-o", ms=3, label=f"{y} dist (km)")
        ax.plot(mo_order, gs, "--", ms=0, alpha=0.6, label=f"{y} gain (1000 m)")
    ax.set_xticks(mo_order); ax.set_xticklabels(MONTHS)
    ax.set_title("5  Monthly distance (solid) & climbing gain (dashed), by year", fontweight="bold")
    ax.set_ylabel("km / 1000 m")
    ax.legend(fontsize=7, ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.12))
    ax.grid(alpha=0.3)

    fig.tight_layout(rect=[0, 0, 1, 0.98])
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return out


def _fmt(r, which):
    """Human body text for a trophy card, or a friendly 'no data yet' if the
    metric is absent (pre-2024 logs have no power/grade)."""
    if r is None:
        return "no data"
    if which == "dist":
        return f"{r['dist']:.1f} km\n{r['date']}"
    if which == "gain":
        return f"{r['gain']:.0f} m\n{r['date']}"
    if which == "power":
        return f"{r['power']:.0f} W\n{r['date']}"
    if which == "time":
        return f"{r['hours']:.1f} h\n{r['date']}"
    if which == "grade":
        return f"{r['grade']:.1f} %\n{r['date']}"
    return r["date"]


# ------------------------------- main ----------------------------------------
def _latest_log():
    """The most recent per-ride table in the stats dir -- the one to report on.

    Prefers the plain per-ride tables (not the '_summary' / '_climbs' variants),
    newest by mtime, so a fresh ride shows up without naming the file.
    """
    stats = cfg.STATS_DIR
    cands = [p for p in stats.glob("trackview-*.txt")
             if not p.name.endswith(("_summary.txt", "_climbs.txt"))]
    if not cands:
        raise SystemExit(f"no per-ride ride log found in {stats} "
                         "(set $TRACKVIEW_HOME or run trackview first)")
    return max(cands, key=lambda p: p.stat().st_mtime)


def _default_out(log):
    """Where to write: next to the log when one was named, else into trackview's
    output/ dir -- the same place the tool drops its maps (cfg.OUTPUT_DIR,
    ~/.trackview/output/ by default; git-ignored), so a regenerable, personal
    dashboard never lands in the repo."""
    return cfg.OUTPUT_DIR / f"{Path(log).stem}_dashboard.png"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("log", nargs="?", help="a per-ride stats table "
                    "(default: the most recent one in the stats dir)")
    ap.add_argument("--out", help="output PNG (default: the output/ dir, or next "
                    "to a named log)")
    ap.add_argument("--title", help="override the dashboard heading")
    ap.add_argument("--top", type=int, default=10, metavar="N",
                    help="how many rides the 'top by distance' list shows "
                         "(panel 5; default 10)")
    args = ap.parse_args(argv)

    log = Path(args.log) if args.log else _latest_log()
    out = Path(args.out) if args.out else _default_out(log)
    out.parent.mkdir(parents=True, exist_ok=True)

    rides = parse_rides(log)
    if not rides:
        raise SystemExit(f"no rides parsed from {log}")
    written = render(rides, out, title=args.title, top_n=args.top)
    print(f"{len(rides)} rides -> {written}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

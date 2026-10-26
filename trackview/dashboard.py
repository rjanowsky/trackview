"""The `--dashboard` "year-in-review" figure for trackview.

Promoted from the ad-hoc `tools/ride_dashboard.py` helper (that file is now a
pointer to `trackview --dashboard`; see the module docstring there).  Unlike the
helper, this is *in-package*: it lives beside `trend.py` / `activitygrid.py`, is
imported normally by `cli.main` (no `sys.path` hack), and honours the CLI's
`--out` / `--format` and its own `--dashboard-top`.

Input is the trackview *per-ride CSV* -- the `trackview-<first>_<last>.csv` ride
log `main` writes to the stats dir (`STATS_DIR`, `~/.trackview/stats/` by
default, via `--csv` / `--dashboard`) -- read back from disk.  So the dashboard is
a *report over the persisted ride log*, decoupled from this run's
`--since/--until/--device/--sport/--top` selection (those filter `tracks`, not the
CSV); a positional `--dashboard LOG` names a specific CSV, and with none it reports
on the newest plain CSV in the stats dir (the `_latest_log` behaviour).  Because
the CSV is pure geometry the figure writes even under `--no-map` / `--sparse`.

The CSV -- not the fixed-width `.txt` ride-log -- is the source, because the CSV is
*stable*: a header row + one row per ride, always the same columns in the same
order.  The `.txt` table is *not* fixed-width -- its column count varies with
`--ext` (and, in older logs, by device type: 8 to 15 columns) -- so a
fixed-position reader would misread it; the CSV's *header* is the anchor instead,
so the reader maps by column name and never drifts.  Only *matplotlib* + *numpy*
(already trackview deps) plus the stdlib `csv` are needed -- no `pandas`.  The
per-ride columns trackview writes (in the CSV header, in order) are:

    Ride | Dist (km) | Duration | Gain (m) | Calories (kcal)
    | Avg power (W) | Avg speed (km/h) | Avg cadence (rpm) | Avg HR (bpm)
    | Max grade (%) | Avg temperature (C) | Device

The `Ride` column is the *ride name* -- for this user, the ride's calendar date
(`YYYY-MM-DD`, the Wahoo stem), from which the reader derives `y` / `mo` / `d`.
Power / HR / temperature / grade only exist from ~2024 on; earlier rows carry a
'-' and are read as "missing", not zero, so the power / climb panels skip them.
"""
from __future__ import annotations

import csv
import math
import re
from collections import defaultdict
from pathlib import Path

import matplotlib
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap

from trackview.config import STATS_DIR, OUTPUT_DIR, __version__

# A per-ride "max grade" above this is physically implausible on a road bike --
# early GPS-era logs report single-point spikes (e.g. 800%+ from a noisy
# altitude sample).  The "steepest climb" trophy caps here so it shows a genuine
# climb, not that noise.
MAX_GRADE = 30.0

# The CSV's `Ride` column is the ride *name*, not a calendar date -- for a Wahoo
# stem (e.g. 2026_09_11_08_07_29, or the already-normalised '2026-09-11' the .txt
# ride-log prints) it encodes the date; for a descriptive komoot title it does
# not.  We read y / mo / d off a YYYY-MM-DD *prefix*, so a date-shaped name yields
# a date and anything else yields "no date" (the ride is still counted, it just
# can't be placed on a time axis).
_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")

MONTHS = "J F M A M J J A S O N D".split()
GREENS = LinearSegmentedColormap.from_list("greens",
    ["#f7fcf5", "#c7e9c0", "#74c476", "#238b45", "#00441b"])

# header -> internal key, so the reader maps by *column name* (the stable anchor),
# never by fixed position.  The header trackview writes is exactly this set, in
# this order; extra/unrecognised columns (e.g. an old 15-col table with an extra
# device sub-column) are ignored, so the reader is robust to column drift.
_HEADER_KEY = {
    "Ride": "date", "Dist (km)": "dist", "Duration": "dur", "Gain (m)": "gain",
    "Calories (kcal)": "cal", "Avg power (W)": "power", "Avg speed (km/h)": "speed",
    "Avg cadence (rpm)": "cad", "Avg HR (bpm)": "hr", "Max grade (%)": "grade",
    "Avg temperature (°C)": "temp", "Avg temperature (C)": "temp", "Device": "device",
}

# A ride with no calendar date (a non-date ride name) still counts toward totals,
# but carries no month/day for the calendar + monthly panels -- use a sentinel
# month out of range so it never collides with a real month and is skipped there.
_NO_DATE = -1


# ------------------------------- parsing -------------------------------------
def _f(tok):
    """A numeric token -> float, or None for a non-numeric one.

    trackview writes '-' for a metric a pre-power-meter ride never recorded, but a
    hand-rolled or narrow CSV may leave a cell blank or carry a stray token; treat
    any non-numeric value as "missing", not zero.
    """
    if tok in ("-", "", None):
        return None
    try:
        return float(tok)
    except ValueError:
        return None


def _date_parts(name):
    """A ride name -> (y, mo, d, date-string) for its YYYY-MM-DD prefix, or
    (None, _NO_DATE, _NO_DATE, name) when it carries no date (a descriptive
    title).  The date the dashboard keys off lives in the `Ride` column, which
    trackview sets to the ride's calendar date."""
    m = _DATE_RE.match(name or "")
    if not m:
        return (None, _NO_DATE, _NO_DATE, name or "")
    y, mo, d = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return (y, mo, d, f"{m.group(1)}-{m.group(2)}-{m.group(3)}")


def _detect_delimiter(text):
    """The CSV field delimiter: trackview's default is ';' (the European/Excel
    default), but a hand-edited file may use ',' -- sniff it off the first
    non-empty line so the reader copes with either."""
    for line in text.splitlines():
        if line.strip():
            return ";" if ";" in line else ","
    return ";"


def _parse_csv(path):
    """Read a per-ride CSV -> a list of {key: value} ride dicts, mapped by header.

    The first non-empty row is the header; each later non-empty row is one ride.
    Columns are keyed by *name* (via `_HEADER_KEY`), not position, so the reader is
    robust to columns being added or reordered.  A header cell we don't recognise
    is skipped; a ride row shorter than the header leaves its tail columns absent
    (read as missing).  Uses the stdlib `csv` with a sniffed delimiter (';' by
    default), so quoted fields and either separator are handled.
    """
    text = Path(path).read_text()
    rows = list(csv.reader(text.splitlines(),
                           delimiter=_detect_delimiter(text)))
    # the header is the first non-empty row
    header = next((r for r in rows if any(c.strip() for c in r)), [])
    cols = [(_HEADER_KEY.get(c.strip()), c.strip())
            for c in header if c.strip()]
    rides = []
    for row in rows[1:]:
        if not any(c.strip() for c in row):
            continue
        cells = [c.strip() for c in row]
        ride = {key: cells[j] for j, (key, _h) in enumerate(cols)
                if key is not None and j < len(cells)}
        rides.append(ride)
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


def parse_rides(path):
    """Parse a per-ride CSV into a list of dict rides.

    Read by *column header* (`_parse_csv`), so it is immune to the .txt table's
    column-count drift -- a row carries `date` (from the `Ride` column), `dist`,
    `gain`, `power`, `grade`, `hours`, `y`/`mo`/`d` and `device`.  The calendar
    date is derived from the `Ride` column's YYYY-MM-DD prefix (`_date_parts`); a
    ride whose name carries no date keeps `y`/`mo`/`d` at the no-date sentinel and
    is skipped by the time-axis panels.  Durations "2h 05m" / "45m" become hours;
    a missing metric ('-') becomes None.
    """
    rides = []
    for row in _parse_csv(path):
        y, mo, d, datestr = _date_parts(row.get("date"))
        row["y"] = y; row["mo"] = mo; row["d"] = d; row["date"] = datestr
        row["dist"] = _f(row.get("dist")); row["gain"] = _f(row.get("gain"))
        row["power"] = _f(row.get("power")); row["grade"] = _f(row.get("grade"))
        row["hours"] = _hours(row.get("dur"))
        rides.append(row)
    return rides


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


def _dated(rides):
    """The subset of rides carrying a calendar date (a YYYY-MM-DD `Ride` name) --
    the ones the time-axis panels can place.  Rides with no date (a descriptive
    title) are excluded here but still counted in the totals."""
    return [r for r in rides if r.get("y") is not None]


# ------------------------------- rendering -----------------------------------
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


def render(rides, out, title=None, top_n=10):
    """Draw the five-panel dashboard to `out` (a file path); returns `out`.

    `top_n` sizes the "top rides by distance" leaderboard (panel 2).
    """
    cumulative(rides)
    agg = monthly(rides)
    tops = top_rides(rides)

    total_km = sum(x["dist"] or 0.0 for x in rides)
    total_gain = sum(x["gain"] or 0.0 for x in rides)
    total_h = sum(x["hours"] or 0.0 for x in rides)
    # the time-axis panels (the headline year range, the cumulative curve, the
    # calendar, the monthly chart) key off a calendar date; a ride whose `Ride`
    # name carries none can't be placed, so it is dropped from those panels only
    # (it still counts in the headline totals above).  Fall back to a single
    # nominal year if every ride is undated, so the figure still renders.
    dated = _dated(rides)
    if dated:
        years = sorted({x["y"] for x in dated})
    else:
        dated = rides
        years = [2000]
    head = title or f"trackview {__version__} - year in review   {len(rides)} rides - " \
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
    # ~1.12x limit and clips at the figure edge.  Round the limit up to the next
    # 10 km *past* the top ride (>= +10 km of room) so the last gridline sits
    # beyond the longest label -- the axis no longer *reads* as "ends at 100" when
    # a ride tops 100 km -- while the bars stay comparable and the span stays
    # tight.  `top` is sorted *descending*, so its first element is the longest
    # ride; use that -- not dists[0], which is the *shortest* here because `dists`
    # tracks the reversed (bottom-to-top) bar order, so dists[0] is the smallest.
    top_dist = (top[0]["dist"] or 0.0) if top else 1.0
    ax.set_xlim(0, math.ceil((top_dist + 10.0) / 10.0) * 10.0)
    ax.set_xticks(range(0, int(top_dist) + 20, 20))
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
    for x in dated:
        grid[x["mo"] - 1, x["d"] - 1] += x["dist"] or 0.0
    nz = grid[grid > 0]
    # Cap the colour scale so the grid reads day-to-day intensity, not one
    # outlier.  A high quantile of the riding days captures the strong days a
    # rider remembers, while a floor keeps a quiet season from under-scaling the
    # grid.
    vmax = max(float(np.quantile(nz, 0.9)), 15.0) if nz.size else 15.0
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
    # key the per-year lines off the years actually present (from the dated rides),
    # not the headline `years` (which is a nominal fallback when every ride is
    # undated) -- so an undated-only log doesn't draw an empty 2000 line.
    agg_years = sorted({y for (y, _m) in agg})
    for y in agg_years or years:
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


# ------------------------------- entry point ---------------------------------
def _latest_log(stats=STATS_DIR):
    """The most recent per-ride CSV in the stats dir -- the one to report on.

    Prefers the plain per-ride CSVs (`trackview-<range>.csv`, not the '_summary'
    / '_climbs' variants, which have no per-ride rows to report on), newest by
    mtime, so a fresh ride shows up without naming the file.
    """
    cands = [p for p in Path(stats).glob("trackview-*.csv")
             if not p.name.endswith(("_summary.csv", "_climbs.csv"))]
    if not cands:
        raise SystemExit(f"no per-ride ride log found in {stats} "
                         "(set $TRACKVIEW_HOME or run trackview --csv first)")
    return max(cands, key=lambda p: p.stat().st_mtime)


def write_dashboard(log=None, out=None, top_n=5, title=None,
                    stats=STATS_DIR, out_dir=OUTPUT_DIR, fmt="png"):
    """Read a per-ride CSV, render the five-panel dashboard, return the path.

    `log` names a specific `stats/` CSV; with none it reports on the newest plain
    CSV there (`_latest_log`).  `out` names the output file anywhere; with none it
    writes `<log-stem>_dashboard.<fmt>` into `out_dir` (the data dir's
    output/ -- the same place the tool drops its maps, git-ignored).  `top_n`
    sizes the leaderboard (panel 2).  A *report over the persisted ride log*, so
    it is decoupled from this run's --since/--until/--device/--sport/--top
    selection; it fetches no basemap (works under --no-map / --sparse).
    """
    log = Path(log) if log is not None else _latest_log(stats)
    out = Path(out) if out is not None else out_dir / f"{log.stem}_dashboard.{fmt}"
    out.parent.mkdir(parents=True, exist_ok=True)
    rides = parse_rides(log)
    if not rides:
        raise SystemExit(f"no rides parsed from {log}")
    written = render(rides, out, title=title, top_n=top_n)
    print(f"   --dashboard: {len(rides)} rides from {log.name} -> {written}")
    return written

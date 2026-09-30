"""Year-in-review summary report helpers for trackview.

Extracted from the trackview monolith (see PLAN.md, Phase 1.5c) -- the --summary
year-in-review report.  _summary_groups splits the rides by calendar year then month
(and an 'undated' bucket for a filename carrying no date), and write_summary prints one
block of monthly rows per year -- ride count, total distance, gain and hours, plus a
per-group point-weighted average power under --ext -- each closed by a TOTAL row, and an
'ALL years' grand total when the log spans more than one year.  Pure over the already-
parsed ride dicts (no rendering, so it writes even under --no-map): its only external
names are _ride_date / _MONTH_ABBR (trackview/helpers) and _metric_avg / _fmt_num
(trackview/metrics), so the module has no back-edge to the monolith.
"""
from __future__ import annotations

from trackview.helpers import _ride_date, _MONTH_ABBR
from trackview.metrics import _fmt_num, _metric_avg


# --- the --summary year-in-review report ------------------------------------
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

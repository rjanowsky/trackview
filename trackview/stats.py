"""Stats / ride-log report helpers for trackview.

Extracted from the trackview monolith (see PLAN.md, Phase 1.5) -- the table
report the CLI emits: the shared ride-log columns and the two writers that
print them (a .txt table and a .csv ride-log).  Pure over the already-parsed
ride dicts (no rendering); the only external names are the metadata / metric
helpers already moved to ``trackview/helpers`` and ``trackview/metrics``, so
this module has no back-edge to the monolith.  ``_stats_columns`` is the shared
column definition (a 4-tuple per column); ``write_stats`` lays it out as a
per-device .txt ride-log and ``write_csv`` the same columns as a .csv.
"""
from __future__ import annotations

import csv
from pathlib import Path

from trackview.helpers import (_title_name, _device_label, _device_groups)
from trackview.metrics import (_fmt_dur_or_dash, _fmt_num, _track_calories,
                               _calories_burned, _metric_avg, _metric_avg_track,
                                _max_grade, _max_grade_group)


# --- the shared ride-log column definition + its two writers ---------------
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

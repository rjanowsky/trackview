#!/usr/bin/env python3
"""A pointer to `trackview --dashboard` (as of 1.1.0).

The "year-in-review" dashboard moved *into* trackview as the `--dashboard` switch
(plus `--dashboard-top N`, default 5).  It now lives in `trackview/dashboard.py`,
reports over the *per-ride CSV* in the stats dir (`stats/trackview-<range>.csv`,
else the newest one -- and a run with none yet writes the current log's CSV
first, ext-forced so it carries power/grade), honours `--out` / `--format`, and
writes to the output dir -- so run it as a first-class trackview output instead of
this ad-hoc helper:

    trackview --dashboard                 # whole ride log -> a dashboard
    trackview --dashboard stats/<log>.csv --dashboard-top 10
    trackview --dashboard --out ~/Desktop/year-in-review.png --format pdf

The CSV -- not the fixed-width .txt ride-log -- is the source: it is stable (a
header + one row per ride, always the same columns), so the reader maps by column
name and never drifts when the .txt's column count varies by device type.  This
file is kept only as a discoverability pointer; its former body (the
matplotlib-only renderer) is now `trackview/dashboard.py`.
"""
import sys


def main(argv=None):
    sys.stderr.write(
        "tools/ride_dashboard.py is now 'trackview --dashboard' (1.1.0+).\n"
        "Run, e.g.:  trackview --dashboard   (or --dashboard-top 10 / --out FILE)\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

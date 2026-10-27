#!/usr/bin/env python3
"""
trackview - render every GPX track in ./gpx onto a static map image (PNG or PDF).

Pipeline:
    parse GPX (gpxpy) -> decimate points -> fetch raster base map (contextily)
     -> overlay tracks coloured by elevation (matplotlib) -> save PNG or PDF.

Usage:
    python trackview.py --version        # print the trackview version and exit
    python trackview.py                # ./gpx -> ./output/tracks_overview.png
    python trackview.py --format pdf      # write a vector PDF instead of PNG
    python trackview.py --split           # one map file per track (default: all in one)
    python trackview.py --profile --split    # an elevation + grade + telemetry ride card under each map
    python trackview.py --gallery 6                 # tile the N most recent rides into one mosaic contact sheet -> output/ (bare --gallery = 9, a 3x3)
    python trackview.py --style sat    # Esri satellite base map
    python trackview.py --detail 15      # override the auto-chosen detail
    python trackview.py --no-elev      # flat colour instead of elevation shading
    python trackview.py --color-by grade       # shade the route by slope (climbs hot, descents cold)
    python trackview.py --color-by power        # shade by effort (fast/high = hot; needs --ext)
    python trackview.py --heat                   # overlay a 2-D "time on route" density under the routes
    python trackview.py --labels                 # label each route by name + distance (a combined map)
    python trackview.py --ext          # add avg power/speed/cadence/hr/temperature + calories burned (kcal) to the title
    python trackview.py --no-map            # skip the map; just compute the stats + write the stats/ file
    python trackview.py --since 2026-09-08    # only tracks on/after a date (from the .gpx filename)
    python trackview.py --until 2026-09-05    # only tracks on/before a date (from the .gpx filename)
    python trackview.py --today                # a "what did I ride today?" glance: --flat --since <today> (with --list it is a no-fetch glance)
    python trackview.py --device "Wahoo ELEMNT BOLT"    # restrict to one device  (GPX <desc>)
    python trackview.py --sport Bike                    # restrict to one sport    (GPX <desc>)
    python trackview.py --top 10 --by gain              # render/stat only the N highest-gain rides (or --by km/recent)
    python trackview.py --top 5                         # ... or the N most recent (--by default)
    python trackview.py --csv                # also write a CSV ride-log (header + rows, no totals) to stats/
    python trackview.py --csv --csv-delimiter ,    # comma-separated instead of the default ';'
    python trackview.py --sparse               # quiet stdout: skip the per-track stats listing
    python trackview.py --gain-noise 1.5       # ignore GPS vertical jitter (a dip must exceed 1.5 m) when summing ascent
    python trackview.py --climbs 10            # also write a climb ranking (top N by gain x avg grade) to stats/
    python trackview.py --trend                  # a per-ride training-trend chart over ride date -> output/
    python trackview.py --calendar              # a GitHub-style activity grid (km/day) over the year -> output/
    python trackview.py --calendar --calendar-by gain # colour each day by m gain (or 'rides') instead of km
    python trackview.py --calendar --year 2026  # restrict the grid to one calendar year
    python trackview.py --summary               # a year-in-review report (per year/month) -> stats/
    python trackview.py --dashboard                # a single shareable 'year-in-review' ride-log PNG (trophy shelf, top-N leaderboard, cumulative distance, a ride calendar, monthly distance-vs-gain by year) reported over the persisted per-ride CSV -> output/
    python trackview.py --dashboard-year 2026      # scope the --dashboard to one calendar year YYYY (implies --no-map; generates that year's ride-log CSV) -> output/
    python trackview.py --html                    # a self-contained interactive Leaflet map (inline GeoJSON + a tile layer) -> output/
    python trackview.py --html --html-cdn         # reference Leaflet from a CDN instead of inlining it (a smaller file, needs internet to view)
    python trackview.py --no-scale             # omit the map's lower-right scale bar (on by default)
    python trackview.py --no-cache             # fetch tiles fresh each run (default: cache them under tiles/)
    python trackview.py --flat                 # look for *.gpx only in the input dir (default: recurse into subfolders, e.g. a year/ layout)
    python trackview.py --list                  # list the rides that survive every filter, then stop (no basemap, no image)
    python trackview.py --list --since 2026-09-01 --top 10 --by gain      # preview a filter selection without fetching a basemap
"""
from __future__ import annotations

from trackview.cli import main


if __name__ == "__main__":
    main()

# trackview

Plot every GPX track in `./gpx` onto a static map image (PNG or PDF).

## What it does

1. Reads all `*.gpx` from the `gpx/` folder (`gpxpy`).
2. Decimates the points (default 5 m spacing) — keeps the route shape, cuts the
   point count for crisp, fast drawing.
3. Fetches a raster base map for the tracks' bounding box (`contextily`,
   OpenStreetMap by default — great for MTB/cycling).
4. Overlays each route, shaded by elevation, with a white halo, start/stop
   markers, an elevation colourbar, a legend and a title.
5. Writes `output/tracks_overview.png` by default (see **Output** for PDF and one-file-per-track).

## Setup

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

## Usage

```bash
python trackview.py                    # ./gpx -> ./output/tracks_overview.png
python trackview.py --format pdf           # vector PDF instead of PNG
python trackview.py --split                # one map file per track (default: all in one)
python trackview.py --style sat        # Esri satellite base map
python trackview.py --style terrain    # Esri shaded-relief
python trackview.py --zoom 13          # override the auto-chosen zoom
python trackview.py --no-elev          # flat per-track colour instead of elevation
python trackview.py --ext              # avg power/speed/cadence/hr + calories burned (kcal) in the title
python trackview.py --no-map             # skip the map image; just compute the stats + write the stats/ ride-log
```

## Output

- **Format** `--format {png,pdf}` (default `png`): PNG is a raster image; PDF is a
  vector file (crisp at any zoom, small, good for print).
- **Combined vs split** `--split` writes one map file *per track*, named after its
  GPX file with spaces made filesystem-safe (e.g.
  `2026-09-07_3264766585_2026-09-07_11_45.png`). By default every track is drawn
  onto a single map.  In `--split` mode each map's title shows the ride date as
  `YYYY-MM-DD` (from a Wahoo-style filename stem, e.g. `2026_09_11_08_07_29`); any
  other name (e.g. a komoot title) is shown as-is.
- The file is `output/tracks_overview.<format>` unless overridden with `--out`;
  with `--split` the per-track files go to the same directory.
- **Telemetry** `--ext` adds the calories-burned **total** (kcal) to the main title
  line and an average power / heart rate / speed / cadence line just below it, read
  from the `<extensions>` that `wahoo_to_gpx --ext` embeds. The calories are
  estimated as average power times the ride's duration, divided by a ~25% efficiency
    (the rides carry no calorie field). Tracks without telemetry (e.g. komoot)
    simply omit both.
- The ride **duration** (`Hh MMm`, e.g. `3h 42m`) is always on the title, between
  the distance and the elevation gain — the total across the tracks when combined.
- Every run also writes a **ride-log table** to `stats/trackview-<first>_<last>.txt`
  (`<first>`/`<last>` are the earliest and latest ride dates, `YYYY-MM-DD`): one row
  per ride with the same stats as the two title lines (distance, duration, gain — plus
  the calories-burned total and avg power / speed / cadence / hr when `--ext`), closing
  with a single **Summary** row of the totals/averages.  A `-` marks a metric a ride
  doesn't carry.

- `--no-map` skips the basemap fetch and image entirely (no output image, no network) and just writes the ride-log table above — a stats-only run.  The map-only flags (`--out`/`--format`/`--style`/`--zoom`/`--split`/`--no-elev`) are ignored when it is set.

## Base-map providers (`--style`)

| key         | source                                    |
| ----------- | ---------------------------------------- |
| `topo`      | OpenTopoMap — contours + relief           |
| `sat`       | Esri World Imagery (satellite)            |
| `terrain`   | Esri World Terrain Base                   |
| `osm`       | OpenStreetMap, German tiles (default)     |

Providers are tried in order; a failed or *blank* tile fetch (near-zero image
variance, e.g. rate-limiting) automatically falls back to the next one.

## Notes

- Base maps are fetched over the network at render time (a proper `User-Agent`
  is sent). Attribution is printed on the image and in the console.
- The projection is Web Mercator (EPSG:3857); the scaling constant is `π·R`
  (`20037508.34`), **not** the equatorial circumference `2·π·R`.

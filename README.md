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
python trackview.py --ext              # avg power/speed/cadence in the title
```

## Output

- **Format** `--format {png,pdf}` (default `png`): PNG is a raster image; PDF is a
  vector file (crisp at any zoom, small, good for print).
- **Combined vs split** `--split` writes one map file *per track*, named after its
  GPX file with spaces made filesystem-safe (e.g.
  `2026-09-07_3264766585_2026-09-07_11_45.png`). By default every track is drawn
  onto a single map.
- The file is `output/tracks_overview.<format>` unless overridden with `--out`;
  with `--split` the per-track files go to the same directory.
- **Telemetry** `--ext` adds a second title line with the average power /
  speed / cadence, read from the `<extensions>` that `wahoo_to_gpx --ext`
  embeds. Tracks without telemetry (e.g. komoot) simply omit the line.

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

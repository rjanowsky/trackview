"""I/O for trackview: the tile-provider config, the basemap fetch and the
self-contained HTML / Leaflet export.

Extracted from the trackview monolith (see PLAN.md, Phase 1.6) -- the home of
the map's I/O.  This holds the *tile-provider tables* the map / HTML / gallery
writers fetch from -- the HTTP User-Agent, the per-style tile-URL SOURCES (the
providers, tried in order until one loads) and the matching per-style ATTRIBUTION
lines -- the basemap fetch itself (_load_basemap: walk those providers, retrying
a transient network failure and skipping blank tiles until one shows real
tiles) -- and the self-contained HTML / Leaflet export (--html): the LEAFLET_*
config plus the _fetch_text / _load_leaflet / _geojson / _leaflet_document /
write_html helpers that build a single-file interactive map (inline GeoJSON on a
tile layer, with start/stop markers, popups and a clickable ride list).  The
--gallery writer still has a back-edge to the monolith (Phase 1.4b-ii); until it
moves, the monolith re-imports the three tables, _load_basemap and write_html,
since `render` reads the tables and calls the fetch and `main` writes the HTML.

LEAFLET_DIR is __file__-relative: it resolves to the repo's lib/ via
.parent.parent (io.py sits one level down in the package), caching the inlined
Leaflet CSS/JS there -- the tile *cache* dir (tiles/) and GPX_DIR still live in
the monolith.
"""
from __future__ import annotations

import json
import math
import time
import urllib.request
from pathlib import Path

import contextily as cx
import numpy as np
import matplotlib
matplotlib.use("Agg")                  # headless, no GUI needed (shared with the monolith)
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection

from trackview.helpers import _title_name, _ride_date
from trackview.rendering import STRONG_COLORS, PAD_FRAC, DPI

USER_AGENT    = "trackview/1.0 (static GPX->map renderer)"
 # A contact/URL can be appended here (e.g. " ...; contact: you@...") so a
 # a tile provider can reach out about rate-limiting; left blank on purpose
 # rather than ship a dead placeholder address nobody will read.

# Base-map tile providers, tried in order until one loads. OpenStreetMap is the
# default; the others are fallbacks (OpenTopoMap's contours suit MTB/cycling).
SOURCES = {
    "topo":   "https://a.tile.opentopomap.org/{z}/{x}/{y}.png",
    "sat":    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    "terrain":"https://server.arcgisonline.com/ArcGIS/rest/services/World_Terrain_Base/MapServer/tile/{z}/{y}/{x}",
    "osm":    "https://tile.openstreetmap.de/{z}/{x}/{y}.png",
}
ATTRIBUTION = {
    "topo":   "© OpenTopoMap (CC-BY-SA)",
    "sat":    "© Esri, Maxar, Earthstar Geographics",
    "terrain":"© Esri, USGS, NOAA",
    "osm":    "© OpenStreetMap contributors",
}


def _load_basemap(ax, bbox, order, detail, min_var: float = 1.0,
                  retries: int = 3, backoff_s: float = 2.0) -> str:
    """Fall back through tile providers until one shows real tiles.
    A transient fetch failure (a reset or closed connection, common when many
    tiles are pulled at once) is retried a few times with growing backoff; a
    blank fetch (near-zero pixel variance) or an empty response then moves on to
    the next provider, each after a short, polite delay."""
    for key in order:
        ax.clear()
        ax.set_xlim(bbox[0], bbox[2])
        ax.set_ylim(bbox[1], bbox[3])
        ax.set_aspect("equal")
        loaded = False
        for attempt in range(1, retries + 1):
            try:
                cx.add_basemap(ax, zoom=detail, source=SOURCES[key],    # contextily's kwarg is "zoom" (tile level)
                               headers={"User-Agent": USER_AGENT},
                               reset_extent=False)
                loaded = True
                break
            except Exception as exc:                # pragma: no cover
                if attempt < retries:
                    delay = backoff_s * (2 ** (attempt - 1))
                    print(f"  base-map '{key}' attempt {attempt}/{retries} failed "
                          f"({type(exc).__name__}); retrying in {delay:.0f}s")
                    time.sleep(delay)
                else:
                    print(f"  base-map '{key}' failed after {retries} attempts: "
                          f"{type(exc).__name__}: {exc}")
        if not loaded:
            time.sleep(2)
            continue                               # give up on this provider, try the next
        if ax.images:
            arr = np.asarray(ax.images[0].get_array()).astype(float)
            var = float(arr.var())
            if var < min_var:
                print(f"  base-map '{key}' returned blank tiles, trying next")
                time.sleep(2)
                continue
        else:
            print(f"  base-map '{key}' added no image, trying next")
            time.sleep(2)
            continue
        return key
    raise RuntimeError("all base-map sources failed")


# ---- Self-contained HTML / Leaflet export (TODO [22]) --------------------------
# A single, self-contained .html that draws the rides as inline GeoJSON on a
# Leaflet map: a tile layer (a URL matching --style, that the browser fetches to
# view) plus the routes embedded as GeoJSON LineStrings, start/stop markers,
# popups and a clickable ride list.  No server: the file opens from disk
# (file://) and zooms/pans, complementing the static PNG/PDF.  It is a different
# deliverable from the parent repo's interactive gpx_viewer.py (a Streamlit +
# Folium upload app) -- this is a static, dependency-light, single file.
#
# The Leaflet CSS + JS are inlined by default, so the output is genuinely offline
# and shareable as one file; the download is cached on disk under lib/
# (git-ignored, like the tile cache) so re-renders don't refetch, and a run with
# no network and no cache falls back to a CDN reference (the file then needs
# internet to *view*, but not to generate).   --html-cdn forces the CDN reference.

LEAFLET_VER      = "1.9.4"
LEAFLET_JS_CDN   = f"https://unpkg.com/leaflet@{LEAFLET_VER}/dist/leaflet.js"
LEAFLET_CSS_CDN  = f"https://unpkg.com/leaflet@{LEAFLET_VER}/dist/leaflet.css"
LEAFLET_DIR      = Path(__file__).resolve().parent.parent / "lib"          # cached library (git-ignored)
LEAFLET_TIMEOUT  = 15.0


def _html_escape(s: str) -> str:
    """Escape the HTML-significant characters in a user-derived string (a ride
    name) before it is written into the document's static <title> tag; the ride
    list and popups escape on the client side (the app script's esc())."""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _fetch_text(url: str, cache_path, timeout: float = LEAFLET_TIMEOUT):
    """Fetch `url` as text, caching the download under `cache_path` (so a
    re-render -- or an offline run -- reuses it, as the tile cache does for the
    basemap).  Returns the text, or None when neither a cache nor a fetch
    succeeds (offline with nothing cached), so the caller can fall back to a CDN
    reference instead of hard-failing."""
    if cache_path is not None and cache_path.exists():
        if cache_path.stat().st_size > 0:
            return cache_path.read_text(encoding="utf-8", errors="replace")
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            data = r.read()
    except Exception as exc:                                # offline / unreachable / rate-limited
        print(f"         --html: could not fetch {url} ({type(exc).__name__}); "
                    "falling back to a CDN reference")
        return None
    text = data.decode("utf-8", "replace")
    if cache_path is not None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(text, encoding="utf-8")
    return text


def _load_leaflet(inline: bool = True):
    """The Leaflet CSS + JS for the HTML head, as ready-to-inject head elements.
    When `inline`, the library text is embedded in the .html (a genuinely offline,
    single-file output) using the on-disk cache or a one-time CDN fetch; when it
    can't be obtained (offline, nothing cached) we fall back to a CDN
    <link>/<script> reference so generation still succeeds.  Returns a
    (css_html, js_html, mode) triple, mode being 'inline' or 'cdn'."""
    if inline:
        js = _fetch_text(LEAFLET_JS_CDN, LEAFLET_DIR / "leaflet.js")
        css = _fetch_text(LEAFLET_CSS_CDN, LEAFLET_DIR / "leaflet.css")
        if js and css:
            # keep an (unlikely) embedded closing tag from ending the inlined block
            js = js.replace("</script", "<\\/script")
            css = css.replace("</style", "<\\/style")
            return f"<style>\n{css}\n</style>", f"<script>\n{js}\n</script>", "inline"
    css = f'<link rel="stylesheet" href="{LEAFLET_CSS_CDN}"/>'
    js = f'<script src="{LEAFLET_JS_CDN}"></script>'
    return css, js, "cdn"


def _ride_feature(t, color) -> dict:
    """One ride as a GeoJSON LineString feature: its decimated WGS84 points
    (rounded to ~11 cm, 5 decimals) as [lon, lat] coordinates -- GeoJSON's
    order, the mirror of the (lat, lon) kept on the ride dict -- with the ride's
    name / distance / gain / duration / colour in the properties the map's popups
    and ride list read."""
    coords = [[round(lo, 5), round(la, 5)] for (la, lo) in t.get("ll") or []]
    return {
        "type": "Feature",
        "properties": {
            "name": _title_name(t["name"]),
            "dist_km": round(t["dist_km"], 1),
            "gain_m": round(t["gain_m"]),
            "duration_s": round(t.get("duration_s", 0.0), 1),
            "color": color,
        },
        "geometry": {"type": "LineString", "coordinates": coords},
    }


def _tracks_geojson(tracks) -> dict:
    """The rides as a GeoJSON FeatureCollection: one LineString feature per ride
    that has at least two decimated points, each coloured by its place in
    STRONG_COLORS (so a many-ride overview stays distinct, as the static map's
    flat mode).  A route with fewer than two points contributes nothing."""
    feats = []
    for i, t in enumerate(tracks):
        if len(t.get("ll") or []) < 2:
            continue
        feats.append(_ride_feature(t, STRONG_COLORS[i % len(STRONG_COLORS)]))
    return {"type": "FeatureCollection", "features": feats}


# The app script: builds the Leaflet map from the embedded GeoJSON -- a tile
# layer at the supplied URL, one white-cased coloured route + start/stop markers
# + a popup per ride, a clickable ride list, fit to the data on load.  The four
# __TOKEN__ placeholders are filled by _leaflet_document.
_APP_JS = r"""
(function () {
  var RIDE_DATA = __DATA__;
  var TILE_URL   = __TILE__;
  var ATTRIB     = __ATTR__;
  var TITLE      = __TITLE__;

  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) {
      return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c];
    });
  }
  function fmtDur(s) {
    var h = Math.floor(s / 3600), m = Math.round((s % 3600) / 60);
    return h > 0 ? (h + 'h ' + String(m).padStart(2, '0') + 'm') : (m + 'm');
  }

  var map = L.map('map', { zoomControl: true });
  L.tileLayer(TILE_URL, { attribution: ATTRIB, maxZoom: 19 }).addTo(map);

  document.getElementById('title').innerHTML = '<b>' + esc(TITLE) + '</b>';

  var totalBounds = L.latLngBounds([]);
  var sidebar = document.getElementById('rides');
  var tot = { dist: 0, gain: 0, n: 0 };

  RIDE_DATA.features.forEach(function (f) {
    var p = f.properties;
    var ll = f.geometry.coordinates.map(function (c) { return [c[1], c[0]]; });
    if (!ll.length) return;
    var color = p.color;
    L.polyline(ll, { color: '#ffffff', weight: 6, opacity: 0.85 }).addTo(map);
    var line = L.polyline(ll, { color: color, weight: 3.5, opacity: 0.95 });
    line.addTo(map);
    L.circleMarker(ll[0], { radius: 5, color: '#000', weight: 1,
                            fillColor: '#2ecc40', fillOpacity: 1 }).addTo(map);
    L.circleMarker(ll[ll.length - 1], { radius: 5, color: '#000', weight: 1,
                            fillColor: '#e41a1c', fillOpacity: 1 }).addTo(map);

    var dur = p.duration_s > 0 ? fmtDur(p.duration_s) : '--';
    line.bindPopup('<b>' + esc(p.name) + '</b><br>'
          + p.dist_km.toFixed(1) + ' km &nbsp; + ' + p.gain_m + ' m &nbsp; ' + dur);

    var row = document.createElement('div');
    row.className = 'ride';
    row.innerHTML = '<span class="dot" style="background:' + color + '"></span>'
          + esc(p.name) + ' <span class="muted">' + p.dist_km.toFixed(1) + ' km</span>';
    row.onclick = function () { map.fitBounds(ll, { padding: [30, 30] }); line.openPopup(); };
    sidebar.appendChild(row);

    totalBounds.extend(ll);
    tot.dist += p.dist_km;
    tot.gain += p.gain_m;
    tot.n += 1;
  });

  var sum = document.createElement('div');
  sum.className = 'total';
  sum.innerHTML = '<b>TOTAL</b> &nbsp; ' + tot.n + ' ride'
        + (tot.n === 1 ? '' : 's') + ' &nbsp; ' + tot.dist.toFixed(1)
        + ' km &nbsp; + ' + Math.round(tot.gain) + ' m';
  sidebar.appendChild(sum);

  if (totalBounds.isValid()) map.fitBounds(totalBounds, { padding: [30, 30] });
})();
"""


def _leaflet_document(gj, tile_url, attribution, title, css_html, js_html) -> str:
    """Build the self-contained interactive-map HTML: a Leaflet map (the CSS +
    JS supplied as `css_html`/`js_html` -- inlined or a CDN reference) with the
    rides as inline GeoJSON (`gj`), a tile layer at `tile_url` (attributed), a
    white-cased coloured route + start/stop markers + a popup per ride, a
    clickable ride list, fit to the data on load.  The GeoJSON is embedded as a
    JSON blob with '<' escaped (so a ride name can never close the <script>), and
    the ride names shown in the DOM are HTML-escaped client-side.  Pure -- no I/O;
    the caller writes the returned string to disk."""
    data = json.dumps(gj, separators=(",", ":")).replace("<", "\\u003c")
    js = (_APP_JS
          .replace("__DATA__", data)
          .replace("__TILE__", json.dumps(tile_url))
          .replace("__ATTR__", json.dumps(attribution))
          .replace("__TITLE__", json.dumps(title)))
    style = (
        "html,body{margin:0;height:100%;"
        "font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;}\n"
        "#map{position:absolute;inset:0;}\n"
        "#panel{position:absolute;top:12px;right:12px;z-index:1000;width:250px;"
        "max-height:80%;overflow:auto;background:rgba(255,255,255,0.92);"
        "border-radius:8px;box-shadow:0 1px 4px rgba(0,0,0,0.3);padding:8px 10px;font-size:13px;}\n"
        "#title{font-size:14px;margin-bottom:6px;border-bottom:1px solid #ddd;padding-bottom:6px;}\n"
        ".ride{cursor:pointer;padding:2px 0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}\n"
        ".ride:hover{background:#eef;}\n"
        ".dot{display:inline-block;width:10px;height:10px;border-radius:50%;"
        "margin-right:6px;vertical-align:middle;}\n"
        ".muted{color:#666;}\n"
        ".total{margin-top:6px;padding-top:6px;border-top:1px solid #ddd;}\n"
        "#legend{margin-top:8px;font-size:11px;color:#555;}\n"
    )
    doc = (
        f'<!DOCTYPE html>\n<html lang="en">\n<head>\n'
        '<meta charset="utf-8"/>\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0"/>\n'
        f'<title>{_html_escape(title)}</title>\n'
        f'{css_html}\n'
        f"<style>\n{style}</style>\n"
        f'{js_html}\n'
        '</head>\n<body>\n'
        '<div id="map"></div>\n'
        '<div id="panel">\n'
        '<div id="title"></div>\n<div id="rides"></div>\n'
        '<div id="legend"><span style="color:#2ecc40">&#9679;</span> start &nbsp; '
        '<span style="color:#e41a1c">&#9679;</span> stop</div>\n'
        '</div>\n'
        f'<script>\n{js}\n</script>\n'
        '</body>\n</html>\n'
    )
    return doc


def write_html(tracks, out_path, style: str = "osm",
               inline: bool = True, title=None):
    """Write a self-contained, single-file interactive Leaflet map to out_path:
    the rides as inline GeoJSON on a tile layer (a URL matching `style`, fetched
    by the browser to view), with a white-cased route, start/stop markers, popups
    and a clickable ride list -- so a shareable, zoomable overview complements the
    static PNG/PDF.  The Leaflet CSS + JS are inlined by default (a genuinely
    offline single file, the download cached under lib/ like the tile cache),
    falling back to a CDN reference when the library can't be fetched or is not
    cached (then --html-cdn, or a network, is needed to *view* it).  A ride with
    fewer than two decimated points contributes no route.  Standalone -- no
    basemap fetch, no telemetry -- so it writes even under --no-map."""
    gj = _tracks_geojson(tracks)
    n = len(gj["features"])
    if not n:
        print("         --html: no ride has a route to plot.")
        return
    tile_url = SOURCES.get(style, SOURCES["osm"])
    attrib = ATTRIBUTION.get(style, ATTRIBUTION["osm"])
    if title is None:
        first = _title_name(tracks[0]["name"])
        last = _title_name(tracks[-1]["name"])
        total_km = sum(t["dist_km"] for t in tracks)
        title = (f"trackview - {n} ride{'s' if n != 1 else ''} "
                 f"({first} .. {last}, {total_km:,.0f} km)")
    css_html, js_html, mode = _load_leaflet(inline)
    html = _leaflet_document(gj, tile_url, attrib, title, css_html, js_html)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    how = ("inlined, offline single file" if mode == "inline"
              else "via CDN (needs internet to view)")
    print(f"  wrote {out_path}      ({out_path.stat().st_size // 1024} KB, leaflet {how})")


# ---- Tile-detail choice + the gallery contact sheet (TODO [32]) ------------------
# choose_detail picks the basemap zoom the fetch consumes (its companion in
# _load_basemap); the gallery tiles the most-recent rides into one mosaic sheet
# (the --split alternative, one image instead of N).
EQUATOR   = 40075016.686            # 2*pi*R: equatorial circumference, used for detail
DETAIL_MIN = 10                      # auto-chosen detail never drops below this level
DETAIL_MAX = 16                      # auto-chosen detail never rises past this level


def choose_detail(bbox, target_px: float = 1600.0, dmin: int = DETAIL_MIN, dmax: int = DETAIL_MAX) -> int:
    """Pick a tile detail level so the bbox spans roughly target_px pixels."""
    w_m = bbox[2] - bbox[0]
    d = math.log2(EQUATOR * target_px / (256.0 * w_m))
    return int(round(min(dmax, max(dmin, d))))


# ---- Gallery mosaic (TODO [32]) -----------------------------------------------
# write_gallery tiles the N most-recent rides into one contact sheet: a single-ride
# basemap + white-haloed flat route + start/stop markers + a caption per cell.
# Its back-edges are all in-module now (SOURCES/ATTRIBUTION/_load_basemap above, the
# detail unit just added) plus rendering's DPI/PAD_FRAC/STRONG_COLORS and helpers'
# _ride_date/_title_name, re-imported here -- so it carries no monolith back-edge.
def _gallery_grid(n: int) -> tuple:
    """Rows x cols that fit `n` cells with as few empty slots as possible -- a near-
    square mosaic (a 3x3 for the 9 rides the bare --gallery draws, a 2x3 for 5, a
     3x4 for 12, etc.).  The empty trailing slots of a ragged last row are just left
     blank on the sheet."""
    cols = math.ceil(math.sqrt(n))
    rows = math.ceil(n / cols)
    return rows, cols


def _gallery_cell(ax, t, idx, style, detail):
    """Draw one mosaic cell: a single-ride basemap + its white-haloed, flat-coloured
    route with green/red start/stop markers and a name/distance/gain caption above it
     -- the flat per-track look of a --split map, shrunk to a thumbnail.  The tile
    detail (zoom) is auto per cell from the ride's own extent unless `detail` pins it,
    so each ride zooms to itself rather than the whole set.  Returns the basemap
    provider actually loaded, so the figure can attribute every source it used."""
    merc = np.asarray(t["merc"], dtype=float)
    w, s, e, n = (merc[:, 0].min(), merc[:, 1].min(),
                  merc[:, 0].max(), merc[:, 1].max())
    dx, dy = (e - w) * PAD_FRAC, (n - s) * PAD_FRAC
    bbox = (w - dx, s - dy, e + dx, n + dy)
    if detail is None:
        detail = choose_detail(bbox)
    ordered = [style] + [k for k in SOURCES if k != style]
    loaded = _load_basemap(ax, bbox, ordered, detail)

    seg = np.array([[merc[j], merc[j + 1]] for j in range(len(merc) - 1)])
    halo = LineCollection(seg, colors="white", linewidths=3.0, alpha=0.9)
    halo.set_zorder(4)
    ax.add_collection(halo)
    lc = LineCollection(seg, colors=[STRONG_COLORS[idx % len(STRONG_COLORS)]],
                        linewidths=2.2, alpha=0.95)
    lc.set_zorder(5)
    ax.add_collection(lc)
    x0, y0 = merc[0]
    x1, y1 = merc[-1]
    ax.scatter([x0], [y0], s=40, color="lime", edgecolors="k",
               linewidths=0.5, zorder=7)
    ax.scatter([x1], [y1], s=40, color="red", edgecolors="k",
               linewidths=0.5, zorder=7)
    ax.axis("off")
    cap = (f"{_title_name(t['name'])}      "
           f"{t['dist_km']:,.0f} km      ▲ {t['gain_m']:,.0f} m")
    ax.set_title(cap, fontsize=9, pad=3)
    return loaded


def write_gallery(tracks, out_path, style="osm", n=9, detail=None):
    """Tile the `n` most recent rides into one mosaic contact sheet -- a 'recent
    rides' overview without opening N files, the mosaic alternative to --split (one
    image instead of N).  Each cell is a single-ride basemap + route with a caption
    (see _gallery_cell); the rides are the most recent (by filename date) of the
    already --since/--until/--device/--sport/--top-filtered tracks, shown newest-first
    so the top-left cell is the latest ride, and a ride with no date in its name ranks
    last so it drops out of a 'most recent' view first.  A ride with no route (< 2
    points, e.g. a suppressed trainer ride that slipped through) is skipped like the
    map, and an empty set is a no-op -- a line on stdout, nothing written.  A map
    output (a basemap per cell), so it fetches tiles and is skipped under --no-map."""
    def _recency(t):
        rd = _ride_date(t["path"])
        return rd.toordinal() if rd is not None else -1
    routed = [t for t in sorted(tracks, key=_recency, reverse=True)
              if len(t.get("merc") or []) >= 2]
    cells = routed if not n or n >= len(routed) else routed[:n]
    if not cells:
        print("      --gallery: no ride has a route to tile.")
        return
    rows, cols = _gallery_grid(len(cells))
    cell = 3.3                       # inches per cell; a 3x3 -> ~10x11 in, the base size
    fig = plt.figure(figsize=(cols * cell, rows * cell + 0.9), dpi=DPI)
    gs = fig.add_gridspec(rows, cols, hspace=0.24, wspace=0.20,
                          left=0.01, right=0.99, top=0.90, bottom=0.04)
    loaded_keys = []
    for k, t in enumerate(cells):
        r, c = divmod(k, cols)
        ax = fig.add_subplot(gs[r, c])
        loaded_keys.append(_gallery_cell(ax, t, k, style, detail))

    total_km = sum(t["dist_km"] for t in cells)
    if len(cells) > 1:
        span = (f"{_title_name(cells[-1]['name'])} .. "
                f"{_title_name(cells[0]['name'])}")
        title = f"trackview - {len(cells)} most recent rides   ({span})"
    else:
        name = _title_name(cells[0]["name"]) or cells[0]["name"]
        title = f"trackview - {name}   ({total_km:,.0f} km)"
    fig.suptitle(title, fontsize=13, fontweight="bold", y=0.985)

    # one attribution line, a distinct entry per basemap provider actually loaded
    used = "    ·    ".join(
        ATTRIBUTION.get(k, "© OpenStreetMap contributors")
        for k in dict.fromkeys(loaded_keys))
    fig.text(0.006, 0.005, used, fontsize=7, color="#555")
    if detail is not None:
        fig.text(0.994, 0.005, f"detail {detail}", fontsize=7,
                 color="#555", ha="right")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=DPI, facecolor="white")
    plt.close(fig)
    print(f"  wrote {out_path}    ({out_path.stat().st_size // 1024} KB)")

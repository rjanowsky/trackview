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
import time
import urllib.request
from pathlib import Path

import contextily as cx
import numpy as np

from trackview.helpers import _title_name
from trackview.rendering import STRONG_COLORS

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

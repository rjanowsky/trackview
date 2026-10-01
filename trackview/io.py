"""I/O and basemap-tile provider config for trackview.

Extracted from the trackview monolith (see PLAN.md, Phase 1.6) -- the home of
the map's I/O.  So far this holds the *tile-provider tables* the map / HTML /
gallery writers fetch from: the HTTP User-Agent, the per-style tile-URL
SOURCES (the providers, tried in order until one loads) and the matching per-
style ATTRIBUTION lines.  Pure data -- no __file__-relative path, no network --
so it moves first, ahead of the basemap fetch (_load_basemap) and the --html /
--gallery writers that consume these tables and still have a back-edge to the
monolith (Phase 1.6 / 1.4b-ii).  The monolith re-imports the three, since
`render` (still in the monolith) and `main`'s argparse both read SOURCES /
ATTRIBUTION.
"""
from __future__ import annotations

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

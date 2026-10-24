"""[Phase 4 / 4.1] The self-contained HTML / Leaflet export -- pure, offline.

        _html_escape     the HTML-significant chars in a ride name;
        _ride_feature    one ride as a GeoJSON LineString feature ([lon, lat],
                         rounded to 5 decimals) with its name / dist / gain /
                         duration / colour in the properties;
        _tracks_geojson  the FeatureCollection (a ride with < 2 points drops out);
        _leaflet_document the single-file HTML: the GeoJSON + a tile layer + the
                         app script, with every __TOKEN__ filled;
        _load_leaflet    the (css, js, mode) head -- 'cdn' mode is offline (no fetch);
        write_html       writes the file (cdn mode needs no network) and prints the
                         "no ride has a route to plot." note for an empty route.
All build the HTML from already-parsed ride dicts; only the *inline* Leaflet path
fetches the library (that is the network marker, not exercised here).
"""
import numpy as np
from pathlib import Path

from trackview.io import (_html_escape, _ride_feature, _tracks_geojson,
                            _leaflet_document, _load_leaflet, write_html,
                            _per_tile_var, _load_basemap, SOURCES, ATTRIBUTION)

# a bare ride dict with the per-segment (lat, lon) array the GeoJSON builders read
# (the shape load_tracks leaves on the ride); a 3-point route -> a real LineString.
LL = [(47.0, 8.0), (47.001, 8.001), (47.002, 8.002)]


def ride(name="2026_01_15_08_00_00", *, ll=LL, dist_km=12.5, gain_m=180.0,
           duration_s=3600.0):
     return {"path": Path("/x/%s.gpx" % name), "name": name, "ll": ll,
              "dist_km": dist_km, "gain_m": gain_m, "duration_s": duration_s}


class TestHtmlEscape:
    def test_escapes_the_html_significant_chars(self):
        out = _html_escape('a&b<c>d"e')
        assert "&amp;" in out and "&lt;" in out and "&gt;" in out and "&quot;" in out

    def test_leaves_plain_text_untouched(self):
        assert _html_escape("2026-01-15") == "2026-01-15"


class TestRideFeature:
    def test_is_a_feature_with_the_expected_properties(self):
        f = _ride_feature(ride(), "#123456")
        assert f["type"] == "Feature"
        assert f["geometry"]["type"] == "LineString"
        p = f["properties"]
        assert p["color"] == "#123456"
        assert p["dist_km"] == 12.5
        assert p["gain_m"] == 180
        assert p["duration_s"] == 3600.0
         # the ride name is normalised to a title (date form), not the raw stem
        assert p["name"] == "2026-01-15"

    def test_coordinates_are_lon_lat_rounded_to_5_decimals(self):
         # GeoJSON orders coords [lon, lat] -- the mirror of the (lat, lon) kept
         # on the ride -- each rounded to ~11 cm (5 decimals)
        coords = _ride_feature(ride(), "#123456")["geometry"]["coordinates"]
        assert coords == [[8.0, 47.0], [8.001, 47.001], [8.002, 47.002]]

    def test_missing_duration_defaults_to_zero(self):
        t = ride(); t.pop("duration_s")
        assert _ride_feature(t, "#000000")["properties"]["duration_s"] == 0.0


class TestTracksGeojson:
    def test_one_feature_per_routed_ride(self):
        gj = _tracks_geojson([ride("a"), ride("b")])
        assert gj["type"] == "FeatureCollection"
        assert len(gj["features"]) == 2

    def test_a_ride_with_fewer_than_two_points_drops_out(self):
        gj = _tracks_geojson([ride(ll=[(47.0, 8.0)]), ride()])
        assert len(gj["features"]) == 1

    def test_ride_with_no_ll_contributes_nothing(self):
        gj = _tracks_geojson([ride(ll=[])])
        assert gj["features"] == []


class TestLeafletDocument:
    def _doc(self):
        css, js = "<link x/>", '<script src="cdn"></script>'
        return _leaflet_document(_tracks_geojson([ride()]), SOURCES["osm"],
                                 ATTRIBUTION["osm"], "My Ride", css, js)

    def test_begins_with_a_doctype(self):
        assert self._doc().startswith("<!DOCTYPE html>")

    def test_title_is_html_escaped_in_its_tag(self):
        doc = _leaflet_document(_tracks_geojson([ride()]), SOURCES["osm"],
                                 ATTRIBUTION["osm"], 'Ri&de', "<c>", "<j>")
        assert "<title>Ri&amp;de</title>" in doc

    def test_every_token_is_filled(self):
        doc = self._doc()
        for tok in ("__DATA__", "__TILE__", "__ATTR__", "__TITLE__"):
            assert tok not in doc

    def test_embeds_the_geojson_and_the_tile_url(self):
        import json
        doc = self._doc()
        assert "FeatureCollection" in doc
          # the tile URL + attribution reach the page through the app script's
          # JSON-escaped __TOKEN__ fill (json.dumps escapes the non-ASCII ©),
          # not as bare literals
        assert json.dumps(SOURCES["osm"]) in doc
        assert json.dumps(ATTRIBUTION["osm"]) in doc


class TestLoadLeaflet:
    def test_cdn_mode_is_offline(self):
         # inline=False never fetches -- it returns the CDN <link>/<script> refs
        css, js, mode = _load_leaflet(inline=False)
        assert mode == "cdn"
        assert "href" in css and "src" in js


class TestWriteHtml:
    def test_writes_a_self_contained_file_in_cdn_mode(self, tmp_path):
         # inline=False needs no network, so the suite stays offline
        out = tmp_path / "map.html"
        write_html([ride()], out, style="osm", inline=False)
        assert out.exists() and out.stat().st_size > 0
        text = out.read_text(encoding="utf-8")
        assert "FeatureCollection" in text
        assert "tile.openstreetmap" in text
        assert "unpkg.com/leaflet" in text       # the CDN reference

    def test_empty_route_writes_nothing(self, tmp_path, capsys):
        out = tmp_path / "empty.html"
        write_html([ride(ll=[])], out, inline=False)
        assert not out.exists()
        assert "no ride has a route to plot" in capsys.readouterr().out

    def test_no_tracks_writes_nothing(self, tmp_path):
        out = tmp_path / "none.html"
        write_html([], out, inline=False)
        assert not out.exists()

    def test_unknown_style_falls_back_to_osm(self, tmp_path):
        out = tmp_path / "unk.html"
        write_html([ride()], out, style="bogus", inline=False)
        assert out.exists()
        assert "tile.openstreetmap" in out.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# The basemap blank/placeholder test (the --style terrain fix): _per_tile_var is
# the real "is this map blank?" check, and _load_basemap's cascade over it decides
# whether a *retired* tile provider (which serves a uniform grey "Map data not yet
# available" placeholder instead of 404-ing) is skipped for the next one.  Both are
# pure, so the whole thing is exercised offline -- the network fetch (contextily)
# is stubbed.
# ---------------------------------------------------------------------------

class TestPerTileVar:
    def test_a_uniform_grey_placeholder_reads_low(self):
         # a single 256x256 tile of one grey level: its *luminance* variance is
         # ~0, so the cascade skips it
        arr = np.full((256, 256, 3), [204, 204, 204], dtype=float)
        assert _per_tile_var(arr, (0, 0, 256, 256)) < 100

    def test_the_textured_placeholder_defeats_the_old_floor(self):
         # the crux of the fix, as a genuine failure of the *old* check.  A retired
         # tile service doesn't 404 -- it stamps a small *textured* grey "Map data
         # not yet available" placeholder.  That texture is a low but *non-zero*
         # grey-level variance (~29, the real measured figure), which clears the old
         # whole-image floor of 1.0 -- so a naive whole-mosaic check reads this blank
         # area as "real" and accepts it.  _per_tile_var uses a floor of 100 instead:
         # the textured placeholder's per-tile variance stays far under it, so the
         # cascade skips the dead provider for a real one.
        rng = np.random.default_rng(0)
        grey = rng.normal(204, 5.4, size=(256, 256))     # std ~5.4 -> var ~29
        tile = np.stack([grey, grey, grey], axis=2)       # one stamped placeholder
        mosaic = np.tile(tile, (3, 3, 1))
        bbox = (0, 0, 768, 768)                           # a 3x3 grid of 256px tiles
        assert mosaic.var() > 1.0                        # the old floor: it accepts it
        assert _per_tile_var(mosaic, bbox) < 100         # the new floor sees through it

    def test_a_real_high_var_area_reads_high(self):
         # a busy, real tile: its per-tile luminance variance is thousands, well
         # above the 100 floor, so the cascade keeps it
        rng = np.random.default_rng(0)
        arr = rng.integers(0, 256, size=(256, 256, 3)).astype(float)
        assert _per_tile_var(arr, (0, 0, 256, 256)) > 100

    def test_a_single_tile_is_the_image_itself(self):
         # one tile: nx == ny == 1, so the image *is* the tile and its own variance
         # is returned unchanged
        rng = np.random.default_rng(1)
        arr = rng.integers(0, 256, size=(256, 256, 3)).astype(float)
        assert _per_tile_var(arr, (0, 0, 256, 256)) == float(arr.mean(axis=2).var())

    def test_a_2d_grey_image_does_not_crash(self):
         # a plain grey/alpha tile is a 2D (H, W) image: there is no channel axis to
         # collapse, so the image *is* the grey level -- the helper must not assume 3D
         # (an old arr.mean(axis=2) raised AxisError on this)
        arr = np.full((256, 256), 204.0)
        assert _per_tile_var(arr, (0, 0, 256, 256)) == 0.0


class _FakeAxes:
    """A tiny stand-in for a matplotlib axes: _load_basemap only touches
    clear / set_xlim / set_ylim / set_aspect / .images, and .images[0] is read
    through np.asarray(...).get_array()."""
    def __init__(self, images):
        self._images = images
        self.limits = []

    def clear(self): self.limits.clear()
    def set_xlim(self, lo, hi): self.limits.append(("x", lo, hi))
    def set_ylim(self, lo, hi): self.limits.append(("y", lo, hi))
    def set_aspect(self, a): self.limits.append(("aspect", a))
    @property
    def images(self):
        return self._images if self._images else None


class _FakeImage:
    def __init__(self, arr): self._arr = arr
    def get_array(self): return self._arr


class TestLoadBasemapCascade:
    """_load_basemap walks the provider order and skips any whose per-tile variance
    lands below min_var (the placeholder floor); the fetch itself (contextily) is
    stubbed so this runs offline.  The providers are real SOURCES keys -- the stub
    routes by the source URL it's handed, but _load_basemap still indexes
    SOURCES[key], so fake keys would KeyError."""

    def _bbox(self):
        return (0.0, 0.0, 512.0, 512.0)      # a 2x2 tile grid

    def _real(self, seed):
        return np.random.default_rng(seed).integers(0, 256,
                                                     size=(512, 512, 3)).astype(float)

    def test_placeholder_cascades_to_the_next_provider(self, monkeypatch, capsys):
        import trackview.io as io
        BBOX = self._bbox()
        grey = np.full((512, 512, 3), [204, 204, 204], dtype=float)      # ~0 var
        ax = _FakeAxes([_FakeImage(grey)])

        def fake_add_basemap(_ax, zoom, source, headers, reset_extent=False):
            # the first provider in the order serves the placeholder, the rest are real
            ax._images = [_FakeImage(grey if "topo" in source else
                                     self._real(7))]
        monkeypatch.setattr(io.cx, "add_basemap", fake_add_basemap)
        monkeypatch.setattr(io.time, "sleep", lambda *_: None)   # no polite delays

        loaded = _load_basemap(ax, BBOX, ["topo", "sat"], 13, retries=1)
        assert loaded == "sat"
        assert "trying next" in capsys.readouterr().out   # it skipped the placeholder

    def test_first_provider_is_kept_when_it_clears_the_floor(self, monkeypatch, capsys):
        import trackview.io as io
        BBOX = self._bbox()
        ax = _FakeAxes([_FakeImage(self._real(3))])
        def fake_add_basemap(_ax, zoom, source, headers, reset_extent=False):
            ax._images = [_FakeImage(self._real(3))]
        monkeypatch.setattr(io.cx, "add_basemap", fake_add_basemap)
        monkeypatch.setattr(io.time, "sleep", lambda *_: None)
        loaded = _load_basemap(ax, BBOX, ["sat", "osm"], 13, retries=1)
        assert loaded == "sat"
        assert "trying next" not in capsys.readouterr().out

    def test_no_provider_clears_the_floor_keeps_the_best(self, monkeypatch, capsys):
        import trackview.io as io
        BBOX = self._bbox()
        grey = np.full((512, 512, 3), [204, 204, 204], dtype=float)
        ax = _FakeAxes([_FakeImage(grey)])
        def fake_add_basemap(_ax, zoom, source, headers, reset_extent=False):
            ax._images = [_FakeImage(grey)]        # every provider is blank
        monkeypatch.setattr(io.cx, "add_basemap", fake_add_basemap)
        monkeypatch.setattr(io.time, "sleep", lambda *_: None)
        loaded = _load_basemap(ax, BBOX, ["sat", "osm"], 13, retries=1)
        # none clear the floor -> the best-effort last one is returned, not an error
        assert loaded in ("sat", "osm")
        assert "best-effort" in capsys.readouterr().out

    def test_all_providers_raise_retries_then_errors(self, monkeypatch):
        import trackview.io as io
        BBOX = self._bbox()
        ax = _FakeAxes([])
        def boom(_ax, zoom, source, headers, reset_extent=False):
            raise ConnectionError("reset")
        monkeypatch.setattr(io.cx, "add_basemap", boom)
        monkeypatch.setattr(io.time, "sleep", lambda *_: None)
        with __import__("pytest").raises(RuntimeError):
            _load_basemap(ax, BBOX, ["sat", "osm"], 13, retries=2)

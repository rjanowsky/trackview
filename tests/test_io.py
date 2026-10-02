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
from pathlib import Path

from trackview.io import (_html_escape, _ride_feature, _tracks_geojson,
                            _leaflet_document, _load_leaflet, write_html,
                            SOURCES, ATTRIBUTION)

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
        css, js, mode = "<link x/>", '<script src="cdn"></script>', "cdn"
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

"""[Phase 4 / 4.1] The metadata / grouping / naming helpers -- pure, offline.

The leaves of trackview/helpers not yet covered elsewhere (the date / parse helpers
live in test_parse_helpers, _select_top / _filter_by_meta / _list_rides in
test_geometry / test_filters / test_dry_run):
      _device_type / _sport_type   the "Device:" / "Sport:" lines a <desc> carries
      _device_label                a device cell, or "unknown" for a plain track
      _device_groups               the rides split into first-seen (device, [rides]) groups
      _match_meta                  one ride's pass/fail on a --device/--sport filter
      _top_key                     a ride's --top ranking value (km / gain / recent)
      _safe_filename               a stem made safe as an output filename
      _short_label                 a compact per-ride colourbar label (title, ellipsised)
All are pure over plain strings / Path / ride dicts -- no GPX, no network, no figure.
"""
from pathlib import Path

from trackview.helpers import (_device_type, _sport_type, _device_label,
                                _device_groups, _match_meta, _top_key,
                                _safe_filename, _short_label)


def ride(name="2026_01_15_08_00_00", *, device=None, dist_km=12.5, gain_m=180.0):
     # a bare ride dict carrying just the fields these helpers read
    return {"path": Path("/x/%s.gpx" % name), "name": name, "device": device,
            "sport": None, "dist_km": dist_km, "gain_m": gain_m}


class TestDeviceAndSportType:
    def test_device_line_is_read_from_desc(self):
        assert _device_type("Converted\nDevice: Wahoo ELEMNT BOLT\nSport: Bike") \
               == "Wahoo ELEMNT BOLT"

    def test_sport_line_is_read_from_desc(self):
        assert _sport_type("Converted\nDevice: Wahoo ELEMNT BOLT\nSport: Bike") \
               == "Bike"

    def test_whitespace_around_the_value_is_trimmed(self):
        assert _device_type("Device:    Garmin Edge  ") == "Garmin Edge"
        assert _sport_type("Sport:   Bike  ") == "Bike"

    def test_none_desc_is_none(self):
        assert _device_type(None) is None
        assert _sport_type(None) is None

    def test_missing_line_is_none(self):
         # a plain komoot-style desc carries neither line
        assert _device_type("Converted from komoot_loop.gpx") is None
        assert _sport_type("Converted from komoot_loop.gpx") is None

    def test_only_the_device_line_matches(self):
         # a desc with a Device: but no Sport: -> sport is None, device is set
        desc = "Converted\nDevice: Kickr Snap"
        assert _device_type(desc) == "Kickr Snap"
        assert _sport_type(desc) is None


class TestDeviceLabel:
    def test_named_device_passes_through(self):
        assert _device_label("Wahoo ELEMNT BOLT") == "Wahoo ELEMNT BOLT"

    def test_missing_device_is_unknown(self):
        assert _device_label(None) == "unknown"

    def test_empty_device_is_unknown(self):
        assert _device_label("") == "unknown"


class TestDeviceGroups:
    def test_groups_in_first_seen_order(self):
        tracks = [ride("a", device="Wahoo ELEMNT BOLT"),
                  ride("b", device="Garmin Edge"),
                  ride("c", device="Wahoo ELEMNT BOLT")]
        groups = _device_groups(tracks)
         # first-seen order: Wahoo, then Garmin
        assert [lbl for lbl, _g in groups] == ["Wahoo ELEMNT BOLT", "Garmin Edge"]
        wahoo, garmin = groups
        assert [t["name"] for t, _g in [wahoo] for t in _g] == ["a", "c"]
        assert [t["name"] for t, _g in [garmin] for t in _g] == ["b"]

    def test_unnamed_ride_falls_in_its_own_unknown_group(self):
        tracks = [ride("a", device="Wahoo ELEMNT BOLT"),
                  ride("b", device=None)]
        groups = _device_groups(tracks)
        labels = [lbl for lbl, _g in groups]
        assert labels == ["Wahoo ELEMNT BOLT", "unknown"]

    def test_every_ride_lands_in_exactly_one_group(self):
        tracks = [ride("a"), ride("b"), ride("c", device="Garmin Edge"), ride("d")]
        groups = _device_groups(tracks)
        total = sum(len(g) for _lbl, g in groups)
        assert total == len(tracks)

    def test_empty_input_is_empty(self):
        assert _device_groups([]) == []


class TestMatchMeta:
    def test_no_filter_passes_every_ride(self):
        assert _match_meta(ride("a", device="Wahoo ELEMNT BOLT")) is True

    def test_device_filter_is_case_insensitive_trimmed(self):
        t = ride("a", device="Wahoo ELEMNT BOLT")
        assert _match_meta(t, device="wahoo elemnt bolt") is True
        assert _match_meta(t, device="Garmin Edge") is False

    def test_sport_filter_matches_the_sport(self):
        t = ride("a", device="Wahoo ELEMNT BOLT")
        t["sport"] = "Bike"
        assert _match_meta(t, sport="bike") is True
        assert _match_meta(t, sport="Run") is False

    def test_missing_value_fails_the_filter(self):
         # a ride with no Device: line never matches an active --device filter
        assert _match_meta(ride("a", device=None), device="Wahoo ELEMNT BOLT") is False

    def test_both_filters_must_hold(self):
        t = ride("a", device="Wahoo ELEMNT BOLT")
        t["sport"] = "Bike"
        assert _match_meta(t, device="Wahoo ELEMNT BOLT", sport="Bike") is True
        assert _match_meta(t, device="Wahoo ELEMNT BOLT", sport="Run") is False


class TestTopKey:
    def test_km_uses_distance(self):
        t = ride("a", dist_km=42.0)
        assert _top_key(t, "km") == 42.0

    def test_gain_uses_elevation_gain(self):
        t = ride("a", gain_m=1500.0)
        assert _top_key(t, "gain") == 1500.0

    def test_recent_uses_the_ride_date_ordinal(self):
        from datetime import date
        t = ride("2026_01_15_08_00_00")
        assert _top_key(t, "recent") == float(date(2026, 1, 15).toordinal())

    def test_recent_without_a_date_ranks_oldest(self):
         # a foreign (komoot) name has no date -> ordinal 0, the lowest rank
        t = ride("komoot_loop")
        assert _top_key(t, "recent") == 0.0

    def test_unknown_by_falls_back_to_recent(self):
         # an unrecognised --by value is not km/gain, so it reads the ride date
        from datetime import date
        t = ride("2026_03_01_08_00_00")
        assert _top_key(t, "bogus") == float(date(2026, 3, 1).toordinal())


class TestSafeFilename:
    def test_unsafe_chars_become_underscores(self):
        assert _safe_filename('a/b:c*d?e') == "a_b_c_d_e"

    def test_dots_and_underscores_are_stripped_at_the_edges(self):
        assert _safe_filename("....track..") == "track"

    def test_blank_falls_back_to_track(self):
        assert _safe_filename("///") == "track"
        assert _safe_filename("   ") == "track"

    def test_clean_name_passes_through(self):
        assert _safe_filename("komoot_loop") == "komoot_loop"


class TestShortLabel:
    def test_short_name_passes_through(self):
        assert _short_label("komoot_loop", width=16) == "komoot_loop"

    def test_long_name_is_ellipsised(self):
        out = _short_label("a_very_long_ride_name_indeed", width=16)
        assert len(out) == 16
        assert out.endswith("…")            # the ellipsis "…"
        assert out[:-1] == "a_very_long_rid"

    def test_wahoo_stem_is_titled_then_truncated(self):
         # _title_name rewrites a Wahoo stem to its date first
        out = _short_label("2026_01_15_08_00_00", width=12)
        assert out.startswith("2026-01-15")

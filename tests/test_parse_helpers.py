"""[25] The date / parse helpers on their own -- pure, no fixtures.

     _ride_date      reads a ride's calendar date off a Wahoo-style filename stem
                     (no GPX parse); None for a foreign (komoot) name.
     _parse_argdate  turns a CLI 'YYYY-MM-DD' into a date, aborting clearly on a
                     bad string instead of crashing.
"""
from datetime import date
from pathlib import Path

import pytest

from trackview.helpers import (_ride_date, _parse_argdate)


class TestRideDate:
    """_ride_date: the calendar date off a filename stem, or None."""

    def test_wahoo_stem(self):
        assert _ride_date(Path("2026_09_07_08_12_47.gpx")) == date(2026, 9, 7)

    def test_nested_path_reads_the_stem(self):
        # a year/ subfolder path (gpx/<YYYY>/...) still reads off the stem
        p = Path("gpx/2026/2026_09_07_08_12_47.gpx")
        assert _ride_date(p) == date(2026, 9, 7)

    def test_foreign_komoot_name_is_undated(self):
        assert _ride_date(Path("komoot_loop.gpx")) is None

    def test_date_but_invalid_calendar_is_none(self):
        # 13/40 isn't a real month/day, so the date() build fails -> None, not a crash
        assert _ride_date(Path("2026_13_40_08_12_47.gpx")) is None

    def test_no_time_part_still_parses_date(self):
        assert _ride_date(Path("2026_01_15.gpx")) == date(2026, 1, 15)


class TestParseArgdate:
    """_parse_argdate: a good YYYY-MM-DD -> a date; a bad string -> a clear abort."""

    def test_good_date(self):
        assert _parse_argdate("2026-09-07", "--since") == date(2026, 9, 7)

    def test_bad_date_aborts_with_a_clear_error(self):
        with pytest.raises(SystemExit) as exc:
            _parse_argdate("not-a-date", "--until")
        msg = str(exc.value)
        assert "not a YYYY-MM-DD date" in msg
        assert "--until" in msg          # names the flag that was bad

    def test_impossible_date_aborts(self):
        with pytest.raises(SystemExit):
            _parse_argdate("2026-13-40", "--since")

"""The shared internals of the two ride converters (`fit_to_gpx`, `wahoo_to_gpx`).

Both scripts read a ride in a vendor's own format and emit a standard GPX 1.1
`<trk>` that `trackview` then renders.  Everything they had in common -- copied
from one into the other, byte for byte -- lives here so there is a single
source, and the two top-level `*_to_gpx.py` scripts stay thin: they re-export
these helpers (so `import *_to_gpx` and `python *_to_gpx.py` are unchanged) and
carry only their own `ride_to_gpx` / `main` (the vendor-specific reading + CLI
glue) plus their own `_ride_date` (the Wahoo and Garmin filename schemes differ).

The single-source pieces are:
    * `_parse_argdate`     the `--since`/`--until` YYYY-MM-DD CLI date parse (was
                           copied into both converters *and* kept in
                           `trackview.helpers`, which now re-exports this one);
    * `_distance_and_gain` the raw per-segment distance + ascent, the equirectangular
                           formula shared by both converters (kept *separate* from
                           `trackview.geometry._distance_and_gain` on purpose: that
                           one is climb-aware and is what the map / ride-log / climb
                           ranking read; these raw numbers go into the GPX
                           `<desc>`/metadata the converter prints);
    * `_fill_altitude`     forward/back-fill a vendor's "no altitude" sentinel so the
                           `<ele>` series is continuous; the sentinel itself is
                           vendor-specific, so the caller passes its own
                           `is_missing(alt)` predicate (Wahoo's `not a`, FIT's
                           `_missing_alt`);
    * `_add_extensions`    embed a sample's telemetry as the un-namespaced
                           `<trkpt><extensions>` children `trackview._TELE_TAGS`
                           reads;
    * the FIT-side reading -- `_iter_messages`, `_extract_meta`, `_start_time_of`,
      `_record_altitude`, `_missing_alt`, `_to_utc`, the machine->human
      `_device_name`/`_sport_name` (and their `_DEVICE_WORDS`/`_SPORT_WORDS` maps)
      -- which the FIT converter uses but the JSON Wahoo one does not.

The two `ride_to_gpx` differ enough (a JSON SAMPLES stream vs a binary FIT
record stream, different metadata) to stay in their own module; `fitparse` is an
optional extra, so its import is guarded here and the `.fit` path degrades to a
clear message when it is absent (the Wahoo JSON path never needs it).
"""
from __future__ import annotations

import math
from datetime import date, datetime, timezone
from pathlib import Path

import xml.etree.ElementTree as ET

from gpxpy import gpx as gpx_struct        # noqa: F401  (shared, schema-valid GPX writer)

try:                                    # fitparse is an optional extra (the `fit` extra);
    from fitparse import FitFile, StandardUnitsDataProcessor, FitParseError
    _HAS_FITPARSE = True
except ImportError:                     # absent: the .fit path is unavailable, JSON still works
    _HAS_FITPARSE = False
    FitParseError = type("FitParseError", (Exception,), {})


# --------------------------------------------------------------------------- #
#  the CLI date filter (shared by both converters and, by re-export, by
#  trackview.helpers / trackview.cli)
# --------------------------------------------------------------------------- #
def _parse_argdate(s: str, flag: str) -> date:
    """Parse a 'YYYY-MM-DD' CLI date, aborting with a clear error if malformed."""
    try:
        return date.fromisoformat(s)
    except ValueError:
        raise SystemExit(f"error: {flag} {s!r} is not a YYYY-MM-DD date")


# --------------------------------------------------------------------------- #
#  the raw per-segment distance (km) + ascent (m) both converters print
# --------------------------------------------------------------------------- #
def _distance_and_gain(points) -> tuple[float, float]:
    """Total distance (km) and positive elevation gain (m) over a list of
    (lat, lon, ele).  Equirectangular approximation (local lat/lon -> metres
    with a mid-latitude cosine).  The gain is the *raw* sum of every rising
    segment (kept identical across both converters on purpose) -- deliberately
    NOT the climb-aware `trackview.geometry._distance_and_gain`, which is what
    the map / ride-log / climb ranking read."""
    dist = gain = 0.0
    for (la0, lo0, e0), (la1, lo1, e1) in zip(points, points[1:]):
        lat_mid = math.radians((la0 + la1) / 2.0)
        dx = (lo1 - lo0) * 111320.0 * math.cos(lat_mid)
        dy = (la1 - la0) * 110540.0
        dist += math.hypot(dx, dy)
        if e0 is not None and e1 is not None:
            gain += max(0.0, e1 - e0)
    return dist / 1000.0, gain


# --------------------------------------------------------------------------- #
#  altitude sentinel filling -- the "no altitude" sentinel is vendor-specific
#  (Wahoo's 0 m, FIT's -500 m), so the caller passes its own is-missing predicate
# --------------------------------------------------------------------------- #
def _fill_altitude(points, is_missing) -> bool:
    """Forward/back-fill the "no altitude" sentinel so the `<ele>` series is
    continuous.  `is_missing(alt)` names the vendor's sentinel (Wahoo's `not a`,
    FIT's `_missing_alt`); returns whether any real altitude was seen at all."""
    have = False
    last = 0.0
    for p in points:
        if not is_missing(p["alt"]):
            last = p["alt"]
            have = True
        elif have:
            p["alt"] = last
    if not have:
        return False
    first = next(p["alt"] for p in points if not is_missing(p["alt"]))
    for p in points:                    # back-fill the leading run before the 1st fix
        if not is_missing(p["alt"]):
            break
        p["alt"] = first
    return True


# --------------------------------------------------------------------------- #
#  per-point telemetry -> the un-namespaced <trkpt><extensions> children
# --------------------------------------------------------------------------- #
def _add_extensions(point, p: dict) -> None:
    """Embed this sample's ride telemetry as `<trkpt><extensions>` children -- the
    same un-namespaced tags `trackview._TELE_TAGS` reads (GPX permits arbitrary
    children of `<extensions>`, processContents="skip", so the file stays valid
    and every GPX tool still reads the core track)."""
    ext = point.extensions
    if p["kph"] > 0:
        e = ET.Element("speed_kmh"); e.text = f"{p['kph']:.1f}"; ext.append(e)
    if p["watts"] > 0:
        e = ET.Element("power"); e.text = str(int(p["watts"])); ext.append(e)
    if p["cad"] > 0:
        e = ET.Element("cadence"); e.text = str(int(p["cad"])); ext.append(e)
    if p["hr"] > 0:
        e = ET.Element("heartrate"); e.text = str(int(p["hr"])); ext.append(e)
    if p["slope"]:
        e = ET.Element("grade"); e.text = f"{p['slope']:.1f}"; ext.append(e)
    if p.get("temp"):
        e = ET.Element("temperature"); e.text = str(int(p["temp"])); ext.append(e)


# --------------------------------------------------------------------------- #
#  the FIT side: a .fit stream -> messages -> a normalised point dict
#  (used by fit_to_gpx; the JSON Wahoo converter never imports the fitparse
#   names, only these, and the guard keeps the module importable without the
#   optional extra)
# --------------------------------------------------------------------------- #
# The FIT altitude field carries a +500 m offset, so a raw 0 decodes to exactly
# -500 m - that (or an absent field) is the "no altitude" sentinel, the FIT
# analogue of Wahoo's 0 m; real altitudes run well above it.
ALT_SENTINEL = -500.0

# fitparse renders the FIT enum tables to lower-case *machine* words (a
# manufacturer like 'wahoo_fitness', a sport like 'cycling'); wahoo_to_gpx.py stamps
# the *human* words its JSON carries (a device type like 'Wahoo ELEMNT BOLT', a sport
# like 'Bike').  Reword the two that disagree so a Garmin ride reads in the same voice
# as a Wahoo one and `trackview --device` / `--sport` match across both converters; any
# word not in the map passes through untouched.
_DEVICE_WORDS = {"wahoo_fitness": "Wahoo ELEMNT BOLT"}
_SPORT_WORDS = {"cycling": "Bike"}


def _to_utc(t: datetime | None) -> datetime | None:
    """fitparse renders a `timestamp` as a *naive* UTC datetime; stamp it with
    timezone.utc so gpxpy writes the trailing "Z" the existing tracks use."""
    if t is None:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _missing_alt(alt) -> bool:
    """Whether an altitude reading is the "no altitude" sentinel / absent."""
    return alt is None or math.isclose(alt, ALT_SENTINEL, abs_tol=1.0)


def _iter_messages(path: Path):
    """Parse one .fit file into its list of data messages, with the standard
    Garmin unit conversions applied (semicircles -> degrees, m/s -> km/h, ...).
    Needs the `fit` extra (fitparse); raises when it is absent."""
    if not _HAS_FITPARSE:
        raise RuntimeError("fitparse is not installed (pip install trackview[fit])")
    with FitFile(str(path), data_processor=StandardUnitsDataProcessor()) as ff:
        return list(ff.get_messages())


def _extract_meta(messages):
    """Pull the first `session` and `file_id` plus *every* `device_info`/`device`
     message out of a stream.  A ride has one session/file_id, but the device_info
     list is long (a per-sensor entry, the first often with no product), so we keep
     them all for _device_name to scan."""
    session = file_id = None
    devices = []
    for m in messages:
        n = m.name
        if n == "session" and session is None:
            session = m
        elif n == "file_id" and file_id is None:
            file_id = m
        elif n in ("device_info", "device"):
            devices.append(m)
    return session, file_id, devices


def _start_time_of(session, file_id, first_record_time) -> datetime | None:
    """The ride start, in priority order: session start_time, then the file_id
    time, then the first record's timestamp.  None when the file has none."""
    t = None
    if session is not None:
        t = _to_utc(session.get_value("start_time"))
    if t is None and file_id is not None:
        t = _to_utc(file_id.get_value("time"))
    if t is None:
        t = first_record_time
    return t


def _record_altitude(rec) -> float | None:
    """This record's altitude: prefer the barometric `enhanced_altitude` when
    present (usually steadier), else the GPS `altitude`; None when both are the
    no-altitude sentinel."""
    for name in ("enhanced_altitude", "altitude"):
        a = rec.get_value(name)
        if not _missing_alt(a):
            return a
    return None


def _reword(value, words) -> str:
    """Reword a fitparse machine word to its human equivalent when the table
    knows it (e.g. 'wahoo_fitness' -> 'Wahoo ELEMNT BOLT'), else pass it through."""
    s = str(value).strip()
    return words.get(s, s)


def _device_name(devices, file_id) -> str | None:
    """A human device label: prefer the `manufacturer` name (fitparse renders the
     FIT manufacturer enum to a string, e.g. 'wahoo_fitness'), else a 'product #N'
     from the product code.  Scans every device message then the file_id, so a sensor
     entry with no name can't win over the real computer's."""
    for src in (*devices, file_id):
        if src is None:
            continue
        man = src.get_value("manufacturer")
        if man:
            return _reword(man, _DEVICE_WORDS)
        prod = src.get_value("product")
        if prod:
            return f"product #{prod}"
    return None


def _sport_name(session) -> str | None:
    """This ride's sport in the Wahoo voice (the FIT enum reworded, e.g.
    'cycling' -> 'Bike'); None when the session carries no sport."""
    if session is None:
        return None
    sport = session.get_value("sport")
    return _reword(sport, _SPORT_WORDS) if sport else None

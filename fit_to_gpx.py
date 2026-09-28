#!/usr/bin/env python3
"""
fit_to_gpx - convert Garmin FIT ride exports (./fit/*.fit) into GPX tracks.

Each ride is a single binary .fit file, e.g.

    fit/2026-09-01-060705-ELEMNT BOLT A8C5-660-0_2026_09_01_08_07_05.fit
           ->    gpx/2026_09_01_08_07_05.gpx

The output stem is the Wahoo-style `YYYY_MM_DD_HH_MM_SS` of the ride *start
time* (not the long Garmin filename), so trackview._ride_date reads the date off
it and the Garmin rides sort / filter / sheet exactly like the Wahoo ones; a ride
with no start time at all keeps its original .fit stem.

A .fit file is a stream of typed messages (parsed via `fitparse`): a `file_id`
(who/when), zero or more `device_info` (the sensor), `session`/`lap` (totals,
sport) and one `record` per second of the ride carrying the GPS point plus
per-second telemetry.  This gathers the `record` stream into a standard GPX 1.1
<trk> with <ele> + <time> per point - the same shape wahoo_to_gpx.py emits for
the Wahoo rides, so trackview.py renders the Garmin rides alongside them.

Garmin/fitparse quirks handled:
    * position is stored in "semicircles" (a Garmin unit) -> the
      StandardUnitsDataProcessor converts it to decimal degrees, and speed
      m/s -> km/h, just like the Wahoo export already uses;
    * a "no altitude" reading is the sentinel -500 m (a raw 0 against the FIT
      altitude offset of 500) or an absent field -> filled from the neighbouring
      valid altitude, exactly as wahoo_to_gpx fills its 0 m sentinel;
    * some records carry no fix (lat/lon 0 or None) -> dropped;
    * a record's absolute time is its own UTC `timestamp`, emitted with a "Z"
      suffix to match the existing tracks;
    * a filename may carry no date at all (a bare device serial) -> the ride date
      is then read from the file's session/file_id start time.
     * the device / sport are reworded to the Wahoo voice: fitparse renders
      the FIT enum to machine words (manufacturer "wahoo_fitness", sport
      "cycling") that the converter maps to the human words wahoo_to_gpx stamps
      ("Wahoo ELEMNT BOLT", "Bike"), so a Garmin ride reads the same as a Wahoo
      one and trackview's --device / --sport match across both; an unknown word
      passes through untouched.

Usage:
    .venv/bin/python fit_to_gpx.py                        # ./fit -> ./gpx
    .venv/bin/python fit_to_gpx.py --fit-dir fit --out-dir gpx
    .venv/bin/python fit_to_gpx.py --ext                  # also embed power/cad/hr/speed(km/h)/grade/temp
    .venv/bin/python fit_to_gpx.py --since 2026-09-05               # only rides on/after a date
    .venv/bin/python fit_to_gpx.py --until 2026-09-08 --ext         # only rides on/before a date
    .venv/bin/python fit_to_gpx.py fit/2026_09_01_080705_12345.fit # one explicit file
"""
from __future__ import annotations

import argparse
import math
import re
from datetime import date, datetime, timezone
from pathlib import Path

import xml.etree.ElementTree as ET

from fitparse import FitFile, StandardUnitsDataProcessor, FitParseError

import gpxpy           # noqa: F401    (shared, schema-valid GPX writer)
from gpxpy import gpx as gpx_struct

# ------------------------------- configuration -------------------------------
IN_DIR    = Path(__file__).resolve().parent / "fit"
OUT_DIR   = Path(__file__).resolve().parent / "gpx"
CREATOR   = "fit_to_gpx/1.0 (trackview)"

# A "no altitude" reading: the FIT altitude field carries a +500 m offset, so a
# raw 0 decodes to exactly -500 m - that (or an absent field) is the sentinel,
# the FIT analogue of Wahoo's 0 m.  Real altitudes here run well above it.
ALT_SENTINEL = -500.0

# Non-standard per-point telemetry embedded under <trkpt><extensions> when --ext
# is passed.  Deliberately un-namespaced and identical to wahoo_to_gpx.py: the
# tags are exactly the keys trackview._TELE_TAGS reads, so a Garmin ride renders
# its power/cadence/heart-rate/speed/grade/temperature alongside a Wahoo one.

# fitparse renders the FIT enum tables to lower-case *machine* words (a
# manufacturer like 'wahoo_fitness', a sport like 'cycling'); wahoo_to_gpx.py stamps
# the *human* words its JSON carries (a device type like 'Wahoo ELEMNT BOLT', a sport
# like 'Bike').  Reword the two that disagree so a Garmin ride reads in the same voice
# as a Wahoo one and `trackview --device` / `--sport` match across both converters; any
# word not in the map passes through untouched.
_DEVICE_WORDS = {"wahoo_fitness": "Wahoo ELEMNT BOLT"}
_SPORT_WORDS = {"cycling": "Bike"}

# --------------------------------- helpers -----------------------------------
# Garmin names an export after its ride start, but the pattern varies by source:
# "2026_09_01_080705_12345" (Connect, underscores), "2026-09-01_080705"
# (hyphenated), or "20260901-080705" (compact, date at the stem start).  A bare
# device serial ("12345678") carries *no* date, so these stop before matching it
# (the compact form only fires when 8 digits are followed by a separator) and we
# fall back to reading the ride start from inside the file.
_NAME_SEPARATED = re.compile(r"(\d{4})[_-](\d{2})[_-](\d{2})")
_NAME_COMPACT    = re.compile(r"^(\d{4})(\d{2})(\d{2})(?=[_-])")


def _fit_date_from_filename(path: Path) -> date | None:
    """Calendar date of the ride from the filename, no parse needed.  None when
    the name (e.g. a bare device serial) carries no date."""
    for rx in (_NAME_SEPARATED, _NAME_COMPACT):
        m = rx.search(path.stem)
        if m:
            y, mo, d = (int(x) for x in m.groups())
            try:
                return date(y, mo, d)
            except ValueError:
                return None
    return None


def _to_utc(t: datetime | None) -> datetime | None:
    """fitparse renders a `timestamp` as a *naive* UTC datetime; stamp it with
    timezone.utc so gpxpy writes the trailing "Z" the existing tracks use."""
    if t is None:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _missing_alt(alt) -> bool:
    """Whether an altitude reading is the "no altitude" sentinel / absent."""
    return alt is None or math.isclose(alt, ALT_SENTINEL, abs_tol=1.0)


def _parse_argdate(s: str, flag: str) -> date:
    """Parse a 'YYYY-MM-DD' CLI date, aborting with a clear error if malformed."""
    try:
        return date.fromisoformat(s)
    except ValueError:
        raise SystemExit(f"error: {flag} {s!r} is not a YYYY-MM-DD date")


def _distance_and_gain(points) -> tuple[float, float]:
    """Total distance (km) and positive elevation gain (m) over a list of
    (lat, lon, ele).  Equirectangular approximation (local lat/lon -> metres
    with a mid-latitude cosine) - kept identical to wahoo_to_gpx.py on purpose."""
    dist = gain = 0.0
    for (la0, lo0, e0), (la1, lo1, e1) in zip(points, points[1:]):
        lat_mid = math.radians((la0 + la1) / 2.0)
        dx = (lo1 - lo0) * 111320.0 * math.cos(lat_mid)
        dy = (la1 - la0) * 110540.0
        dist += math.hypot(dx, dy)
        if e0 is not None and e1 is not None:
            gain += max(0.0, e1 - e0)
    return dist / 1000.0, gain


def _fill_altitude(points) -> bool:
    """Forward/back-fill the -500 m 'no altitude' sentinel so the <ele> series
    is continuous.  Returns whether any real altitude was seen at all."""
    have = False
    last = 0.0
    for p in points:
        if not _missing_alt(p["alt"]):
            last = p["alt"]
            have = True
        elif have:
            p["alt"] = last
    if not have:
        return False
    first = next(p["alt"] for p in points if not _missing_alt(p["alt"]))
    for p in points:                    # back-fill the leading run before the 1st fix
        if not _missing_alt(p["alt"]):
            break
        p["alt"] = first
    return True


def _record_altitude(rec) -> float | None:
    """This record's altitude: prefer the barometric `enhanced_altitude` when
    present (usually steadier), else the GPS `altitude`; None when both are the
    no-altitude sentinel."""
    for name in ("enhanced_altitude", "altitude"):
        a = rec.get_value(name)
        if not _missing_alt(a):
            return a
    return None


def _add_extensions(point, p: dict) -> None:
    """Embed this sample's ride telemetry as <trkpt><extensions> children - the
    same un-namespaced tags wahoo_to_gpx.py writes."""
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


# --------------------------------- fit reading --------------------------------
def _iter_messages(path: Path):
    """Parse one .fit file into its list of data messages, with the standard
    Garmin unit conversions applied (semicircles -> degrees, m/s -> km/h, ...)."""
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


def _ride_date(path: Path) -> date | None:
    """Calendar date of the ride: read from the filename first (no parse), and
    when the name is undated (a bare serial) fall back to the file's start time.
    None when neither yields a date, so a filter can skip it rather than guess."""
    d = _fit_date_from_filename(path)
    if d is not None:
        return d
    try:
        messages = _iter_messages(path)
    except (FitParseError, OSError):
        return None
    session, file_id, _ = _extract_meta(messages)
    first = None
    for m in messages:
        if m.name == "record":
            first = _to_utc(m.get_value("timestamp"))
            break
    t = _start_time_of(session, file_id, first)
    return t.date() if t else None


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


def _reword(value, words) -> str:
    """Reword a fitparse machine word to its human equivalent when the table
    knows it (e.g. 'wahoo_fitness' -> 'Wahoo ELEMNT BOLT'), else pass it through."""
    s = str(value).strip()
    return words.get(s, s)


def _sport_name(session) -> str | None:
    """This ride's sport in the Wahoo voice (the FIT enum reworded, e.g.
    'cycling' -> 'Bike'); None when the session carries no sport."""
    if session is None:
        return None
    sport = session.get_value("sport")
    return _reword(sport, _SPORT_WORDS) if sport else None


# --------------------------------- conversion ---------------------------------
def ride_to_gpx(path: Path, *, with_ext: bool = False):
    """Parse one Garmin .fit file into a gpxpy.GPX (single track, one segment).
    Returns (gpx, info); gpx is None when the ride has no GPS fixes."""
    messages = _iter_messages(path)
    session, file_id, devices = _extract_meta(messages)

    # keep only records with a GPS fix; a -500 m altitude is the "no altitude"
    # sentinel and is filled in by _fill_altitude below.
    pts = []
    last_t = None
    for rec in messages:
        if rec.name != "record":
            continue
        lat, lon = rec.get_value("position_lat"), rec.get_value("position_long")
        if (lat is None or lat == 0) and (lon is None or lon == 0):
            continue
        t = rec.get_value("timestamp")
        if t is not None:
            last_t = _to_utc(t)
        pts.append({
            "t":     last_t,
            "lat":   lat, "lon": lon,
            "alt":   _record_altitude(rec),
            "watts": rec.get_value("power") or 0,
            "cad":   rec.get_value("cadence") or 0,
            "hr":    rec.get_value("heart_rate") or 0,
            "kph":   rec.get_value("speed") or 0,
            "slope": rec.get_value("grade") or 0,
            "temp":  rec.get_value("temperature") or 0,
        })
    if not pts:
        return None, {}

    have_alt = _fill_altitude(pts)
    raw = [(p["lat"], p["lon"], p["alt"] if have_alt else None) for p in pts]
    dist_km, gain_m = _distance_and_gain(raw)

    first_t = _to_utc(pts[0]["t"])
    start = _start_time_of(session, file_id, first_t)

    # Wahoo names its GPX after the ride start (YYYY_MM_DD_HH_MM_SS), and
    # trackview._ride_date reads the date off that stem; do the same so the
    # Garmin rides sort/filter like the Wahoo ones.  Fall back to the (longer)
    # FIT stem when the ride carries no start time at all.
    stem = start.strftime("%Y_%m_%d_%H_%M_%S") if start else path.stem

    gpx = gpx_struct.GPX()
    gpx.version = "1.1"
    gpx.creator = CREATOR
    gpx.name = stem
    parts = [f"Converted from {path.name}"]
    dev = _device_name(devices, file_id)
    if dev:
        parts.append(f"Device: {dev}")
    sport = _sport_name(session)
    if sport:
        parts.append(f"Sport: {sport}")
    if start:
        parts.append(f"Recorded: {start.strftime('%Y/%m/%d %H:%M:%S UTC')}")
        gpx.time = start
    gpx.description = "\n".join(parts)

    trk = gpx_struct.GPXTrack(name=stem)
    gpx.tracks.append(trk)
    seg = gpx_struct.GPXTrackSegment()
    trk.segments.append(seg)
    for p in pts:
        pt = gpx_struct.GPXTrackPoint(
            latitude=p["lat"], longitude=p["lon"],
            elevation=(p["alt"] if have_alt else None),
            time=p["t"])
        if with_ext:
            _add_extensions(pt, p)
        seg.points.append(pt)

    info = {"dist_km": dist_km, "gain_m": gain_m, "n": len(pts),
            "src": sum(1 for m in messages if m.name == "record"),
            "have_alt": have_alt, "stem": stem}
    return gpx, info


# --------------------------------- entry point --------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(
        description="Convert Garmin FIT ride files (fit/) into GPX tracks (gpx/).")
    ap.add_argument("files", nargs="*",
                    help="explicit *.fit files (default: every *.fit in --fit-dir)")
    ap.add_argument("--fit-dir", "--in-dir", default=str(IN_DIR),
                    help="folder of Garmin .fit rides to read (default: ./fit); "
                         "--in-dir is kept as an alias")
    ap.add_argument("--out-dir", default=str(OUT_DIR),
                    help="folder for the .gpx output (default: ./gpx)")
    ap.add_argument("--ext", action="store_true",
                    help="also embed power/cadence/heart rate/speed/grade/temperature as "
                         "<trkpt> extensions (off by default: plain lat/lon/ele/time)")
    ap.add_argument("--since", metavar="YYYY-MM-DD", default=None,
                    help="only convert rides on/after this date; the ride date is read from "
                         "the filename, or the file's start time when the name is undated")
    ap.add_argument("--until", metavar="YYYY-MM-DD", default=None,
                    help="only convert rides on/before this date; same date source as --since")
    args = ap.parse_args()

    fit_dir, out_dir = Path(args.fit_dir), Path(args.out_dir)
    if args.files:
        paths = [Path(f) for f in args.files]
    else:
        # a .FIT and a .fit can coexist on a case-sensitive FS; dedupe by name.
        seen: set[str] = set()
        paths = []
        for pat in ("*.fit", "*.FIT"):
            for p in sorted(fit_dir.glob(pat)):
                if p.is_file() and p.name.lower() not in seen:
                    seen.add(p.name.lower())
                    paths.append(p)
    if not paths:
        print(f"No Garmin FIT files found in {fit_dir} - nothing to convert.")
        return

    lo = _parse_argdate(args.since, "--since") if args.since else None
    hi = _parse_argdate(args.until, "--until") if args.until else None
    if lo or hi:
        lo_s = lo.isoformat() if lo else "any"
        hi_s = hi.isoformat() if hi else "any"
        kept, out_of_range, undated = [], [], []
        for p in paths:
            rd = _ride_date(p)
            if rd is None:
                undated.append(p)
            elif (lo and rd < lo) or (hi and rd > hi):
                out_of_range.append(p)
            else:
                kept.append(p)
        paths = kept
        for p in undated:
            print(f"  skip (no ride date in name or file): {p.name}")
        n_total = len(kept) + len(out_of_range) + len(undated)
        if out_of_range:
            print(f"  --since/--until: {len(kept)}/{n_total} ride(s) in range "
                  f"{lo_s}..{hi_s}")
        if not paths:
            print(f"No rides within {lo_s}..{hi_s} - nothing to convert.")
            return

    print(f"fit_to_gpx - converting {len(paths)} ride(s) from {fit_dir} -> {out_dir}"
          + ("      (+telemetry extensions)" if args.ext else ""))
    out_dir.mkdir(parents=True, exist_ok=True)

    for path in paths:
        try:
            gpx, info = ride_to_gpx(path, with_ext=args.ext)
        except (FitParseError, OSError) as e:
            print(f"  skip (could not parse): {path.name}   ({e})")
            continue
        if gpx is None:
            print(f"  skip (no GPS fixes): {path.name}")
            continue
        out_path = out_dir / f"{info['stem']}.gpx"
        out_path.write_text(gpx.to_xml(version="1.1", prettyprint=True), encoding="utf-8")
        print(f"    {path.stem:<22s} {info['dist_km']:6.1f} km      "
              f"+{info['gain_m']:6.0f} m      "
              f"{info['src']:>6,} -> {info['n']:>6,} pts"
              + ("     [no altitude]" if not info["have_alt"] else "")
              + f"      -> {out_path.name}")

    print(f"done: {len(paths)} file(s) scanned, written to {out_dir}")


if __name__ == "__main__":
    main()

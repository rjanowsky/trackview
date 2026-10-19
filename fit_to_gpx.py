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

This is a thin shim over the shared internals in `trackview.convert`: the
reading helpers (`_iter_messages`, `_extract_meta`, `_start_time_of`,
`_record_altitude`, `_to_utc`, `_device_name`, `_sport_name`), the shared
distance / altitude / extension helpers, the `--since`/`--until` CLI date filter
and the `FitParseError` guard all live there (shared with `wahoo_to_gpx`); this
module carries only its own `ride_to_gpx` / `main` (the FIT-specific record loop
+ CLI glue) and its `_ride_date` (Garmin's filename scheme).  See that module
for the algorithm.

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
import re
from datetime import date
from pathlib import Path

import gpxpy           # noqa: F401    (shared, schema-valid GPX writer)
from gpxpy import gpx as gpx_struct

# The shared internals -- imported into this module's namespace so the
# `import fit_to_gpx as f2g` tests (and `python fit_to_gpx.py`) keep working,
# unchanged, against the single source in trackview.convert.  `FitParseError`
# comes through convert's optional-import guard, so the module imports even when
# the `fit` extra is absent (only the .fit path is then unavailable).
from trackview.convert import (
    _parse_argdate, _distance_and_gain, _fill_altitude, _add_extensions,
    _iter_messages, _extract_meta, _start_time_of, _to_utc, _record_altitude,
    _missing_alt, _device_name, _sport_name,
    FitParseError,
)

# ------------------------------- configuration -------------------------------
IN_DIR    = Path(__file__).resolve().parent / "fit"
OUT_DIR   = Path(__file__).resolve().parent / "gpx"
CREATOR   = "fit_to_gpx/1.0 (trackview)"

# Garmin names an export after its ride start, but the pattern varies by source:
# "2026_09_01_080705_12345" (Connect, underscores), "2026-09-01_080705"
# (hyphenated), or "20260901-080705" (compact, date at the stem start).  A bare
# device serial ("12345678") carries *no* date, so these stop before matching it
# (the compact form only fires when 8 digits are followed by a separator) and we
# fall back to reading the ride start from inside the file.
_NAME_SEPARATED = re.compile(r"(\d{4})[_-](\d{2})[_-](\d{2})")
_NAME_COMPACT    = re.compile(r"^(\d{4})(\d{2})(\d{2})(?=[_-])")


# --------------------------------- helpers -----------------------------------
def _ride_date(path: Path) -> date | None:
    """Calendar date of the ride: read from the filename first (no parse), and
    when the name is undated (a bare serial) fall back to the file's start time.
    None when neither yields a date, so a filter can skip it rather than guess."""
    for rx in (_NAME_SEPARATED, _NAME_COMPACT):
        m = rx.search(path.stem)
        if m:
            y, mo, d = (int(x) for x in m.groups())
            try:
                return date(y, mo, d)
            except ValueError:
                return None
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

    have_alt = _fill_altitude(pts, _missing_alt)
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

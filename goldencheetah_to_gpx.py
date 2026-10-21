#!/usr/bin/env python3
"""
goldencheetah_to_gpx - convert GoldenCheetah ride exports (./gc/*.json) into
GPX tracks.

The ./gc/*.json rides are exported by GoldenCheetah (the "gc" in the folder
name): the Wahoo ELEMNT BOLT itself writes Garmin .fit files, which are opened
in GoldenCheetah and re-saved in this JSON form.  So the *source* of these
files is GoldenCheetah -- the reason for the goldencheetah_to_gpx name -- even
though the ride data originated on a Wahoo device.

Each ride is a single JSON file, e.g.

    gc/2026_09_01_08_07_05.json    ->   gpx/2026_09_01_08_07_05.gpx

A file is {"RIDE": {...}} holding one SAMPLES array - one row per RECINTSECS
(usually 1 s) - with LAT/LON (already WGS-84 *decimal degrees*), ALT (metres; 0
while the GPS altitude has not locked), plus WATTS/CAD/KPH/SLOPE/TEMP.  This
turns that stream into a standard GPX 1.1 <trk> with <ele> + <time> per point -
the same shape the komoot tracks in gpx/ use, so trackview.py renders these
rides alongside them.

This is a thin shim over the shared internals in `trackview.convert` (the
distance / altitude-fill / extension helpers live there, shared with
`fit_to_gpx`); it re-exports what its tests and `python goldencheetah_to_gpx.py` need,
and carries only its own `ride_to_gpx` / `main` / `_parse_start` / `_ride_date`
(the JSON reading + CLI glue that differs from the FIT converter).  See that
module for the algorithm.

GoldenCheetah / JSON quirks handled:
   * the JSON is UTF-8 *with a BOM* -> opened as utf-8-sig;
   * a ride starts and ends with a few "no fix" rows (LAT/LON == 0) -> dropped;
   * ALT is 0 for the first minute or so (altitude lags the position lock) and 0
     is the "no altitude" sentinel (real altitudes here run 12-120 m), so the
     0 readings are filled from the neighbouring valid altitude;
   * absolute time = STARTTIME ("... UTC") + SECS, emitted with a "Z" suffix to
     match the existing tracks.

Usage:
    .venv/bin/python goldencheetah_to_gpx.py                      # ./gc -> ./gpx
    .venv/bin/python goldencheetah_to_gpx.py --gc-dir gc --out-dir gpx
    .venv/bin/python goldencheetah_to_gpx.py --ext                  # also embed power/cad/hr/speed(km/h)/grade/temp
    .venv/bin/python goldencheetah_to_gpx.py --since 2026-09-05             # only rides on/after a date
    .venv/bin/python goldencheetah_to_gpx.py --until 2026-09-08 --ext        # only rides on/before a date
    .venv/bin/python goldencheetah_to_gpx.py gc/2026_09_01_08_07_05.json    # one explicit file
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from gpxpy import gpx as gpx_struct

# The shared internals -- imported into this module's namespace so the
# `import goldencheetah_to_gpx as gcx` tests (and `python goldencheetah_to_gpx.py`)
# keep working, unchanged, against the single source in trackview.convert.
from trackview.convert import (
    _parse_argdate, _distance_and_gain, _fill_altitude, _add_extensions,
)

# ------------------------------- configuration -------------------------------
IN_DIR   = Path(__file__).resolve().parent / "gc"
OUT_DIR  = Path(__file__).resolve().parent / "gpx"
CREATOR  = "goldencheetah_to_gpx/1.0 (trackview)"

# Non-standard per-point telemetry embedded under <trkpt><extensions> when --ext
# is passed.  Deliberately un-namespaced: they are self-describing by tag name
# and GPX permits arbitrary children of <extensions> (processContents="skip"), so
# the file stays valid XML and every GPX tool can still read the core
# lat/lon/ele/time track.   (The "official" Garmin power namespace is literally
# ".../Power v1.0" - it contains a space, which would emit *invalid* XML, so we
# avoid it.)

# --------------------------------- helpers -----------------------------------
_START_RE = re.compile(r"(\d{4})/(\d{2})/(\d{2})\s+(\d{2}):(\d{2}):(\d{2})")
# GoldenCheetah names each export after the ride start time (local), so the stem
# alone tells us *when* the ride was: "2026_09_01_08_07_05".  Used by the date filter.
_STEM_RE = re.compile(r"(\d{4})_(\d{2})_(\d{2})_\d{2}_\d{2}_\d{2}")


def _parse_start(starttime: str) -> datetime:
    """'2026/09/01 06:07:05 UTC' -> tz-aware UTC datetime.  SAMPLES SECS are
    relative to this, and a tz-aware UTC value renders with a trailing "Z"."""
    m = _START_RE.search(starttime or "")
    if not m:
        raise ValueError(f"unparseable STARTTIME: {starttime!r}")
    y, mo, d, h, mi, s = (int(x) for x in m.groups())
    return datetime(y, mo, d, h, mi, s, tzinfo=timezone.utc)


def _ride_date(path: Path) -> date | None:
    """Calendar date of the ride, read from the filename stem
    (YYYY_MM_DD_HH_MM_SS, local time) - no JSON parse needed.  None when the
    name isn't Wahoo-style, so a filter can skip it rather than guess."""
    m = _STEM_RE.match(path.stem)
    if not m:
        return None
    y, mo, d, *_ = (int(x) for x in m.groups()[:3])
    return date(y, mo, d)


# --------------------------------- conversion ---------------------------------
def ride_to_gpx(path: Path, *, with_ext: bool = False):
    """Parse one GoldenCheetah ride JSON into a gpxpy.GPX (single track, one
    segment).  Returns (gpx, info); gpx is None when the ride has no GPS fixes."""
    with open(path, encoding="utf-8-sig") as fh:        # BOM-safe
        ride = json.load(fh)["RIDE"]
    start = _parse_start(ride.get("STARTTIME", ""))
    tags = ride.get("TAGS", {}) or {}

    # keep only rows with a GPS fix; a 0 altitude is the "no altitude" sentinel
    # and is filled in by _fill_altitude below.
    pts = []
    for s in ride.get("SAMPLES", []):
        lat, lon = s.get("LAT") or 0, s.get("LON") or 0
        if lat == 0 and lon == 0:
            continue
        pts.append({
            "t":     start + timedelta(seconds=int(s.get("SECS") or 0)),
            "lat":   lat, "lon": lon,
            "alt":   s.get("ALT") or 0,
            "watts": s.get("WATTS") or 0, "cad": s.get("CAD") or 0,
            "hr":    s.get("HR") or 0,
            "kph":   s.get("KPH") or 0, "slope": s.get("SLOPE") or 0,
            "temp":  s.get("TEMP") or 0,
        })
    if not pts:
        return None, {}

    have_alt = _fill_altitude(pts, lambda a: not a)
    raw = [(p["lat"], p["lon"], p["alt"] if have_alt else None) for p in pts]
    dist_km, gain_m = _distance_and_gain(raw)

    gpx = gpx_struct.GPX()
    gpx.version = "1.1"
    gpx.creator = CREATOR
    gpx.name = path.stem
    parts = [f"Converted from {path.name}",
             f"Device: {ride.get('DEVICETYPE', '?')}"]
    for label, key in (("Athlete", "Athlete"), ("Sport", "Sport"),
                       ("Workout", "Workout Code")):
        if tags.get(key):
            parts.append(f"{label}: {tags[key]}")
    st = ride.get("STARTTIME", "").strip()
    if st:
        parts.append(f"Recorded: {st}")
        gpx.time = start
    gpx.description = "\n".join(parts)
    if tags.get("Athlete"):
        gpx.author_name = tags["Athlete"]

    trk = gpx_struct.GPXTrack(name=path.stem)
    gpx.tracks.append(trk)
    seg = gpx_struct.GPXTrackSegment()
    trk.segments.append(seg)
    for p in pts:
        pt = gpx_struct.GPXTrackPoint(latitude=p["lat"], longitude=p["lon"],
                                      elevation=(p["alt"] if have_alt else None),
                                      time=p["t"])
        if with_ext:
            _add_extensions(pt, p)
        seg.points.append(pt)

    info = {"dist_km": dist_km, "gain_m": gain_m, "n": len(pts),
            "src": len(ride.get("SAMPLES", [])), "have_alt": have_alt}
    return gpx, info


# --------------------------------- entry point --------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(
        description="Convert GoldenCheetah ride JSON (gc/) into GPX tracks (gpx/).")
    ap.add_argument("files", nargs="*",
                    help="explicit *.json files (default: every *.json in --gc-dir)")
    ap.add_argument("--gc-dir", "--in-dir", default=str(IN_DIR),
                    help="folder of GoldenCheetah JSON rides to read (default: ./gc); "
                             "--in-dir is kept as an alias")
    ap.add_argument("--out-dir", default=str(OUT_DIR),
                    help="folder for the .gpx output (default: ./gpx)")
    ap.add_argument("--ext", action="store_true",
                    help="also embed power/cadence/heart rate/speed/grade/temperature as "
                         "<trkpt> extensions (off by default: plain lat/lon/ele/time)")
    ap.add_argument("--since", metavar="YYYY-MM-DD", default=None,
                    help="only convert rides on/after this date (local, read from the "
                            "filename); default: no lower bound")
    ap.add_argument("--until", metavar="YYYY-MM-DD", default=None,
                    help="only convert rides on/before this date (local, read from the "
                            "filename); default: no upper bound")
    args = ap.parse_args()

    gc_dir, out_dir = Path(args.gc_dir), Path(args.out_dir)
    paths = [Path(f) for f in args.files] if args.files else sorted(gc_dir.glob("*.json"))
    if not paths:
        print(f"No GoldenCheetah JSON files found in {gc_dir} - nothing to convert.")
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
            print(f"  skip (date not in filename): {p.name}")
        n_total = len(kept) + len(out_of_range) + len(undated)
        if out_of_range:
            print(f"  --since/--until: {len(kept)}/{n_total} ride(s) in range "
                  f"{lo_s}..{hi_s}")
        if not paths:
            print(f"No rides within {lo_s}..{hi_s} - nothing to convert.")
            return

    print(f"goldencheetah_to_gpx - converting {len(paths)} ride(s) from {gc_dir} -> {out_dir}"
          + ("    (+telemetry extensions)" if args.ext else ""))
    out_dir.mkdir(parents=True, exist_ok=True)

    for path in paths:
        gpx, info = ride_to_gpx(path, with_ext=args.ext)
        if gpx is None:
            print(f"  skip (no GPS fixes): {path.name}")
            continue
        out_path = out_dir / f"{path.stem}.gpx"
        out_path.write_text(gpx.to_xml(version="1.1", prettyprint=True), encoding="utf-8")
        print(f"  {path.stem:<22s} {info['dist_km']:6.1f} km    "
              f"+{info['gain_m']:6.0f} m    "
              f"{info['src']:>6,} -> {info['n']:>6,} pts"
              + ("   [no altitude]" if not info["have_alt"] else "")
              + f"    -> {out_path.name}")

    print(f"done: {len(paths)} file(s) written to {out_dir}")


if __name__ == "__main__":
    main()

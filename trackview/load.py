"""The GPX-reading cluster for trackview, extracted in PLAN.md Phase 1.7.

It holds `load_tracks`, the one reader that turns the caller's
discovered-and-filtered list of .gpx paths into the in-memory ride dicts
everything downstream (geometry / metrics / rendering / reports) consumes: it
parses each file with gpxpy, merges its track segments into one polyline each,
and -- over the pre-decimation samples -- accumulates the Wahoo `--ext`
telemetry and the ride's first->last timestamp span (its duration, feeding the
calories-burned estimate).  It depends only on the already-extracted leaves --
`trackview.geometry` (latlon_to_merc / decimate / _distance_and_gain /
_grade_and_cumkm), `trackview.helpers` (_device_type / _sport_type) and
`trackview.metrics` (_point_telemetry) -- so it has no back-edge to the
monolith.
"""
from __future__ import annotations

import os
from pathlib import Path

import gpxpy

from trackview.geometry import latlon_to_merc, decimate, _distance_and_gain, _grade_and_cumkm
from trackview.helpers import _device_type, _sport_type
from trackview.metrics import _point_telemetry

def load_tracks(paths, decimate_m: float, with_ext: bool = False,
                noise_m: float = 0.0) -> list[dict]:
    """Read every .gpx path (discovered and date-filtered by the caller);
    merge its segments into one polyline each.
    Always record each ride's first->last timestamp span: its duration, shown on the
    title and feeding the calories-burned estimate.  With with_ext, also collect the
    Wahoo telemetry embedded by `wahoo_to_gpx --ext` (power/speed/cadence/hr) per
    point, accumulated over every sample (pre-decimation) so the caller can show an
    accurate average.  With noise_m > 0 each ride's gain ignores GPS vertical jitter
    below noise_m (see _distance_and_gain); 0 (the default) sums every rising segment."""
    tracks = []
    for path in sorted(paths):
        with open(path, "rb") as fh:
            gpx = gpxpy.parse(fh)
        raw = []                            # (lat, lon, ele) for every point
        tele = {k: [0.0, 0] for k in ("power", "speed", "cadence", "hr", "temp")} if with_ext else None
        records = [] if with_ext else None     # per-point {time, speed, power}, carried through decimation
        t_first = t_last = None               # ride span (1st -> last timestamp) for calories
        for trk in gpx.tracks:
            for seg in trk.segments:
                for pt in seg.points:
                    raw.append((pt.latitude, pt.longitude, pt.elevation))
                    st = pt.time              # ride span -> duration (+ calories when --ext)
                    if st is not None:
                        t_first = st if t_first is None or st < t_first else t_first
                        t_last   = st if t_last  is None or st > t_last  else t_last
                    if with_ext:
                          # a per-point record: the timestamp plus any telemetry on the point
                        rec = {"t": st}
                        for key, val in _point_telemetry(pt).items():
                            rec[key] = val
                            tele[key][0] += val
                            tele[key][1] += 1
                        records.append(rec)
        if not raw:
            print(f"  skip (no points): {os.path.basename(path)}")
            continue
        dist_km, gain_m = _distance_and_gain(raw, noise_m)
        dec, dec_records = decimate(raw, decimate_m, carry=records)
        merc = [latlon_to_merc(la, lo) for (la, lo, _e) in dec]
        ele = [e for (_la, _lo, e) in dec]
        ll = [(la, lo) for (la, lo, _e) in dec]            # decimated WGS84 lat/lon,
                                                          # the --html GeoJSON export's source
        grade, cum_km = _grade_and_cumkm(dec)
        name = (gpx.name or (gpx.tracks[0].name if gpx.tracks
                              and gpx.tracks[0].name else None)
                 or Path(path).stem)
        device = _device_type(gpx.description)           # "Device: <name>" line, if any
        sport  = _sport_type(gpx.description)            # "Sport: <name>" line, if any
        d = {"path": path, "name": name, "device": device, "sport": sport,
              "n": len(raw), "ndec": len(dec),
              "merc": merc, "ele": ele, "ll": ll,
              "dist_km": dist_km, "gain_m": gain_m,
              "grade": grade, "cum_km": cum_km,
              "duration_s": (t_last - t_first).total_seconds() if t_first else 0.0}
        if tele is not None:
            d.update(tele)                    # per-metric [sum, count] pairs
        if records is not None:
            # per-decimated-point arrays, aligned with merc/ele/grade
            d["tsec"] = [r.get("t") for r in dec_records]
            d["speed_pts"] = [r.get("speed") for r in dec_records]
            d["power_pts"] = [r.get("power") for r in dec_records]
            d["cadence_pts"] = [r.get("cadence") for r in dec_records]
            d["hr_pts"] = [r.get("hr") for r in dec_records]
        tracks.append(d)
    return tracks

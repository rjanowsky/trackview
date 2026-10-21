"""Metric / telemetry / calorie / formatting helpers for trackview.

Extracted from the trackview monolith (see PLAN.md, Phase 1.3).  These turn a
parsed ride into the numbers the ride-log, the stats report and the colour scales
display: a trackpoint's optional Wahoo telemetry, the point-weighted averages and
steepest grades a ride (or a group of rides) carries, the calorie estimate from
average power and ride time, and the small "value or a dash" formatters the tables
share.  They are pure over the already-parsed ride dicts (numpy for the percentile
capping), depend on no I/O and no rendering -- the one rendering-coupled colour norm
(``_metric_norm``, which returns a matplotlib ``Normalize``) lives in
``trackview/rendering.py`` -- and are unit-tested directly.
"""
from __future__ import annotations

import numpy as np


# The grade norm is capped robustly (a high percentile of |grade|, clamped
# to a floor/ceiling) so a lone GPS-noise spike (e.g. a spurious 20 % blip)
# can't squash the whole ramp to its neutral centre and leave the route
# nearly colourless.  The colourbar shows the capped range.
GRADE_CAP_PCT    = 98.0     # % of segments inside the (capped) colour range
GRADE_CAP_FLOOR = 3.0      # min range: an all-flat ride still shows colour
GRADE_CAP_CEIL   = 15.0     # max range: steeper is rare, clamp the rest


JOULES_PER_KCAL = 4184.0        # 1 dietary "kcal" (as on food labels) = 4184 J
METABOLIC_EFFICIENCY = 0.25     # only ~25% of food energy -> pedal work; rest is heat


# Wahoo telemetry embedded under <trkpt><extensions> by `goldencheetah_to_gpx --ext`,
# mapped to the short key trackview averages.  Un-namespaced on purpose (see
# goldencheetah_to_gpx.py); gpxpy flattens the <extensions> children straight onto a
# trackpoint's .extensions list, so each element's bare .tag is the metric.
_TELE_TAGS = {"power": "power", "speed_kmh": "speed", "cadence": "cadence",
              "heartrate": "hr", "temperature": "temp"}


def _point_telemetry(point) -> dict:
    """Optional Wahoo telemetry off a trackpoint -> {key: float}.  Empty when
    the point carries no extensions (e.g. a plain komoot track)."""
    out = {}
    for ext in point.extensions:
        key = _TELE_TAGS.get(ext.tag)
        if key and ext.text:
            try:
                out[key] = float(ext.text)
            except ValueError:
                pass
    return out


def _metric_avg(tracks, key) -> float | None:
    """Point-weighted average of a per-track [sum, count] metric across the
    tracks being drawn.  None when no track carries that metric."""
    s = c = 0.0
    for t in tracks:
        m = t.get(key)
        if m:
            s += m[0]
            c += m[1]
    return s / c if c else None


def _metric_avg_track(t, key) -> float | None:
    """One ride's own average for a per-track [sum, count] metric; None when it has no samples."""
    m = t.get(key)
    if m and m[1]:
        return m[0] / m[1]
    return None


def _max_grade(t) -> float | None:
    """A ride's steepest per-segment grade (%); None when it has no graded segment."""
    gs = [g for g in t.get("grade", []) if g is not None]
    return max(gs) if gs else None


def _max_grade_group(tracks) -> float | None:
    """The steepest grade (%) across a group of rides (their per-ride maxima)."""
    gs = [v for v in (_max_grade(t) for t in tracks) if v is not None]
    return max(gs) if gs else None


def _grade_cap(grades, grade_cap: float | None) -> float:
    """|grade| colour-range cap: an explicit --grade-cap wins, else the GRADE_CAP_PCT percentile of |grade| clamped to [FLOOR, CEIL] (a GPS-noise spike can't squash the ramp, an all-flat ride still shows colour)."""
    if grade_cap and grade_cap > 0:
        return float(grade_cap)
    a = np.array([abs(g) for g in grades], dtype=float)
    cap = float(np.percentile(a, GRADE_CAP_PCT)) if a.size else GRADE_CAP_FLOOR
    return min(max(cap, GRADE_CAP_FLOOR), GRADE_CAP_CEIL)


def _track_calories(t) -> float | None:
    """This ride's 'calories burned' (kcal): avg power (W) x ride duration (s) over 4184 J/kcal and a ~25% efficiency; None without a power average or a ride span."""
    p = t.get("power")                            # [sum, count] power samples
    dur = t.get("duration_s", 0.0)
    if p and p[1] and dur:
        return (p[0] / p[1]) * dur / JOULES_PER_KCAL / METABOLIC_EFFICIENCY
    return None


def _calories_burned(tracks) -> float | None:
    """Total "calories burned" (kcal) across the tracks, estimated from average
    power (W) x ride duration (s): the mechanical work in kcal, then divided by a
    ~25% muscular efficiency (only ~1 in 4 kcal of food energy becomes pedal work).
    Summed per track; None when no track has both a power average and a measured
    duration (e.g. a plain komoot track without Wahoo telemetry)."""
    total = 0.0
    have = False
    for t in tracks:
        p = t.get("power")                        # [sum, count] power samples
        dur = t.get("duration_s", 0.0)
        if p and p[1] and dur:
            total += (p[0] / p[1]) * dur / JOULES_PER_KCAL / METABOLIC_EFFICIENCY
            have = True
    return total if have else None


def _fmt_duration(total_s: float) -> str:
    """Ride time as 'Hh MMm' (e.g. 3h 05m); '0m' for a ride under a minute."""
    h, rem = divmod(int(round(total_s)), 3600)
    m = rem // 60
    return f"{h}h {m:02d}m"


def _fmt_dur_or_dash(total_s: float) -> str:
    """Ride time as 'Hh MMm', or a '-' for a track with no measured span."""
    return _fmt_duration(total_s) if total_s > 0 else "-"


def _fmt_num(v, spec: str) -> str:
    """Format a metric value, or a "-" when it is absent (None)."""
    return "-" if v is None else f"{v:{spec}}"

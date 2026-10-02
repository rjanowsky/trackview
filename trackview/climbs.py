"""Climb-ranking report helpers for trackview.

Extracted from the trackview monolith (see PLAN.md, Phase 1.5b) -- the sustained-climb
detection and its ranking report.  A "climb" is a run of segments whose *smoothed* grade
clears CLIMB_MIN_GR over at least CLIMB_MIN_LEN of horizontal run; _ride_climbs finds the
sustained climbs in one ride, _all_climbs ranks every ride's climbs by a gain x
average-grade score, and write_climbs prints the top_n as a self-describing table.
Pure over the already-parsed ride dicts (their per-segment grade / cumulative-km /
elevation arrays): its only external names are _moving_avg (already in trackview/rendering)
and _title_name (trackview/helpers), so the module has no back-edge to the monolith.
"""

from __future__ import annotations

import numpy as np
from pathlib import Path

from trackview.helpers import _title_name
from trackview.rendering import _moving_avg

# A "climb" (see _ride_climbs) is a sustained run of segments whose *smoothed* grade stays
# above CLIMB_MIN_GR over at least CLIMB_MIN_LEN of horizontal run; the grade is smoothed
# over CLIMB_SMOOTH segments (as the profile is) so GPS jitter can't break a run.  A climb's
# 'score' (gain x its average grade) ranks a long moderate climb against a short steep one.
CLIMB_MIN_GR    = 4.0         # smoothed grade (%) a segment must clear to count as "climbing"
CLIMB_MIN_LEN    = 250.0      # min horizontal length (m) of a run to count as a climb
CLIMB_SMOOTH     = 9.0        # centred moving-avg window (segments) for the climb grade scan


def _ride_climbs(t, min_gr=CLIMB_MIN_GR, min_len_m=CLIMB_MIN_LEN,
                 smooth=CLIMB_SMOOTH) -> list[dict]:
    """Sustained climbs in one ride: maximal runs of segments whose *smoothed* grade
    stays >= min_gr and whose horizontal length reaches min_len_m.  Raw GPS grade jitters
    (as the profile's), so a centred moving average over `smooth` segments (as in
    _draw_profile) is run first; a run's gain is the positive elevation rise across it, its
    average grade the distance-weighted slope (gain / length), its max grade the steepest
    smoothed segment, and a 'score' (gain x average grade) ranks a long climb against a short
    steep one.   [] when the ride carries no grade (some tracks omit elevation)."""
    gr = t.get("grade") or []
    cum = t.get("cum_km") or []
    ele = t.get("ele") or []
    if len(gr) < 1 or len(cum) < 2 or len(ele) < 2:
        return []
    garr = np.array([(g if g is not None else np.nan) for g in gr], dtype=float)
    if not np.isfinite(garr).any():
        return []
    gs = _moving_avg(garr, smooth)
    n = len(gr)
    climbs = []
    j = 0
    while j < n:
        if not np.isfinite(gs[j]) or gs[j] < min_gr:
            j += 1
            continue
        k = j
        while k + 1 < n and np.isfinite(gs[k + 1]) and gs[k + 1] >= min_gr:
            k += 1
             # run [j, k] spans points j..k+1: length from the cumulative km, the gain from
             # the positive elevation rise across it (the ascent of that climb)
        e = min(k + 1, n - 1)
        len_km = cum[e] - cum[j]
        if len_km * 1000.0 >= min_len_m:
            gain_m = sum(max(0.0, (ele[j + 1] or 0.0) - (ele[j] or 0.0))
                         for j2 in range(j, e))
            avg_gr = 100.0 * gain_m / (len_km * 1000.0) if len_km > 0 else 0.0
            max_gr = float(np.nanmax(gs[j:e]))
            climbs.append({
                  "ride": t["name"], "device": t.get("device"),
                  "start_km": cum[j], "end_km": cum[e], "len_km": len_km,
                  "gain_m": gain_m, "avg_gr": avg_gr, "max_gr": max_gr,
                  "score": gain_m * avg_gr,
             })
        j = k + 1
    return climbs


def _all_climbs(tracks) -> list[dict]:
    """Every climb across the tracks, ranked most-significant first (by score)."""
    allc = []
    for t in tracks:
        allc.extend(_ride_climbs(t))
    allc.sort(key=lambda c: c["score"], reverse=True)
    return allc


def write_climbs(tracks, out_path: Path, top_n: int,
                 min_gr: float = CLIMB_MIN_GR, min_len_m: float = CLIMB_MIN_LEN) -> None:
    """Write a climb ranking to out_path: the top_n most-significant sustained climbs
    (runs of smoothed grade >= min_gr over at least min_len_m of horizontal run, found by
    _ride_climbs), one row each - the ride, where it sits (start->end km), its length, gain,
    average and steepest grade, and a 'score' (gain x average grade).  The header names the
    detection thresholds so the list is self-describing; an empty run writes a note."""
    climbs = _all_climbs(tracks)[:top_n]
    lines = [f"trackview - top {len(climbs)} climb"
             f"{'s' if len(climbs) != 1 else ''}  "
             f"(grade >= {min_gr:.0f}%, run >= {min_len_m:.0f} m)",
              ""]
    if not climbs:
        lines.append("  no sustained climbs found.")
    else:
        head = ["#", "Ride", "From (km)", "To (km)", "Len (km)", "Gain (m)",
                 "Avg %", "Max %", "Score"]
        align = [True, False, True, True, True, True, True, True, True]
        rows = [[str(i), _title_name(c["ride"]), f"{c['start_km']:.1f}",
                  f"{c['end_km']:.1f}", f"{c['len_km']:.1f}", f"{c['gain_m']:,.0f}",
                  f"{c['avg_gr']:.1f}", f"{c['max_gr']:.1f}", f"{c['score']:,.0f}"]
                 for i, c in enumerate(climbs, 1)]
        widths = [max(len(head[i]), *(len(r[i]) for r in rows)) for i in range(len(head))]
        sep = "         "
        def fmt(cells):
            out = []
            for i, (cell, a) in enumerate(zip(cells, align)):
                out.append(cell.rjust(widths[i]) if a else cell.ljust(widths[i]))
            return sep.join(out)
        rule = sep.join("-" * w for w in widths)
        lines.append(fmt(head))
        lines.append(rule)
        lines += [fmt(r) for r in rows]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  wrote {out_path}")

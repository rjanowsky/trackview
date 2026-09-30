"""Rendering helpers for trackview.

Extracted from the trackview monolith (see PLAN.md, Phase 1.4) -- the *leaf*
rendering helpers, the matplotlib-coupled half of the old "Rendering" phase.  These
are the colour / numeric helpers the map and profile figures build on: the two
colour-ramp constants and the device-suppression set, plus the robust colour
norm and the centred moving average.  The big render / render_* / write_* figure
cluster that *uses* them is a back-edge (it still calls helpers living in the
monolith) and stays put for the next sub-step; these leaves have no such edge,
so they move first.  They depend only on numpy and matplotlib.colors.Normalize,
so they stand on their own.
"""
from __future__ import annotations

import numpy as np
from matplotlib.colors import Normalize


# --- constants ---------------------------------------------------------------
# A sequential "effort" ramp for the telemetry colourings (--color-by speed/power):
# low = cold/dark, high = hot/bright, perceptually uniform so a rider reads pacing
# and effort at a glance (fast / high power at the hot end).  Paired with the same
# dark under-lay as the grade shading so even the cold low end pops on a pale basemap.
CMAPEED = "inferno"
GRADE_CBAR_MAX = 4.0      # max rides that each get their own grade colourbar on a
                              # combined map; beyond it a single shared scale is used (and noted)

# A "Kickr Snap" is a stationary smart trainer: its session has no route of its
# own, so its points would just clutter the basemap.  Keep such tracks off the
# rendered image, matched case-sensitively against the trimmed 'Device:' line -
# they are still listed in the ride-log/CSV (a trainer ride is still a ride).
SUPPRESSED_RENDER_DEVICES = {"Kickr Snap"}


# --- functions ---------------------------------------------------------------
def _metric_norm(vals, lo_pct: float = 2.0, hi_pct: float = 98.0):
    """A robust sequential colour norm for a telemetry metric (--color-by speed/power):
    the [lo_pct, hi_pct] percentiles of the per-segment values, so a lone outlier (a GPS
    speed spike, a one-off sprint) can't squash the ramp the way an un-capped min/max would.
    Returns None when there are no values (the caller then falls back to flat colour)."""
    if not vals:
        return None
    a = np.asarray(vals, dtype=float)
    lo = float(np.percentile(a, lo_pct))
    hi = float(np.percentile(a, hi_pct))
    if hi <= lo:
        hi = lo + 1.0
    return Normalize(vmin=lo, vmax=hi, clip=True)


def _moving_avg(arr, window: int) -> "np.ndarray":
    """Centred moving average over a fixed (odd) window, skipping NaN so a gap just shortens the window (quiet the GPS jitter in a per-segment grade line)."""
    w = max(1, int(window))
    half = w // 2
    out = np.full(len(arr), np.nan)
    for i in range(len(arr)):
        seg = arr[max(0, i - half): i + half + 1]
        good = seg[np.isfinite(seg)]
        if good.size:
            out[i] = good.mean()
    return out

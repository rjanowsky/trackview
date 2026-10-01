"""
Geometry utilities for trackview.

This module provides functions for geometric calculations and transformations
used in GPS track processing and visualization.
"""

from __future__ import annotations
import math

# Constants
PI_R      = 20037508.342789244     # pi*R: scales the Web-Mercator x/y projection


def latlon_to_merc(lat: float, lon: float) -> tuple[float, float]:
    """WGS84 (lat, lon) -> Web-Mercator (x, y) in metres."""
    x = lon * PI_R / 180.0
    y = math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)) * PI_R / math.pi
    return x, y


def decimate(points, min_m: float, carry=None):
    """Keep only points spaced >= min_m apart (equirectangular distance).  Returns the kept
    points; when `carry` (a parallel sequence, one entry per point -- e.g. the per-point
    telemetry) is given, its kept entries are returned too, aligned with the kept points."""
    if len(points) < 2:
        return points, (carry if carry is not None else None)
    n = len(points)
    keep = [0]
    last_lat, last_lon = points[0][0], points[0][1]
    min_m2 = min_m * min_m
    for i in range(1, n):
        lat, lon = points[i][0], points[i][1]
        lat_mid = math.radians((lat + last_lat) / 2.0)
        dx = (lon - last_lon) * 111320.0 * math.cos(lat_mid)
        dy = (lat - last_lat) * 110540.0
        if dx * dx + dy * dy >= min_m2:
            keep.append(i)
            last_lat, last_lon = lat, lon
    keep.append(n - 1)                     # always keep the last point
    out = [points[i] for i in keep]
    if carry is not None:
        return out, [carry[i] for i in keep]
    return out, None


def _distance_and_gain(points, noise_m: float = 0.0) -> tuple[float, float]:
    """Total distance (km) and positive elevation gain (m).  The gain is the sum of the
    rises; a descent ends the climb in progress (resetting its base) only once it exceeds
    noise_m metres, so a few cm of GPS vertical jitter can't be counted as fresh ascent on
    the way back up.  noise_m = 0 counts every rising segment - the raw ascent."""
    dist = 0.0
    gain = 0.0
    base = last = None                        # base/last (m) of the climb in progress
    for i in range(1, len(points)):
        la0, lo0, e0 = points[i - 1]
        la1, lo1, e1 = points[i]
        lat_mid = math.radians((la0 + la1) / 2.0)
        dx = (lo1 - lo0) * 111320.0 * math.cos(lat_mid)
        dy = (la1 - la0) * 110540.0
        dist += math.hypot(dx, dy)
        if e0 is None or e1 is None:          # some GPX points omit elevation
            base = last = None
            continue
        if base is None:
            base = last = e0
        if e1 > last:
            last = e1                         # track the top of the climb
        elif last - e1 >= noise_m:            # a descent past the band ends the climb
            gain += last - base
            base = e1
            last = e1
    if base is not None:
        gain += last - base                   # commit the climb still open at the end
    return dist / 1000.0, gain


def _grade_and_cumkm(points) -> tuple[list, list]:
    """Per-segment grade (%) and per-point cumulative distance (km) of an
      equirectangular (lat, lon, ele) track.  A segment's grade is its rise over
      its horizontal run, x100; a segment with a missing end-elevation or a zero
      run is None.  Cumulative distance is the running metre total over every
      segment, reported in km at each point."""
    grades = []
    cum = [0.0]
    dist = 0.0
    for i in range(1, len(points)):
        la0, lo0, e0 = points[i - 1]
        la1, lo1, e1 = points[i]
        lat_mid = math.radians((la0 + la1) / 2.0)
        dx = (lo1 - lo0) * 111320.0 * math.cos(lat_mid)
        dy = (la1 - la0) * 110540.0
        run = math.hypot(dx, dy)
        dist += run
        cum.append(dist / 1000.0)
        if e0 is not None and e1 is not None and run > 0.0:
            grades.append((e1 - e0) / run * 100.0)
        else:
            grades.append(None)
    return grades, cum


# Additional geometry functions can be added here as they are identified
# in the main trackview.py file

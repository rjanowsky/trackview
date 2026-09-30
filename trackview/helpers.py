"""Metadata / filter / selection helpers for trackview.

Extracted from the trackview monolith (see PLAN.md, Phase 1.2).  These read the
metadata a ride carries -- its calendar date (off a Wahoo-style filename stem)
and its device / sport (off the GPX <desc> line `wahoo_to_gpx` stamps) -- and
apply the --since/--until, --device/--sport and --top filters, plus a couple of
string helpers.  They are pure (no I/O, no rendering) and depend only on `re`,
`datetime.date` and `pathlib.Path`, so they stand on their own and are unit-tested
directly.
"""
from __future__ import annotations
import re
from datetime import date
from pathlib import Path


# --------------------------------- constants ----------------------------------
# A Wahoo export stem is 'YYYY_MM_DD_HH_MM_SS'; the date filter and the --split
# title read just the date head, and a name that isn't Wahoo-shaped (a foreign
# komoot title) is undated.
_NAME_DATE_RE = re.compile(r"^(\d{4})_(\d{2})_(\d{2})(?=_|$)")
# `wahoo_to_gpx` stamps a "Device: <name>" and a "Sport: <name>" line into the
# GPX <desc> (e.g. "Wahoo ELEMNT BOLT", "Bike"); a plain komoot track has
# neither, and an undated/foreign file may carry one but not the other.
_DEVICE_RE = re.compile(r"(?im)^\s*Device:\s*(.+)$")
_SPORT_RE    = re.compile(r"(?im)^\s*Sport:\s*(.+)$")
# Filename characters a GPX stem must shed to be a safe output filename.
_UNSAFE_CHARS = re.compile(r'[<>:"/\\|?*\s]+')

# The human phrasing for each --top ranking (--by value -> the adjective a "top N"
# note reads as, e.g. "the 10 longest").  The dict order doubles as the --by choices.
_TOP_BY = {
       "km":         "longest",
       "gain":       "highest-gain",
       "recent": "most recent",
}

# The month-abbreviation labels a report month reads by (indexed by calendar month
# 1..12, index 0 a pad), shared by the --calendar activity grid and the --summary
# year-in-review report.
_MONTH_ABBR = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


# --------------------------------- metadata -----------------------------------
def _title_name(name: str) -> str:
    """For a --split single-track title, show a Wahoo-style date stem
    (e.g. 2026_09_11_08_07_29) as just its calendar date (2026-09-11); any other
    name (a descriptive komoot title) passes through unchanged."""
    m = _NAME_DATE_RE.match(name)
    if not m:
        return name
    try:
        return date(int(m[1]), int(m[2]), int(m[3])).isoformat()
    except ValueError:
        return name


def _ride_date(path: Path) -> date | None:
    """Calendar date of a ride, read from the .gpx filename stem
    (YYYY_MM_DD_HH_MM_SS, local time) - no GPX parse needed.  None when the
    name isn't Wahoo-shaped, so a date filter can skip it rather than guess."""
    m = _NAME_DATE_RE.match(path.stem)
    if not m:
        return None
    try:
        return date(int(m[1]), int(m[2]), int(m[3]))
    except ValueError:
        return None


def _device_type(desc: str | None) -> str | None:
    """Device type embedded by `wahoo_to_gpx` as a 'Device: <name>' line in the
    GPX <desc> (e.g. 'Wahoo ELEMNT BOLT', 'Kickr Snap'); None when the track
    carries no such line (e.g. a plain komoot track)."""
    m = _DEVICE_RE.search(desc) if desc else None
    return m.group(1).strip() if m else None


def _sport_type(desc: str | None) -> str | None:
    """Sport embedded by `wahoo_to_gpx` as a 'Sport: <name>' line in the GPX <desc>
    (e.g. 'Bike'); None when the track carries no such line (e.g. a plain komoot
    track), so a --sport filter can skip it rather than guess."""
    m = _SPORT_RE.search(desc) if desc else None
    return m.group(1).strip() if m else None


def _device_label(device: str | None) -> str:
    """Cell text for the ride-log 'Device' column; 'unknown' when the track
    carries no Device line (e.g. a plain komoot track)."""
    return device or "unknown"


def _device_groups(tracks) -> list[tuple[str, list]]:
    """Split the rides into (device label, [rides]) groups in first-seen order
    (the (recursive) glob is date-ascending), so the ride-log can print one totals row per
    device type.  A ride with no device line falls in its own 'unknown' group."""
    order: list[str] = []
    groups: dict[str, list] = {}
    for t in tracks:
        label = _device_label(t.get("device"))
        if label not in groups:
            groups[label] = []
            order.append(label)
        groups[label].append(t)
    return [(lbl, groups[lbl]) for lbl in order]


def _match_meta(t, device=None, sport=None) -> bool:
    """True when a ride passes the active --device/--sport filter.  Each active filter
    is an exact, case-insensitive, whitespace-trimmed match on the ride's own 'Device:' /
    'Sport:' value (the same <desc> line _device_type / _sport_type read), so a ride
    missing that line fails the filter (never guessed, as an undated ride under
    --since/--until).  With no active filter every ride passes."""
    if device and (t.get("device") or "").casefold() != device.casefold():
        return False
    if sport and (t.get("sport") or "").casefold() != sport.casefold():
        return False
    return True


def _filter_by_meta(tracks, device=None, sport=None) -> list:
    """Keep only the rides passing the active --device/--sport filter, so a mixed-
    device/sport folder can be narrowed; the filter runs after load_tracks (the values
    live in the parsed <desc>, not the filename).  A ride missing the line an active
    filter names is skipped (never guessed); when nothing matches, the distinct values
    the log *does* carry are printed so a typo is easy to fix.  Returns the kept rides
    (unchanged when no filter is active)."""
    if not (device or sport):
        return tracks
    kept = [t for t in tracks if _match_meta(t, device, sport)]
    skipped = len(tracks) - len(kept)
    if not skipped:
        return kept
    why = []
    if device:
        why.append(f"device '{device}'")
    if sport:
        why.append(f"sport '{sport}'")
    print(f"      --device/--sport: {len(kept)}/{len(tracks)} track(s) match "
          f"{' and '.join(why)}")
    if not kept:
        for key, val in (("device", device), ("sport", sport)):
            if not val:
                continue
            present = sorted({(t.get(key) or "unknown") for t in tracks})
            print(f"      --{key}: no ride matches '{val}'; "
                  f"the log has: {', '.join(present)}")
    return kept


def _top_key(t, by: str) -> float:
    """A ride's --top ranking value on `by` (a larger value ranks higher): 'km' is its
    distance, 'gain' its elevation gain, and 'recent' its Wahoo-filename ride date as a day
    ordinal (a ride with no date in the filename ranks as the oldest, so it drops out of a
    most-recent selection first).  Pure geometry -- the values are already on the ride dict --
    so it works with or without telemetry."""
    if by == "km":
        return t["dist_km"]
    if by == "gain":
        return t["gain_m"]
    rd = _ride_date(t["path"])
    return float(rd.toordinal()) if rd is not None else 0.0


def _select_top(tracks, n: int, by: str) -> list:
    """Keep only the top `n` rides ranked by `by` ('km'/'gain'/'recent', see _top_key),
    then restore the kept rides to their original (date-ascending) order, so the map, the
    ride-log/CSV and the stats/ reports read as usual -- e.g. the stats filename's
    earliest->latest span (tracks[0]/tracks[-1]) and the ride-log's top-down listing.
    Ties fall back to that original order (a stable rank on the already date-ascending list),
    and `n` >= the ride count (or a non-positive `n`) is a no-op, so an unbounded run is
    returned unchanged."""
    if not n or n <= 0 or n >= len(tracks):
        return tracks
    order = sorted(range(len(tracks)), key=lambda i: _top_key(tracks[i], by),
                   reverse=True)
    picked = set(order[:n])
    return [tracks[i] for i in range(len(tracks)) if i in picked]


def _list_rides(tracks) -> None:
    """The --list dry-run preview: one line per ride that survives *every* filter
    (the --since/--until range, the --device/--sport filter and the --top N
    selection, all applied upstream in main), giving its filename date, its name,
    its distance and its gain, closed by a totals row -- the core of the ride-log
    printed to stdout so a filter selection can be previewed cheaply.  It stops
    before any basemap fetch, image or stats/CSV/report write, so it has no
    output side effects.  A ride with no date in its filename shows 'undated'
    (the date filter would already have skipped it, so this only arises under
    --flat or for a foreign name)."""
    if not tracks:
        print("      --list: no ride matches the filters")
        return
    def date_cell(t):
        rd = _ride_date(t["path"])
        return rd.isoformat() if rd else "undated"
    rows = [[date_cell(t), t["name"],
             f"{t['dist_km']:,.1f}", f"{t['gain_m']:,.0f}"] for t in tracks]
    head = ["Date", "Ride", "Dist (km)", "Gain (m)"]
    right = [False, False, True, True]
    total = ["TOTAL", "",
             f"{sum(t['dist_km'] for t in tracks):,.1f}",
             f"{sum(t['gain_m'] for t in tracks):,.0f}"]
    widths = [max(len(head[i]), len(total[i]),
                 max((len(r[i]) for r in rows), default=0))
              for i in range(len(head))]
    def fmt(cells):
        return "      ".join((c.rjust(widths[i]) if right[i] else c.ljust(widths[i]))
                             for i, c in enumerate(cells))
    n = len(tracks)
    print(f"      --list: {n} ride{'s' if n != 1 else ''} match the filters "
          f"(no basemap fetched, no image written)")
    print("     " + fmt(head))
    print("     " + "      ".join("-" * w for w in widths))
    for r in rows:
        print("     " + fmt(r))
    print("     " + "      ".join("-" * w for w in widths))
    print("     " + fmt(total))


def _parse_argdate(s: str, flag: str) -> date:
    """Parse a 'YYYY-MM-DD' CLI date, aborting with a clear error if malformed."""
    try:
        return date.fromisoformat(s)
    except ValueError:
        raise SystemExit(f"error: {flag} {s!r} is not a YYYY-MM-DD date")


def _safe_filename(name: str) -> str:
    """Make a GPX file stem safe to use as an output filename."""
    cleaned = _UNSAFE_CHARS.sub("_", name).strip("._")
    return cleaned or "track"


def _short_label(name, width=16) -> str:
    """Compact per-ride label for a stacked colourbar: _title_name, truncated with an ellipsis so the bar stays narrow."""
    s = _title_name(name) or str(name)
    return s if len(s) <= width else s[: width - 1] + "…"

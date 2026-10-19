"""The CLI entry point for trackview, extracted in PLAN.md Phase 3.1.

`main` parses the command line, runs the filter sequence, and dispatches to the
render / stats / report writers.  It is the one orchestrator that drives every
extracted leaf (config / helpers / rendering / stats / climbs / summary / calendar
/ trend / io / mapfig / load), so it imports them straight from their own modules
and has no back-edge to the trackview.py monolith.  The headless matplotlib
backend guard -- moved here from the monolith -- runs before the mapfig /
rendering imports below, so the very first figure is drawn on the Agg backend.
"""
from __future__ import annotations

import argparse
import contextily as cx
from datetime import date
from pathlib import Path

import matplotlib
matplotlib.use("Agg")                        # headless, no GUI needed

from trackview.config import (GPX_DIR, OUTPUT_DIR, STATS_DIR,
                              TILE_CACHE_DIR, DECIMATE_M, __version__)
from trackview.helpers import (_title_name, _ride_date,
                               _filter_by_meta, _select_top, _list_rides,
                               _parse_argdate, _safe_filename, _TOP_BY)
from trackview.rendering import (SUPPRESSED_RENDER_DEVICES, _has_metric_pts)
from trackview.stats import (write_stats, write_csv)
from trackview.climbs import (write_climbs)
from trackview.summary import (write_summary)
from trackview.calendar import (write_calendar, _CALENDAR_METRICS)
from trackview.trend import (write_trend)
from trackview.io import (SOURCES, write_html,
                          DETAIL_MIN, DETAIL_MAX, write_gallery)
from trackview.mapfig import (render, PROF_METRICS)
from trackview.load import load_tracks

# --------------------------------- entry point --------------------------------
def main() -> None:
    """Parse the CLI and drive the render / stats / report pipeline.

    The single orchestrator that turns the command line into trackview's outputs: it
    builds the argparse surface (the `--gpx-dir` discovery, the `--since/--until`,
    `--device/--sport` and `--top --by` filters, the `--list` dry-run, and the map /
    stats / report flags), applies that filter sequence in order, and dispatches to the
    leaf writers -- `render` (the map, its `--profile` ride card and `--heat` overlay),
    the `write_*` reports (stats / climbs / summary / calendar / trend), the `--html`
    export and the `--list` preview.  `--no-map` skips the basemap fetch and every
    map-only flag yet still writes the pure-geometry reports; `--today` folds into
    `--flat --since <today>` before anything reads the selection, so it composes with
    every downstream filter.  Returns early (having fetched no basemap) when the filters
    leave no tracks to render."""
    ap = argparse.ArgumentParser(
        description="Render GPX tracks from a folder onto a static map image "
                     "(PNG or PDF).")
    # --version prints the package version (read from the config single-source
    # `__version__`, the same value pyproject.toml stamps into the build) and
    # exits -- a pure, side-effect-free glance that fetches no basemap and writes
    # nothing, so it honours --no-map's spirit even though --no-map never sees it.
    # The value is a fully-formed "trackview <version>" line (this Python's
    # argparse prints the version string verbatim, with no program name of its
    # own), read from __version__ so it can't drift from the build.
    ap.add_argument("--version", action="version",
                    version=f"trackview {__version__}",
                    help="print the trackview version and exit")
    ap.add_argument("--gpx-dir", default=str(GPX_DIR))
    ap.add_argument("--flat", action="store_true",
                    help="look for *.gpx only in --gpx-dir itself, not its subfolders "
                         "(default: recurse into subfolders, so rides organised under a "
                         "year/ or device/ layout are found too)")
    ap.add_argument("--since", metavar="YYYY-MM-DD", default=None,
                    help="only render tracks on/after this date (local, read from the "
                             ".gpx filename); default: no lower bound")
    ap.add_argument("--until", metavar="YYYY-MM-DD", default=None,
                    help="only render tracks on/before this date (local, read from the "
                             ".gpx filename); default: no upper bound")
    ap.add_argument("--today", action="store_true",
                    help="shorthand for '--flat --since <today>': a 'what did I ride "
                             "today?' glance that switches to flat discovery and bounds "
                             "--since to the current calendar day (date.today() at run "
                             "time, never a baked-in constant); it folds into those two "
                             "flags, so it composes with --list, --until and the stats "
                             "path, and is not a map-only flag (a --no-map run honours it)")
    ap.add_argument("--device", metavar="NAME", default=None,
                    help="only render/list rides whose GPX <desc> 'Device:' line is NAME "
                              "(case-insensitive; a ride with no such line is skipped, as an "
                              "undated ride under --since/--until); complements the date "
                              "filter for a mixed-device folder")
    ap.add_argument("--sport", metavar="NAME", default=None,
                    help="only render/list rides whose GPX <desc> 'Sport:' line is NAME "
                              "(case-insensitive; a ride with no such line is skipped); "
                              "complements the date filter for a mixed-sport folder")
    ap.add_argument("--top", type=int, metavar="N", default=None,
                    help="render/stat only the N rides ranked by --by -- a 'best-of' map, "
                              "or a way to keep a huge combined map legible; applied after "
                              "the --since/--until and --device/--sport filters; default: no limit")
    ap.add_argument("--by", choices=list(_TOP_BY), default="recent",
                    help="what --top ranks the rides by: 'km' (the longest), 'gain' (the "
                              "highest elevation gain) or 'recent' (the most recent, the "
                              "default); ties keep date order")

    ap.add_argument("--list", action="store_true",
                    help="print the rides that survive every filter (--since/--until/"
                                 "--device/--sport/--top) -- their name, date, distance "
                                 "and gain -- then stop: a dry-run that fetches no "
                                 "basemap and writes no image or stats, so a filter "
                                 "selection can be previewed cheaply (overrides --sparse)")

    ap.add_argument("--out", default=None,
                    help="output file for the combined map "
                         "(default: output/tracks_overview.<format>)")
    ap.add_argument("--format", choices=["png", "pdf"], default="png",
                    help="image format for the auto-named / split outputs")
    ap.add_argument("--style", choices=list(SOURCES), default="osm")
    ap.add_argument("--detail", type=int, default=None,
                    help=f"basemap detail level: higher = closer / more detail, lower = "
                             f"wider / less detail.  Default: auto-chosen so the track's "
                             f"bbox fills the image, clamped to levels {DETAIL_MIN}-{DETAIL_MAX} "
                             f"(pass an int to override the auto choice)")
    ap.add_argument("--no-elev", action="store_true", help="flat colour, not elevation")
    ap.add_argument("--color-by", choices=["elev", "grade", "flat", "speed", "power"],
                    default="elev",
                    help="what shades the route line: 'elev' (default, the elevation "
                               "ramp), 'grade' (a diverging ramp, steep climbs hot and "
                               "descents cold), 'speed'/'power' (a telemetry ramp, fast/high = hot; needs "
                               "wahoo_to_gpx --ext, else flat), or 'flat' (one distinct colour per track); "
                               "--no-elev is shorthand for 'flat'")
    ap.add_argument("--grade-cap", type=float, default=None, metavar="N",
                    help="pin the grade colour range to +/-N%% (overrides the auto "
                              "percentile cap); a few rides then get their own "
                              "colourbar, beyond which one shared scale is used")
    ap.add_argument("--split", action="store_true",
                    help="one map file per track (default: all tracks in one file)")
    ap.add_argument("--profile", action="store_true",
                    help="add a 'ride card' below the map: an elevation + grade vs. "
                            "distance panel plus a slim mini-panel each for power, "
                            "speed, HR and cadence when the ride carries telemetry "
                            "(auto-collected -- no --ext on the line needed); needs "
                            "--split, or a single track -- one card per ride)")
    ap.add_argument("--gallery", type=int, nargs="?", const=9, metavar="N",
                    default=None,
                    help="instead of one combined (or --split) map, tile the N most "
                               "recent rides into a single mosaic contact sheet -- a "
                               "'recent rides' overview without opening N files; N "
                               "defaults to 9 (a 3x3).  Each cell is that ride's own "
                               "basemap + route (the flat per-track look of a --split "
                               "cell) with a name/distance/gain caption.  A map output, "
                               "so it fetches tiles and is skipped under --no-map; --split "
                               "is ignored when --gallery is set (it is the mosaic instead)")
    ap.add_argument("--ext", action="store_true",
                    help="add the calories-burned total (kcal) to the title and an avg "
                           "power/speed/cadence/hr line below it, from wahoo_to_gpx --ext telemetry (calories = avg power x ride duration / efficiency; ignored when absent)")
    ap.add_argument("--no-map", action="store_true",
                    help="skip map/image generation (no basemap fetch or output "
                            "image); just compute the stats and write the ride-log to "
                            "stats/.   The map-only flags --out/--format/--style/--detail/"
                            "--split/--gallery/--no-elev/--color-by/--grade-cap/--profile/--heat/"
                             "--labels/--no-scale/--no-cache are then ignored)")
    ap.add_argument("--csv", action="store_true",
                    help="also write a CSV ride-log to stats/ (a header row + one row "
                              "per ride, the same columns as the ride-log but no totals "
                              "row); its field delimiter is --csv-delimiter")
    ap.add_argument("--csv-delimiter", default=";",
                    help="field delimiter for the --csv file (default ';', the "
                              "European/Excel default); e.g. ',' for comma-separated")
    ap.add_argument("--sparse", action="store_true",
                    help="quiet stdout: skip the per-track stats listing (one line per "
                             "read ride); print only the summary lines - where it reads, "
                             "the track count, and the files written (plus any date-filter "
                              "skips when --since/--until is active)")
    ap.add_argument("--no-scale", action="store_true",
                    help="omit the map's scale bar (a 'N km' bar in the lower-right, "
                               "on by default); a map-only flag, ignored with --no-map")
    ap.add_argument("--no-cache", action="store_true",
                    help="fetch basemap tiles fresh each run (default: cache them on disk "
                                 "under tiles/, keyed by z/x/y, so re-renders and offline runs reuse "
                                 "them; a map-only flag, ignored with --no-map")
    ap.add_argument("--heat", action="store_true",
                    help="overlay a 2-D 'time on route' density under the routes (a "
                                "YlOrRd heatmap, brighter where you spend the most time or "
                                "ride most; weighted by point timestamps when --ext, else by "
                                "point count); a map-only flag, ignored with --no-map")
    ap.add_argument("--labels", action="store_true",
                    help="label each route with its name + distance near its start marker "
                                "(a halo'd tag, for a combined multi-ride map); ignored when "
                                "one track (the name is already in its title); a map-only flag, "
                                "ignored with --no-map")

    ap.add_argument("--gain-noise", type=float, default=0.0, metavar="M",
                    help="ignore GPS vertical jitter when summing ascent: a descent must "
                               "exceed M metres (default 0 = raw, every rising segment) "
                               "before it ends the climb in progress")
    ap.add_argument("--climbs", nargs="?", const=10, type=int, default=None, metavar="N",
                    help="also write a climb ranking (top N by gain x avg grade, default "
                               "10) to stats/trackview-<range>_climbs.txt; grade is "
                               "geometry-derived, so it works even with --no-map")
    ap.add_argument("--trend", action="store_true",
                    help="also write a per-ride training-trend chart over ride date -- "
                                 "distance, gain, duration, and a calories-burned panel when a "
                                 "power average is available -- to "
                                 "output/trackview-<range>_trend.<format>; a standalone figure "
                                 "(no basemap), so it writes even with --no-map")
    ap.add_argument("--calendar", action="store_true",
                    help="also write a GitHub-style activity grid -- one square per calendar "
                          "day, coloured by that day's total of --calendar-by, one 7xweeks block "
                          "per year that has rides -- to "
                          "output/trackview-<range>_calendar.<format>; a standalone figure "
                          "(no basemap), so it writes even with --no-map")
    ap.add_argument("--calendar-by", choices=list(_CALENDAR_METRICS), default="distance",
                    help="what colours each day of the --calendar grid: 'distance' (default, km "
                          "ridden that day), 'gain' (metres of ascent) or 'rides' (how many "
                          "rides that day)")
    ap.add_argument("--year", type=int, default=None, metavar="YYYY",
                    help="restrict --calendar to a single calendar year (default: every year "
                          "that has rides, stacked one block each)")
    ap.add_argument("--summary", action="store_true",
                    help="also write a year-in-review report to "
                          "stats/trackview-<range>_summary.txt: the rides grouped by year (and "
                          "month) with their ride count, total distance, gain and hours, plus "
                          "avg power under --ext; pure geometry, so it works even with --no-map")
    ap.add_argument("--html", action="store_true",
                    help="also write a self-contained, single-file interactive "
                            "Leaflet map -- the rides as inline GeoJSON on a tile "
                            "layer (matching --style), with start/stop markers, popups "
                            "and a clickable ride list -- to "
                            "output/trackview-<range>_map.html; zoomable and shareable "
                            "with no server, a complement to the static PNG/PDF.  The "
                            "Leaflet library is inlined (a genuinely offline single "
                            "file, cached under lib/); a standalone output, so it "
                            "writes even with --no-map")
    ap.add_argument("--html-cdn", action="store_true",
                    help="reference Leaflet from a CDN instead of inlining it into the "
                            "--html file: a smaller .html that needs internet to view "
                            "(default: inline it for a genuinely offline single file)")
    args = ap.parse_args()

    if args.csv and not args.csv_delimiter:
        raise SystemExit("error: --csv-delimiter must be a non-empty character")

      # --today is the shorthand for '--flat --since <today>' -- a one-flag "what did I
      # ride today?" glance.  It folds into the two existing knobs -- flat discovery
      # (today's rides sit at the top level of the folder) and a --since bound at the
      # current calendar day -- so every downstream reader (the date filter, --list, the
      # stats path) sees the narrow selection transparently, and it composes with --list
      # (a no-fetch dry-run of today's rides) and --no-map.  The date is date.today() at
      # run time, never a baked-in constant.
    if args.today:
        args.flat = True
        args.since = date.today().isoformat()
        print(f"        --today: flat discovery + since {args.since} (today's rides)")

    gpx_dir = Path(args.gpx_dir)
       # By default the search recurses into subfolders (rglob), so rides organised
       # under a year/ or device/ layout are found too; --flat restricts it to
       # --gpx-dir itself (the old single-level glob).  Either way the (recursive)
       # glob stays date-ascending, because the Wahoo filename embeds the ride date,
       # so the ride-log and the trackview-<first>_<last> filename read as usual.
    recurse = not args.flat
    print(f"trackview - reading *.gpx{' recursively' if recurse else ''} from {gpx_dir}")
    paths = sorted(gpx_dir.rglob("*.gpx") if recurse else gpx_dir.glob("*.gpx"))

     # date filter: Wahoo-style .gpx names carry the ride start date (local) in the
     # stem, so --since/--until select by that (mirrors wahoo_to_gpx.py).  A name with
     # no date is skipped (never guessed) when a bound is active.
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
            print(f"    --since/--until: {len(kept)}/{n_total} track(s) in range "
                  f"{lo_s}..{hi_s}")
        if not paths:
            print(f"No tracks within {lo_s}..{hi_s} - nothing to render.")
            return

    color_by = "flat" if args.no_elev else args.color_by
        # Per-point telemetry (power/speed/hr/cadence) is auto-collected for the
        # features that need it: --color-by speed/power shade by it, --profile's
        # ride card plots it, --heat's density wants point timestamps, and --trend's
        # calories panel needs a power average.  The map-only ones (speed/power,
        # profile, heat) collect only when a map is drawn; --trend is standalone (a
        # --no-map run still charts it), so it always collects.     --ext additionally
        # gates the avg-telemetry title line and the ride-log columns.
    want_ext = args.ext or args.trend or (not args.no_map
                  and (color_by in ("speed", "power") or args.heat or args.profile))
    tracks = load_tracks(paths, DECIMATE_M, with_ext=want_ext, noise_m=args.gain_noise)
    if not tracks:
        print(f"No *.gpx found in {gpx_dir}"
              f"{' (or its subfolders)' if recurse else ''} - nothing to render.")
        return

      # --device/--sport narrow the rides to one device and/or sport (each matched on
      # its own parsed <desc> 'Device:'/'Sport:' line, case-insensitively), complementing
      # the --since/--until date filter for a mixed-device/sport folder.  Filtering the
      # `tracks` list here means every downstream reader - the map, the ride-log/CSV and
      # the stats/ reports - sees only the kept rides; a ride missing the line an active
      # filter names is skipped, and when nothing matches we stop (nothing to render).
    if args.device or args.sport:
        tracks = _filter_by_meta(tracks, args.device, args.sport)
        if not tracks:
            print("      no track matches the --device/--sport filter - nothing to render.")
            return

      # --top N --by {km,gain,recent} keep only the N most-significant rides -- a
      # 'best-of' map, or a way to keep a huge combined map legible -- ranked by distance
      # ('km'), elevation gain ('gain') or recency ('recent', the default).  It runs
      # *after* every other filter (the --since/--until range and the --device/--sport
      # filter above), so it selects the top N of whatever rides remain; filtering the
      # `tracks` list here means the map, the ride-log/CSV and the stats/ reports all see
      # only the selected rides, which _select_top re-sorts back into date order so the
      # ride-log and the stats filename read as usual.
    if args.top is not None:
        kept = _select_top(tracks, args.top, args.by)
        if len(kept) < len(tracks):
            print(f"         --top {args.top} --by {args.by}: {len(kept)}/{len(tracks)} "
                  f"ride(s) kept (the {args.top} {_TOP_BY[args.by]})")
        tracks = kept

    if args.list:
        # --list is a dry-run preview: list the rides that survive every filter
        # and stop -- no basemap fetch, no image and no stats/CSV/report write, so
        # a --since/--until/--device/--sport/--top selection can be previewed
        # cheaply; it prints its own listing, so it is not gated on --sparse.
        _list_rides(tracks)
        return

    print(f"   {len(tracks)} track(s), "
          f"{sum(t['n'] for t in tracks):,} pts -> "
          f"{sum(t['ndec'] for t in tracks):,} after {DECIMATE_M:.0f} m decimation")
    if not args.sparse:
        for t in tracks:
            print(f"     - {t['name']:<20s} {t['dist_km']:6.1f} km     "
                  f"+{t['gain_m']:6.0f} m     {t['n']:>6,} -> {t['ndec']:>5,} pts")

    if args.no_map:
        print("      --no-map: skipping map generation (stats + ride-log only)")
    else:
        out_dir = Path(args.out).parent if args.out is not None else OUTPUT_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        split_prefix = (f"{_safe_filename(Path(args.out).stem)}_" if args.out else "")

         # Basemap tiles are cached to disk under tiles/ (contextily's on-disk tile
         # cache, keyed by z/x/y per provider), so re-renders and offline runs reuse
         # them instead of refetching every tile; --no-cache fetches fresh instead
         # (contextily's ephemeral per-session cache, the old behaviour).
        if not args.no_cache:
            TILE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cx.set_cache_dir(str(TILE_CACHE_DIR))
            if not args.sparse:
                print(f"       tile cache: {TILE_CACHE_DIR} "
                          "(re-renders reuse downloaded tiles; --no-cache fetches fresh)")

        # a stationary-trainer 'Kickr Snap' session has no route of its own, so
        # it would just clutter the basemap; keep such tracks off the image while
        # the ride-log/CSV still list them (a trainer ride is still a ride)
        suppressed = [t for t in tracks if t.get("device") in SUPPRESSED_RENDER_DEVICES]
        render_tracks = [t for t in tracks if t.get("device") not in SUPPRESSED_RENDER_DEVICES]
        if suppressed:
            print(f"      suppressing {len(suppressed)} 'Kickr Snap' track(s) from the map "
                  f"(still in the ride-log)")

        profile = args.profile
        if profile and not args.split and len(render_tracks) != 1:
            print("        --profile draws one distance profile, so it needs --split "
                    "(or a single track); skipping the profile panel")
            profile = False
        elif profile and not any(_has_metric_pts(t, m[0])
                                         for t in render_tracks for m in PROF_METRICS):
                  # --profile auto-collects the per-point telemetry the ride card's
                  # mini-panels plot; with none (e.g. a plain komoot track, no --ext)
                  # the card falls back to elevation + grade only
            print("          --profile: no ride carries per-point telemetry "
                              "(need wahoo_to_gpx --ext); each card shows elevation + grade only")

        if not render_tracks:
            print("      no tracks left to render after suppression.")
        elif args.gallery is not None:
             # a mosaic of the N most recent rides -- the --split alternative (one
             # image instead of N files); --out names the single file, else the
             # dated auto name in output/
            glabel = _safe_filename(f"{_title_name(render_tracks[0]['name'])}_"
                                   f"{_title_name(render_tracks[-1]['name'])}")
            out_path = (Path(args.out) if args.out is not None
                        else out_dir / f"trackview-{glabel}_gallery.{args.format}")
            print(f"       --gallery: {args.gallery} most recent ride(s) -> '{out_path.name}'")
            write_gallery(render_tracks, out_path, style=args.style,
                          n=args.gallery, detail=args.detail)
        elif args.split:
            if args.out:
                print(f"        --split + --out: each file -> '{split_prefix}<ride>.{args.format}' in {out_dir}")
            for t in render_tracks:
                out_path = out_dir / f"{split_prefix}{_safe_filename(Path(t['path']).stem)}.{args.format}"
                render([t], style=args.style, out_path=out_path, detail=args.detail,
                       color_by=color_by, show_ext=args.ext, split=True,
                       profile=profile, grade_cap=args.grade_cap,
                       scale=not args.no_scale,
                       heat=args.heat, labels=args.labels)
        else:
            out_path = (Path(args.out) if args.out is not None
                        else out_dir / f"tracks_overview.{args.format}")
            render(render_tracks, style=args.style, out_path=out_path, detail=args.detail,
                   color_by=color_by, show_ext=args.ext, profile=profile,
                   grade_cap=args.grade_cap, scale=not args.no_scale,
                   heat=args.heat, labels=args.labels)

     # a per-run ride-log -> ./stats/trackview-<first>_<last ride date>.txt, holding
     # the two title headers' stats as a table, one row per ride, plus a totals row
    first = _title_name(tracks[0]["name"])        # earliest ride (the glob is date-ascending)
    last   = _title_name(tracks[-1]["name"])       # latest ride
    label  = _safe_filename(f"{first}_{last}")
    stats_path = STATS_DIR / f"trackview-{label}.txt"
    write_stats(tracks, stats_path, show_ext=args.ext)

     # --csv: the same ride-log as CSV (header + one row per ride, no totals row),
     # written next to the .txt; the field delimiter is --csv-delimiter (default ';')
    if args.csv:
        csv_path = STATS_DIR / f"trackview-{label}.csv"
        write_csv(tracks, csv_path, show_ext=args.ext, delimiter=args.csv_delimiter)

       # --climbs: a climb ranking -> ./stats/trackview-<first>_<last ride date>_climbs.txt,
       # the top N most-significant sustained climbs (gain x avg grade); pure geometry, so
       # it works even with --no-map
    if args.climbs is not None:
        climbs_path = STATS_DIR / f"trackview-{label}_climbs.txt"
        write_climbs(tracks, climbs_path, top_n=args.climbs)

      # --summary: a year-in-review report -> ./stats/trackview-<first>_<last ride
      # date>_summary.txt, the rides grouped by year (and month) with their ride
      # count, total distance, gain and hours (plus avg power under --ext, as the
      # ride-log does); pure geometry, so it works even with --no-map.
    if args.summary:
        summary_path = STATS_DIR / f"trackview-{label}_summary.txt"
        write_summary(tracks, summary_path, show_ext=args.ext)

        # --trend: a per-ride training-trend chart over ride date (distance, gain,
        # duration, plus a calories-burned panel when any ride carries a power
        # average); a standalone figure (no basemap), so it writes even under
        # --no-map, alongside the stats/ ride-log.    --trend auto-collects the
        # telemetry the calories panel needs (see want_ext above).
    if args.trend:
        trend_path = OUTPUT_DIR / f"trackview-{label}_trend.{args.format}"
        write_trend(tracks, trend_path)

       # --calendar: a GitHub-style activity grid -> ./output/trackview-<first>_<last
       # ride date>_calendar.<format>, one square per calendar day coloured by
       # --calendar-by, one 7xweeks block per year that has rides; a standalone figure
       # (no basemap), so it writes even under --no-map, alongside the --trend chart.
    if args.calendar:
        cal_path = OUTPUT_DIR / f"trackview-{label}_calendar.{args.format}"
        write_calendar(tracks, cal_path, metric=args.calendar_by, year=args.year)

        # --html: a self-contained, single-file interactive Leaflet map ->
        # ./output/trackview-<first>_<last ride date>_map.html: the rides as inline
        # GeoJSON on a tile layer (matching --style), start/stop markers, popups and a
        # clickable ride list.  A standalone output (no basemap fetch, no telemetry),
        # so it writes even under --no-map; the Leaflet library is inlined by default
        # (a genuinely offline single file, cached under lib/) and --html-cdn references
        # it from a CDN instead.
    if args.html:
        html_path = OUTPUT_DIR / f"trackview-{label}_map.html"
        write_html(tracks, html_path, style=args.style, inline=not args.html_cdn)

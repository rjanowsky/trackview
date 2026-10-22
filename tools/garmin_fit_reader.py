#!/usr/bin/env python3
"""
Garmin FIT file reader (diagnostic tool)
Reads training data out of Garmin FIT files.

A fitparse-based *diagnostic* for a Garmin .fit ride: it prints the
file/session/lap/record layout plus a short stats summary, and dumps the *full*
record stream to a sibling "<name>_records.json".  It is NOT the converter that
feeds trackview.py -- that is fit_to_gpx.py (fit/ -> gpx/, a schema-valid GPX
1.1 track).  With no argument it inspects the most recent *.fit in the data
dir's fit/ folder ($TRACKVIEW_HOME or ~/.trackview, the same root the converter
reads from); pass one or more explicit paths to inspect those instead.  The .fit
inputs and the dumped _records.json are personal data / regenerable output and
are git-ignored (see .gitignore).
"""

import sys
import json
from datetime import datetime
from pathlib import Path

try:
    import fitparse
except ImportError:
    print("Error: fitparse is not installed.")
    print("Install it with: pip install fitparse")
    sys.exit(1)


def read_fit_file(filepath: str):
    """Read a FIT file and print its data."""

    print(f"Reading file: {filepath}\n")

    try:
        fit = fitparse.FitFile(filepath)
    except Exception as e:
        print(f"Error opening the file: {e}")
        return

    # Basic file information
    print("=" * 60)
    print("FILE INFORMATION")
    print("=" * 60)

    for record in fit.messages:
        if record.name == 'file_id':
            for data_field in record.fields:
                print(f"{data_field.name}: {data_field.value}")
            print()
            break

    # Session information (a summary of the activity)
    print("=" * 60)
    print("SESSION INFORMATION")
    print("=" * 60)

    for record in fit.messages:
        if record.name == 'session':
            for data_field in record.fields:
                value = data_field.value
                # Format timestamps more readably
                if isinstance(value, datetime):
                    value = value.strftime("%Y-%m-%d %H:%M:%S")
                print(f"{data_field.name}: {value}")
            print()
            break

    # Lap information (if present)
    print("=" * 60)
    print("LAP INFORMATION")
    print("=" * 60)

    lap_count = 0
    for record in fit.messages:
        if record.name == 'lap':
            lap_count += 1
            print(f"\n--- Lap {lap_count} ---")
            for data_field in record.fields:
                value = data_field.value
                if isinstance(value, datetime):
                    value = value.strftime("%Y-%m-%d %H:%M:%S")
                print(f"{data_field.name}: {value}")

    print("\n")

    # Record data (the detailed measurement points)
    print("=" * 60)
    print("DETAILED RECORD DATA (first 20 entries)")
    print("=" * 60)
    print()

    record_count = 0
    records_data = []

    for record in fit.messages:
        if record.name != 'record':
            continue
        record_count += 1
        data_dict = {}
        for data_field in record.fields:
            value = data_field.value
            if isinstance(value, datetime):
                value = value.strftime("%Y-%m-%d %H:%M:%S")
            data_dict[data_field.name] = value
        records_data.append(data_dict)

        if record_count <= 20:
            if record_count == 1:
                # Print the header row
                print(" | ".join(f"{k:20}" for k in data_dict.keys()))
                print("-" * (len(data_dict) * 22))

            # Print the values (only the first 20 as a preview; the JSON export
            # carries all of them)
            print(" | ".join(f"{str(v):20}" for v in data_dict.values()))

    print(f"\n... {record_count} record entries in this file in total "
          f"(preview: first 20, JSON export: all)\n")

    # Statistics summary
    print("=" * 60)
    print("STATISTICS SUMMARY")
    print("=" * 60)

    total_distance = 0
    total_duration = 0
    max_speed = 0
    max_heart_rate = 0
    max_cadence = 0
    max_power = 0

    for record in fit.messages:
        if record.name == 'record':
            for data_field in record.fields:
                if data_field.name == 'distance' and data_field.value:
                    total_distance = max(total_distance, data_field.value)
                elif data_field.name == 'speed' and data_field.value:
                    max_speed = max(max_speed, data_field.value)
                elif data_field.name == 'heart_rate' and data_field.value:
                    max_heart_rate = max(max_heart_rate, data_field.value)
                elif data_field.name == 'cadence' and data_field.value:
                    max_cadence = max(max_cadence, data_field.value)
                elif data_field.name == 'power' and data_field.value:
                    max_power = max(max_power, data_field.value)

        elif record.name == 'session':
            for data_field in record.fields:
                if data_field.name == 'total_elapsed_time' and data_field.value:
                    total_duration = data_field.value

    print(f"Total distance: {total_distance:.2f} m ({total_distance/1000:.2f} km)")
    print(f"Total duration: {total_duration:.0f} seconds ({total_duration/3600:.2f} hours)")
    print(f"Max. speed: {max_speed:.2f} m/s ({max_speed*3.6:.2f} km/h)")
    print(f"Max. heart rate: {max_heart_rate:.0f} bpm")
    print(f"Max. cadence: {max_cadence:.0f} rpm")
    print(f"Max. power: {max_power:.0f} W")
    print()

    # Export the raw data as JSON
    export_json(filepath, records_data)


def export_json(filepath: str, records_data):
    """Export all record data as JSON (a sibling "<name>_records.json")."""

    json_path = str(filepath).replace('.fit', '_records.json')

    try:
        with open(json_path, 'w') as f:
            json.dump(records_data, f, indent=2, default=str)
        print(f"✓ {len(records_data)} record entries exported to: {json_path}")
    except Exception as e:
        print(f"Error on the JSON export: {e}")


def _default_fit_files():
    """The most recent *.fit in the data dir's fit/ folder as strings
    ($TRACKVIEW_HOME or ~/.trackview, the same root the converter reads from --
    see trackview.config's DATA_DIR; imported here so the diagnostic and the
    converter never disagree on where the rides live).  None when the dir holds
    no ride - the caller then prints usage."""
    import sys
    # run as `python tools/..py`, sys.path[0] is tools/, not the repo root -- so
    # make the package importable whether it is pip-installed or a source checkout.
    if str(Path(__file__).resolve().parent.parent) not in sys.path:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from trackview.config import DATA_DIR
    fit_dir = DATA_DIR / "fit"
    return [str(p) for p in sorted(fit_dir.glob("*.fit"))]


if __name__ == "__main__":
    if len(sys.argv) > 1:
        fit_files = sys.argv[1:]
    else:
        fit_files = _default_fit_files()
        if not fit_files:
            print("Usage: python garmin_fit_reader.py <path-to-fit-file> [..]")
            print("With no argument the most recent *.fit in fit/ is read.")
            print("\nExample: python garmin_fit_reader.py activity.fit")
            sys.exit(1)

    for fit_file in fit_files:
        read_fit_file(fit_file)

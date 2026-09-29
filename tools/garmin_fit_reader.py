#!/usr/bin/env python3
"""
Garmin FIT Datei Reader (diagnose-Werkzeug / diagnostic)
Liest Trainingsdaten aus Garmin FIT-Dateien aus.

A fitparse-based *diagnostic* for a Garmin .fit ride: it prints the
file/session/lap/record layout plus a short stats summary, and dumps the *full*
record stream to a sibling "<name>_records.json".  It is NOT the converter that
feeds trackview.py -- that is fit_to_gpx.py (fit/ -> gpx/, a schema-valid GPX
1.1 track).  With no argument it inspects the most recent *.fit in the repo's
fit/ dir; pass one or more explicit paths to inspect those instead.  The .fit
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
    print("Fehler: fitparse ist nicht installiert.")
    print("Installation: pip install fitparse")
    sys.exit(1)


def read_fit_file(filepath: str):
    """Liest eine FIT-Datei und gibt die Daten aus."""

    print(f"Lese Datei: {filepath}\n")

    try:
        fit = fitparse.FitFile(filepath)
    except Exception as e:
        print(f"Fehler beim Öffnen der Datei: {e}")
        return

    # Grundlegende Datei-Informationen
    print("=" * 60)
    print("DATEI-INFORMATIONEN")
    print("=" * 60)

    for record in fit.messages:
        if record.name == 'file_id':
            for data_field in record.fields:
                print(f"{data_field.name}: {data_field.value}")
            print()
            break

    # Session-Informationen (Zusammenfassung der Aktivität)
    print("=" * 60)
    print("SESSION-INFORMATIONEN")
    print("=" * 60)

    for record in fit.messages:
        if record.name == 'session':
            for data_field in record.fields:
                value = data_field.value
                # Formatiere Timestamps besser
                if isinstance(value, datetime):
                    value = value.strftime("%Y-%m-%d %H:%M:%S")
                print(f"{data_field.name}: {value}")
            print()
            break

    # Lap-Informationen (falls vorhanden)
    print("=" * 60)
    print("LAP-INFORMATIONEN")
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

    # Record-Daten (detaillierte Messpunkte)
    print("=" * 60)
    print("DETAILLIERTE RECORD-DATEN (erste 20 Einträge)")
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
                # Header drucken
                print(" | ".join(f"{k:20}" for k in data_dict.keys()))
                print("-" * (len(data_dict) * 22))

            # Werte drucken (nur die ersten 20 als Vorschau; der JSON-Export bringt alle)
            print(" | ".join(f"{str(v):20}" for v in data_dict.values()))

    print(f"\n... insgesamt {record_count} Record-Einträge in dieser Datei "
          f"(Vorschau: erste 20, JSON-Export: alle)\n")

    # Statistik-Zusammenfassung
    print("=" * 60)
    print("STATISTIK-ZUSAMMENFASSUNG")
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

    print(f"Gesamtstrecke: {total_distance:.2f} m ({total_distance/1000:.2f} km)")
    print(f"Gesamtdauer: {total_duration:.0f} Sekunden ({total_duration/3600:.2f} Stunden)")
    print(f"Max. Geschwindigkeit: {max_speed:.2f} m/s ({max_speed*3.6:.2f} km/h)")
    print(f"Max. Herzfrequenz: {max_heart_rate:.0f} bpm")
    print(f"Max. Trittfrequenz: {max_cadence:.0f} rpm")
    print(f"Max. Leistung: {max_power:.0f} W")
    print()

    # Exportiere Rohdaten als JSON
    export_json(filepath, records_data)


def export_json(filepath: str, records_data):
    """Exportiert alle Record-Daten als JSON (sibling "<name>_records.json")."""

    json_path = str(filepath).replace('.fit', '_records.json')

    try:
        with open(json_path, 'w') as f:
            json.dump(records_data, f, indent=2, default=str)
        print(f"✓ {len(records_data)} Record-Einträge exportiert nach: {json_path}")
    except Exception as e:
        print(f"Fehler beim JSON-Export: {e}")


def _default_fit_files():
    """The most recent *.fit in the repo's fit/ dir as strings (no-arg default).
    None when the dir holds no ride - the caller then prints usage."""
    fit_dir = Path(__file__).resolve().parent.parent / "fit"
    return [str(p) for p in sorted(fit_dir.glob("*.fit"))]


if __name__ == "__main__":
    if len(sys.argv) > 1:
        fit_files = sys.argv[1:]
    else:
        fit_files = _default_fit_files()
        if not fit_files:
            print("Verwendung: python garmin_fit_reader.py <pfad-zur-fit-datei> [..]")
            print("Ohne Argument wird die neueste *.fit in fit/ gelesen.")
            print("\nBeispiel: python garmin_fit_reader.py activity.fit")
            sys.exit(1)

    for fit_file in fit_files:
        read_fit_file(fit_file)

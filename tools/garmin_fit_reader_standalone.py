#!/usr/bin/env python3
"""
Garmin FIT Datei Reader (standalone, ohne externe Abhängigkeiten)
Liest Grundinformationen aus Garmin FIT-Dateien ohne fitparse.

A *dependency-free* fallback diagnostic: with no `fitparse` installed it reads
only what the file's raw bytes give for free -- the 14-byte FIT header, a 16-byte
hex dump, and the readable strings embedded in the binary -- and then points at
the tools that *can* decode the rest.  For the full record stream use
`garmin_fit_reader.py` (needs fitparse); the converter that feeds trackview.py
is `fit_to_gpx.py` (fit/ -> gpx/, a schema-valid GPX 1.1 track).  With no
argument it inspects the most recent *.fit in the repo's fit/ dir; pass one or
more explicit paths to inspect those instead.  The .fit inputs are personal data
and git-ignored (see .gitignore).
"""

import struct
import sys
from pathlib import Path


def hex_dump(filepath: str, max_bytes=500):
    """Gibt einen Hex-Dump der ersten max_bytes Bytes der Datei aus."""
    with open(filepath, 'rb') as f:
        data = f.read(max_bytes)

    print("=" * 60)
    print(f"HEX-DUMP (erste {max_bytes} bytes)")
    print("=" * 60)

    for i in range(0, len(data), 16):
        hex_part = ' '.join(f'{b:02x}' for b in data[i:i+16])
        ascii_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in data[i:i+16])
        print(f'{i:08x}: {hex_part:<48} {ascii_part}')
    print()


class SimpleFITAnalyzer:
    """Einfache Analyse von FIT-Dateien durch Pattern-Matching (ohne fitparse)."""

    def __init__(self, filepath: str):
        self.filepath = filepath

    def analyze(self):
        """Analysiert die FIT-Datei (Header + String-Fragmente + Empfehlung)."""
        print("=" * 60)
        print("DATEI-INFORMATIONEN")
        print("=" * 60)

        try:
            with open(self.filepath, 'rb') as f:
                data = f.read()

            file_size = len(data)
            print(f"Dateigröße: {file_size} bytes")

            # Lese Header
            if len(data) >= 14:
                header_size = data[0]
                protocol_version = data[1]
                profile_version = int.from_bytes(data[2:4], 'little')
                data_size = int.from_bytes(data[4:8], 'little')
                data_type = data[8:12].decode('utf-8', errors='ignore')

                print(f"Header Size: {header_size}")
                print(f"Protocol Version: {protocol_version >> 4}.{protocol_version & 0x0F}")
                print(f"Profile Version: {profile_version}")
                print(f"Data Size: {data_size} bytes")
                print(f"Data Type: {data_type}")

            print()
            print("=" * 60)
            print("DATEI-STATISTIKEN")
            print("=" * 60)

            # Suche nach String-Daten
            strings = self._extract_strings(data)
            print(f"\nGefundene Textfragmente:")
            for s in strings[:20]:
                if len(s) > 3:
                    print(f"    - {s}")

            hex_dump(self.filepath)

            print("\n" + "=" * 60)
            print("EMPFEHLUNG")
            print("=" * 60)
            print(f"\nDie Datei enthält {file_size} Bytes Binärdaten. "
                   "Für den vollständigen Record-Stream:")
            print("    - fitparse (Python): pip install fitparse (-> tools/garmin_fit_reader.py)")
            print("    - Fit SDK: https://developer.garmin.com/fit/download")
            print("    - Online Viewer: https://www.fitfileviewer.com")
            print("    - trackview: .venv/bin/python fit_to_gpx.py  (-> GPX)")

        except Exception as e:
            print(f"Fehler: {e}")

    def _extract_strings(self, data, min_length=4):
        """Extrahiert leserbare Strings aus den Binärdaten."""
        strings = []
        current = []

        for byte in data:
            if 32 <= byte < 127:  # Druckbare ASCII-Zeichen
                current.append(chr(byte))
            else:
                if len(current) >= min_length:
                    strings.append(''.join(current))
                current = []

        if len(current) >= min_length:
            strings.append(''.join(current))

        return strings


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
            print("Verwendung: python garmin_fit_reader_standalone.py <pfad-zur-fit-datei> [..]")
            print("Ohne Argument wird die neueste *.fit in fit/ gelesen.")
            sys.exit(1)

    for fit_file in fit_files:
        SimpleFITAnalyzer(fit_file).analyze()

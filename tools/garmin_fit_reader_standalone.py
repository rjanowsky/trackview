#!/usr/bin/env python3
"""
Garmin FIT file reader (standalone, no external dependencies)
Reads basic information out of Garmin FIT files without fitparse.

A *dependency-free* fallback diagnostic: with no `fitparse` installed it reads
only what the file's raw bytes give for free -- the 14-byte FIT header, a 16-byte
hex dump, and the readable strings embedded in the binary -- and then points at
the tools that *can* decode the rest.  For the full record stream use
`garmin_fit_reader.py` (needs fitparse); the converter that feeds trackview.py
is `fit_to_gpx.py` (fit/ -> gpx/, a schema-valid GPX 1.1 track).  With no
argument it inspects the most recent *.fit in the data dir's fit/ folder
($TRACKVIEW_HOME or ~/.trackview; the same root the converter reads from);
pass one or more explicit paths to inspect those instead.  The .fit inputs are personal data
and git-ignored (see .gitignore).
"""

import sys
from pathlib import Path


def hex_dump(filepath: str, max_bytes=500):
    """Print a hex dump of the first max_bytes bytes of the file."""
    with open(filepath, 'rb') as f:
        data = f.read(max_bytes)

    print("=" * 60)
    print(f"HEX DUMP (first {max_bytes} bytes)")
    print("=" * 60)

    for i in range(0, len(data), 16):
        hex_part = ' '.join(f'{b:02x}' for b in data[i:i+16])
        ascii_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in data[i:i+16])
        print(f'{i:08x}: {hex_part:<48} {ascii_part}')
    print()


class SimpleFITAnalyzer:
    """A simple analysis of FIT files via pattern matching (no fitparse)."""

    def __init__(self, filepath: str):
        self.filepath = filepath

    def analyze(self):
        """Analyse the FIT file (header + string fragments + a recommendation)."""
        print("=" * 60)
        print("FILE INFORMATION")
        print("=" * 60)

        try:
            with open(self.filepath, 'rb') as f:
                data = f.read()

            file_size = len(data)
            print(f"File size: {file_size} bytes")

            # Read the header
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
            print("FILE STATISTICS")
            print("=" * 60)

            # Look for string data
            strings = self._extract_strings(data)
            print("\nFound text fragments:")
            for s in strings[:20]:
                if len(s) > 3:
                    print(f"    - {s}")

            hex_dump(self.filepath)

            print("\n" + "=" * 60)
            print("RECOMMENDATION")
            print("=" * 60)
            print(f"\nThe file holds {file_size} bytes of binary data. "
                   "For the full record stream:")
            print("    - fitparse (Python): pip install fitparse (-> tools/garmin_fit_reader.py)")
            print("    - Fit SDK: https://developer.garmin.com/fit/download")
            print("    - Online Viewer: https://www.fitfileviewer.com")
            print("    - trackview: .venv/bin/python fit_to_gpx.py  (-> GPX)")

        except Exception as e:
            print(f"Error: {e}")

    def _extract_strings(self, data, min_length=4):
        """Extract readable strings from the binary data."""
        strings = []
        current = []

        for byte in data:
            if 32 <= byte < 127:  # Printable ASCII characters
                current.append(chr(byte))
            else:
                if len(current) >= min_length:
                    strings.append(''.join(current))
                current = []

        if len(current) >= min_length:
            strings.append(''.join(current))

        return strings


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
            print("Usage: python garmin_fit_reader_standalone.py <path-to-fit-file> [..]")
            print("With no argument the most recent *.fit in fit/ is read.")
            sys.exit(1)

    for fit_file in fit_files:
        SimpleFITAnalyzer(fit_file).analyze()

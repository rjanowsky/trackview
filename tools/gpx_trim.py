#!/usr/bin/env python3
"""
Removes trackpoints (<trkpt>) from the start and/or end of a GPX file.

Examples:
    python3 gpx_trim.py Sample-1.gpx --start 10
    python3 gpx_trim.py Sample-1.gpx --end 500
    python3 gpx_trim.py Sample-1.gpx --start 10 --end 500 -o result.gpx
"""

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def local_name(tag):
    """Returns the tag name without namespace, e.g. '{uri}trkpt' -> 'trkpt'."""
    return tag.rsplit("}", 1)[-1]


def register_namespaces(path):
    """Remembers the namespace prefixes of the original file so they are preserved when writing."""
    for _, (prefix, uri) in ET.iterparse(path, events=["start-ns"]):
        ET.register_namespace(prefix, uri)


def trim_trackpoints(tree, start, end):
    root = tree.getroot()
    parent_map = {child: parent for parent in root.iter() for child in parent}

    trkpts = [el for el in root.iter() if local_name(el.tag) == "trkpt"]
    total = len(trkpts)

    if total == 0:
        sys.exit("Error: No trackpoints found in the file.")

    if start + end >= total:
        print(f"Warning: The file only has {total} trackpoints, start and end overlap. "
              f"All trackpoints will be removed.")
        to_remove = trkpts
    else:
        to_remove = trkpts[:start] + (trkpts[-end:] if end else [])

    for trkpt in to_remove:
        parent_map[trkpt].remove(trkpt)

    # Remove empty track segments
    for el in list(root.iter()):
        if local_name(el.tag) == "trkseg" and len(el) == 0:
            parent_map[el].remove(el)

    return len(to_remove), total - len(to_remove)


def main():
    parser = argparse.ArgumentParser(description="Removes trackpoints from the start and/or end of a GPX file.")
    parser.add_argument("file", type=Path, help="input GPX file")
    parser.add_argument("--start", type=int, default=0, metavar="N",
                        help="number of trackpoints to remove from the start (default: 0)")
    parser.add_argument("--end", type=int, default=0, metavar="M",
                        help="number of trackpoints to remove from the end (default: 0)")
    parser.add_argument("-o", "--output", type=Path,
                        help="output file (default: <name>_trimmed.gpx in the same folder)")
    args = parser.parse_args()

    if not args.file.is_file():
        sys.exit(f"Error: File '{args.file}' not found.")
    if args.start < 0 or args.end < 0:
        sys.exit("Error: The counts must not be negative.")
    if args.start == 0 and args.end == 0:
        sys.exit("Error: Please specify --start and/or --end.")

    output = args.output or args.file.with_name(f"{args.file.stem}_trimmed{args.file.suffix}")

    register_namespaces(args.file)
    tree = ET.parse(args.file)

    removed, remaining = trim_trackpoints(tree, args.start, args.end)

    if hasattr(ET, "indent"):  # Python 3.9+
        ET.indent(tree, space="  ")
    tree.write(output, encoding="UTF-8", xml_declaration=True)

    print(f"Removed {removed} trackpoints ({args.start} from start, {args.end} from end), "
          f"{remaining} remaining.")
    print(f"Saved as: {output}")


if __name__ == "__main__":
    main()

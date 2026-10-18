"""trackview -- render every GPX track in a folder onto a static map (PNG/PDF), with a
ride-log, climb ranking, a training trend, an activity calendar and a self-contained
HTML/Leaflet map.

A regular package (a bare, re-export-free `__init__.py`): its submodules are imported by
their full names (`trackview.cli`, `trackview.mapfig`, `trackview.config`, ...) and this
package object re-exports nothing, so it stays a namespace for the extracted leaves
rather than a second monolith.  The CLI lives in `trackview.cli:main` (the console entry
point the `pyproject.toml` build wires up); the root `trackview.py` is a thin launcher
that re-enters that same `main`.  See `API.md` for the module map and each module's
public surface."""

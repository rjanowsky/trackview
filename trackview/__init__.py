"""trackview package -- a refactoring bridge (see PLAN.md, Phase 1).

Logic is being extracted out of the single-file monolith `../trackview.py` into
submodules under this package (so far `geometry.py`; next, the metadata/filter
helpers).  A name lives in exactly one place even as it migrates: the monolith
imports the extracted pieces *back* from here (e.g. `from trackview.geometry
import ...`), and this package, in turn, re-exports the monolith's namespace so
that `import trackview` keeps exposing every name the CLI, the standalone scripts
and the test suite rely on (PLAN -> "Backward Compatibility").

The two must coexist under one import name.  A top-level `trackview/` package
otherwise *shadows* the same-named `trackview.py` module, so we load the monolith
from its file under the private name `trackview._main` and mirror its namespace
into this package.  `__file__` stays the monolith's real path, so its
`Path(__file__).parent` config (gpx/, output/, stats/, tiles/) still resolves to
the repo root.  Once every module has moved, this bridge is deleted and the
package stands on its own.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

# The monolith, a sibling of this package dir.  Loaded as `trackview._main` (a
# private submodule) so the package and the script share one import name.
_MONOLITH = Path(__file__).resolve().parent.parent / "trackview.py"
_spec = importlib.util.spec_from_file_location("trackview._main", _MONOLITH)
_main = importlib.util.module_from_spec(_spec)
sys.modules["trackview._main"] = _main
_spec.loader.exec_module(_main)

# Mirror the monolith's namespace here (public + the underscore-prefixed helpers
# the tests reach for, e.g. `trackview._ride_date`).  Excluding dunders keeps the
# bridge from clobbering the package's own `__file__` / `__name__`.
for _name in dir(_main):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_main, _name)

__version__ = "0.1.0"

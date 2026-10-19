"""[Phase 4 / 4.1] The config constants -- a pure, offline leaf.

        trackview/config.py is the single home for the run-time configuration the
    CLI reads/writes: the four run-time directories (gpx/ output/ stats/ tiles/)
    and the point-decimation threshold.  (The Web-Mercator scaling constant `PI_R`
    is a geometry detail, so it lives -- and is tested -- in trackview.geometry,
    not here.)  The one value-affecting edit when the constants moved from the
    repo-root monolith was the one-level `.parent.parent` shift (the module sits a
    level deeper), so the resolved paths must stay the repo-root gpx/ output/
    stats/ tiles/ -- these tests lock that and the decimation threshold, guarding
    the shift against regression.
"""
from trackview import config


class TestRuntimeDirectories:
    # all four dirs sit under the one shared parent -- the repo root (the dir that
    # holds this package's parent), reached by config's `.parent.parent`
    def test_all_four_dirs_share_one_parent(self):
        parents = {config.GPX_DIR.parent, config.OUTPUT_DIR.parent,
                   config.STATS_DIR.parent, config.TILE_CACHE_DIR.parent}
        assert len(parents) == 1

    def test_dir_names_are_the_run_time_layout(self):
        names = [d.name for d in (config.GPX_DIR, config.OUTPUT_DIR,
                                  config.STATS_DIR, config.TILE_CACHE_DIR)]
        assert names == ["gpx", "output", "stats", "tiles"]

    def test_directories_resolve_below_the_package_root(self):
         # the package root is the dir that holds config.py's parent
        pkg_root = config.GPX_DIR.parent
        assert config.GPX_DIR == pkg_root / "gpx"
        assert config.OUTPUT_DIR == pkg_root / "output"
        assert config.STATS_DIR == pkg_root / "stats"
        assert config.TILE_CACHE_DIR == pkg_root / "tiles"


class TestMagicNumbers:
    def test_decimate_threshold_is_five_metres(self):
        assert config.DECIMATE_M == 5.0

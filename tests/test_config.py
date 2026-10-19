"""[Phase 4 / 4.1] The config constants -- a pure, offline leaf.

        trackview/config.py is the single home for the run-time configuration the
    CLI reads/writes: the four run-time directories (gpx/ output/ stats/ tiles/),
    the point-decimation threshold, and the package version (`__version__`, the
    single source of truth `pyproject.toml` reads dynamically and the `--version`
    switch reports).  (The Web-Mercator scaling constant `PI_R` is a geometry
    detail, so it lives -- and is tested -- in trackview.geometry, not here.)  The
    one value-affecting edit when the constants moved from the repo-root monolith
    was the one-level `.parent.parent` shift (the module sits a level deeper), so
    the resolved paths must stay the repo-root gpx/ output/ stats/ tiles/ -- these
    tests lock that, the decimation threshold and the version constant, guarding
    them against regression.
"""
import re

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


class TestVersion:
    # `__version__` is the package's single source of truth: pyproject.toml reads
    # it dynamically (`[tool.setuptools.dynamic] version = {attr = ...}`), and the
    # CLI's `--version` switch reports it -- so the constant must stay a clean,
    # non-empty PEP 440 release tag (a leading-numeric X.Y.Z), the shape a build
    # stamp and a `--version` line both expect.
    def test_version_is_a_pep440_release_tag(self):
        v = config.__version__
        assert isinstance(v, str) and v.strip()
        # a numeric core "X" or "X.Y" or "X.Y.Z" (no leading dot / junk)
        assert re.match(r"^\d+(?:\.\d+){0,2}$", v)

    def test_cli_reads_the_same_version(self):
        # the --version switch reports config's constant (not a second literal), so
        # the two can't drift; importing cli must not raise (its `__version__` comes
        # from config, the single source).
        from trackview.cli import __version__ as cli_version
        assert cli_version == config.__version__

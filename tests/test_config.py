"""[Phase 4 / 4.1] The config constants -- a pure, offline leaf.

        trackview/config.py is the single home for the run-time configuration the
    CLI reads/writes: the per-user data dir (DATA_DIR, $TRACKVIEW_HOME else
    ~/.trackview) and the four run-time directories that hang off it (gpx/ output/
    stats/ tiles/), the point-decimation threshold, and the package version
    (`__version__`, the single source of truth `pyproject.toml` reads dynamically
    and the `--version` switch reports).  (The Web-Mercator scaling constant `PI_R`
    is a geometry detail, so it lives -- and is tested -- in trackview.geometry, not
    here.)  The data dirs are anchored to the *user's home*, not the package -- so
    an installed run (whose __file__ is site-packages/) never scatters a ride log
    into the package -- these tests lock the layout (the four subdirs under one
    shared root) and that the root is the home-anchored DATA_DIR (relocatable via
    $TRACKVIEW_HOME), never a path off this file, guarding them plus the decimation
    threshold and the version constant against regression.
"""
import os
import re
from pathlib import Path

from trackview import config


class TestRuntimeDirectories:
    # all four dirs sit under the one shared root -- the per-user data dir (DATA_DIR,
    # $TRACKVIEW_HOME else ~/.trackview), *not* the repo / the package
    def test_all_four_dirs_share_one_parent(self):
        parents = {config.GPX_DIR.parent, config.OUTPUT_DIR.parent,
                   config.STATS_DIR.parent, config.TILE_CACHE_DIR.parent}
        assert len(parents) == 1

    def test_dir_names_are_the_run_time_layout(self):
        names = [d.name for d in (config.GPX_DIR, config.OUTPUT_DIR,
                                  config.STATS_DIR, config.TILE_CACHE_DIR)]
        assert names == ["gpx", "output", "stats", "tiles"]

    def test_directories_resolve_below_the_data_root(self):
        # the four run-time dirs are the data dir's subdirs; the shared root they
        # all sit under is DATA_DIR itself.
        data_root = config.GPX_DIR.parent
        assert config.DATA_DIR == data_root
        assert config.GPX_DIR == data_root / "gpx"
        assert config.OUTPUT_DIR == data_root / "output"
        assert config.STATS_DIR == data_root / "stats"
        assert config.TILE_CACHE_DIR == data_root / "tiles"

    def test_data_root_is_the_home_not_the_package(self):
        # the heart of the home anchoring: with no override the data root is
        # ~/.trackview, NOT a path off this file -- so an installed run (whose
        # __file__ is site-packages/) never scatters a ride log into the package.
        import importlib
        saved = os.environ.get("TRACKVIEW_HOME")
        os.environ.pop("TRACKVIEW_HOME", None)
        try:
            importlib.reload(config)
            assert config.DATA_DIR == Path.home() / ".trackview"
            # ...and it is not under the package's own tree (install-independence)
            pkg_root = Path(config.__file__).resolve().parents[1]
            assert not config.DATA_DIR.resolve().is_relative_to(pkg_root)
        finally:
            if saved is not None:
                os.environ["TRACKVIEW_HOME"] = saved
            importlib.reload(config)

    def test_trackview_home_env_relocates_the_data_root(self):
        # $TRACKVIEW_HOME relocates every run-time dir at once (the migration /
        # test escape hatch): a converter and the renderer then share the same
        # gpx/ ride log under the override.
        import importlib
        saved = os.environ.get("TRACKVIEW_HOME")
        try:
            os.environ["TRACKVIEW_HOME"] = "/tmp/trackview-test-home"
            importlib.reload(config)
            assert config.DATA_DIR == Path("/tmp/trackview-test-home")
            assert config.GPX_DIR == Path("/tmp/trackview-test-home/gpx")
            assert config.OUTPUT_DIR == Path("/tmp/trackview-test-home/output")
            assert config.STATS_DIR == Path("/tmp/trackview-test-home/stats")
            assert config.TILE_CACHE_DIR == Path("/tmp/trackview-test-home/tiles")
        finally:
            if saved is not None:
                os.environ["TRACKVIEW_HOME"] = saved
            else:
                os.environ.pop("TRACKVIEW_HOME", None)
            importlib.reload(config)


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

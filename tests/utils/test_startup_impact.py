"""Tests for app.utils.startup_impact — Loading Progress report parsing."""

import os
import shutil
from pathlib import Path
from typing import Generator

import pytest

from app.utils.startup_impact import (
    STARTUP_IMPACT_FILENAME,
    format_impact,
    get_startup_impact_file_path,
    invalidate_startup_impact_cache,
    load_startup_impact_report,
    normalize_package_id,
)

DATA_DIR = Path(__file__).parent.parent / "data" / "startup_impact"


@pytest.fixture(autouse=True)
def _clear_cache() -> Generator[None, None, None]:
    invalidate_startup_impact_cache()
    yield
    invalidate_startup_impact_cache()


def _instance_with_report(tmp_path: Path, fixture: str) -> str:
    """Build a fake RimWorld save-data folder; return its Config subfolder."""
    config_folder = tmp_path / "Config"
    config_folder.mkdir()
    shutil.copy(DATA_DIR / fixture, tmp_path / STARTUP_IMPACT_FILENAME)
    return str(config_folder)


def test_file_path_is_parent_of_config_folder(tmp_path: Path) -> None:
    config_folder = tmp_path / "Config"
    assert (
        get_startup_impact_file_path(str(config_folder))
        == tmp_path / STARTUP_IMPACT_FILENAME
    )


def test_parse_full_report(tmp_path: Path) -> None:
    """Values are stored in milliseconds and exposed in seconds."""
    report = load_startup_impact_report(_instance_with_report(tmp_path, "full.xml"))
    assert report is not None
    assert report.loading_time_s == 42.5
    assert len(report.mods) == 3

    harmony = report.mods[0]
    assert harmony.mod_name == "Harmony"
    assert harmony.package_id == "brrainz.harmony"
    assert harmony.total_impact_s == 1.0
    # fractional milliseconds (512.5 in the file) convert exactly
    assert harmony.off_thread_total_impact_s == 0.5125
    assert harmony.metrics == {
        "LoadingProgress.StartupImpact.Constructor": 0.75,
        "LoadingProgress.StartupImpact.LoadModXml": 0.25,
    }
    assert harmony.off_thread_metrics == {
        "LoadingProgress.StartupImpact.Textures": 0.5125
    }

    # packageId is normalized to lowercase at parse time
    assert report.mods[1].package_id == "author.bigcontentmod"
    # legacy entries without modPackageId
    assert report.mods[2].package_id is None


def test_parse_single_mod_entry(tmp_path: Path) -> None:
    """A single <li> is parsed as a dict (not list) by xml_path_to_json."""
    report = load_startup_impact_report(
        _instance_with_report(tmp_path, "single_mod.xml")
    )
    assert report is not None
    assert len(report.mods) == 1
    assert report.mods[0].mod_name == "Only Mod"
    assert report.mods[0].total_impact_s == 1.5


def test_parse_omitted_defaults(tmp_path: Path) -> None:
    """Scribe omits default-valued elements; empty modName entries dropped."""
    report = load_startup_impact_report(
        _instance_with_report(tmp_path, "omitted_defaults.xml")
    )
    assert report is not None
    assert report.loading_time_s == 0.0
    assert len(report.mods) == 1
    mod = report.mods[0]
    assert mod.mod_name == "Zero Impact Mod"
    assert mod.total_impact_s == 0.0
    assert mod.metrics == {}


def test_malformed_report_returns_none(tmp_path: Path) -> None:
    assert (
        load_startup_impact_report(_instance_with_report(tmp_path, "malformed.xml"))
        is None
    )


def test_missing_file_returns_none(tmp_path: Path) -> None:
    config_folder = tmp_path / "Config"
    config_folder.mkdir()
    assert load_startup_impact_report(str(config_folder)) is None


def test_empty_config_folder_returns_none() -> None:
    assert load_startup_impact_report("") is None


def test_find_prefers_package_id_over_name(tmp_path: Path) -> None:
    report = load_startup_impact_report(_instance_with_report(tmp_path, "full.xml"))
    assert report is not None

    # packageId hit, any case, with a Steam-copy suffix
    entry = report.find("BRRAINZ.HARMONY_steam", "Wrong Name")
    assert entry is not None and entry.mod_name == "Harmony"

    # name fallback (case-insensitive) when packageId misses
    entry = report.find("no.such.mod", "legacy named mod")
    assert entry is not None and entry.mod_name == "Legacy Named Mod"

    # no match at all
    assert report.find("no.such.mod", "No Such Mod") is None
    assert report.find(None, None) is None


def test_normalize_package_id() -> None:
    assert normalize_package_id("Author.Mod_steam") == "author.mod"
    assert normalize_package_id("Author.Mod") == "author.mod"


def test_cache_by_mtime(tmp_path: Path) -> None:
    config_folder = _instance_with_report(tmp_path, "full.xml")
    report_path = tmp_path / STARTUP_IMPACT_FILENAME

    first = load_startup_impact_report(config_folder)
    assert first is not None
    # unchanged mtime -> same cached object
    assert load_startup_impact_report(config_folder) is first

    # touching the file with new content invalidates the cache entry
    shutil.copy(DATA_DIR / "single_mod.xml", report_path)
    os.utime(report_path, (1e9, 1e9))
    second = load_startup_impact_report(config_folder)
    assert second is not None
    assert second is not first
    assert len(second.mods) == 1

    # explicit invalidation forces a re-read
    invalidate_startup_impact_cache()
    third = load_startup_impact_report(config_folder)
    assert third is not None
    assert third is not second

    # deleting the file drops the cache entry and returns None
    report_path.unlink()
    assert load_startup_impact_report(config_folder) is None


def test_format_impact() -> None:
    """Every duration is shown as whole milliseconds."""
    assert format_impact(0.0) == "0ms"
    assert format_impact(0.042) == "42ms"
    assert format_impact(0.42) == "420ms"
    assert format_impact(0.0004) == "0ms"
    assert format_impact(2.34) == "2340ms"
    assert format_impact(36.3872266) == "36387ms"
    assert format_impact(476.738906) == "476739ms"

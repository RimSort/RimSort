"""Tests for the MCP read-only tools: status, search, details and active list."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.mcp.core import MAX_SEARCH_RESULTS, RimSortMcpCore
from app.models.settings import Settings
from tests.game_layout_fixtures import GameInstall
from tests.mcp.conftest import (
    build_core,
    write_mod,
    write_mods_config,
)


@pytest.fixture
def populated(
    mcp_core: RimSortMcpCore, game_install: GameInstall, config_folder: Path
) -> RimSortMcpCore:
    """Core with a handful of mods on disk and a saved active list."""
    mods = game_install.mods_path
    write_mod(
        mods,
        "Harmony",
        "brrainz.harmony",
        description="A patching library used by many mods.",
        authors=("Andreas Pardeike",),
    )
    write_mod(
        mods,
        "Core_Lib",
        "test.core",
        description="Shared framework for the test mods.",
        authors=("Framework Dev",),
    )
    write_mod(
        mods,
        "Dependent",
        "test.dependent",
        rules="<loadAfter><li>test.core</li></loadAfter>",
        description="Requires the shared framework.",
    )
    write_mod(
        mods,
        "Old",
        "test.legacy",
        versions=("1.4",),
        description="Only supports an older game version.",
    )
    write_mods_config(
        config_folder,
        ["ludeon.rimworld", "brrainz.harmony", "test.not.installed"],
        known_expansions=["ludeon.rimworld.royalty"],
    )
    return build_core(mcp_core.settings)


def test_status_reports_instance_and_counts(
    populated: RimSortMcpCore, game_install: GameInstall, config_folder: Path
) -> None:
    status = populated.get_instance_status()

    assert status["instance_name"] == populated.settings.current_instance
    assert status["game_version"].startswith("1.7.")
    assert status["paths"]["config_folder"] == str(config_folder)
    assert status["paths"]["local_folder"] == str(game_install.mods_path)
    assert status["paths"]["mods_config"] == str(config_folder / "ModsConfig.xml")
    assert status["total_installed_mods"] == 7  # Core, 2 DLC + 4 local mods
    assert status["active_mods_count"] == 2
    assert status["active_mods_declared_count"] == 3
    assert status["known_expansions"] == ["ludeon.rimworld.royalty"]
    assert status["duplicate_package_ids"] == []


def test_status_without_configured_instance(
    game_install: GameInstall,
) -> None:
    settings = Settings()
    core = build_core(settings)

    status = core.get_instance_status()

    assert status["paths"]["config_folder"] == ""
    assert status["paths"]["mods_config"] is None
    assert status["active_mods_count"] == 0
    assert status["known_expansions"] == []


def test_search_matches_name_packageid_author_and_description(
    populated: RimSortMcpCore,
) -> None:
    assert [r["packageid"] for r in populated.search_installed_mods("harmony")] == [
        "brrainz.harmony"
    ]
    assert [r["packageid"] for r in populated.search_installed_mods("test.core")] == [
        "test.core"
    ]
    assert [
        r["packageid"] for r in populated.search_installed_mods("framework dev")
    ] == ["test.core"]
    assert [
        r["packageid"] for r in populated.search_installed_mods("patching library")
    ] == ["brrainz.harmony"]


def test_search_is_case_insensitive_and_and_matches_all_tokens(
    populated: RimSortMcpCore,
) -> None:
    assert [r["packageid"] for r in populated.search_installed_mods("HARMONY")] == [
        "brrainz.harmony"
    ]
    assert populated.search_installed_mods("harmony nonexistenttoken") == []


def test_search_filters_by_supported_version(populated: RimSortMcpCore) -> None:
    legacy = populated.search_installed_mods(supported_version="1.4")
    assert [r["packageid"] for r in legacy] == ["test.legacy"]

    current = populated.search_installed_mods(supported_version="1.7")
    assert "test.legacy" not in {r["packageid"] for r in current}
    assert "test.core" in {r["packageid"] for r in current}


def test_search_active_only(populated: RimSortMcpCore) -> None:
    active = populated.search_installed_mods(active_only=True)

    ids = {r["packageid"] for r in active if "packageid" in r}
    assert ids == {"brrainz.harmony", "ludeon.rimworld"}
    assert all(r["is_active"] for r in active if "packageid" in r)


def test_search_omits_description_unless_requested(
    populated: RimSortMcpCore,
) -> None:
    without = populated.search_installed_mods("harmony")[0]
    assert "description" not in without

    with_description = populated.search_installed_mods(
        "harmony", include_description=True
    )[0]
    assert with_description["description"].startswith("A patching library")


def test_search_truncates_long_descriptions(
    populated: RimSortMcpCore, game_install: GameInstall
) -> None:
    long_text = "x" * 5000
    write_mod(
        game_install.mods_path,
        "Verbose",
        "test.verbose",
        description=long_text,
    )
    core = build_core(populated.settings)

    result = core.search_installed_mods("verbose", include_description=True)[0]

    assert len(result["description"]) < len(long_text)
    assert result["description"].endswith("...")


def test_search_reports_truncation_when_over_limit(
    mcp_core: RimSortMcpCore, game_install: GameInstall
) -> None:
    for index in range(MAX_SEARCH_RESULTS + 5):
        write_mod(
            game_install.mods_path,
            f"Bulk{index}",
            f"test.bulk.{index}",
            description="bulk mod",
        )
    core = build_core(mcp_core.settings)

    results = core.search_installed_mods("bulk")

    assert len(results) == MAX_SEARCH_RESULTS + 1
    assert results[-1]["truncated"] is True
    assert results[-1]["total_matches"] == MAX_SEARCH_RESULTS + 5
    assert results[-1]["returned"] == MAX_SEARCH_RESULTS
    # Deterministic: alphabetical by name, so Bulk0..Bulk199 survive.
    assert results[0]["name"] == "Bulk0"


def test_get_mod_details_returns_rules_and_dependencies(
    populated: RimSortMcpCore, game_install: GameInstall
) -> None:
    mods = game_install.mods_path
    write_mod(
        mods,
        "WithDeps",
        "test.withdeps",
        rules=(
            "<modDependencies><li><packageId>test.core</packageId>"
            "<displayName>Core</displayName></li></modDependencies>"
            "<loadBefore><li>test.dependent</li></loadBefore>"
            "<incompatibleWith><li>test.legacy</li></incompatibleWith>"
        ),
    )
    core = build_core(populated.settings)

    result = core.get_mod_details(["TEST.WITHDEPS", "missing.mod"])

    assert result["found"] == ["test.withdeps"]
    assert result["not_found"] == ["missing.mod"]
    details = result["mods"]["test.withdeps"]
    assert details["loadbefore"] == ["test.dependent"]
    assert details["incompatiblewith"] == ["test.legacy"]
    assert details["dependencies"][0]["packageid"] == "test.core"
    assert details["dependencies"][0]["name"] == "Core"
    assert details["supportedversions"] == ["1.7"]
    assert "Test Author" in details["authors"]


def test_get_active_modlist_orders_and_flags_missing(populated: RimSortMcpCore) -> None:
    result = populated.get_active_modlist()

    assert result["found"] is True
    assert result["game_version_in_file"] == "1.7.4976 rev1043"
    assert [entry["packageid"] for entry in result["active_mods"]] == [
        "ludeon.rimworld",
        "brrainz.harmony",
    ]
    assert result["missing"] == ["test.not.installed"]
    assert result["known_expansions"] == ["ludeon.rimworld.royalty"]


def test_get_active_modlist_without_config_file(
    mcp_core: RimSortMcpCore, config_folder: Path
) -> None:
    result = mcp_core.get_active_modlist()

    assert result["found"] is False
    assert result["active_mods"] == []
    assert result["mods_config_path"] == str(config_folder / "ModsConfig.xml")


def test_get_active_modlist_does_not_create_missing_file(
    mcp_core: RimSortMcpCore, config_folder: Path
) -> None:
    """Reading must not have the side effect of writing a default mod list."""
    mcp_core.get_active_modlist()

    assert not (config_folder / "ModsConfig.xml").exists()

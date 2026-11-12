"""Tests for the MCP write-path tools: analysis, sorting and ModsConfig writes."""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from io import BufferedWriter
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock
from xml.etree import ElementTree

import pytest

from app.controllers.sort_controller import Sorter
from app.mcp import core as mcp_core_module
from app.mcp.core import RimSortMcpCore
from app.models.instance import Instance
from app.models.metadata.metadata_structure import ModType
from app.models.settings import Settings
from app.services.import_export_service import ImportExportService
from app.services.mod_list_parser import parse_mod_list_file
from app.sort import topo_sort as topo_sort_module
from tests.game_layout_fixtures import GameInstall, make_game_install
from tests.mcp.conftest import build_core, write_mod, write_mods_config


@pytest.fixture
def ordered(mcp_core: RimSortMcpCore, game_install: GameInstall) -> RimSortMcpCore:
    """Core whose local mods have a clear, testable load order."""
    mods = game_install.mods_path
    write_mod(mods, "Harmony", "brrainz.harmony")
    write_mod(mods, "Core_Lib", "test.core")
    write_mod(
        mods,
        "Dependent",
        "test.dependent",
        rules="<loadAfter><li>test.core</li></loadAfter>",
    )
    return build_core(mcp_core.settings)


def test_sort_orders_dependencies_before_dependents(ordered: RimSortMcpCore) -> None:
    result = ordered.analyze_and_sort_modlist(["test.dependent", "test.core"])

    assert result["sort_success"] is True
    assert result["errors"] == []
    order = result["sorted_package_ids"]
    assert order.index("test.core") < order.index("test.dependent")
    # Core content is always part of a valid load order.
    assert order[0] == "ludeon.rimworld"


def test_sort_adds_base_game_when_omitted(ordered: RimSortMcpCore) -> None:
    result = ordered.analyze_and_sort_modlist(["brrainz.harmony"])

    assert "ludeon.rimworld" in result["candidate_package_ids"]
    assert "ludeon.rimworld" in result["sorted_package_ids"]


def test_sort_does_not_enable_disabled_dlc(
    ordered: RimSortMcpCore, config_folder: Path
) -> None:
    """An expansion the player disabled must not be silently enabled."""
    write_mods_config(config_folder, ["ludeon.rimworld"])

    result = build_core(ordered.settings).analyze_and_sort_modlist(["brrainz.harmony"])

    assert "ludeon.rimworld.royalty" not in result["candidate_package_ids"]
    assert "ludeon.rimworld.odyssey" not in result["candidate_package_ids"]


def test_sort_keeps_enabled_dlc(ordered: RimSortMcpCore, config_folder: Path) -> None:
    write_mods_config(
        config_folder,
        ["ludeon.rimworld", "ludeon.rimworld.royalty"],
        known_expansions=["ludeon.rimworld.royalty"],
    )

    result = build_core(ordered.settings).analyze_and_sort_modlist(["brrainz.harmony"])

    assert "ludeon.rimworld.royalty" in result["sorted_package_ids"]


def test_sort_flags_installed_but_missing_dependency(
    mcp_core: RimSortMcpCore, game_install: GameInstall
) -> None:
    mods = game_install.mods_path
    write_mod(mods, "Core_Lib", "test.core")
    write_mod(
        mods,
        "Dependent",
        "test.dependent",
        rules=(
            "<modDependencies><li><packageId>test.core</packageId>"
            "<displayName>Core</displayName></li></modDependencies>"
        ),
    )
    core = build_core(mcp_core.settings)

    result = core.analyze_and_sort_modlist(["test.dependent"])

    missing = result["missing_installed_dependencies"]
    assert [entry["packageid"] for entry in missing] == ["test.core"]
    assert missing[0]["required_by"] == "test.dependent"
    assert any(w["type"] == "missing_dependency_installed" for w in result["warnings"])


def test_sort_flags_uninstalled_dependency(
    mcp_core: RimSortMcpCore, game_install: GameInstall
) -> None:
    write_mod(
        game_install.mods_path,
        "Needy",
        "test.needy",
        rules=(
            "<modDependencies><li><packageId>test.absent</packageId>"
            "<displayName>Absent</displayName>"
            "<steamWorkshopUrl>steam://url/CommunityFilePage/123456</steamWorkshopUrl>"
            "</li></modDependencies>"
        ),
    )
    core = build_core(mcp_core.settings)

    result = core.analyze_and_sort_modlist(["test.needy"])

    missing = result["missing_uninstalled_dependencies"]
    assert [entry["packageid"] for entry in missing] == ["test.absent"]
    assert missing[0]["workshop_id"] == "123456"


def test_incompatibility_detected_once_per_pair(
    mcp_core: RimSortMcpCore, game_install: GameInstall
) -> None:
    mods = game_install.mods_path
    write_mod(mods, "Alpha", "test.alpha")
    write_mod(
        mods,
        "Beta",
        "test.beta",
        rules="<incompatibleWith><li>test.alpha</li></incompatibleWith>",
    )
    core = build_core(mcp_core.settings)

    result = core.analyze_and_sort_modlist(["test.alpha", "test.beta"])

    assert result["incompatibilities"] == [
        {
            "packageids": ["test.alpha", "test.beta"],
            "declared_by": "test.beta",
        }
    ]
    assert sum(w["type"] == "incompatible_mods" for w in result["warnings"]) == 1


def test_mutual_incompatibility_reported_once(
    mcp_core: RimSortMcpCore, game_install: GameInstall
) -> None:
    mods = game_install.mods_path
    write_mod(
        mods,
        "Alpha",
        "test.alpha",
        rules="<incompatibleWith><li>test.beta</li></incompatibleWith>",
    )
    write_mod(
        mods,
        "Beta",
        "test.beta",
        rules="<incompatibleWith><li>test.alpha</li></incompatibleWith>",
    )
    core = build_core(mcp_core.settings)

    result = core.analyze_and_sort_modlist(["test.alpha", "test.beta"])

    assert len(result["incompatibilities"]) == 1


def test_version_mismatch_flagged(
    mcp_core: RimSortMcpCore, game_install: GameInstall
) -> None:
    write_mod(game_install.mods_path, "Old", "test.legacy", versions=("1.4", "1.5"))
    core = build_core(mcp_core.settings)

    result = core.analyze_and_sort_modlist(["test.legacy"])

    assert [entry["packageid"] for entry in result["version_mismatches"]] == [
        "test.legacy"
    ]
    entry = result["version_mismatches"][0]
    assert entry["supportedversions"] == ["1.4", "1.5"]
    assert entry["game_version"].startswith("1.7.")
    assert any(w["type"] == "version_mismatch" for w in result["warnings"])


def test_version_matching_mod_not_flagged(
    mcp_core: RimSortMcpCore, game_install: GameInstall
) -> None:
    write_mod(game_install.mods_path, "Current", "test.current", versions=("1.7",))
    core = build_core(mcp_core.settings)

    result = core.analyze_and_sort_modlist(["test.current"])

    assert result["version_mismatches"] == []


def test_circular_dependency_reported_as_error_without_blocking(
    mcp_core: RimSortMcpCore, game_install: GameInstall
) -> None:
    """A cycle must surface as a structured error, never a modal dialog."""
    mods = game_install.mods_path
    write_mod(
        mods, "LoopA", "test.loopa", rules="<loadAfter><li>test.loopb</li></loadAfter>"
    )
    write_mod(
        mods, "LoopB", "test.loopb", rules="<loadAfter><li>test.loopa</li></loadAfter>"
    )
    core = build_core(mcp_core.settings)

    result = core.analyze_and_sort_modlist(["test.loopa", "test.loopb"])

    assert result["sort_success"] is False
    assert result["sorted_package_ids"] == []
    assert [error["type"] for error in result["errors"]] == ["circular_dependency"]
    assert result["errors"][0]["cycles"]


def test_unresolved_package_id_reported_as_error(ordered: RimSortMcpCore) -> None:
    result = ordered.analyze_and_sort_modlist(["test.does.not.exist"])

    assert result["unresolved_package_ids"] == ["test.does.not.exist"]
    assert [error["type"] for error in result["errors"]] == ["unresolved_package_id"]


def test_apply_writes_valid_mods_config(
    ordered: RimSortMcpCore, config_folder: Path
) -> None:
    result = ordered.apply_active_modlist(
        ["test.dependent", "test.core"], auto_sort=True
    )

    assert result["saved"] is True
    assert result["errors"] == []
    written = config_folder / "ModsConfig.xml"
    assert written.is_file()

    parsed = parse_mod_list_file(str(written))
    assert parsed.package_ids == result["sorted_package_ids"]
    assert parsed.package_ids.index("test.core") < parsed.package_ids.index(
        "test.dependent"
    )

    root = ElementTree.parse(written).getroot()
    assert root.findtext("version") == ordered.metadata_controller.game_version
    assert root.find("activeMods") is not None
    assert root.find("knownExpansions") is not None


def test_apply_creates_timestamped_backup(
    ordered: RimSortMcpCore, config_folder: Path
) -> None:
    original = write_mods_config(config_folder, ["ludeon.rimworld"])
    original_text = original.read_text(encoding="utf-8")

    result = ordered.apply_active_modlist(["brrainz.harmony"])

    assert result["saved"] is True
    backup = Path(str(result["backup_path"]))
    assert backup.is_file()
    assert backup.read_text(encoding="utf-8") == original_text


def test_apply_without_backup_when_disabled(
    ordered: RimSortMcpCore, config_folder: Path
) -> None:
    write_mods_config(config_folder, ["ludeon.rimworld"])

    result = ordered.apply_active_modlist(["brrainz.harmony"], create_backup=False)

    assert result["saved"] is True
    assert result["backup_path"] is None


def test_apply_skips_backup_when_no_existing_file(
    ordered: RimSortMcpCore, config_folder: Path
) -> None:
    assert not (config_folder / "ModsConfig.xml").exists()

    result = ordered.apply_active_modlist(["brrainz.harmony"])

    assert result["saved"] is True
    assert result["backup_path"] is None


def test_apply_respects_requested_order_without_sorting(
    ordered: RimSortMcpCore, config_folder: Path
) -> None:
    result = ordered.apply_active_modlist(
        ["test.dependent", "test.core"], auto_sort=False
    )

    assert result["saved"] is True
    parsed = parse_mod_list_file(str(config_folder / "ModsConfig.xml"))
    assert parsed.package_ids.index("test.dependent") < parsed.package_ids.index(
        "test.core"
    )


def test_apply_refuses_unresolved_package_ids(
    ordered: RimSortMcpCore, config_folder: Path
) -> None:
    """Never write a list that silently dropped an unknown package ID."""
    existing = write_mods_config(config_folder, ["ludeon.rimworld"])
    before = existing.read_text(encoding="utf-8")

    result = ordered.apply_active_modlist(["brannz.harmony", "test.core"])

    assert result["saved"] is False
    assert [error["type"] for error in result["errors"]] == ["unresolved_package_id"]
    assert existing.read_text(encoding="utf-8") == before


def test_apply_refuses_unsortable_list(
    mcp_core: RimSortMcpCore, game_install: GameInstall, config_folder: Path
) -> None:
    mods = game_install.mods_path
    write_mod(
        mods, "LoopA", "test.loopa", rules="<loadAfter><li>test.loopb</li></loadAfter>"
    )
    write_mod(
        mods, "LoopB", "test.loopb", rules="<loadAfter><li>test.loopa</li></loadAfter>"
    )
    core = build_core(mcp_core.settings)
    existing = write_mods_config(config_folder, ["ludeon.rimworld"])
    before = existing.read_text(encoding="utf-8")

    result = core.apply_active_modlist(["test.loopa", "test.loopb"])

    assert result["saved"] is False
    assert {error["type"] for error in result["errors"]} >= {
        "circular_dependency",
        "sort_failed",
    }
    assert existing.read_text(encoding="utf-8") == before


def test_apply_reports_missing_config_folder(
    game_install: GameInstall,
) -> None:
    from app.models.instance import Instance
    from app.models.settings import Settings

    settings = Settings()
    settings.instances[settings.current_instance] = Instance(
        name=settings.current_instance,
        game_folder=str(game_install.launch_location),
        config_folder="",
        local_folder=str(game_install.mods_path),
    )
    core = build_core(settings)

    result = core.apply_active_modlist(["ludeon.rimworld"])

    assert result["saved"] is False
    assert result["errors"][0]["type"] == "config_folder_missing"


def test_refresh_metadata_cache_picks_up_new_mods(
    mcp_core: RimSortMcpCore, game_install: GameInstall
) -> None:
    before = mcp_core.refresh_metadata_cache()
    write_mod(game_install.mods_path, "Newcomer", "test.newcomer")

    after = mcp_core.refresh_metadata_cache()

    assert after["total_installed_mods"] == before["total_installed_mods"] + 1
    assert after["refreshed"] is True
    assert after["game_version"].startswith("1.7.")


def test_refresh_metadata_cache_reloads_settings_from_disk(
    mcp_core: RimSortMcpCore, game_install: GameInstall, tmp_path: Path
) -> None:
    """A settings edit made outside the process applies on the next refresh.

    The server must pick up a ``workshop_folder`` written to ``settings.json``
    while it is running, instead of requiring a process restart.
    """
    # RimSort only keeps a workshop folder that looks like a real Steam
    # Workshop location: the leaf must be the RimWorld app ID and
    # ``appworkshop_294100.acf`` must sit two levels up.
    steamapps = tmp_path / "steamapps"
    workshop = steamapps / "workshop" / "content" / "294100"
    write_mod(workshop, "WorkshopMod", "test.workshopmod")
    (steamapps / "workshop" / "appworkshop_294100.acf").write_text(
        '"AppWorkshop"{}', encoding="utf-8"
    )

    # The edit lands on disk, while this process keeps its stale in-memory copy
    # (integration disabled, no workshop path) - exactly what a running server
    # looks like after an external edit.
    instance = mcp_core.settings.instances[mcp_core.settings.current_instance]
    instance.workshop_folder = str(workshop)
    instance.steam_client_integration = True
    mcp_core.settings.save()
    instance.workshop_folder = ""
    instance.steam_client_integration = False
    assert instance.workshop_folder == ""

    result = mcp_core.refresh_metadata_cache()

    assert mcp_core.settings.instances[
        mcp_core.settings.current_instance
    ].workshop_folder == str(workshop)
    assert mcp_core.get_instance_status()["paths"]["workshop_folder"] == str(workshop)
    assert "test.workshopmod" in {
        record["packageid"] for record in mcp_core.search_installed_mods("workshopmod")
    }
    assert result["refreshed"] is True


def test_refresh_metadata_cache_keeps_clearing_invalid_workshop_folder(
    mcp_core: RimSortMcpCore, game_install: GameInstall
) -> None:
    """Reloading must not bypass steam-integration validation.

    A workshop path without the app ID leaf and ACF is cleared on load, so the
    refresh reports it as unset rather than scanning an arbitrary folder.
    """
    instance = mcp_core.settings.instances[mcp_core.settings.current_instance]
    instance.workshop_folder = str(game_install.mods_path.parent / "not-a-workshop")
    instance.steam_client_integration = True
    mcp_core.settings.save()

    mcp_core.refresh_metadata_cache()

    assert (
        mcp_core.settings.instances[mcp_core.settings.current_instance].workshop_folder
        == ""
    )


# ---- defensive branches ----


def test_mods_config_without_root_is_treated_as_absent(
    mcp_core: RimSortMcpCore, config_folder: Path
) -> None:
    """A file without ``ModsConfigData`` yields no active list, not a crash."""
    (config_folder / "ModsConfig.xml").write_text(
        "<NotModsConfig><activeMods><li>brrainz.harmony</li></activeMods>"
        "</NotModsConfig>",
        encoding="utf-8",
    )

    result = mcp_core.get_active_modlist()

    assert result["found"] is False
    assert result["active_mods"] == []


def test_empty_package_id_list_resolves_to_nothing(mcp_core: RimSortMcpCore) -> None:
    assert mcp_core.get_mod_details([])["requested"] == []
    assert mcp_core.get_mod_details(["   "])["not_found"] == []


def test_dedupe_drops_blanks_and_case_insensitive_duplicates() -> None:
    assert RimSortMcpCore._dedupe(
        ["test.core", "  ", "TEST.CORE", "", "test.other"]
    ) == ["test.core", "test.other"]
    # Non-string entries (possible through a JSON caller) are skipped, not kept.
    assert RimSortMcpCore._dedupe(cast("list[str]", ["test.core", 42, None])) == [
        "test.core"
    ]


def test_steam_lookup_prefers_first_entry_and_ignores_blanks(
    mcp_core: RimSortMcpCore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Blank package IDs are skipped; the first entry wins on a collision."""

    def entry(package_id: str | None) -> MagicMock:
        built = MagicMock()
        built.packageId = package_id
        built.name = package_id
        return built

    db = MagicMock()
    db.database = {
        "111": entry(None),
        "222": entry("Test.Core"),
        "333": entry("test.core"),
        "444": entry("other.mod"),
    }
    monkeypatch.setattr(type(mcp_core.metadata_controller), "steam_db", db, False)
    mcp_core._packageid_to_steam_entry = None

    assert mcp_core._steam_entry_for("TEST.CORE") is db.database["222"]
    assert mcp_core._steam_entry_for("other.mod") is db.database["444"]
    assert mcp_core._steam_entry_for("absent.mod") is None


def test_incompatibility_ignores_self_declaration(
    mcp_core: RimSortMcpCore, game_install: GameInstall
) -> None:
    write_mod(
        game_install.mods_path,
        "Selfish",
        "test.selfish",
        rules="<incompatibleWith><li>test.selfish</li></incompatibleWith>",
    )
    core = build_core(mcp_core.settings)

    result = core.analyze_and_sort_modlist(["test.selfish"])

    assert result["incompatibilities"] == []


def test_unsortable_algorithm_unwinds_the_list(
    ordered: RimSortMcpCore, config_folder: Path
) -> None:
    """An unknown sorting algorithm is reported instead of raising."""
    ordered.settings.sorting_algorithm = "NotARealAlgorithm"  # type: ignore[assignment]

    result = ordered.apply_active_modlist(["test.core"])

    assert result["saved"] is False
    assert "sorting_algorithm_unimplemented" in [
        error["type"] for error in result["errors"]
    ]
    assert result["sorted_package_ids"] == []


def test_dropped_mods_are_reported(
    ordered: RimSortMcpCore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A sorter that silently loses a mod must surface as a warning."""

    def drop_everything(
        self: object,
        sort_method: object = None,
    ) -> tuple[bool, list[str]]:
        return True, []

    monkeypatch.setattr(Sorter, "sort", drop_everything, raising=True)

    result = ordered.analyze_and_sort_modlist(["test.core", "brrainz.harmony"])

    assert result["sorted_package_ids"] == []
    dropped = [w for w in result["warnings"] if w["type"] == "mods_dropped_from_sort"]
    assert dropped and dropped[0]["packageids"]


def test_load_order_violations_are_reported(
    ordered: RimSortMcpCore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Wrong output order is caught by the post-sort verification pass."""
    paths = ordered.metadata_controller.packageid_to_paths
    dependent_path = next(iter(paths["test.dependent"]))
    core_path = next(iter(paths["test.core"]))
    wrong_order = [dependent_path, core_path]

    def reverse_sort(
        self: object, sort_method: object = None
    ) -> tuple[bool, list[str]]:
        return True, list(wrong_order)

    monkeypatch.setattr(Sorter, "sort", reverse_sort, raising=True)

    result = ordered.analyze_and_sort_modlist(
        ["test.core", "test.dependent", "brrainz.harmony"]
    )

    violations = [w for w in result["warnings"] if w["type"] == "load_order_violation"]
    assert violations
    assert violations[0]["packageid"] == "test.dependent"
    assert violations[0]["target"] == "test.core"
    assert violations[0]["relation"] == "loadAfter"


def test_load_before_violation_is_reported(
    mcp_core: RimSortMcpCore,
    game_install: GameInstall,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The ``loadBefore`` half of the verification pass is reported too."""
    mods = game_install.mods_path
    write_mod(mods, "Core_Lib", "test.core")
    write_mod(
        mods,
        "Early",
        "test.early",
        rules="<loadBefore><li>test.core</li></loadBefore>",
    )
    core = build_core(mcp_core.settings)

    paths = core.metadata_controller.packageid_to_paths
    core_path = next(iter(paths["test.core"]))
    early_path = next(iter(paths["test.early"]))
    # core before early violates "early must load before core".
    wrong_order = [core_path, early_path]

    def reverse_sort(
        self: object, sort_method: object = None
    ) -> tuple[bool, list[str]]:
        return True, list(wrong_order)

    monkeypatch.setattr(Sorter, "sort", reverse_sort, raising=True)

    result = core.analyze_and_sort_modlist(["test.core", "test.early"])

    violations = [w for w in result["warnings"] if w["type"] == "load_order_violation"]
    assert violations
    assert violations[0]["packageid"] == "test.early"
    assert violations[0]["target"] == "test.core"
    assert violations[0]["relation"] == "loadBefore"


def test_apply_refuses_ids_resolved_after_analysis(
    ordered: RimSortMcpCore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The write path re-resolves its own output and refuses anything unknown."""
    original = type(ordered).analyze_and_sort_modlist

    def analysis_with_ghost(
        self: RimSortMcpCore, package_ids: list[str]
    ) -> dict[str, object]:
        result = original(self, package_ids)
        result["sorted_package_ids"] = ["test.ghost"]
        return result

    monkeypatch.setattr(
        type(ordered), "analyze_and_sort_modlist", analysis_with_ghost, raising=True
    )

    result = ordered.apply_active_modlist(["test.core"])

    assert result["saved"] is False
    assert [error["type"] for error in result["errors"]] == ["unresolved_package_id"]
    assert result["sorted_package_ids"] == ["test.ghost"]


def test_apply_reports_write_failure(
    ordered: RimSortMcpCore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unwritable target is reported, not raised, so the session survives."""

    def boom(self: object, active_mods: list[str]) -> str:
        raise OSError("disk is full")

    monkeypatch.setattr(ImportExportService, "save_to_mods_config", boom, raising=True)

    result = ordered.apply_active_modlist(["test.core"])

    assert result["saved"] is False
    assert [error["type"] for error in result["errors"]] == ["write_failed"]
    assert "disk is full" in result["errors"][0]["message"]


def test_duplicate_workshop_ids_get_the_steam_suffix() -> None:
    """Both copies of a duplicate stay in the file, the Workshop one suffixed."""

    def mod(package_id: str, mod_type: ModType) -> MagicMock:
        built = MagicMock()
        built.package_id = package_id
        built.mod_type = mod_type
        return built

    duplicate = {"test.core": ["/workshop/test.core", "/local/test.core"]}

    assert (
        RimSortMcpCore._config_package_id(
            mod("test.core", ModType.STEAM_WORKSHOP), duplicate
        )
        == "test.core_steam"
    )
    assert (
        RimSortMcpCore._config_package_id(mod("test.core", ModType.LOCAL), duplicate)
        == "test.core"
    )
    # A package ID that is not duplicated is written verbatim.
    assert (
        RimSortMcpCore._config_package_id(
            mod("other.mod", ModType.STEAM_WORKSHOP), duplicate
        )
        == "other.mod"
    )


def _core_with_local_and_workshop_copy(
    mcp_core: RimSortMcpCore, game_install: GameInstall, tmp_path: Path
) -> RimSortMcpCore:
    """Build a core that has the same package ID as both local and Workshop."""
    write_mod(game_install.mods_path, "CopyLocal", "test.copy")

    steamapps = tmp_path / "steamapps"
    workshop = steamapps / "workshop" / "content" / "294100"
    write_mod(workshop, "1234567890", "test.copy")
    (steamapps / "workshop" / "appworkshop_294100.acf").write_text(
        '"AppWorkshop"{}', encoding="utf-8"
    )

    instance = mcp_core.settings.instances[mcp_core.settings.current_instance]
    instance.workshop_folder = str(workshop)
    instance.steam_client_integration = True
    return build_core(mcp_core.settings)


@pytest.mark.parametrize("auto_sort", [True, False])
def test_apply_keeps_workshop_copy_when_local_duplicate_exists(
    mcp_core: RimSortMcpCore,
    game_install: GameInstall,
    config_folder: Path,
    tmp_path: Path,
    auto_sort: bool,
) -> None:
    """Saving ``test.copy_steam`` must not fall back to the local copy."""
    core = _core_with_local_and_workshop_copy(mcp_core, game_install, tmp_path)
    write_mods_config(config_folder, ["ludeon.rimworld"])

    result = core.apply_active_modlist(["test.copy_steam"], auto_sort=auto_sort)

    assert result["saved"] is True
    written = result["written_package_ids"]
    assert "test.copy_steam" in written
    assert "test.copy" not in written
    parsed = parse_mod_list_file(str(config_folder / "ModsConfig.xml"))
    assert "test.copy_steam" in parsed.package_ids
    assert "test.copy" not in parsed.package_ids


def test_get_active_modlist_round_trip_keeps_workshop_copy(
    mcp_core: RimSortMcpCore,
    game_install: GameInstall,
    config_folder: Path,
    tmp_path: Path,
) -> None:
    """IDs returned by get must save the same Workshop copy they were read from."""
    core = _core_with_local_and_workshop_copy(mcp_core, game_install, tmp_path)
    write_mods_config(config_folder, ["ludeon.rimworld", "test.copy_steam"])

    active = core.get_active_modlist()
    package_ids = [str(entry["packageid"]) for entry in active["active_mods"]]

    assert "test.copy_steam" in package_ids
    assert "test.copy" not in package_ids

    result = core.apply_active_modlist(package_ids)
    parsed = parse_mod_list_file(str(config_folder / "ModsConfig.xml"))

    assert result["saved"] is True
    assert "test.copy_steam" in result["written_package_ids"]
    assert "test.copy" not in result["written_package_ids"]
    assert "test.copy_steam" in parsed.package_ids
    assert "test.copy" not in parsed.package_ids


def _bind_other_instance(
    mcp_core: RimSortMcpCore,
    game_install: GameInstall,
    other_config: Path,
) -> RimSortMcpCore:
    """Bind a core to ``Other`` with its own config folder and the same game."""
    settings = mcp_core.settings
    settings.instances["Other"] = Instance(
        name="Other",
        game_folder=str(game_install.launch_location),
        config_folder=str(other_config),
        local_folder=str(game_install.mods_path),
    )
    settings.current_instance = "Other"
    return build_core(settings)


def _prepare_other_instance(
    mcp_core: RimSortMcpCore,
    game_install: GameInstall,
    config_folder: Path,
    tmp_path: Path,
) -> tuple[RimSortMcpCore, Path, bytes]:
    """Bind ``Other`` and snapshot Default's ``ModsConfig.xml``."""
    other_config = tmp_path / "OtherConfig"
    write_mods_config(config_folder, ["ludeon.rimworld", "only.default"])
    write_mods_config(other_config, ["ludeon.rimworld", "only.other"])
    default_before = (config_folder / "ModsConfig.xml").read_bytes()
    return (
        _bind_other_instance(mcp_core, game_install, other_config),
        other_config,
        default_before,
    )


def test_refresh_keeps_bound_instance_across_settings_reload(
    mcp_core: RimSortMcpCore,
    game_install: GameInstall,
    config_folder: Path,
    tmp_path: Path,
) -> None:
    """A refresh must keep later writes on the instance given at startup."""
    core, other_config, default_before = _prepare_other_instance(
        mcp_core, game_install, config_folder, tmp_path
    )

    core.settings.current_instance = "Default"
    core.settings.save()
    core.settings.current_instance = "Other"

    core.refresh_metadata_cache()

    status = core.get_instance_status()
    assert core.settings.current_instance == "Other"
    assert status["instance_name"] == "Other"
    assert status["paths"]["config_folder"] == str(other_config)

    result = core.apply_active_modlist(["ludeon.rimworld"])

    assert result["saved"] is True
    assert (config_folder / "ModsConfig.xml").read_bytes() == default_before
    other_text = (other_config / "ModsConfig.xml").read_text(encoding="utf-8")
    assert "only.other" not in other_text
    assert "ludeon.rimworld" in other_text


def test_refresh_refuses_write_when_bound_instance_was_removed(
    mcp_core: RimSortMcpCore,
    game_install: GameInstall,
    config_folder: Path,
    tmp_path: Path,
) -> None:
    """A deleted instance must not send the next write at the saved one."""
    core, other_config, default_before = _prepare_other_instance(
        mcp_core, game_install, config_folder, tmp_path
    )
    other_before = (other_config / "ModsConfig.xml").read_bytes()

    core.settings.current_instance = "Default"
    del core.settings.instances["Other"]
    core.settings.save()

    refreshed = core.refresh_metadata_cache()
    applied = core.apply_active_modlist(["ludeon.rimworld"])

    assert refreshed["refreshed"] is False
    assert applied["saved"] is False
    assert applied["errors"][0]["type"] == "instance_unbound"
    assert applied["backup_path"] is None
    assert (config_folder / "ModsConfig.xml").read_bytes() == default_before
    assert (other_config / "ModsConfig.xml").read_bytes() == other_before


def test_overlapping_refresh_cannot_redirect_apply_to_saved_instance(
    mcp_core: RimSortMcpCore,
    game_install: GameInstall,
    config_folder: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A save that overlaps ``Settings.load`` still writes the startup instance."""
    core, other_config, default_before = _prepare_other_instance(
        mcp_core, game_install, config_folder, tmp_path
    )
    core.settings.current_instance = "Default"
    core.settings.save()
    core.settings.current_instance = "Other"

    apply_paused = threading.Event()
    release_apply = threading.Event()
    load_paused = threading.Event()
    release_load = threading.Event()
    errors: list[BaseException] = []
    real_rebind = RimSortMcpCore._rebind_instance
    real_load = Settings.load

    def rebind_and_pause(self: RimSortMcpCore) -> bool:
        bound = real_rebind(self)
        if not apply_paused.is_set():
            apply_paused.set()
            if not release_apply.wait(timeout=5):
                raise TimeoutError("apply was not released")
        return bound

    def load_and_pause(self: Settings) -> None:
        real_load(self)
        load_paused.set()
        if not release_load.wait(timeout=5):
            raise TimeoutError("refresh was not released")

    monkeypatch.setattr(RimSortMcpCore, "_rebind_instance", rebind_and_pause)
    monkeypatch.setattr(Settings, "load", load_and_pause)

    def refresh() -> None:
        try:
            core.refresh_metadata_cache()
        except BaseException as exc:
            errors.append(exc)

    def apply() -> None:
        try:
            core.apply_active_modlist(["ludeon.rimworld"])
        except BaseException as exc:
            errors.append(exc)

    writer = threading.Thread(target=apply)
    refresher = threading.Thread(target=refresh)
    writer.start()
    assert apply_paused.wait(timeout=5)
    refresher.start()
    refresh_entered_load = load_paused.wait(timeout=0.5)
    if refresh_entered_load:
        release_apply.set()
        writer.join(timeout=5)
        release_load.set()
    else:
        release_apply.set()
        writer.join(timeout=5)
        assert load_paused.wait(timeout=5)
        release_load.set()
    refresher.join(timeout=5)

    assert errors == []
    assert not writer.is_alive()
    assert not refresher.is_alive()
    assert not refresh_entered_load
    assert core.settings.current_instance == "Other"
    assert (config_folder / "ModsConfig.xml").read_bytes() == default_before
    other_text = (other_config / "ModsConfig.xml").read_text(encoding="utf-8")
    assert "only.other" not in other_text
    assert "ludeon.rimworld" in other_text


def test_overlapping_sort_dialog_capture_does_not_restore_early() -> None:
    """A nested/overlapping capture must not reinstate the real dialog callback."""
    original = topo_sort_module.show_warning
    second_entered = threading.Event()
    first_may_exit = threading.Event()
    failures: list[str] = []

    def first() -> None:
        with mcp_core_module._capture_sort_dialogs() as captured:
            if not second_entered.wait(timeout=2):
                failures.append("second capture never entered")
                return
            if topo_sort_module.show_warning is original:
                failures.append("show_warning restored while first capture active")
            topo_sort_module.show_warning("one", "cycle-a", details="A -> B -> A")
            first_may_exit.set()
            assert captured

    def second() -> None:
        with mcp_core_module._capture_sort_dialogs() as captured:
            second_entered.set()
            if not first_may_exit.wait(timeout=2):
                failures.append("first capture never reached midpoint")
                return
            if topo_sort_module.show_warning is original:
                failures.append("show_warning restored while second capture active")
            topo_sort_module.show_warning("two", "cycle-b", details="B -> A -> B")
            assert captured

    threads = [threading.Thread(target=first), threading.Thread(target=second)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert failures == []
    assert topo_sort_module.show_warning is original


def test_backup_names_are_unique_within_the_same_second(
    ordered: RimSortMcpCore,
    config_folder: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two backups in the same second must not overwrite each other."""
    write_mods_config(config_folder, ["ludeon.rimworld"])
    fixed = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)

    class _FixedDateTime:
        @staticmethod
        def now(tz: object | None = None) -> datetime:
            return fixed

    monkeypatch.setattr(mcp_core_module, "datetime", _FixedDateTime)

    first = ordered._backup_mods_config()
    write_mods_config(config_folder, ["ludeon.rimworld", "brrainz.harmony"])
    second = ordered._backup_mods_config()

    assert first is not None and second is not None
    assert first != second
    assert first.is_file() and second.is_file()
    assert first.read_text(encoding="utf-8") != second.read_text(encoding="utf-8")


def test_overlapping_saves_keep_the_pre_save_backup(
    ordered: RimSortMcpCore,
    config_folder: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A save paused in the backup copy must not record the other save's config."""
    original = write_mods_config(
        config_folder, ["ludeon.rimworld", "brrainz.harmony"]
    ).read_bytes()
    copy_started = threading.Event()
    release_copy = threading.Event()
    errors: list[BaseException] = []
    found: dict[str, dict[str, object]] = {}
    real_copy = RimSortMcpCore._copy_into_reserved_backup

    def pausing_copy(
        self: RimSortMcpCore, source: Path, handle: BufferedWriter
    ) -> None:
        if not copy_started.is_set():
            copy_started.set()
            if not release_copy.wait(timeout=5):
                raise TimeoutError("backup copy was not released")
        real_copy(self, source, handle)

    def fast_analysis(
        self: RimSortMcpCore, package_ids: list[str]
    ) -> dict[str, object]:
        return {
            "warnings": [],
            "errors": [],
            "unresolved_package_ids": [],
            "sort_success": True,
            "sorted_package_ids": list(package_ids),
        }

    monkeypatch.setattr(RimSortMcpCore, "_copy_into_reserved_backup", pausing_copy)
    monkeypatch.setattr(RimSortMcpCore, "analyze_and_sort_modlist", fast_analysis)

    def run(label: str, package_ids: list[str]) -> None:
        try:
            found[label] = cast(
                dict[str, object],
                ordered.apply_active_modlist(package_ids, auto_sort=False),
            )
        except BaseException as exc:
            errors.append(exc)

    first = threading.Thread(target=run, args=("first", ["ludeon.rimworld"]))
    second = threading.Thread(
        target=run, args=("second", ["ludeon.rimworld", "brrainz.harmony"])
    )
    first.start()
    assert copy_started.wait(timeout=5)
    second.start()
    second.join(timeout=1)
    assert second.is_alive()
    release_copy.set()
    first.join(timeout=5)
    second.join(timeout=5)

    assert errors == []
    assert not first.is_alive()
    assert not second.is_alive()
    assert found["first"]["saved"] is True
    assert found["second"]["saved"] is True
    first_backup = Path(str(found["first"]["backup_path"]))
    second_backup = Path(str(found["second"]["backup_path"]))
    final = (config_folder / "ModsConfig.xml").read_bytes()
    assert first_backup != second_backup
    assert first_backup.read_bytes() == original
    assert b"brrainz.harmony" not in second_backup.read_bytes()
    assert b"brrainz.harmony" in final
    assert second_backup.read_bytes() != final


def test_overlapping_cycle_sorts_do_not_open_a_dialog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two real cycle sorts must both stay on the interceptor."""
    dialog_calls: list[str] = []

    def spy(*_args: object, **_kwargs: object) -> None:
        dialog_calls.append("dialog")

    monkeypatch.setattr(topo_sort_module, "show_warning", spy)
    cores: list[tuple[RimSortMcpCore, str]] = []
    for name in ("alpha", "beta"):
        install = make_game_install(tmp_path / name, "linux")
        config = tmp_path / f"{name}-config"
        config.mkdir()
        write_mod(
            install.mods_path,
            "LoopA",
            f"{name}.loopa",
            rules=f"<loadAfter><li>{name}.loopb</li></loadAfter>",
        )
        write_mod(
            install.mods_path,
            "LoopB",
            f"{name}.loopb",
            rules=f"<loadAfter><li>{name}.loopa</li></loadAfter>",
        )
        settings = Settings()
        settings.instances[settings.current_instance] = Instance(
            name=settings.current_instance,
            game_folder=str(install.launch_location),
            config_folder=str(config),
            local_folder=str(install.mods_path),
        )
        cores.append((build_core(settings), name))

    results: list[dict[str, object]] = []
    errors: list[BaseException] = []
    barrier = threading.Barrier(2)

    def run(core: RimSortMcpCore, name: str) -> None:
        try:
            barrier.wait(timeout=5)
            results.append(
                core.analyze_and_sort_modlist([f"{name}.loopa", f"{name}.loopb"])
            )
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=run, args=(core, name)) for core, name in cores]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert errors == []
    assert not any(thread.is_alive() for thread in threads)
    assert dialog_calls == []
    assert topo_sort_module.show_warning is spy
    assert len(results) == 2
    for result in results:
        assert result["sort_success"] is False
        errors_payload = cast(list[dict[str, object]], result["errors"])
        assert errors_payload[0]["type"] == "circular_dependency"


def test_apply_refuses_write_when_core_cannot_be_resolved(
    ordered: RimSortMcpCore, config_folder: Path
) -> None:
    """Metadata failure must not replace ModsConfig with an empty Unknown list."""
    existing = write_mods_config(config_folder, ["ludeon.rimworld", "brrainz.harmony"])
    before = existing.read_text(encoding="utf-8")

    ordered.metadata_controller.mods_metadata.clear()
    ordered.metadata_controller._packageid_to_paths_cache = None
    ordered.metadata_controller.metadata_mediator._game_version = "Unknown"

    result = ordered.apply_active_modlist([])

    assert result["saved"] is False
    assert result["errors"][0]["type"] == "core_unresolved"
    assert result["backup_path"] is None
    assert existing.read_text(encoding="utf-8") == before


def test_apply_refuses_write_when_game_version_cannot_be_resolved(
    ordered: RimSortMcpCore, config_folder: Path, game_install: GameInstall
) -> None:
    """Core without a readable Version.txt must not save ``<version>Unknown</version>``."""
    existing = write_mods_config(config_folder, ["ludeon.rimworld", "brrainz.harmony"])
    before = existing.read_bytes()
    (game_install.content_root / "Version.txt").unlink()

    refreshed = ordered.refresh_metadata_cache()
    result = ordered.apply_active_modlist(["ludeon.rimworld"])

    indexed = {
        package_id.lower()
        for package_id in ordered.metadata_controller.packageid_to_paths
    }
    assert "ludeon.rimworld" in indexed
    assert refreshed["game_version"] == "Unknown"
    assert result["saved"] is False
    assert result["errors"][0]["type"] == "version_unresolved"
    assert result["backup_path"] is None
    assert existing.read_bytes() == before

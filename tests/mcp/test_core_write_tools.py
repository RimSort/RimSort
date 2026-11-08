"""Tests for the MCP write-path tools: analysis, sorting and ModsConfig writes."""

from __future__ import annotations

from pathlib import Path
from typing import cast
from unittest.mock import MagicMock
from xml.etree import ElementTree

import pytest

from app.controllers.sort_controller import Sorter
from app.mcp.core import RimSortMcpCore
from app.models.metadata.metadata_structure import ModType
from app.services.import_export_service import ImportExportService
from app.services.mod_list_parser import parse_mod_list_file
from tests.game_layout_fixtures import GameInstall
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

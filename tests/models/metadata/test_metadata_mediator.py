import json
from pathlib import Path

import pytest

from app.models.metadata.metadata_mediator import MetadataMediator
from app.models.metadata.metadata_structure import AboutXmlMod


@pytest.fixture
def mediator() -> MetadataMediator:
    return MetadataMediator(
        user_rules_path=Path("tests/data/dbs/userRules.json"),
        community_rules_path=None,
        steam_db_path=None,
        workshop_mods_path=None,
        local_mods_path=Path("tests/data/mod_examples/Local"),
        game_path=Path("tests/data/mod_examples/RimWorld"),
    )


def test_initial_state(mediator: MetadataMediator) -> None:
    assert mediator.user_rules is None
    assert mediator.community_rules is None
    assert mediator.steam_db is None
    assert mediator.game_version == "Unknown"

    assert mediator.mods_metadata == {}


def test_refresh_metadata(mediator: MetadataMediator) -> None:
    mediator.refresh_metadata()
    assert mediator.user_rules is not None
    assert mediator.community_rules is None
    assert mediator.steam_db is None
    assert mediator.mods_metadata is not None
    assert len(mediator.mods_metadata) > 0
    a = len(mediator.mods_metadata)
    assert mediator.game_version != "Unknown"

    mediator.workshop_mods_path = Path("tests/data/mod_examples/Steam")
    mediator.steam_db_path = Path("tests/data/dbs/steamDB.json")
    mediator.refresh_metadata()
    assert mediator.user_rules is not None
    assert mediator.community_rules is None
    assert mediator.steam_db is not None
    assert mediator.mods_metadata is not None
    assert len(mediator.mods_metadata) > 0
    assert len(mediator.mods_metadata) > a
    assert mediator.game_version != "Unknown"

    mediator.game_path = Path("tests/data/mod_examples")
    mediator.refresh_metadata()
    assert mediator.game_version == "Unknown"


def test_user_rules_addition(mediator: MetadataMediator) -> None:
    mediator.refresh_metadata()

    assert mediator.user_rules is not None
    assert mediator.mods_metadata is not None
    assert len(mediator.mods_metadata) > 0

    mod = mediator.mods_metadata.get(
        str(Path("tests/data/mod_examples/Local/local_mod_1")), None
    )
    assert mod is not None

    assert isinstance(mod, AboutXmlMod)
    assert mod.about_rules.load_after == {}
    assert len(mod.user_rules.load_after) > 0
    assert len(mod.overall_rules.load_after) > 0

    assert mod.user_rules.load_last
    assert mod.overall_rules.load_last


def test_mediator_no_version_warning_defaults_none(tmp_path: Path) -> None:
    """no_version_warning is None when no path configured."""
    mediator = MetadataMediator(
        user_rules_path=tmp_path / "rules.json",
        community_rules_path=None,
        steam_db_path=None,
        workshop_mods_path=None,
        local_mods_path=None,
        game_path=None,
    )
    assert mediator.no_version_warning is None


def test_mediator_use_this_instead_defaults_none(tmp_path: Path) -> None:
    """use_this_instead is None when no path configured."""
    mediator = MetadataMediator(
        user_rules_path=tmp_path / "rules.json",
        community_rules_path=None,
        steam_db_path=None,
        workshop_mods_path=None,
        local_mods_path=None,
        game_path=None,
    )
    assert mediator.use_this_instead is None


def test_mediator_loads_no_version_warning(tmp_path: Path) -> None:
    """Mediator loads No Version Warning from XML file."""
    xml_content = '<?xml version="1.0" encoding="utf-8"?>\n<ModIdsToFix><li>mod.a</li><li>mod.b</li></ModIdsToFix>'
    nvw_path = tmp_path / "ModIdsToFix.xml"
    nvw_path.write_text(xml_content)

    mediator = MetadataMediator(
        user_rules_path=tmp_path / "rules.json",
        community_rules_path=None,
        steam_db_path=None,
        workshop_mods_path=None,
        local_mods_path=None,
        game_path=None,
        no_version_warning_path=nvw_path,
    )
    mediator._load_no_version_warning()
    assert mediator.no_version_warning is not None
    assert "mod.a" in mediator.no_version_warning
    assert "mod.b" in mediator.no_version_warning


def test_mediator_loads_use_this_instead(tmp_path: Path) -> None:
    """Mediator loads Use This Instead from JSON file, indexed by oldWorkshopId."""
    uti_data = {
        "version": "2026-01-01T00:00:00Z",
        "rules": [
            {
                "oldWorkshopId": "111111",
                "oldName": "Old Mod",
                "oldPackageId": "old.mod.a",
                "newWorkshopId": "222222",
                "newName": "New Mod",
                "newPackageId": "new.mod.b",
                "newAuthor": "Author",
                "oldVersions": ["1.4"],
                "newVersions": ["1.5"],
            }
        ],
    }
    uti_path = tmp_path / "use_this_instead.json"
    uti_path.write_text(json.dumps(uti_data))

    mediator = MetadataMediator(
        user_rules_path=tmp_path / "rules.json",
        community_rules_path=None,
        steam_db_path=None,
        workshop_mods_path=None,
        local_mods_path=None,
        game_path=None,
        use_this_instead_path=uti_path,
    )
    mediator._load_use_this_instead()
    assert mediator.use_this_instead is not None
    assert "111111" in mediator.use_this_instead
    entry = mediator.use_this_instead["111111"]
    assert entry["newName"] == "New Mod"
    assert entry["newPackageId"] == "new.mod.b"

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

    try:
        assert mediator.mods_metadata is None
    except ValueError:
        pass
    else:
        assert False


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

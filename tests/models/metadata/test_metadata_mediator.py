from pathlib import Path

import pytest

from app.models.metadata.metadata_mediator import MetadataMediator


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
    assert mediator.user_rules is not None
    assert mediator.community_rules is None
    assert mediator.steam_db is None
    assert mediator.mods_metadata is not None
    assert len(mediator.mods_metadata) > 0
    assert mediator.game_version != "Unknown"


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

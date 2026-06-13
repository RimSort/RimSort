from unittest.mock import MagicMock

from app.models.metadata.metadata_structure import AboutXmlMod


def test_init_db_from_local_metadata_structure() -> None:
    """Verify _init_db_from_local_metadata produces correct dict structure from typed objects."""
    from app.utils.steam.db_builder_thread import SteamDatabaseBuilder

    mod = AboutXmlMod()
    mod.name = "Test Mod"
    mod.authors = ["Author A", "Author B"]
    mod.steam_app_id = -1  # no appid
    mod.supported_versions = {"1.4", "1.5"}
    mod.mod_path = __import__("pathlib").Path("/fake/mod")

    builder = SteamDatabaseBuilder.__new__(SteamDatabaseBuilder)
    builder.mods = {"/fake/mod": mod}
    builder.appid = 294100
    builder.db_builder_message_output_signal = MagicMock()

    result = builder._init_db_from_local_metadata()
    assert result["version"] == 0
    assert result["database"] == {}


def test_init_db_excludes_negative_steam_app_id() -> None:
    """steam_app_id=-1 (default) must be excluded from appid entries."""
    from app.utils.steam.db_builder_thread import SteamDatabaseBuilder

    mod = AboutXmlMod()
    mod.steam_app_id = -1
    mod.mod_path = __import__("pathlib").Path("/fake")

    builder = SteamDatabaseBuilder.__new__(SteamDatabaseBuilder)
    builder.mods = {"/fake": mod}
    builder.appid = 294100
    builder.db_builder_message_output_signal = MagicMock()

    result = builder._init_db_from_local_metadata()
    assert "-1" not in result["database"]


def test_init_db_authors_is_string() -> None:
    """authors field must be a comma-separated string, not a list."""
    from app.utils.steam.db_builder_thread import SteamDatabaseBuilder

    mod = AboutXmlMod()
    mod.steam_app_id = 294100
    mod.authors = ["Alice", "Bob"]
    mod.mod_path = __import__("pathlib").Path("/fake")

    builder = SteamDatabaseBuilder.__new__(SteamDatabaseBuilder)
    builder.mods = {"/fake": mod}
    builder.appid = 294100
    builder.db_builder_message_output_signal = MagicMock()

    result = builder._init_db_from_local_metadata()
    entry = result["database"]["294100"]
    assert isinstance(entry["authors"], str)
    assert entry["authors"] == "Alice, Bob"

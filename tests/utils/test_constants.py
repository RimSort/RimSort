from app.utils.constants import (
    DEFAULT_INSTANCE_NAME,
    DEFAULT_MISSING_PACKAGEID,
    KNOWN_MOD_REPLACEMENTS,
    KNOWN_TIER_ZERO_MODS,
    RIMWORLD_DLC_METADATA,
    RIMWORLD_PACKAGE_IDS,
    SEARCH_DATA_SOURCE_FILTER_INDEXES,
    SortMethod,
)


class TestSortMethod:
    def test_values(self) -> None:
        assert SortMethod.ALPHABETICAL == "Alphabetical"
        assert SortMethod.TOPOLOGICAL == "Topological"

    def test_is_string_enum(self) -> None:
        assert isinstance(SortMethod.ALPHABETICAL, str)


class TestRimworldDlcMetadata:
    def test_all_dlcs_have_required_fields(self) -> None:
        for app_id, meta in RIMWORLD_DLC_METADATA.items():
            assert "packageid" in meta, f"Missing packageid for {app_id}"
            assert "name" in meta, f"Missing name for {app_id}"
            assert "steam_url" in meta, f"Missing steam_url for {app_id}"

    def test_package_ids_derived_correctly(self) -> None:
        expected = [v["packageid"] for v in RIMWORLD_DLC_METADATA.values()]
        assert RIMWORLD_PACKAGE_IDS == expected

    def test_base_game_included(self) -> None:
        assert "ludeon.rimworld" in RIMWORLD_PACKAGE_IDS

    def test_known_dlc_count(self) -> None:
        # Base game + 5 DLCs = 6 entries
        assert len(RIMWORLD_DLC_METADATA) == 6


class TestKnownMods:
    def test_tier_zero_contains_base_game(self) -> None:
        assert "ludeon.rimworld" in KNOWN_TIER_ZERO_MODS

    def test_tier_zero_contains_harmony(self) -> None:
        assert "brrainz.harmony" in KNOWN_TIER_ZERO_MODS

    def test_replacements_keys_exist(self) -> None:
        for key, replacements in KNOWN_MOD_REPLACEMENTS.items():
            assert isinstance(key, str)
            assert isinstance(replacements, set)
            assert len(replacements) > 0


class TestMiscConstants:
    def test_default_instance_name(self) -> None:
        assert DEFAULT_INSTANCE_NAME == "Default"

    def test_default_missing_packageid(self) -> None:
        assert DEFAULT_MISSING_PACKAGEID == "missing.packageid"

    def test_search_filter_indexes(self) -> None:
        assert "all" in SEARCH_DATA_SOURCE_FILTER_INDEXES
        assert "workshop" in SEARCH_DATA_SOURCE_FILTER_INDEXES

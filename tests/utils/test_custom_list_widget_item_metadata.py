"""Tests for CustomListWidgetItemMetadata.get_updated_timestamp_by_path.

Covers the "recently updated" timestamp resolution: only Steam Workshop /
SteamCMD mods yield a timestamp; every other source (and missing mods) return
None. The method holds no instance state, so we exercise it on a bare instance
created via ``object.__new__`` to avoid the heavy ``__init__``.
"""

from unittest.mock import MagicMock, patch

from app.models.metadata.metadata_structure import ModType
from app.utils.custom_list_widget_item_metadata import CustomListWidgetItemMetadata

MODULE = "app.utils.custom_list_widget_item_metadata"


def _bare_instance() -> CustomListWidgetItemMetadata:
    """A CustomListWidgetItemMetadata without running __init__."""
    return object.__new__(CustomListWidgetItemMetadata)


def _mod(mod_type: ModType) -> MagicMock:
    mod = MagicMock()
    mod.mod_type = mod_type
    return mod


def _aux_entry(acf: int = -1, external: int = -1) -> MagicMock:
    entry = MagicMock()
    entry.acf_time_updated = acf
    entry.external_time_updated = external
    return entry


class TestGetUpdatedTimestampByPath:
    def test_workshop_mod_returns_acf_timestamp(self) -> None:
        """A Steam Workshop mod resolves to its aux DB acf_time_updated."""
        with (
            patch(f"{MODULE}.MetadataController.instance") as mock_instance,
            patch(f"{MODULE}.auxdb_get_aux_db_entry") as mock_aux,
        ):
            mock_instance.return_value.get_mod.return_value = _mod(
                ModType.STEAM_WORKSHOP
            )
            mock_aux.return_value = _aux_entry(acf=12345, external=999)

            result = _bare_instance().get_updated_timestamp_by_path(
                "/mods/ws", MagicMock(), None, None
            )

        assert result == 12345
        mock_aux.assert_called_once()

    def test_steamcmd_mod_falls_back_to_external(self) -> None:
        """A SteamCMD mod with no ACF time falls back to external_time_updated."""
        with (
            patch(f"{MODULE}.MetadataController.instance") as mock_instance,
            patch(f"{MODULE}.auxdb_get_aux_db_entry") as mock_aux,
        ):
            mock_instance.return_value.get_mod.return_value = _mod(ModType.STEAM_CMD)
            mock_aux.return_value = _aux_entry(acf=-1, external=888)

            result = _bare_instance().get_updated_timestamp_by_path(
                "/mods/cmd", MagicMock(), None, None
            )

        assert result == 888

    def test_local_mod_is_skipped(self) -> None:
        """Local mods are never flagged and never hit the aux DB."""
        with (
            patch(f"{MODULE}.MetadataController.instance") as mock_instance,
            patch(f"{MODULE}.auxdb_get_aux_db_entry") as mock_aux,
        ):
            mock_instance.return_value.get_mod.return_value = _mod(ModType.LOCAL)

            result = _bare_instance().get_updated_timestamp_by_path(
                "/mods/local", MagicMock(), None, None
            )

        assert result is None
        mock_aux.assert_not_called()

    def test_git_mod_is_skipped(self) -> None:
        with (
            patch(f"{MODULE}.MetadataController.instance") as mock_instance,
            patch(f"{MODULE}.auxdb_get_aux_db_entry") as mock_aux,
        ):
            mock_instance.return_value.get_mod.return_value = _mod(ModType.GIT)

            result = _bare_instance().get_updated_timestamp_by_path(
                "/mods/git", MagicMock(), None, None
            )

        assert result is None
        mock_aux.assert_not_called()

    def test_ludeon_mod_is_skipped(self) -> None:
        with (
            patch(f"{MODULE}.MetadataController.instance") as mock_instance,
            patch(f"{MODULE}.auxdb_get_aux_db_entry") as mock_aux,
        ):
            mock_instance.return_value.get_mod.return_value = _mod(ModType.LUDEON)

            result = _bare_instance().get_updated_timestamp_by_path(
                "/mods/core", MagicMock(), None, None
            )

        assert result is None
        mock_aux.assert_not_called()

    def test_missing_mod_returns_none(self) -> None:
        """When get_mod returns None, no timestamp is produced."""
        with (
            patch(f"{MODULE}.MetadataController.instance") as mock_instance,
            patch(f"{MODULE}.auxdb_get_aux_db_entry") as mock_aux,
        ):
            mock_instance.return_value.get_mod.return_value = None

            result = _bare_instance().get_updated_timestamp_by_path(
                "/mods/missing", MagicMock(), None, None
            )

        assert result is None
        mock_aux.assert_not_called()

    def test_keyerror_returns_none(self) -> None:
        """A KeyError from get_mod is swallowed and yields None."""
        with (
            patch(f"{MODULE}.MetadataController.instance") as mock_instance,
            patch(f"{MODULE}.auxdb_get_aux_db_entry") as mock_aux,
        ):
            mock_instance.return_value.get_mod.side_effect = KeyError("nope")

            result = _bare_instance().get_updated_timestamp_by_path(
                "/mods/err", MagicMock(), None, None
            )

        assert result is None
        mock_aux.assert_not_called()

    def test_workshop_mod_without_aux_entry_returns_none(self) -> None:
        """A workshop mod with no aux DB entry resolves to None."""
        with (
            patch(f"{MODULE}.MetadataController.instance") as mock_instance,
            patch(f"{MODULE}.auxdb_get_aux_db_entry") as mock_aux,
        ):
            mock_instance.return_value.get_mod.return_value = _mod(
                ModType.STEAM_WORKSHOP
            )
            mock_aux.return_value = None

            result = _bare_instance().get_updated_timestamp_by_path(
                "/mods/ws", MagicMock(), None, None
            )

        assert result is None

from pathlib import Path

from PySide6.QtCore import QObject, Slot

from app.controllers.metadata_db_controller import AuxMetadataController
from app.controllers.settings_controller import SettingsController
from app.models.metadata.metadata_db import AuxMetadataEntry
from app.models.metadata.metadata_mediator import MetadataMediator
from app.models.metadata.metadata_structure import ListedMod
from app.utils.app_info import AppInfo


class MetadataController(QObject):
    """Controller class for metadata."""

    def __init__(
        self,
        settings_controller: SettingsController,
        metadata_db_controller: AuxMetadataController,
    ) -> None:
        super().__init__()

        self.settings_controller = settings_controller
        active_instance = self.settings_controller.active_instance
        active_settings = self.settings_controller.settings

        cr_path = (
            Path(active_settings.external_community_rules_file_path)
            if active_settings.external_community_rules_file_path
            else None
        )
        steam_db_path = (
            Path(active_settings.external_steam_metadata_file_path)
            if active_settings.external_steam_metadata_file_path
            else None
        )

        self.metadata_mediator = MetadataMediator(
            user_rules_path=AppInfo().user_rules_file,
            community_rules_path=Path(
                active_settings.external_community_rules_file_path
            ),
            steam_db_path=steam_db_path,
            workshop_mods_path=cr_path,
            local_mods_path=Path(active_instance.local_folder),
            game_path=Path(active_instance.game_folder),
        )
        self.metadata_db_controller = metadata_db_controller

    @Slot()
    def refresh_metadata(self) -> None:
        """Refresh the metadata."""
        self.metadata_mediator.refresh_metadata()

    @Slot()
    def reset_paths(self) -> None:
        """Reset the paths.
        This is used when the paths are changed in the settings.

        Does not refresh the metadata.
        """
        active_instance = self.settings_controller.active_instance
        active_settings = self.settings_controller.settings

        self.metadata_mediator.local_mods_path = Path(active_instance.local_folder)
        self.metadata_mediator.game_path = Path(active_instance.game_folder)
        self.metadata_mediator.workshop_mods_path = (
            Path(active_settings.external_community_rules_file_path)
            if active_settings.external_community_rules_file_path
            else None
        )
        self.metadata_mediator.steam_db_path = (
            Path(active_settings.external_steam_metadata_file_path)
            if active_settings.external_steam_metadata_file_path
            else None
        )

    @Slot(str)
    def get_metadata_path(
        self, path: str | Path
    ) -> tuple[ListedMod, AuxMetadataEntry] | tuple[None, None]:
        mod_data = self.metadata_mediator.mods_metadata.get(str(path), None)
        if mod_data is None:
            return None, None

        with self.metadata_db_controller.Session() as session:
            entry = self.metadata_db_controller.get_or_create(session, path)

        return mod_data, entry

    @Slot(str)
    def delete_mod(self, uuid: str) -> None:
        """Delete a mod from the metadata.

        :param uuid: The UUID of the mod to delete.
        :type uuid: str | list[str]
        """
        pass

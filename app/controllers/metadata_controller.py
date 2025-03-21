from pathlib import Path

from PySide6.QtCore import QObject, Slot

from app.controllers.metadata_db_controller import AuxMetadataController
from app.controllers.settings_controller import SettingsController
from app.models.metadata.metadata_db import AuxMetadataEntry
from app.models.metadata.metadata_mediator import MetadataMediator
from app.models.metadata.metadata_structure import ListedMod, ModType
from app.utils.app_info import AppInfo
from app.utils.steam.steamcmd.wrapper import SteamcmdInterface


class MetadataController(QObject):
    """Controller class for metadata."""

    def __init__(
        self,
        settings_controller: SettingsController,
        metadata_db_controller: AuxMetadataController,
    ) -> None:
        super().__init__()

        self.settings_controller = settings_controller

        self.metadata_mediator = MetadataMediator(
            user_rules_path=AppInfo().user_rules_file,
            community_rules_path=None,
            steam_db_path=None,
            workshop_mods_path=None,
            local_mods_path=None,
            game_path=None,
        )
        self.reset_paths()

        self.metadata_db_controller = metadata_db_controller
        self.steamcmd_wrapper = SteamcmdInterface.instance()

    @Slot()
    def refresh_metadata(self) -> None:
        """Refresh the metadata."""
        self.metadata_mediator.refresh_metadata()
        self._refresh_metadata_db()

        with self.metadata_db_controller.Session() as session:
            self.metadata_db_controller.update_from_acf(
                session,
                Path(self.steamcmd_wrapper.steamcmd_appworkshop_acf_path),
                ModType.STEAM_CMD,
            )

            if self.metadata_mediator.workshop_mods_path is not None:
                self.metadata_db_controller.update_from_acf(
                    session,
                    self.metadata_mediator.workshop_mods_path.parent.parent
                    / "appworkshop_294100.acf",
                    ModType.STEAM_WORKSHOP,
                )

    def _refresh_metadata_db(self) -> None:
        """Refresh the metadata database."""
        with self.metadata_db_controller.Session() as session:
            for path, mod_data in self.metadata_mediator.mods_metadata.items():
                entry = self.metadata_db_controller.get_or_create(session, path)

                entry.type = str(mod_data.mod_type)
                entry.published_file_id = mod_data.published_file_id

            session.commit()

    @Slot()
    def reset_paths(self) -> None:
        """Reset the paths.
        This is used when the paths are changed in the settings.

        Does not refresh the metadata.
        """

        def _get_path(path_str: str) -> Path | None:
            return Path(path_str) if path_str else None

        active_instance = self.settings_controller.active_instance
        active_settings = self.settings_controller.settings

        cr_path = _get_path(active_settings.external_community_rules_file_path)
        steam_db_path = _get_path(active_settings.external_steam_metadata_file_path)
        workshop_mods_path = _get_path(active_instance.workshop_folder)
        local_mods_path = _get_path(active_instance.local_folder)
        game_path = _get_path(active_instance.game_folder)

        self.metadata_mediator.community_rules_path = cr_path
        self.metadata_mediator.steam_db_path = steam_db_path
        self.metadata_mediator.workshop_mods_path = workshop_mods_path
        self.metadata_mediator.local_mods_path = local_mods_path
        self.metadata_mediator.game_path = game_path

    def get_metadata_with_path(
        self, path: str | Path
    ) -> tuple[ListedMod, AuxMetadataEntry] | tuple[None, None]:
        mod_data = self.metadata_mediator.mods_metadata.get(str(path), None)
        if mod_data is None:
            return None, None

        with self.metadata_db_controller.Session() as session:
            entry = self.metadata_db_controller.get_or_create(session, path)

        return mod_data, entry

    @Slot(str)
    def delete_mod(self, *path: Path) -> None:
        """Delete a mod from the metadata, and aux metadata
        Does not remove the mod from disk.

        :param path:
        :type Path: Path
        """
        with self.metadata_db_controller.Session() as session:
            self.metadata_db_controller.delete(session, *path)

        for p in path:
            self.metadata_mediator.mods_metadata.pop(str(p), None)

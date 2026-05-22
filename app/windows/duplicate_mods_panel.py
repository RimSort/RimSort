from typing import Any

from loguru import logger

from app.controllers.settings_controller import SettingsController
from app.windows.base_mods_panel import (
    BaseModsPanel,
)


class DuplicateModsPanel(BaseModsPanel):
    """
    A panel used when duplicate mods are detected, allowing users to choose which version to keep.

    This panel displays duplicate mods grouped by their package ID, showing detailed
    information for each mod version. Users can select which versions to keep and
    use the deletion menu to remove unwanted duplicates.

    Attributes:
        duplicate_mods (dict[str, list[str]]): Dictionary mapping package IDs to lists of UUIDs
            of duplicate mods.
        settings_controller (SettingsController): Controller for application settings.
        metadata_manager: MetadataManager instance from base class for accessing mod data.
    """

    def __init__(
        self,
        duplicate_mods: dict[str, list[str]],
        settings_controller: SettingsController,
    ) -> None:
        """
        Initialize the DuplicateModsPanel with duplicate mods data.

        Args:
            duplicate_mods: Dictionary mapping package IDs to lists of UUIDs of duplicate mods.
            settings_controller: Controller for managing application settings.
        """
        logger.debug("Initializing DuplicateModsPanel")
        self.duplicate_mods = duplicate_mods
        self.settings_controller = settings_controller

        super().__init__(
            object_name="duplicateModsPanel",
            window_title=self.tr("RimSort - Duplicate Mods Found"),
            title_text=self.tr("Duplicate mods detected!"),
            details_text=self.tr(
                "\nThe following table displays duplicate mods grouped by package ID. "
                "Select which versions to keep and choose an action."
            ),
            additional_columns=self._get_standard_mod_columns(),
        )

        button_configs = self._get_base_button_configs()
        self._extend_button_configs_with_steam_actions(button_configs)
        button_configs.append(
            self._create_delete_button_config(self.tr("Delete Selected Mods"))
        )
        self._setup_buttons_from_config(button_configs)

        # Populate the table with duplicate mod data
        self._populate_from_metadata()
        # Sorting is disabled by default in _setup_table_and_model

        # TODO: let user configure window launch state and size from settings controller
        self.showNormal()

    def _populate_from_metadata(self) -> None:
        """
        Populate the table with duplicate mod data.
        """
        try:
            # Convert duplicate_mods dict to the format expected by _populate_mods
            groups: dict[str, list[tuple[str, dict[str, Any]]]] = {}
            for packageid, uuids in self.duplicate_mods.items():
                mod_list = []
                for uuid in uuids:
                    metadata = self.metadata_manager.internal_local_metadata.get(uuid)
                    if metadata:
                        mod_list.append((uuid, metadata))
                    else:
                        logger.warning(
                            f"Metadata not found for UUID: {uuid} in package group {packageid}"
                        )
                if mod_list:  # Only add groups that have mods
                    groups[packageid] = mod_list

            # Use the refactored base class method to populate grouped mods
            self._populate_mods(groups, add_group_headers=True)
        except Exception as e:
            logger.error(f"Error populating table from metadata: {e}")

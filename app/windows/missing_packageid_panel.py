from loguru import logger

from app.controllers.settings_controller import SettingsController
from app.windows.base_mods_panel import BaseModsPanel


class MissingPackageIdPanel(BaseModsPanel):
    """
    A panel used when mods with missing Package ID are detected.

    This panel displays mods that lack a valid Package ID defined in their
    About.xml file, showing detailed information for each mod. Users can
    view mod details and access Steam Workshop links if available.

    Attributes:
        missing_packageid_mods (list[str]): List of UUIDs for mods with missing Package ID.
        settings_controller (SettingsController): Controller for application settings.
        metadata_manager: MetadataManager instance from base class for accessing mod data.
    """

    def __init__(
        self,
        missing_packageid_mods: list[str],
        settings_controller: SettingsController,
    ) -> None:
        """
        Initialize the MissingPackageIdPanel with mods data.

        Args:
            missing_packageid_mods: List of UUIDs for mods with missing Package ID.
            settings_controller: Controller for managing application settings.
        """
        logger.debug("Initializing MissingPackageIdPanel")
        self.missing_packageid_mods = missing_packageid_mods
        self.settings_controller = settings_controller

        super().__init__(
            object_name="missingPackageIdPanel",
            window_title=self.tr("RimSort - Mods with Missing Package ID"),
            title_text=self.tr("Mods with Missing Package ID detected!"),
            details_text=self.tr(
                "The following mods do not have a valid Package ID defined in their About.xml file. "
                "This may cause issues with mod dependencies and compatibility checking.\n\n"
                "For Workshop mods, you can identify them by the Published File ID column. "
                "Please contact the mod authors to add a Package ID to their About.xml file."
            ),
            additional_columns=self._get_standard_mod_columns(),
        )

        button_configs = self._get_base_button_configs()
        self._extend_button_configs_with_steam_actions(button_configs)
        self._setup_buttons_from_config(button_configs)

        # Populate the table with missing packageid mod data
        self._populate_from_metadata()

        # Configure table settings
        self._setup_table_configuration(sorting_enabled=False)

        # TODO: let user configure window launch state and size from settings controller
        self.showNormal()

    def _populate_from_metadata(self) -> None:
        """
        Populate the table with missing packageid mod data.
        Displays all mod metadata in the table, with Published File ID column
        showing Workshop IDs for Workshop mods.
        """
        try:
            # Convert list of UUIDs to the format expected by _populate_mods
            mod_list = []
            for uuid in self.missing_packageid_mods:
                metadata = self.metadata_manager.internal_local_metadata.get(uuid)
                if metadata:
                    mod_list.append((uuid, metadata))
                else:
                    logger.warning(
                        f"Metadata not found for UUID: {uuid} in missing packageid mods"
                    )

            # Use the refactored base class method to populate mods
            if mod_list:
                self._populate_mods(
                    {"Mods with Missing Package ID": mod_list}, add_group_headers=True
                )
        except Exception as e:
            logger.error(f"Error populating table from metadata: {e}")

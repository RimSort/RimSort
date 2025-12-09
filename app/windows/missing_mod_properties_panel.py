from typing import Any

from loguru import logger

from app.controllers.settings_controller import SettingsController
from app.windows.base_mods_panel import BaseModsPanel


class MissingModPropertiesPanel(BaseModsPanel):
    """
    A unified panel for displaying mods with missing properties.

    This panel displays mods that lack either a valid Package ID (in About.xml) or a valid Publish Field ID (Steam Workshop ID).
    Users can view detailed information for each mod and access Steam Workshop links, if available

    Attributes:
        missing_packageid_mods (list[str]): List of UUIDs for mods with missing Package ID.
        missing_publishfieldid_mods (list[str]): List of UUIDs for mods with missing Publish Field ID.
        settings_controller (SettingsController): Controller for application settings.
        metadata_manager: MetadataManager instance from base class for accessing mod data.
    """

    def __init__(
        self,
        missing_packageid_mods: list[str],
        missing_publishfieldid_mods: list[str],
        settings_controller: SettingsController,
    ) -> None:
        """
        Initialize the MissingModPropertiesPanel with mods data.

        Args:
            missing_packageid_mods: List of UUIDs for mods with missing Package ID.
            missing_publishfieldid_mods: List of UUIDs for mods with missing Publish Field ID.
            settings_controller: Controller for managing application settings.
        """
        logger.debug("Initializing MissingModPropertiesPanel")
        self.missing_packageid_mods = missing_packageid_mods
        self.missing_publishfieldid_mods = missing_publishfieldid_mods
        self.settings_controller = settings_controller

        super().__init__(
            object_name="missingModPropertiesPanel",
            window_title=self.tr("RimSort - Mods with Missing Properties"),
            title_text=self.tr("Mods with Missing Properties detected!"),
            details_text=self.tr(
                "The following mods are missing important properties that may cause issues:\n\n"
                "• Missing Package ID: Mods without a valid Package ID in About.xml may have dependency and compatibility issues.\n"
                "• Missing Publish Field ID: Workshop mods without a Publish Field ID may not support redownloads and update checking.\n\n"
                "Please contact the mod authors to add these properties to their mods."
            ),
            additional_columns=self._get_standard_mod_columns(),
        )

        button_configs = self._get_base_button_configs()
        self._extend_button_configs_with_steam_actions(button_configs)
        self._setup_buttons_from_config(button_configs)

        # Populate the table with missing properties mod data
        self._populate_from_metadata()

        # Configure table settings
        self._setup_table_configuration(sorting_enabled=False)

        # TODO: let user configure window launch state and size from settings controller
        self.showNormal()

    def _populate_from_metadata(self) -> None:
        """
        Populate the table with mods organized by missing property type.

        This method retrieves metadata for all mods with missing properties
        and organizes them into two categories (Missing Package ID and Missing
        Publish Field ID). The resulting table displays mods grouped by category,
        with group headers for clear visual organization.

        Metadata lookup failures are logged but do not interrupt the population
        process, ensuring partial data is still displayed to the user.
        """
        try:
            # Initialize dictionary to store categorized mods
            # Structure: {category_name: [(uuid, metadata_dict), ...]}
            grouped_mods: dict[str, list[tuple[str, dict[str, Any]]]] = {}

            # Process mods by category, checking only non-empty UUID lists
            for category, uuids in [
                ("Mods with Missing Package ID", self.missing_packageid_mods),
                (
                    "Mods with Missing Publish Field ID",
                    self.missing_publishfieldid_mods,
                ),
            ]:
                # Skip empty categories to avoid creating empty groups in the table
                if uuids:
                    grouped_mods[category] = []
                    # Retrieve and pair each UUID with its corresponding metadata
                    for uuid in uuids:
                        metadata = self.metadata_manager.internal_local_metadata.get(
                            uuid
                        )
                        if metadata:
                            # Successfully found metadata for this UUID
                            grouped_mods[category].append((uuid, metadata))
                        else:
                            # Log warning if metadata is missing (data inconsistency)
                            logger.warning(f"Metadata not found for UUID: {uuid}")

            # Use base class method to populate the table with grouped mods
            # Group headers are enabled to visually separate the two categories
            if grouped_mods:
                self._populate_mods(grouped_mods, add_group_headers=True)
        except Exception as e:
            # Log errors but don't raise - allow graceful degradation
            logger.error(f"Error populating table from metadata: {e}")

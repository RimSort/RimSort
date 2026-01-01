from typing import Any

from loguru import logger

from app.utils.metadata import MetadataManager
from app.utils.mod_info import ModInfo
from app.utils.mod_utils import filter_eligible_mods_for_update
from app.windows.base_mods_panel import (
    BaseModsPanel,
    ButtonConfig,
    ButtonType,
    ColumnIndex,
    OperationMode,
)


class WorkshopModUpdaterPanel(BaseModsPanel):
    """
    A panel for updating Workshop mods that have newer versions available.

    This panel displays mods that can be updated, showing current and available versions,
    and provides options to update mods via SteamCMD or the Steam client. It helps users
    keep their mods up-to-date with the latest versions from the Workshop.
    """

    def __init__(self) -> None:
        """
        Initialize the WorkshopModUpdaterPanel.

        Sets up the panel with mods eligible for update and configures buttons
        for updating via SteamCMD or Steam client (if enabled).
        """
        logger.debug("Initializing WorkshopModUpdaterPanel")
        self.metadata_manager = MetadataManager.instance()
        self.eligible_metadata: list[tuple[str, dict[str, Any]]] = []

        super().__init__(
            object_name="updateModsPanel",
            window_title=self.tr("RimSort - Updates found for Workshop mods"),
            title_text=self.tr("There are updates available for Workshop mods!"),
            details_text=self.tr(
                "\nThe following table displays Workshop mods available for update from Steam."
            ),
            additional_columns=self._get_standard_mod_columns(),
        )

        button_configs = [
            ButtonConfig(
                button_type=ButtonType.CUSTOM,
                text=self.tr("Update Mods with SteamCMD"),
                custom_callback=self._create_update_callback(
                    ColumnIndex.PUBLISHED_FILE_ID.value,
                    OperationMode.STEAMCMD,
                ),
            ),
        ]

        # Check if Steam client integration is enabled
        steam_client_integration_enabled = self._get_steam_client_integration_enabled()
        # Only add Steam client download button if Steam client integration is enabled
        if steam_client_integration_enabled:
            button_configs.append(
                ButtonConfig(
                    button_type=ButtonType.CUSTOM,
                    text=self.tr("Update Mods with Steam"),
                    custom_callback=self._create_update_callback(
                        ColumnIndex.PUBLISHED_FILE_ID.value,
                        OperationMode.STEAM,
                        "resubscribe",
                    ),
                )
            )

        # Set up buttons based on configurations
        self._setup_buttons_from_config(button_configs)

        # Populate the table with mods that have updates available
        self._populate_from_metadata()

        # Enable table sorting
        self._reconfigure_table_sorting(sorting_enabled=True)

    def _filter_eligible_mods(self) -> list[tuple[str, dict[str, Any]]]:
        """
        Filter mods that are eligible for update.

        Returns:
            List of (uuid, metadata) tuples for mods eligible for update.
        """
        eligible_mods = filter_eligible_mods_for_update(
            self.metadata_manager.internal_local_metadata
        )
        # Return tuples of (uuid, metadata) by looking up UUIDs from internal_local_metadata
        return [
            (uuid, metadata)
            for uuid, metadata in self.metadata_manager.internal_local_metadata.items()
            if metadata in eligible_mods
        ]

    def _populate_from_metadata(self) -> None:
        """
        Populate the table with mods that have available updates.
        """
        try:
            logger.debug(
                "Starting to populate table with mods that have updates available"
            )

            # Clear existing table data before populating since it shows duplicate rows if not cleared
            self._clear_table_model()

            self.eligible_metadata = self._filter_eligible_mods()
            logger.debug(
                f"Found {len(self.eligible_metadata)} eligible mods for update"
            )

            if not self.eligible_metadata:
                logger.info("No mods with updates available")
                return

            # Add each eligible mod as a row in the table
            for uuid, metadata in self.eligible_metadata:
                mod_info = ModInfo.from_metadata(uuid, metadata)
                self._add_mod_row(mod_info)
        except Exception as e:
            logger.error(f"Error populating table from metadata: {e}")

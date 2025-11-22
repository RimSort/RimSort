from functools import partial
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
        """
        logger.debug("Initializing WorkshopModUpdaterPanel")
        self.metadata_manager = MetadataManager.instance()

        super().__init__(
            object_name="updateModsPanel",
            window_title=self.tr("RimSort - Updates found for Workshop mods"),
            title_text=self.tr("There updates available for Workshop mods!"),
            details_text=self.tr(
                "\nThe following table displays Workshop mods available for update from Steam."
            ),
            additional_columns=self._get_standard_mod_columns(),
        )

        button_configs = [
            ButtonConfig(
                button_type=ButtonType.CUSTOM,
                text=self.tr("Update with SteamCMD"),
                custom_callback=partial(
                    self._update_mods_from_table,
                    pfid_column=ColumnIndex.PUBLISHED_FILE_ID.value,
                    mode="SteamCMD",
                ),
            ),
        ]

        steam_client_integration_enabled = self._get_steam_client_integration_enabled()
        if steam_client_integration_enabled:
            button_configs.append(
                ButtonConfig(
                    button_type=ButtonType.CUSTOM,
                    text=self.tr("Update with Steam client"),
                    custom_callback=partial(
                        self._update_mods_from_table,
                        pfid_column=ColumnIndex.PUBLISHED_FILE_ID.value,
                        mode="Steam",
                    ),
                )
            )
        self._setup_buttons_from_config(button_configs)

        # Populate the table with mods that have updates available
        self._populate_from_metadata()

        # Configure table settings
        self._setup_table_configuration(sorting_enabled=True)

        # TODO: let user configure window launch state and size from settings controller
        self.showNormal()

    def _filter_eligible_mods(self) -> list[dict[str, Any]]:
        """
        Filter mods that are eligible for update.

        Returns:
            List of metadata dictionaries for mods eligible for update.
        """
        return filter_eligible_mods_for_update(
            self.metadata_manager.internal_local_metadata
        )

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

            eligible_metadata = self._filter_eligible_mods()
            logger.debug(f"Found {len(eligible_metadata)} eligible mods for update")

            for metadata in eligible_metadata:
                self._add_update_mod_row(metadata)
        except Exception as e:
            logger.error(f"Error populating table from metadata: {e}")

    def _add_update_mod_row(self, metadata: dict[str, Any]) -> None:
        """
        Add a mod row to the table.

        Args:
            metadata: Metadata dictionary for the mod.
        """
        # Get UUID for the mod
        uuid = None
        path = metadata.get("path")
        if isinstance(path, str):
            uuid = self.metadata_manager.mod_metadata_dir_mapper.get(path)

        # Create ModInfo from metadata
        mod_info = ModInfo.from_metadata(uuid, metadata)

        # Use the base class method to add the mod row
        self._add_mod_row(mod_info)

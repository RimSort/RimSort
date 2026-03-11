from typing import Any, Iterable

from loguru import logger
from PySide6.QtWidgets import QMessageBox

from app.controllers.settings_controller import SettingsController
from app.utils.constants import DEFAULT_MISSING_PACKAGEID
from app.utils.event_bus import EventBus
from app.utils.ignore_manager import IgnoreManager
from app.utils.mod_info import ModInfo
from app.windows.base_mods_panel import BaseModsPanel, ButtonConfig, ButtonType


class MissingModPropertiesPanel(BaseModsPanel):
    """
    A unified panel for displaying mods with missing properties.

    This panel displays mods that lack either a valid Package ID (in About.xml)
    or a valid Publish Field ID (Steam Workshop ID). Users can view detailed
    information for each mod and add them to the ignore list.

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

        # Build button configurations
        button_configs = self._get_base_button_configs()
        self._extend_button_configs_with_steam_actions(button_configs)

        # Add delete button
        button_configs.append(
            self._create_delete_button_config(
                menu_title=self.tr("Delete Mods"),
                enable_delete_and_unsubscribe=False,
            )
        )

        # Add button to add selected mods to ignore list
        button_configs.append(
            ButtonConfig(
                button_type=ButtonType.CUSTOM,
                text=self.tr("Add to Ignore List"),
                custom_callback=self._add_to_ignore_list,
            )
        )

        self._setup_buttons_from_config(button_configs)

        # Populate the table with missing properties mod data
        self._populate_from_metadata()
        # Sorting is disabled by default in _setup_table_and_model

        # TODO: let user configure window launch state and size from settings controller
        self.showNormal()

    def _add_to_ignore_list(self) -> None:
        """
        Add selected mods to the ignore list.

        Allows users to ignore mods with missing properties so they won't
        trigger warnings on future refresh operations.
        """
        # Get selected mod indices
        selected_indices = self._get_selected_row_indices()

        if not selected_indices:
            self._show_message(
                "No Selection",
                "Please select mods to add to the ignore list.",
                "information",
            )
            return

        try:
            if self._process_ignore_list_addition(selected_indices):
                self.close()
                # Emit event to check and warn about missing mod properties after closing the panel
                EventBus().do_check_missing_mod_properties.emit()
        except Exception as e:
            logger.error(f"Error adding mods to ignore list: {e}")
            self._show_message(
                "Error",
                f"Error adding mods to ignore list: {str(e)}",
                "critical",
            )

    def _process_ignore_list_addition(self, selected_indices: Iterable[int]) -> bool:
        """
        Process adding selected mods to ignore list.

        Args:
            selected_indices: Indices of selected rows

        Returns:
            True if addition was successful, False otherwise
        """
        # Extract package IDs and categorize by validity
        packageids_to_add, skipped_mods = self._extract_and_validate_packageids(
            selected_indices
        )

        if not packageids_to_add:
            self._show_no_valid_packageids_warning(skipped_mods)
            return False

        # Add mods to ignore list
        if not IgnoreManager.add_ignored_mods(packageids_to_add):
            logger.error("Failed to save changes to ignore list file")
            self._show_message(
                "Error",
                "Failed to add mods to ignore list.",
                "critical",
            )
            return False

        mod_count = len(packageids_to_add)
        logger.info(f"Added {mod_count} mod(s) to ignore list")

        # Show success message
        # Parent will re-check and reload panel with fresh ignore.json data
        self._show_message(
            "Success",
            "Mods added to ignore list. Panel will refresh.",
            "information",
        )
        return True

    def _get_valid_mod_metadata(self, uuid: str) -> ModInfo | None:
        """
        Get validated mod info from UUID.

        Args:
            uuid: The UUID to lookup

        Returns:
            ModInfo instance if valid, None otherwise
        """
        mod_metadata = self.metadata_manager.internal_local_metadata.get(uuid)
        if not mod_metadata:
            return None

        try:
            return ModInfo.from_metadata(uuid, mod_metadata)
        except ValueError as e:
            logger.warning(f"Failed to extract mod info for UUID {uuid}: {e}")
            return None

    def _extract_and_validate_packageids(
        self, row_indices: Iterable[int]
    ) -> tuple[list[str], list[str]]:
        """
        Extract and validate package IDs from selected rows.

        Separates valid package IDs from mods with missing/placeholder IDs.

        Args:
            row_indices: Iterable of row indices to process

        Returns:
            Tuple of (valid_packageids, skipped_mod_names)
        """
        valid_packageids = []
        skipped_mods = []

        for row in row_indices:
            uuid = self._get_uuid_from_row(row)
            if not uuid:
                continue

            mod_info = self._get_valid_mod_metadata(uuid)
            if not mod_info:
                continue

            packageid = mod_info.packageid

            # Validate package ID
            if packageid and packageid != DEFAULT_MISSING_PACKAGEID:
                valid_packageids.append(packageid)
            elif packageid == DEFAULT_MISSING_PACKAGEID:
                # Collect for warning
                skipped_mods.append(mod_info.name)

        return valid_packageids, skipped_mods

    def _show_no_valid_packageids_warning(self, skipped_mods: list[str]) -> None:
        """
        Show warning when no valid package IDs can be added.

        Args:
            skipped_mods: List of mod names that were skipped
        """
        if skipped_mods:
            skipped_list = "\n".join([f"• {m}" for m in skipped_mods])
            message = (
                "Cannot add mods with missing Package IDs to the ignore list.\n"
                "These mods need valid Package IDs first:\n" + skipped_list
            )
            self._show_message("Cannot Add", message, "warning")
        else:
            self._show_message(
                "Error",
                "Could not extract package IDs from selected mods.",
                "warning",
            )

    def _show_message(
        self, title: str, message: str, message_type: str = "information"
    ) -> None:
        """
        Show a message dialog with configurable type.

        Args:
            title: Dialog title
            message: Message to display
            message_type: Type of message ('information', 'warning', 'critical')
        """
        translated_title = self.tr(title)
        translated_message = self.tr(message)

        if message_type == "warning":
            QMessageBox.warning(
                self,
                translated_title,
                translated_message,
                QMessageBox.StandardButton.Ok,
            )
        elif message_type == "critical":
            QMessageBox.critical(
                self,
                translated_title,
                translated_message,
                QMessageBox.StandardButton.Ok,
            )
        else:
            QMessageBox.information(
                self,
                translated_title,
                translated_message,
                QMessageBox.StandardButton.Ok,
            )

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
            # Build grouped mods dict efficiently
            grouped_mods = self._build_grouped_mods()

            # Use base class method to populate the table with grouped mods
            if grouped_mods:
                self._populate_mods(grouped_mods, add_group_headers=True)
        except Exception as e:
            # Log errors but don't raise - allow graceful degradation
            logger.error(f"Error populating table from metadata: {e}")

    def _build_grouped_mods(
        self,
    ) -> dict[str, list[tuple[str, dict[str, Any]]]]:
        """
        Build dictionary of grouped mods from UUID lists.

        Returns:
            Dictionary mapping category names to list of (uuid, metadata) tuples
        """
        grouped_mods: dict[str, list[tuple[str, dict[str, Any]]]] = {}

        categories = [
            ("Mods with Missing Package ID", self.missing_packageid_mods),
            ("Mods with Missing Publish Field ID", self.missing_publishfieldid_mods),
        ]

        for category_name, uuids in categories:
            if not uuids:
                continue

            category_mods: list[tuple[str, dict[str, Any]]] = []
            for uuid in uuids:
                mod_metadata = self.metadata_manager.internal_local_metadata.get(uuid)
                if mod_metadata:
                    category_mods.append((uuid, mod_metadata))
                else:
                    logger.warning(f"Metadata not found for UUID: {uuid}")

            if category_mods:
                grouped_mods[category_name] = category_mods

        return grouped_mods

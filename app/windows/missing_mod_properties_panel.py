from typing import Any, Iterable

from loguru import logger
from PySide6.QtWidgets import QMessageBox

from app.controllers.metadata_controller import MetadataController
from app.models.metadata.metadata_structure import ListedMod
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
        missing_packageid_mods (list[str]): Mod path keys with missing Package ID.
        missing_publishfieldid_mods (list[str]): Mod path keys with missing Publish Field ID.
        metadata_controller: Metadata controller instance from base class for accessing mod data.
    """

    def __init__(
        self,
        missing_packageid_mods: list[str],
        missing_publishfieldid_mods: list[str],
        metadata_controller: MetadataController,
    ) -> None:
        """
        Initialize the MissingModPropertiesPanel.

        Args:
            missing_packageid_mods: Mod path keys with missing Package ID.
            missing_publishfieldid_mods: Mod path keys with missing Publish Field ID.
        """
        logger.debug("Initializing MissingModPropertiesPanel")
        self.missing_packageid_mods = missing_packageid_mods
        self.missing_publishfieldid_mods = missing_publishfieldid_mods

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
            metadata_controller=metadata_controller,
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

    def _get_valid_mod_metadata(self, key: str) -> ModInfo | None:
        """
        Get validated mod info from path key.

        Args:
            key: The mod path key to lookup

        Returns:
            ModInfo instance if valid, None otherwise
        """
        mod_metadata = self.metadata_controller.mods_metadata.get(key)
        if not mod_metadata:
            return None

        try:
            mod_info = ModInfo.from_listed_mod(mod_metadata)
            mod_info.key = key
            return mod_info
        except ValueError as e:
            logger.warning(f"Failed to extract mod info for key {key}: {e}")
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
            key = self._get_key_from_row(row)
            if not key:
                continue

            mod_info = self._get_valid_mod_metadata(key)
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
            skipped_list = "<br>".join([f"• {m}" for m in skipped_mods])
            message = (
                "Cannot add mods with missing Package IDs to the ignore list.<br>"
                "These mods need valid Package IDs first:<br>" + skipped_list
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
    ) -> dict[str, list[tuple[str, dict[str, Any] | ListedMod]]]:
        """
        Build dictionary of grouped mods from path key lists.

        Returns:
            Dictionary mapping category names to list of (path_key, metadata) tuples
        """
        grouped_mods: dict[str, list[tuple[str, dict[str, Any] | ListedMod]]] = {}

        categories = [
            ("Mods with Missing Package ID", self.missing_packageid_mods),
            ("Mods with Missing Publish Field ID", self.missing_publishfieldid_mods),
        ]

        for category_name, path_keys in categories:
            if not path_keys:
                continue

            category_mods: list[tuple[str, dict[str, Any] | ListedMod]] = []
            for path_key in path_keys:
                mod_metadata = self.metadata_controller.mods_metadata.get(path_key)
                if mod_metadata:
                    category_mods.append((path_key, mod_metadata))
                else:
                    logger.warning(f"Metadata not found for path: {path_key}")

            if category_mods:
                grouped_mods[category_name] = category_mods

        return grouped_mods

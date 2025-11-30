from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from typing import Any, Generator, Optional

from loguru import logger
from PySide6.QtGui import QStandardItem
from PySide6.QtWidgets import QCheckBox

from app.utils.metadata import MetadataManager
from app.utils.mod_info import ModInfo
from app.views import dialogue
from app.windows.base_mods_panel import (
    BaseModsPanel,
    ButtonConfig,
    ButtonType,
    ColumnIndex,
    MenuItem,
)


class InstallationStatus(Enum):
    """Enumeration for installation status."""

    INSTALLED = "Installed"
    NOT_INSTALLED = "Not Installed"


@dataclass
class ReplacementInfo:
    """
    Represents information about a replacement mod.

    Attributes:
        name: Name of the replacement mod.
        author: Author of the replacement mod.
        packageid: Package ID of the replacement mod.
        pfid: Published file ID of the replacement mod.
        supportedversions: Supported versions of the replacement mod.
    """

    name: str
    author: str
    packageid: str
    pfid: str
    supportedversions: Any
    source: str


@dataclass
class ModGroupItem:
    """
    Represents a mod item in a group, containing metadata and identifiers.

    Attributes:
        mod_id: Unique identifier for the mod.
        metadata: Dictionary containing mod metadata.
        replacement: Optional replacement mod information.
    """

    mod_id: str
    metadata: dict[str, Any]
    replacement: Optional[ReplacementInfo] = None


class UseThisInsteadPanel(BaseModsPanel):
    """
    Panel for displaying Workshop mods with suggested replacements from the "Use This Instead" database.
    Groups mods by replacement mod and provides actions for subscription, unsubscription, and deletion.
    """

    def __init__(self, mod_metadata: dict[str, Any]) -> None:
        """
        Initialize the UseThisInsteadPanel with mod metadata.

        Args:
            mod_metadata: Dictionary of mod metadata keyed by mod identifier.
        """
        logger.debug("Initializing UseThisInsteadPanel")
        self.mod_metadata = mod_metadata

        super().__init__(
            object_name="useThisInsteadModsPanel",
            window_title=self.tr("RimSort - Replacements found for Workshop mods"),
            title_text=self.tr("There are replacements available for Workshop mods!"),
            details_text=self.tr(
                "The following table displays Workshop mods with suggested replacements "
                'according to the "Use This Instead" database, grouped by replacement mod.'
            ),
            additional_columns=self._get_standard_mod_columns(),
        )

        steam_client_integration_enabled = self._get_steam_client_integration_enabled()

        button_configs = [
            ButtonConfig(
                button_type=ButtonType.SELECT,
                text=self.tr("Select"),
                menu_items=[
                    MenuItem(
                        text=self.tr("Select all Originals"),
                        callback=self._select_all_originals,
                    ),
                    MenuItem(
                        text=self.tr("Select all Replacements"),
                        callback=self._select_all_replacements,
                    ),
                ],
            ),
        ]
        button_configs.extend(self._get_base_button_configs())

        if steam_client_integration_enabled:
            button_configs.extend(
                [
                    ButtonConfig(
                        button_type=ButtonType.SUBSCRIBE,
                        pfid_column=ColumnIndex.PUBLISHED_FILE_ID.value,
                        completion_callback=self._on_subscribe_completed,
                    ),
                    ButtonConfig(
                        button_type=ButtonType.UNSUBSCRIBE,
                        pfid_column=ColumnIndex.PUBLISHED_FILE_ID.value,
                        completion_callback=self._on_unsubscribe_completed,
                    ),
                ]
            )

        button_configs.append(
            self._create_delete_button_config(
                self.tr("Delete Selected Mods"),
                enable_delete_and_unsubscribe=steam_client_integration_enabled,
            )
        )
        self._setup_buttons_from_config(button_configs)

        # Initialize row index trackers for bulk selection operations
        self._original_rows: set[int] = set()
        self._replacement_rows: set[int] = set()

    def show_if_has_alternatives(self) -> bool:
        """
        Populate the panel and show it if alternatives exist.

        Returns:
            True if alternatives were found and panel was shown, False otherwise.
        """
        self._populate_from_metadata()
        self._setup_table_configuration(sorting_enabled=False)

        if self.editor_model.rowCount() > 0:
            self.showNormal()
            return True
        return False

    def _on_mod_action_completed(self, action: str, count: int) -> None:
        """Handle successful mod action completion."""
        dialogue.show_information(
            self.tr("Use This Instead"),
            self.tr(f"Successfully {action}d {count} mods"),
        )

    def _on_subscribe_completed(self) -> None:
        """Handle subscribe completion."""
        count = self._get_selected_count()
        self._on_mod_action_completed("subscribe", count)

    def _on_unsubscribe_completed(self) -> None:
        """Handle unsubscribe completion."""
        count = self._get_selected_count()
        self._on_mod_action_completed("unsubscribe", count)

    def _get_selected_count(self) -> int:
        """Get the count of selected mods."""
        count = 0
        for row in range(self.editor_model.rowCount()):
            if self._row_is_checked(row):
                count += 1
        return count

    def _populate_from_metadata(self) -> None:
        """
        Populate the table with mod data grouped by replacement mod.

        This method computes mod groups based on replacement suggestions,
        and populates the table with headers, original mods, and replacement mods.
        """
        try:
            # Clear the table before populating
            self._clear_table_model()

            # Filter and group mods
            groups = self._filter_and_group_mods()

            if not groups:
                logger.debug("No groups found to populate the use this instead panel.")
                return

            # Add groups to table
            self._add_groups_to_table(groups)

            # Track row indices for selection during population to avoid double iteration
            self._track_row_indices_during_population(groups)
        except Exception as e:
            logger.error(f"Error populating metadata: {e}")
            # Graceful degradation: clear table if error occurs
            self._clear_table_model()

    def _track_row_indices_during_population(
        self, groups: dict[str, list[ModGroupItem]]
    ) -> None:
        """
        Track row indices for originals and replacements during population.

        Args:
            groups: Dictionary of groups by package ID.
        """
        current_row = 0
        for package_id, originals in groups.items():
            # Skip header row
            current_row += 1
            # Add original rows to tracking
            for _ in originals:
                self._original_rows.add(current_row)
                current_row += 1
            # Add replacement row to tracking
            self._replacement_rows.add(current_row)
            current_row += 1

    def _prepare_formatted_groups(
        self, groups: dict[str, list[ModGroupItem]]
    ) -> dict[str, list[tuple[str | None, dict[str, Any]]]]:
        """
        Prepare formatted groups for population.

        Args:
            groups: Dictionary of groups by package ID.

        Returns:
            Formatted groups dictionary.
        """
        formatted_groups: dict[str, list[tuple[str | None, dict[str, Any]]]] = {}
        for package_id, originals in groups.items():
            mod_list = self._prepare_mod_list_for_group(originals)
            formatted_groups[package_id] = mod_list
        return formatted_groups

    def _prepare_mod_list_for_group(
        self, originals: list[ModGroupItem]
    ) -> list[tuple[str | None, dict[str, Any]]]:
        """
        Prepare mod list for a group, including originals and replacement.

        Args:
            originals: List of original mod group items.

        Returns:
            List of (uuid, metadata) tuples.
        """
        mod_list = []
        for mod_item in originals:
            metadata_copy = self._create_original_metadata(mod_item)
            path = mod_item.metadata.get("path")
            uuid = self._extract_uuid_from_path(path) if isinstance(path, str) else None
            mod_list.append((uuid, metadata_copy))

        # Add replacement mod
        mod_replacement = originals[0].replacement if originals else None
        if mod_replacement is not None:
            uuid, fake_metadata = self._create_replacement_metadata(mod_replacement)
            mod_list.append((uuid, fake_metadata))
        return mod_list

    def _create_original_metadata(self, mod_item: ModGroupItem) -> dict[str, Any]:
        """
        Create metadata for an original mod with type.

        Args:
            mod_item: The mod group item.

        Returns:
            Metadata dictionary with type.
        """
        metadata_copy = mod_item.metadata.copy()
        metadata_copy["type"] = "Original"
        return metadata_copy

    def _create_replacement_metadata(
        self, mod_replacement: ReplacementInfo
    ) -> tuple[str | None, dict[str, Any]]:
        """
        Create metadata for a replacement mod.

        Args:
            mod_replacement: The replacement mod information.

        Returns:
            Tuple of (uuid, metadata).
        """
        # Check if the replacement mod already exists locally
        exists_locally, uuid = self._check_replacement_exists_locally(
            mod_replacement.pfid
        )

        fake_metadata = self._build_replacement_metadata(
            mod_replacement, exists_locally, uuid
        )
        return uuid, fake_metadata

    def _check_replacement_exists_locally(self, pfid: str) -> tuple[bool, str | None]:
        """
        Check if replacement mod exists locally and get its UUID.

        Args:
            pfid: Published file ID.

        Returns:
            Tuple of (exists_locally, uuid).
        """
        exists_locally = any(
            mod.get("publishedfileid") == pfid
            for mod in self.metadata_manager.internal_local_metadata.values()
        )
        uuid = None
        if exists_locally:
            for (
                mod_uuid,
                mod_metadata,
            ) in self.metadata_manager.internal_local_metadata.items():
                if mod_metadata.get("publishedfileid") == pfid:
                    uuid = mod_uuid
                    break
        return exists_locally, uuid

    def _get_local_metadata_for_replacement(
        self, uuid: str | None
    ) -> dict[str, Any] | None:
        """
        Retrieve local metadata for a replacement mod if it exists.

        Args:
            uuid: UUID of the replacement mod.

        Returns:
            Local metadata dictionary or None if not found.
        """
        if uuid and uuid in self.metadata_manager.internal_local_metadata:
            return self.metadata_manager.internal_local_metadata[uuid]
        return None

    def _merge_local_and_external_metadata(
        self, external_metadata: dict[str, Any], local_metadata: dict[str, Any] | None
    ) -> dict[str, Any]:
        """
        Merge local and external metadata for a replacement mod.

        Args:
            external_metadata: Metadata from external source.
            local_metadata: Local metadata if available.

        Returns:
            Merged metadata dictionary.
        """
        if local_metadata:
            external_metadata.update(
                {
                    "supportedversions": local_metadata.get(
                        "supportedversions", external_metadata["supportedversions"]
                    ),
                    "path": local_metadata.get("path", ""),
                    "internal_time_touched": local_metadata.get(
                        "internal_time_touched"
                    ),
                    "external_time_updated": local_metadata.get(
                        "external_time_updated"
                    ),
                    "data_source": local_metadata.get("source"),
                }
            )
        return external_metadata

    def _create_base_replacement_metadata(
        self, mod_replacement: ReplacementInfo, exists_locally: bool
    ) -> dict[str, Any]:
        """
        Create base metadata dictionary for replacement mod.

        Args:
            mod_replacement: Replacement mod info.
            exists_locally: Whether it exists locally.

        Returns:
            Metadata dictionary.
        """
        return {
            "name": mod_replacement.name,
            "authors": mod_replacement.author,
            "packageid": mod_replacement.packageid,
            "publishedfileid": mod_replacement.pfid,
            "supportedversions": mod_replacement.supportedversions,
            "internal_time_touched": None,
            "external_time_updated": None,
            "data_source": mod_replacement.source,
            "path": None,
            "type": "Replacement",
            "installed_status": (
                self.tr("Installed") if exists_locally else self.tr("Not Installed")
            ),
        }

    def _build_replacement_metadata(
        self, mod_replacement: ReplacementInfo, exists_locally: bool, uuid: str | None
    ) -> dict[str, Any]:
        """
        Build metadata dictionary for replacement mod.

        Args:
            mod_replacement: Replacement mod info.
            exists_locally: Whether it exists locally.
            uuid: UUID if exists locally.

        Returns:
            Metadata dictionary.
        """
        fake_metadata = self._create_base_replacement_metadata(
            mod_replacement, exists_locally
        )
        local_metadata = self._get_local_metadata_for_replacement(uuid)
        return self._merge_local_and_external_metadata(fake_metadata, local_metadata)

    def _filter_and_group_mods(self) -> dict[str, list[ModGroupItem]]:
        """
        Filter mods that have alternatives and group them by package ID.

        Returns:
            Dictionary grouping mods by package ID.
        """
        # Pre-filter alternatives and compute groups
        alternatives = self._filter_alternatives()
        groups = self._group_mods_by_package_id(alternatives)
        return groups

    def _add_groups_to_table(self, groups: dict[str, list[ModGroupItem]]) -> None:
        """
        Add all groups to the table.

        Args:
            groups: Dictionary of groups by package ID.
        """
        for group_counter, package_id, originals, current_row in self._process_groups(
            groups
        ):
            self._add_group_to_table(group_counter, package_id, originals, current_row)

    def _process_groups(
        self, groups: dict[str, list[ModGroupItem]]
    ) -> Generator[tuple[int, str, list[ModGroupItem], int], None, None]:
        """
        Process and yield each group to the table.

        Args:
            groups: Dictionary of groups by package ID.
        """
        current_row = 0
        group_counter = 1
        for package_id, originals in groups.items():
            yield group_counter, package_id, originals, current_row
            current_row += 1 + len(originals) + 1  # header + originals + replacement
            group_counter += 1

    def _filter_alternatives(self) -> dict[str, Any]:
        """
        Filter mods that have alternatives.

        Returns:
            Dictionary of mods with their alternatives.
        """
        try:
            metadata_manager = MetadataManager.instance()
            alternatives: dict[str, Any] = {}
            for mod in self.mod_metadata:
                alt = metadata_manager.has_alternative_mod(mod)
                if alt is not None:
                    alternatives[mod] = alt
            return alternatives
        except Exception as e:
            logger.error(f"Error filtering alternatives: {e}")
            return {}

    def _group_mods_by_package_id(
        self, alternatives: dict[str, Any]
    ) -> dict[str, list[ModGroupItem]]:
        """
        Group mods by their replacement's package ID.

        Args:
            alternatives: Dictionary of mods with alternatives.

        Returns:
            Dictionary grouping mods by replacement's package ID.
        """
        groups = defaultdict(list)
        for mod, mod_orignal in self.mod_metadata.items():
            mod_replacement = alternatives.get(mod)
            if mod_replacement is None or mod_orignal is None:
                continue
            package_id: str = mod_replacement.packageid
            groups[package_id].append(ModGroupItem(mod, mod_orignal, mod_replacement))
        return groups

    def _add_group_to_table(
        self,
        group_counter: int,
        package_id: str,
        originals: list[ModGroupItem],
        current_row: int,
    ) -> None:
        """
        Add a complete group (header, originals, replacement) to the table.

        Args:
            group_counter: The group number.
            package_id: The package ID for the group.
            originals: List of original mods in the group.
            current_row: The starting row index.
        """
        # Add group header row
        self._add_group_header(group_counter, current_row)

        # Add all original mods in this group
        self._add_original_mods(originals, package_id, current_row + 1)

        # Add the replacement mod for this group
        self._add_replacement_mod(
            originals[0].replacement, package_id, current_row + 1 + len(originals)
        )

    def _add_group_header(self, group_number: int, current_row: int) -> None:
        """
        Add a group header row to the table.

        Args:
            group_number: The number of the group.
            current_row: The current row index.
        """
        self._add_group_header_row(self.tr("Group {0}").format(group_number))

    def _add_mod_to_group(
        self,
        mod_item: ModGroupItem,
        package_id: str,
        current_row: int,
        is_original: bool,
    ) -> None:
        """
        Add a mod to a group in the table.

        Args:
            mod_item: The mod group item to add.
            package_id: The package ID for the group.
            current_row: The row index for adding the mod.
            is_original: Whether this is an original mod or a replacement.
        """
        try:
            # Use modified metadata for originals to include type
            if is_original:
                metadata = self._create_original_metadata(mod_item)
            else:
                metadata = mod_item.metadata

            # Retrieve UUID for the mod from the directory mapper
            path = metadata.get("path")
            uuid = (
                self.metadata_manager.mod_metadata_dir_mapper.get(path)
                if isinstance(path, str)
                else None
            )

            # Create ModInfo from metadata
            mod_info = self._extract_mod_info_from_metadata(uuid, metadata)

            mod_info.name = mod_info.name

            # Use base class method to add the mod row
            self._add_mod_row(mod_info)
            if is_original:
                self._original_rows.add(current_row)
        except Exception as e:
            logger.error(f"Error accessing metadata for mod in group {package_id}: {e}")

    def _check_and_get_replacement_local_metadata(
        self, pfid: str
    ) -> tuple[bool, str | None, dict[str, Any] | None]:
        """
        Check if replacement mod exists locally by published file ID and retrieve local metadata.

        Args:
            pfid: Published file ID for replacement mod.

        Returns:
            tuple:
                - exists_locally (bool): True if exists locally.
                - uuid (str | None): UUID if exists locally.
                - local_metadata (dict | None): Local metadata dict or None.
        """
        exists_locally = False
        uuid = None
        local_metadata = None
        try:
            exists_locally = any(
                mod.get("publishedfileid") == pfid
                for mod in self.metadata_manager.internal_local_metadata.values()
            )
            if exists_locally:
                for (
                    mod_uuid,
                    mod_metadata,
                ) in self.metadata_manager.internal_local_metadata.items():
                    if mod_metadata.get("publishedfileid") == pfid:
                        uuid = mod_uuid
                        local_metadata = mod_metadata
                        break
        except Exception as e:
            logger.error(
                f"Error checking local replacement metadata for pfid {pfid}: {e}"
            )
        return exists_locally, uuid, local_metadata

    def _create_replacement_mod_info(self, mod_replacement: Any) -> "ModInfo":
        """
        Create ModInfo for a replacement mod.

        Args:
            mod_replacement: The replacement mod information.

        Returns:
            ModInfo object for the replacement mod.
        """
        exists_locally, uuid, local_metadata = (
            self._check_and_get_replacement_local_metadata(mod_replacement.pfid)
        )

        if exists_locally and uuid and local_metadata is not None:
            local_metadata_copy = dict(local_metadata)
            local_metadata_copy["type"] = "Replacement"
            local_metadata_copy["installed_status"] = self.tr("Installed")
            return ModInfo.from_metadata(uuid, local_metadata_copy)
        else:
            metadata = self._create_base_replacement_metadata(mod_replacement, False)
            return ModInfo.from_metadata(None, metadata)

    def _add_original_mods(
        self, originals: list[ModGroupItem], package_id: str, current_row: int
    ) -> None:
        """
        Add original mods to the table.

        Args:
            originals: List of original mod group items.
            package_id: The package ID for the group.
            current_row: The starting row index for adding mods.
        """
        for i, original in enumerate(originals):
            self._add_mod_to_group(
                original, package_id, current_row + i, is_original=True
            )

    def _add_replacement_mod(
        self, mod_replacement: Any, package_id: str, current_row: int
    ) -> None:
        """
        Add a replacement mod to the table.

        Args:
            mod_replacement: The replacement mod information.
            package_id: The package ID for the group.
            current_row: The row index for adding the mod.
        """
        # Create ModInfo for the replacement mod using consolidated check method
        mod_info = self._create_replacement_mod_info(mod_replacement)

        # Add the row to the table using base class method
        self._add_mod_row(mod_info)
        self._replacement_rows.add(current_row)

    def _clear_all_checkboxes(self) -> None:
        """Clear all checkboxes in the table."""
        for row in range(self.editor_model.rowCount()):
            widget = self.editor_table_view.indexWidget(
                self.editor_model.item(row, 0).index()
            )
            if isinstance(widget, QCheckBox):
                widget.setChecked(False)

    def _select_rows_by_indices(self, row_indices: set[int]) -> None:
        """
        Select rows by their indices using set operations for bulk selections.

        Args:
            row_indices: Set of row indices to select.
        """
        for row in range(self.editor_model.rowCount()):
            checkbox = self.editor_table_view.indexWidget(
                self.editor_model.item(row, 0).index()
            )
            if isinstance(checkbox, QCheckBox):
                checkbox.setChecked(row in row_indices)

    def _select_all_originals(self) -> None:
        """Select all original mods in the table."""
        self._select_rows_by_indices(self._original_rows)

    def _select_all_replacements(self) -> None:
        """Select all replacement mods in the table."""
        self._select_rows_by_indices(self._replacement_rows)

    def _add_mod_row(
        self,
        mod_info: "ModInfo",
        additional_items: list[QStandardItem] | None = None,
        default_checkbox_state: bool = False,
    ) -> None:
        """
        Override to set checkbox text based on mod type.

        Args:
            mod_info: ModInfo object containing mod data
            additional_items: Optional additional QStandardItem objects for extra columns
            default_checkbox_state: Default state for the checkbox
        """
        super()._add_mod_row(mod_info, additional_items, default_checkbox_state)

        # Set checkbox text based on type
        row = self.editor_model.rowCount() - 1  # Last added row
        checkbox = self.editor_table_view.indexWidget(
            self.editor_model.item(row, 0).index()
        )
        if isinstance(checkbox, QCheckBox):
            if mod_info.type == "Original":
                checkbox.setText(self.tr("Original"))
            elif mod_info.type == "Replacement":
                checkbox.setText(
                    self.tr("Replacement [{0}]").format(mod_info.installed_status)
                )

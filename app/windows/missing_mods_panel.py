from functools import partial
from typing import Any

from loguru import logger
from PySide6.QtGui import QStandardItem
from PySide6.QtWidgets import (
    QComboBox,
)

from app.utils.constants import RIMWORLD_DLC_METADATA
from app.windows.base_mods_panel import (
    BaseModsPanel,
    ButtonConfig,
    ButtonType,
)


class MissingModsPrompt(BaseModsPanel):
    """
    A panel for prompting users to download missing mods from their active mods list.

    This panel queries the SteamDB database to find available variants for missing package IDs,
    allowing users to select and download preferred mod variants. It handles multiple variants
    per package ID and provides options for downloading via SteamCMD or the Steam client.
    """

    def __init__(
        self,
        packageids: list[str],
    ) -> None:
        """
        Initialize the MissingModsPrompt.

        Args:
            packageids: List of package IDs for missing mods.
        """
        logger.debug("Initializing MissingModsPrompt")

        super().__init__(
            object_name="missingModsPanel",
            window_title=self.tr("RimSort - Missing mods found"),
            title_text=self.tr("There are mods missing from the active mods list!"),
            details_text=self.tr(
                "\nUser-configured SteamDB database was queried. The following table displays mods available for download from Steam. "
                + '\n\nRimworld mods on Steam Workshop that share a packageId are "variants". Please keep this in mind before downloading. '
                + "\n\nPlease select your preferred mod variant in the table below. You can also open each variant in Steam/Web browser to verify."
            ),
            additional_columns=[
                self.tr(self.COL_MOD_NAME),
                self.tr(self.COL_PACKAGE_ID),
                self.tr(self.COL_SUPPORTED_VERSIONS),
                self.tr("# Variants"),
                self.tr(self.COL_PUBLISHED_FILE_ID),
                self.tr(self.COL_WORKSHOP_PAGE),
            ],
        )

        self.data_by_variants: dict[str, dict[str, Any]] = {}
        self.DEPENDENCY_TAG = "_-_DEPENDENCY_-_"
        self.DEFAULT_NOT_FOUND = "Not found in steam database"
        # Validate and filter package IDs
        self.packageids = self._validate_packageids(packageids)
        self.packageid_to_row: dict[str, int] = {}

        # Check if Steam client integration is enabled
        steam_client_integration_enabled = self._get_steam_client_integration_enabled()

        # Set up buttons using standardized configuration
        button_configs = [
            ButtonConfig(
                button_type=ButtonType.REFRESH,
                custom_callback=self._refresh_metadata_and_panel,
            ),
            ButtonConfig(
                button_type=ButtonType.CUSTOM,
                text=self.tr("Download with SteamCMD"),
                custom_callback=partial(
                    self._update_mods_from_table,
                    pfid_column=5,
                    mode="SteamCMD",
                ),
            ),
        ]

        # Only add Steam client download button if Steam client integration is enabled
        if steam_client_integration_enabled:
            button_configs.append(
                ButtonConfig(
                    button_type=ButtonType.CUSTOM,
                    text=self.tr("Download with Steam client"),
                    custom_callback=partial(
                        self._update_mods_from_table,
                        pfid_column=5,
                        mode="Steam",
                    ),
                )
            )
        self._setup_buttons_from_config(button_configs)

        # Configure table settings
        self._setup_table_configuration(sorting_enabled=True)

        # TODO: let user configure window launch state and size from settings controller
        self.showNormal()

    def _validate_packageids(self, packageids: list[str]) -> list[str]:
        """
        Validate and filter package IDs to prevent empty or invalid IDs.

        Args:
            packageids: List of package IDs to validate.

        Returns:
            List of validated and filtered package IDs.
        """
        validated = []
        for pid in packageids:
            if pid and isinstance(pid, str):
                stripped = pid.strip()
                if stripped:
                    validated.append(stripped)
        return validated

    def _missing_mods_add_row(
        self,
        name: str,
        packageid: str,
        game_versions: list[str],
        mod_variants: str,
        published_file_id: str,
    ) -> None:
        """
        Add a row for a missing mod, handling variants.

        Args:
            name: Mod name
            packageid: Package ID
            game_versions: List of supported game versions
            mod_variants: Number of variants as string
            published_file_id: Published file ID
        """
        # Check if a row with the given packageid already exists
        existing_row = self._find_existing_row_by_packageid(packageid)
        if existing_row is not None:
            # If an existing row is found, add the new published_file_id
            self._add_variant_to_existing_row(existing_row, published_file_id)
            return  # Return here to exit function

        # If we're still here, we need to actually create a new row
        self._create_new_missing_mod_row(
            name, packageid, game_versions, mod_variants, published_file_id
        )

    def _filter_eligible_mods(self) -> list[str]:
        """
        Filter package IDs that are eligible for missing mod processing.

        Returns:
            List of package IDs that need to be processed.
        """
        return self.packageids

    def _build_variant_data_from_steam_metadata(self) -> dict[str, dict[str, Any]]:
        """
        Build variant data from Steam metadata, grouping by package ID.

        Returns:
            Dictionary mapping package IDs to their variant data.
        """
        if not hasattr(self, "_cached_steam_metadata"):
            self._cached_steam_metadata = self.metadata_manager.external_steam_metadata

        steam_metadata = self._cached_steam_metadata
        if steam_metadata and len(steam_metadata) > 500:
            logger.info(
                f"Processing large Steam metadata set with {len(steam_metadata)} items"
            )

        variants_by_packageid: dict[str, dict[str, Any]] = {}
        if steam_metadata:
            for published_file_id, metadata in steam_metadata.items():
                name = metadata.get(
                    "steamName", metadata.get("name", "Not found in steam database")
                )
                packageid = metadata.get("packageId", "").lower()
                game_versions = metadata.get(
                    "gameVersions", ["Not found in steam database"]
                )

                # Remove AppId dependencies from this dict. They cannot be subscribed like mods.
                dependencies = {
                    key: value
                    for key, value in metadata.get("dependencies", {}).items()
                    if key not in RIMWORLD_DLC_METADATA.keys()
                }

                # Populate variants_by_packageid dict
                if packageid in self.packageids:
                    variants = variants_by_packageid.setdefault(packageid, {})
                    variants[published_file_id] = {
                        "name": name,
                        "gameVersions": game_versions,
                        "dependencies": dependencies,
                    }
        return variants_by_packageid

    def _add_default_entries_for_missing_packageids(
        self, variants_by_packageid: dict[str, dict[str, Any]]
    ) -> None:
        """
        Add default entries for package IDs not found in Steam metadata.

        Args:
            variants_by_packageid: Dictionary of variants by package ID to update.
        """
        for packageid in self.packageids:
            if packageid not in variants_by_packageid:
                variants_by_packageid[packageid] = {
                    "": {
                        "name": self.DEFAULT_NOT_FOUND,
                        "gameVersions": self.DEFAULT_NOT_FOUND,
                    }
                }

    def _populate_table_from_variants(
        self, variants_by_packageid: dict[str, dict[str, Any]]
    ) -> None:
        """
        Populate the table with mod variants.

        Args:
            variants_by_packageid: Dictionary of variants grouped by package ID.
        """
        for packageid, variants in variants_by_packageid.items():
            for published_file_id, variant_data in variants.items():
                self._missing_mods_add_row(
                    name=variant_data["name"],
                    packageid=packageid,
                    game_versions=variant_data["gameVersions"],
                    mod_variants=str(len(variants.keys())),
                    published_file_id=published_file_id,
                )

    def _find_existing_row_by_packageid(self, packageid: str) -> int | None:
        """
        Find the row index for an existing packageid.

        Args:
            packageid: The package ID to search for.

        Returns:
            Row index if found, None otherwise.
        """
        return self.packageid_to_row.get(packageid)

    def _add_variant_to_existing_row(self, row: int, published_file_id: str) -> None:
        """
        Add a new variant to an existing row's combo box.

        Args:
            row: Row index to update.
            published_file_id: Published file ID to add to the combo box.
        """
        existing_item = self.editor_model.item(row, 5)
        if existing_item is None:
            logger.error(f"No item found at row {row}, column 5")
            return

        combo_box = self.editor_table_view.indexWidget(existing_item.index())
        if not isinstance(combo_box, QComboBox):
            logger.error(
                f"Expected QComboBox at row {row}, column 5, but found {type(combo_box)}"
            )
            return

        combo_box.addItem(published_file_id)

    def _create_new_missing_mod_row(
        self,
        name: str,
        packageid: str,
        game_versions: list[str],
        mod_variants: str,
        published_file_id: str,
    ) -> None:
        """
        Create a new row for a missing mod.

        Args:
            name: Mod name.
            packageid: Package ID.
            game_versions: List of supported game versions.
            mod_variants: Number of variants as string.
            published_file_id: Published file ID.
        """
        # Create items for the custom columns in this panel
        name_item = QStandardItem(name)
        packageid_item = QStandardItem(packageid)
        game_versions_item = QStandardItem(str(game_versions))
        variants_item = QStandardItem(mod_variants if published_file_id != "" else "0")
        published_file_id_combo_item = QStandardItem()  # PublishedFileId (combo box)
        workshop_item = QStandardItem()  # Workshop Page (button)

        items = [
            name_item,
            packageid_item,
            game_versions_item,
            variants_item,
            published_file_id_combo_item,
            workshop_item,
        ]
        self._add_row(items)
        self._setup_variant_combo_box(items, published_file_id)
        # Generate workshop button only if published_file_id exists
        if published_file_id:
            self._add_workshop_button_to_row(items, published_file_id, 5)
        # Track the row index for this packageid
        self.packageid_to_row[packageid] = self.editor_model.rowCount() - 1

    def _setup_variant_combo_box(
        self, items: list[QStandardItem], published_file_id: str
    ) -> None:
        """
        Set up the combo box for variant selection.

        Args:
            items: List of QStandardItem for the row.
            published_file_id: Initial published file ID for the combo box.
        """
        combo_box = QComboBox()
        combo_box.setEditable(True)
        combo_box.setObjectName("missing_mods_variant_cb")
        combo_box.addItem(published_file_id)
        # Connect the currentTextChanged signal
        combo_box.currentTextChanged.connect(self._update_mod_info)
        # Set the combo_box as the index widget
        self.editor_table_view.setIndexWidget(items[4].index(), combo_box)

    def _populate_from_metadata(self) -> None:
        """
        Populate the table with missing mod variants.
        """
        try:
            # Cache Steam metadata to avoid repeated access
            self._cached_steam_metadata = self.metadata_manager.external_steam_metadata
            if (
                self._cached_steam_metadata
                and len(self._cached_steam_metadata.keys()) > 0
            ):
                # Group mods by package ID from Steam metadata
                variants_by_packageid = self._build_variant_data_from_steam_metadata()

                # Add default entries for package IDs not found in Steam metadata
                self._add_default_entries_for_missing_packageids(variants_by_packageid)

                # Populate the table with all variants
                self._populate_table_from_variants(variants_by_packageid)

                # Update the instance variable for compatibility with existing methods
                self.data_by_variants = variants_by_packageid
        except Exception as e:
            logger.error(f"Error populating table from metadata: {e}")

    def _update_mod_info(self, published_file_id: str) -> None:
        """
        Update mod information when variant selection changes.

        Args:
            published_file_id: The selected published file ID.
        """
        combo_box = self.sender()
        if not isinstance(combo_box, QComboBox):
            raise ValueError(f"Sender is not a QComboBox!: {combo_box}")
        index = self.editor_table_view.indexAt(combo_box.pos())
        if index.isValid():
            row = index.row()
            packageid = self.editor_model.item(row, 1).text()
            variant_data = self.data_by_variants.get(packageid, {}).get(
                published_file_id, {}
            )
            self.editor_model.item(row, 0).setText(
                variant_data.get("name", self.DEFAULT_NOT_FOUND)
            )
            self.editor_model.item(row, 2).setText(
                str(variant_data.get("gameVersions", self.DEFAULT_NOT_FOUND))
            )

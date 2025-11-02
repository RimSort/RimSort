from datetime import datetime
from functools import partial
from typing import Dict, List

from loguru import logger
from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem
from PySide6.QtWidgets import QPushButton, QToolButton

from app.controllers.settings_controller import SettingsController
from app.utils.event_bus import EventBus
from app.utils.generic import platform_specific_open
from app.utils.metadata import MetadataManager, ModMetadata
from app.views.deletion_menu import ModDeletionMenu
from app.windows.base_mods_panel import BaseModsPanel


class DuplicateModsPanel(BaseModsPanel):
    """
    A panel used when duplicate mods are detected, allowing users to choose which version to keep.
    """

    def __init__(
        self,
        duplicate_mods: Dict[str, List[str]],
        settings_controller: SettingsController,
    ) -> None:
        """
        Initialize the DuplicateModsPanel with duplicate mods data.
        """
        logger.debug("Initializing DuplicateModsPanel")
        self.duplicate_mods = duplicate_mods
        self.settings_controller = settings_controller
        self.mm = MetadataManager.instance()

        super().__init__(
            object_name="duplicateModsPanel",
            window_title=self.tr("RimSort - Duplicate Mods Found"),
            title_text=self.tr("Duplicate mods detected!"),
            details_text=self.tr(
                "\nThe following table displays duplicate mods grouped by package ID. "
                "Select which versions to keep and choose an action."
            ),
            additional_columns=[
                self.tr("Mod Name"),
                self.tr("Author"),
                self.tr("PublishedFileId"),
                self.tr("Updated on Workshop"),
                self.tr("Path"),
                self.tr("Workshop Page"),
            ],
        )

        self._setup_buttons()
        self._populate_from_metadata()

        # Disable sorting to maintain mod grouping by package ID
        self.editor_table_view.setSortingEnabled(False)
        # TODO: let user configure windowTitle from settings controller
        self.showNormal()

    def _setup_buttons(self) -> None:
        """
        Setup buttons for the panel including delete.
        """
        self._setup_deletion_button()

    def _setup_deletion_button(self) -> None:
        """
        Setup the deletion menu for the panel.
        """
        self.deletion_tool_button = QToolButton()
        self.deletion_tool_button.setText(self.tr("Delete"))
        self.deletion_menu = ModDeletionMenu(
            settings_controller=self.settings_controller,
            get_selected_mod_metadata=self._get_selected_mod_metadata,
            menu_title=self.tr("Delete Selected Duplicates..."),
            enable_delete_mod=True,
            enable_delete_keep_dds=False,
            enable_delete_dds_only=False,
            enable_delete_and_unsubscribe=True,
            enable_delete_and_resubscribe=False,
            completion_callback=self._refresh_after_deletion,
        )
        self.deletion_tool_button.setMenu(self.deletion_menu)
        self.deletion_tool_button.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup
        )
        self.editor_main_actions_layout.addWidget(self.deletion_tool_button)

    def _populate_from_metadata(self) -> None:
        """
        Populates the table with data from the duplicate mods, grouped by packageid.
        """
        self.editor_model.removeRows(0, self.editor_model.rowCount())

        # Load ACF data for timeupdated
        self.timeupdated_data: dict[str, int] = {}
        self._load_acf_data()

        for packageid, uuids in self.duplicate_mods.items():
            # Add header row for the packageid group
            header_item = QStandardItem(f"--- Package ID: {packageid} ---")
            header_item.setData(None, Qt.ItemDataRole.UserRole)  # No uuid for header
            self.editor_model.appendRow(
                [
                    header_item,
                    QStandardItem(""),
                    QStandardItem(""),
                    QStandardItem(""),
                    QStandardItem(""),
                    QStandardItem(""),
                    QStandardItem(""),
                ]
            )
            # Add mod rows for this group
            for uuid in uuids:
                mod_data = self.mm.internal_local_metadata.get(uuid)
                if not mod_data:
                    continue

                name = mod_data.get("name", "")
                authors_tag = mod_data.get("authors")
                authors_str = (
                    ", ".join(authors_tag.get("li", [""]))
                    if isinstance(authors_tag, dict)
                    else str(authors_tag)
                    if authors_tag
                    else ""
                )
                path = mod_data.get("path", "")
                pfid = mod_data.get("publishedfileid", "")

                # Get timestamp from ACF data
                timeupdated = self.timeupdated_data.get(pfid)
                if timeupdated:
                    try:
                        dt = datetime.fromtimestamp(int(timeupdated))
                        abs_time = dt.strftime("%Y-%m-%d %H:%M:%S")
                        rel_time = self.get_relative_time(int(timeupdated))
                        combined_text = f"{abs_time} | {rel_time}"
                        time_item = QStandardItem(combined_text)
                        time_item.setData(Qt.ItemDataRole.UserRole, int(timeupdated))
                    except (ValueError, TypeError):
                        time_item = QStandardItem("")
                else:
                    time_item = QStandardItem("")

                name_item = QStandardItem(name)
                name_item.setData(uuid, Qt.ItemDataRole.UserRole)
                name_item.setToolTip(name)

                authors_item = QStandardItem(authors_str)
                authors_item.setToolTip(authors_str)

                path_item = QStandardItem(path)
                pfid_item = QStandardItem(pfid)

                workshop_btn_item = QStandardItem(pfid)
                workshop_btn = self._create_workshop_button(
                    f"https://steamcommunity.com/sharedfiles/filedetails/?id={pfid}",
                    "workshopButton",
                )

                self._add_row(
                    [
                        name_item,
                        authors_item,
                        pfid_item,
                        time_item,
                        path_item,
                        workshop_btn_item,
                    ]
                )

                self.editor_table_view.setIndexWidget(
                    workshop_btn_item.index(), workshop_btn
                )

    def _create_workshop_button(self, url: str, object_name: str) -> QPushButton:
        """
        Create a QPushButton that opens a Steam Workshop page.
        """
        btn = QPushButton()
        btn.setObjectName(object_name)
        btn.setText(self.tr("Open Workshop Page"))
        btn.clicked.connect(partial(platform_specific_open, url))
        return btn

    def _get_selected_mod_metadata(self) -> List[ModMetadata]:
        """
        Get metadata for selected mods in the table based on checkbox states.
        """
        selected_mods = []
        for row in range(self.editor_model.rowCount()):
            if self._row_is_checked(row):
                uuid = self.editor_model.item(row, 1).data(Qt.ItemDataRole.UserRole)
                if uuid and uuid in self.mm.internal_local_metadata:
                    selected_mods.append(self.mm.internal_local_metadata[uuid])

        return selected_mods

    def _load_acf_data(self) -> None:
        """
        Load ACF data to get timeupdated timestamps for mods from MetadataManager.
        """
        # Ensure ACF data is loaded
        self.mm.refresh_acf_metadata()

        # Directly build timeupdated_data from merged ACF sources
        for acf_data in [self.mm.steamcmd_acf_data, self.mm.workshop_acf_data]:
            if acf_data:
                workshop_items = acf_data.get("AppWorkshop", {}).get(
                    "WorkshopItemsInstalled", {}
                )
                for pfid, item in workshop_items.items():
                    if isinstance(item, dict) and "timeupdated" in item:
                        self.timeupdated_data[str(pfid)] = item["timeupdated"]

    def get_relative_time(self, timestamp: int) -> str:
        """
        Convert a timestamp to a relative time string (e.g. "2 days ago").
        """
        try:
            dt = datetime.fromtimestamp(timestamp)
            now = datetime.now()
            delta = now - dt

            if delta.days > 365:
                return f"{delta.days // 365} years ago"
            elif delta.days > 30:
                return f"{delta.days // 30} months ago"
            elif delta.days > 0:
                return f"{delta.days} days ago"
            elif delta.seconds > 3600:
                return f"{delta.seconds // 3600} hours ago"
            elif delta.seconds > 60:
                return f"{delta.seconds // 60} minutes ago"
            else:
                return "Just now"
        except (ValueError, TypeError):
            return "Invalid timestamp"

    def _refresh_after_deletion(self) -> None:
        """
        Refresh the mod list and close the panel after deletion operations.
        """
        logger.debug(
            "Refreshing mod list and closing DuplicateModsPanel after deletion"
        )
        EventBus().do_refresh_mods_lists.emit()
        self.close()

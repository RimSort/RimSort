from functools import partial
from typing import Any, Dict

from loguru import logger
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QStandardItem
from PySide6.QtWidgets import QMenu, QPushButton, QToolButton

import app.views.dialogue as dialogue
from app.utils.event_bus import EventBus
from app.utils.generic import platform_specific_open
from app.utils.metadata import MetadataManager, ModMetadata
from app.views.deletion_menu import ModDeletionMenu
from app.windows.base_mods_panel import BaseModsPanel


class UseThisInsteadPanel(BaseModsPanel):
    """
    A panel used when a user is checking their installed mods against the "Use This Instead" database
    """

    def __init__(
        self,
        mod_metadata: Dict[str, Any],
    ):
        logger.debug("Initializing UseThisInsteadPanel")
        self.mod_metadata = mod_metadata

        super().__init__(
            object_name="useThisInsteadModsPanel",
            window_title="RimSort - Replacements found for Workshop mods",
            title_text="There are replacements available for Workshop mods!",
            details_text='\nThe following table displays Workshop mods with suggested replacements according to the "Use This Instead" database',
            additional_columns=[
                "Original Mod Name",
                "Original Author",
                "Original Workshop Page",
                "Replacement Mod Name",
                "Replacement Author",
                "Replacement Workshop Page",
            ],
            minimum_size=QSize(1100, 600),
        )

        def __subscribe_cb(_: UseThisInsteadPanel) -> None:
            dialogue.show_information(
                "Use This Instead",
                "Succesfully subscribed to replacement mods",
            )

        self.editor_update_mods_button = QPushButton("Subscribe replacements")
        self.editor_update_mods_button.clicked.connect(
            partial(self._update_mods_from_table, 6, "Steam", completed=__subscribe_cb)
        )
        self.editor_update_all_button = QPushButton("Subscribe all replacements")
        self.editor_update_all_button.clicked.connect(
            partial(self._steamworks_cmd_for_all, 6, completed=__subscribe_cb)
        )

        self.editor_tool_button = QToolButton()
        self.editor_tool_button.setText("More Options")

        self.editor_tool_menu = QMenu(self.editor_tool_button)

        refresh_mods_action = QAction("Refresh Mod List", self)
        refresh_mods_action.triggered.connect(EventBus().do_refresh_mods_lists.emit)

        refresh_table_action = QAction("Refresh Table", self)
        refresh_table_action.triggered.connect(self._populate_from_metadata)

        def __unsubscribe_cb(_: UseThisInsteadPanel) -> None:
            dialogue.show_information(
                "Use This Instead",
                "Succesfully unsubscribed to original mods",
            )

        unsub_action = QAction("Unsubscribe outdated", self)
        unsub_action.triggered.connect(
            partial(
                self._update_mods_from_table,
                3,
                "Steam",
                "unsubscribe",
                __unsubscribe_cb,
            )
        )
        unsub_all_action = QAction("Unsubscribe all outdated", self)
        unsub_all_action.triggered.connect(
            partial(self._steamworks_cmd_for_all, 3, "unsubscribe", __unsubscribe_cb)
        )

        deletion_menu = ModDeletionMenu(
            lambda: self._run_for_selected_rows(self._retrieve_metadata_from_row),
            None,
            "Delete Selected Original Mods...",
        )

        self.editor_tool_menu.addAction(refresh_mods_action)
        self.editor_tool_menu.addAction(refresh_table_action)
        self.editor_tool_menu.addAction(unsub_action)
        self.editor_tool_menu.addAction(unsub_all_action)
        self.editor_tool_menu.addMenu(deletion_menu)

        self.editor_tool_button.setMenu(self.editor_tool_menu)
        # When clicked, show menu immediately
        self.editor_tool_button.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup
        )

        self.editor_main_actions_layout.addWidget(self.editor_update_mods_button)
        self.editor_main_actions_layout.addWidget(self.editor_update_all_button)
        self.editor_main_actions_layout.addWidget(self.editor_tool_button)

    def _populate_from_metadata(self) -> None:
        """
        Populates the table with data from the mod metadata
        """
        self.editor_model.removeRows(0, self.editor_model.rowCount())
        mm = MetadataManager.instance()
        for mod, mv in self.mod_metadata.items():
            mr = mm.has_alternative_mod(mod)
            if mr is None:
                continue

            if mv is None:
                logger.warning(
                    f"mod {mod} has no metadata - skipping despite found replacement"
                )
                continue

            original_pfid_btn: QPushButton | None = None

            if "publishedfileid" in mv and "steam_uri" in mv:
                original_pfid_btn_item = QStandardItem(mv["publishedfileid"])
                original_pfid_btn = QPushButton()
                original_pfid_btn.setObjectName("originalPFIDButton")
                original_pfid_btn.setText("Open Workshop Page")
                original_pfid_btn.clicked.connect(
                    partial(platform_specific_open, mv["steam_uri"])
                )
            else:
                original_pfid_btn_item = QStandardItem("Not Found")

            replacement_pfid_btn_item = QStandardItem(mr.pfid)

            replacement_pfid_btn = QPushButton()
            replacement_pfid_btn.setObjectName("replacementPFIDButton")
            replacement_pfid_btn.setText("Open Workshop Page")
            replacement_pfid_btn.clicked.connect(
                partial(
                    platform_specific_open,
                    f"https://steamcommunity.com/sharedfiles/filedetails/?id={mr.pfid}",
                )
            )

            name = mv.get("name")
            if name is None:
                logger.error(f"Missing 'name' key in metadata for mod: {mod}")
                name = "Unknown Name"
            elif not isinstance(name, str):
                # Convert list or dict name to string representation
                if isinstance(name, list):
                    name = ", ".join(str(n) for n in name)
                else:
                    name = str(name)
            original_name_item = QStandardItem(name)
            original_name_item.setData(mv, Qt.ItemDataRole.UserRole)
            original_name_item.setToolTip(name)

            authors = mv.get("authors")
            if authors is None:
                logger.error(f"Missing 'authors' key in metadata for mod: {mod}")
                authors = "Unknown Author"
            elif not isinstance(authors, str):
                # Convert list or dict authors to string representation
                if isinstance(authors, list):
                    authors = ", ".join(str(a) for a in authors)
                else:
                    authors = str(authors)
            original_authors_item = QStandardItem(authors)
            original_authors_item.setToolTip(authors)

            replacement_name_item = QStandardItem(mr.name)
            replacement_name_item.setToolTip(mr.name)

            replacement_authors_item = QStandardItem(mr.author)
            replacement_authors_item.setToolTip(mr.author)

            self._add_row(
                [
                    original_name_item,
                    original_authors_item,
                    original_pfid_btn_item,
                    replacement_name_item,
                    replacement_authors_item,
                    replacement_pfid_btn_item,
                ]
            )

            self.editor_table_view.setIndexWidget(
                replacement_pfid_btn_item.index(), replacement_pfid_btn
            )

            if original_pfid_btn is not None:
                self.editor_table_view.setIndexWidget(
                    original_pfid_btn_item.index(), original_pfid_btn
                )

    def _retrieve_metadata_from_row(self, row: int) -> ModMetadata:
        """
        Retrieves the metadata for a row in the table - which is packaged with the original name
        """
        return self.editor_model.item(row, 1).data(Qt.ItemDataRole.UserRole)

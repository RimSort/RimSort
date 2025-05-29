from functools import partial
from typing import Any, Dict

from loguru import logger
from PySide6.QtCore import Qt
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
    ) -> None:
        """
        Initialize the UseThisInsteadPanel with mod metadata.
        """
        logger.debug("Initializing UseThisInsteadPanel")
        self.mod_metadata = mod_metadata

        super().__init__(
            object_name="useThisInsteadModsPanel",
            window_title=self.tr("RimSort - Replacements found for Workshop mods"),
            title_text=self.tr("There are replacements available for Workshop mods!"),
            details_text=self.tr(
                '\nThe following table displays Workshop mods with suggested replacements according to the "Use This Instead" database'
            ),
            additional_columns=[
                self.tr("Original Mod Name"),
                self.tr("Original Author"),
                self.tr("Original Workshop Page"),
                self.tr("Replacement Mod Name"),
                self.tr("Replacement Author"),
                self.tr("Replacement Workshop Page"),
            ],
        )

        self._setup_buttons()

    def _setup_buttons(self) -> None:
        """
        Setup buttons for the panel including download, subscribe, unsubscribe, refresh, and delete.
        """
        self._setup_steamcmd_download_button()
        self._setup_subscribe_button()
        self._setup_unsubscribe_button()
        self._setup_refresh_button()
        self._setup_deletion_button()

    def _setup_steamcmd_download_button(self) -> None:
        self.steamcmd_download_button = QPushButton()
        self.steamcmd_download_button.setText(self.tr("Download with SteamCMD"))
        self.steamcmd_download_button.clicked.connect(
            partial(self._update_mods_from_table, 6, "SteamCMD")
        )
        self.editor_main_actions_layout.addWidget(self.steamcmd_download_button)

    def _setup_subscribe_button(self) -> None:
        self.subscribe_tool_button = QToolButton()
        self.subscribe_tool_button.setText(self.tr("Subscribe"))
        subscribe_menu = QMenu(self.subscribe_tool_button)

        subscribe_replacements_action = QAction(self.tr("Subscribe replacements"), self)
        subscribe_replacements_action.triggered.connect(
            partial(
                self._update_mods_from_table,
                6,
                "Steam",
                completed=lambda _: self.subscribe_completed(),
            )
        )
        subscribe_all_replacements_action = QAction(
            self.tr("Subscribe all replacements"), self
        )
        subscribe_all_replacements_action.triggered.connect(
            partial(
                self._steamworks_cmd_for_all,
                6,
                "subscribe",
                completed=lambda _: self.subscribe_completed(),
            )
        )
        subscribe_menu.addAction(subscribe_replacements_action)
        subscribe_menu.addAction(subscribe_all_replacements_action)
        self.subscribe_tool_button.setMenu(subscribe_menu)
        self.subscribe_tool_button.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup
        )
        self.editor_main_actions_layout.addWidget(self.subscribe_tool_button)

    def _setup_unsubscribe_button(self) -> None:
        self.unsubscribe_tool_button = QToolButton()
        self.unsubscribe_tool_button.setText(self.tr("Unsubscribe"))
        unsubscribe_menu = QMenu(self.unsubscribe_tool_button)

        unsubscribe_outdated_action = QAction(self.tr("Unsubscribe outdated"), self)
        unsubscribe_outdated_action.triggered.connect(
            partial(
                self._update_mods_from_table,
                3,
                "Steam",
                "unsubscribe",
                completed=lambda _: self.unsubscribe_completed(),
            )
        )
        unsubscribe_all_outdated_action = QAction(
            self.tr("Unsubscribe all outdated"), self
        )
        unsubscribe_all_outdated_action.triggered.connect(
            partial(
                self._steamworks_cmd_for_all,
                3,
                "unsubscribe",
                completed=lambda _: self.unsubscribe_completed(),
            )
        )
        unsubscribe_menu.addAction(unsubscribe_outdated_action)
        unsubscribe_menu.addAction(unsubscribe_all_outdated_action)
        self.unsubscribe_tool_button.setMenu(unsubscribe_menu)
        self.unsubscribe_tool_button.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup
        )
        self.editor_main_actions_layout.addWidget(self.unsubscribe_tool_button)

    def _setup_refresh_button(self) -> None:
        self.refresh_tool_button = QToolButton()
        self.refresh_tool_button.setText(self.tr("Refresh"))
        refresh_menu = QMenu(self.refresh_tool_button)

        refresh_mods_action = QAction(self.tr("Refresh Mod List"), self)
        refresh_mods_action.triggered.connect(EventBus().do_refresh_mods_lists.emit)

        refresh_table_action = QAction(self.tr("Refresh Table"), self)
        refresh_table_action.triggered.connect(self._populate_from_metadata)

        refresh_menu.addAction(refresh_mods_action)
        refresh_menu.addAction(refresh_table_action)
        self.refresh_tool_button.setMenu(refresh_menu)
        self.refresh_tool_button.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup
        )
        self.editor_main_actions_layout.addWidget(self.refresh_tool_button)

    def _setup_deletion_button(self) -> None:
        self.deletion_tool_button = QToolButton()
        self.deletion_tool_button.setText(self.tr("Delete"))
        self.deletion_menu = ModDeletionMenu(
            lambda: self._run_for_selected_rows(self._retrieve_metadata_from_row),
            None,
            self.tr("Delete Selected Original Mods..."),
        )
        self.deletion_tool_button.setMenu(self.deletion_menu)
        self.deletion_tool_button.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup
        )
        self.editor_main_actions_layout.addWidget(self.deletion_tool_button)

    def subscribe_completed(self) -> None:
        """
        Show information dialog when subscription to replacement mods is successful.
        """
        dialogue.show_information(
            self.tr("Use This Instead"),
            self.tr("Successfully subscribed to replacement mods"),
        )

    def unsubscribe_completed(self) -> None:
        """
        Show information dialog when unsubscription from original mods is successful.
        """
        dialogue.show_information(
            self.tr("Use This Instead"),
            self.tr("Successfully unsubscribed to original mods"),
        )

    def _populate_from_metadata(self) -> None:
        """
        Populates the table with data from the mod metadata.
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

            original_pfid_btn_item = QStandardItem(mv["publishedfileid"])
            original_pfid_btn = self._create_workshop_button(
                f"https://steamcommunity.com/sharedfiles/filedetails/?id={mv['publishedfileid']}",
                "originalPFIDButton",
            )

            replacement_pfid_btn_item = QStandardItem(mr.pfid)

            replacement_pfid_btn = self._create_workshop_button(
                f"https://steamcommunity.com/sharedfiles/filedetails/?id={mr.pfid}",
                "replacementPFIDButton",
            )

            name = self._get_string_from_metadata(mv, "name", mod)
            original_name_item = QStandardItem(name)
            original_name_item.setData(mv, Qt.ItemDataRole.UserRole)
            original_name_item.setToolTip(name)

            authors = self._get_string_from_metadata(mv, "authors", mod)
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

    def _create_workshop_button(self, url: str, object_name: str) -> QPushButton:
        """
        Create a QPushButton that opens a Steam Workshop page.
        """
        btn = QPushButton()
        btn.setObjectName(object_name)
        btn.setText(self.tr("Open Workshop Page"))
        btn.clicked.connect(partial(platform_specific_open, url))
        return btn

    def _get_string_from_metadata(
        self, metadata: dict[str, object], key: str, mod: str
    ) -> str:
        """
        Extract a string value from metadata, handling missing keys and different types.
        """
        value = metadata.get(key)
        if value is None:
            logger.error(f"Missing '{key}' key in metadata for mod: {mod}")
            return f"Unknown {key.capitalize()}"
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            return ", ".join(str(v) for v in value)
        return str(value)

    def _retrieve_metadata_from_row(self, row: int) -> ModMetadata:
        """
        Retrieves the metadata for a row in the table - which is packaged with the original name
        """
        return self.editor_model.item(row, 1).data(Qt.ItemDataRole.UserRole)

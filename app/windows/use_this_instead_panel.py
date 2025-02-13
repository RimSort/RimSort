from functools import partial
from typing import Any, Dict

from loguru import logger
from PySide6.QtCore import QSize
from PySide6.QtGui import QStandardItem
from PySide6.QtWidgets import QPushButton

from app.utils.generic import platform_specific_open
from app.utils.metadata import MetadataManager
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
            minimum_size=QSize(1000, 600),
        )

        self.editor_unsub_mods_button = QPushButton("Unsubscribe outdated")
        self.editor_unsub_mods_button.clicked.connect(
            partial(self._update_mods_from_table, 6, "Steam", "unsubscribe")
        )
        self.editor_unsub_all_mods_button = QPushButton("Unsubscribe all outdated")
        self.editor_unsub_all_mods_button.clicked.connect(
            partial(self._update_all, "unsubscribe")
        )

        self.editor_update_mods_button = QPushButton("Subscribe replacements")
        self.editor_update_mods_button.clicked.connect(
            partial(self._update_mods_from_table, 6, "Steam")
        )
        self.editor_update_all_button = QPushButton("Subscribe all replacements")
        self.editor_update_all_button.clicked.connect(partial(self._update_all))

        self.editor_actions_layout.addSpacing(25)
        self.editor_actions_layout.addWidget(self.editor_unsub_mods_button)
        self.editor_actions_layout.addWidget(self.editor_unsub_all_mods_button)
        self.editor_actions_layout.addSpacing(25)
        self.editor_actions_layout.addWidget(self.editor_update_mods_button)
        self.editor_actions_layout.addWidget(self.editor_update_all_button)

    def _update_all(self, steamworks_cmd: str = "resubscribe") -> None:
        self._set_all_checkbox_rows(True)
        self._update_mods_from_table(6, "Steam", steamworks_cmd)

    def _populate_from_metadata(self) -> None:
        """
        Populates the table with data from the mod metadata
        """
        mm = MetadataManager.instance()
        for mod, mv in self.mod_metadata.items():
            mr = mm.has_alternative_mod(mod)
            if mr is None:
                continue

            original_pfid_btn_item = QStandardItem(mv["publishedfileid"])
            replacement_pfid_btn_item = QStandardItem(mr.pfid)

            self._add_row(
                [
                    QStandardItem(mv["name"]),
                    QStandardItem(mv["authors"]),
                    original_pfid_btn_item,
                    QStandardItem(mr.name),
                    QStandardItem(mr.author),
                    replacement_pfid_btn_item,
                ]
            )
            original_pfid_btn = QPushButton()
            original_pfid_btn.setObjectName("originalPFIDButton")
            original_pfid_btn.setText("Open Workshop Page")
            original_pfid_btn.clicked.connect(
                partial(platform_specific_open, mv["steam_uri"])
            )
            self.editor_table_view.setIndexWidget(
                original_pfid_btn_item.index(), original_pfid_btn
            )
            replacement_pfid_btn = QPushButton()
            replacement_pfid_btn.setObjectName("replacementPFIDButton")
            replacement_pfid_btn.setText("Open Workshop Page")
            replacement_pfid_btn.clicked.connect(
                partial(
                    platform_specific_open,
                    f"https://steamcommunity.com/sharedfiles/filedetails/?id={mr.pfid}",
                )
            )
            self.editor_table_view.setIndexWidget(
                replacement_pfid_btn_item.index(), replacement_pfid_btn
            )

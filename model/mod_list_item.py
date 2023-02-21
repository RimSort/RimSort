import logging
from typing import Any, Dict

from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *

logger = logging.getLogger(__name__)


class ModListItemInner(QWidget):
    """
    Subclass for QWidget. Used to store data for a single
    mod and display relevant data on a mod list.
    """

    def __init__(self, data: Dict[str, Any], container_width: float) -> None:
        """
        Initialize the QWidget with mod data.
        All tags are set to the corresponding field if it
        exists in the input dict, otherwise are None. See tags:
        https://rimworldwiki.com/wiki/About.xml

        :param data: mod data by tag
        """

        super(ModListItemInner, self).__init__()

        # All data, includig name, author, package id, dependencies,
        # whether the mod is a workshop mod or expansion, etc is encapsulated
        # in this variable. This is exactly equal to the dict value of a
        # single all_mods key-value
        self.json_data = data

        # Visuals
        self.setToolTip(self.get_tool_tip_text())
        self.main_item_layout = QHBoxLayout()
        self.main_item_layout.setContentsMargins(0, 0, 0, 0)
        self.main_item_layout.setSpacing(0)
        item_name = self.json_data.get("name", "UNKNOWN")
        self.font_metrics = QFontMetrics(self.font())
        text_width_needed = QRectF(self.font_metrics.boundingRect(item_name)).width()
        if text_width_needed > container_width - 70:
            available_width = container_width - 70
            shortened_text = self.font_metrics.elidedText(
                item_name, Qt.ElideRight, available_width
            )
            self.main_label = QLabel(str(shortened_text))
        else:
            self.main_label = QLabel(item_name)

        # Icons by mod source
        self.mod_source_icon = QLabel()
        self.mod_source_icon.setPixmap(self.get_icon().pixmap(QSize(20, 20)))

        # Warning icon hidden by default
        self.warning_icon_label = QLabel()
        self.warning_icon_label.setPixmap(
            self.style().standardIcon(QStyle.SP_MessageBoxWarning).pixmap(QSize(20, 20))
        )
        self.warning_icon_label.setHidden(True)

        self.main_label.setObjectName("ListItemLabel")
        self.main_item_layout.addWidget(self.mod_source_icon, 10)
        self.main_item_layout.addWidget(self.main_label, 90)
        self.main_item_layout.addWidget(self.warning_icon_label, 10)
        self.main_item_layout.addStretch()
        self.setLayout(self.main_item_layout)

    def get_tool_tip_text(self) -> str:
        name_line = f"Mod: {self.json_data.get('name', 'UNKNOWN')}\n"
        if self.json_data.get("authors"):
            list_of_authors = self.json_data.get("authors")["li"]
            authors_text = ", ".join(list_of_authors)
            author_line = f"Authors: {authors_text}\n"
        else:
            author_line = f"Authors: {self.json_data.get('author', 'UNKNOWN')}\n"
        package_id_line = f"PackageID: {self.json_data.get('packageId', 'UNKNOWN')}\n"
        # TODO: version information should be read from manifest file, which is not currently
        # being used. This file actually also contains some load rule data so use that too.
        version_line = f"Version: {self.json_data.get('version', 'UNKNOWN')}\n"
        path_line = f"Path: {self.json_data.get('path', 'UNKNOWN')}"
        return name_line + author_line + package_id_line + version_line + path_line

    def get_icon(self) -> QIcon:
        """
        Check custom tags added to mod metadata upon initialization, and return the cooresponding
        QIcon for the type of mod that it is (expansion, workshop, or local mod?)

        :return icon: QIcon object set to the path of the cooresponding icon image
        """
        if self.json_data.get("isExpansion"):
            return QIcon("data/ludeon_icon.png")
        elif self.json_data.get("isWorkshop"):
            return QIcon("data/steam_icon.png")
        elif self.json_data.get("isLocal"):
            return self.style().standardIcon(QStyle.SP_FileDialogStart)
        else:
            logger.error(
                f"No type found for ModListItemInner with package id {self.json_data.get('packageId')}"
            )

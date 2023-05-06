from logger_tt import logger
from typing import Any, Dict

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QFontMetrics, QIcon, QResizeEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QStyle, QWidget


class ModListItemInner(QWidget):
    """
    Subclass for QWidget. Used to store data for a single
    mod and display relevant data on a mod list.
    """

    def __init__(
        self,
        data: Dict[str, Any],
        local_icon_path: str,
        steam_icon_path: str,
        ludeon_icon_path: str,
    ) -> None:
        """
        Initialize the QWidget with mod data.
        All tags are set to the corresponding field if it
        exists in the input dict, otherwise are None. See tags:
        https://rimworldwiki.com/wiki/About.xml

        :param data: mod data by tag
        :param container_width: width of container
        :param steam_icon_path: path to the Steam icon to be used for list items
        :param ludeon_icon_path: path to the Ludeon icon to be used for list items
        """

        super(ModListItemInner, self).__init__()

        # All data, including name, author, package id, dependencies,
        # whether the mod is a workshop mod or expansion, etc is encapsulated
        # in this variable. This is exactly equal to the dict value of a
        # single all_mods key-value
        self.json_data = data
        self.item_name = self.json_data.get("name", "UNKNOWN")
        self.ludeon_icon_path = ludeon_icon_path
        self.local_icon_path = local_icon_path
        self.steam_icon_path = steam_icon_path
        self.main_label = QLabel()

        # Visuals
        self.setToolTip(self.get_tool_tip_text())
        self.main_item_layout = QHBoxLayout()
        self.main_item_layout.setContentsMargins(0, 0, 0, 0)
        self.main_item_layout.setSpacing(0)
        self.font_metrics = QFontMetrics(self.font())

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
        self.main_item_layout.addWidget(self.mod_source_icon, Qt.AlignRight)
        self.main_item_layout.addWidget(self.main_label, Qt.AlignCenter)
        self.main_item_layout.addWidget(self.warning_icon_label, Qt.AlignRight)
        self.main_item_layout.addStretch()
        self.setLayout(self.main_item_layout)

    def get_tool_tip_text(self) -> str:
        """
        Compose a mod_list_item's tool_tip_text

        :return: string containing the tool_tip_text
        """
        name_line = f"Mod: {self.json_data.get('name', 'UNKNOWN')}\n"

        author_line = "Author: UNKNOWN\n"
        if "authors" in self.json_data:
            if "li" in self.json_data["authors"]:
                list_of_authors = self.json_data["authors"]["li"]
                authors_text = ", ".join(list_of_authors)
                author_line = f"Authors: {authors_text}\n"
            else:
                logger.error(
                    f"[authors] tag does not contain [li] tag: {self.json_data['authors']}"
                )
        else:
            author_line = f"Author: {self.json_data.get('author', 'UNKNOWN')}\n"

        package_id_line = f"PackageID: {self.json_data.get('packageId', 'UNKNOWN')}\n"
        version_line = f"Version: {self.json_data.get('modVersion', 'Not specified')}\n"
        path_line = f"Path: {self.json_data.get('path', 'UNKNOWN')}"
        return name_line + author_line + package_id_line + version_line + path_line

    def get_icon(self) -> QIcon:  # type: ignore
        """
        Check custom tags added to mod metadata upon initialization, and return the cooresponding
        QIcon for the mod's source type (expansion, workshop, or local mod?)

        :return: QIcon object set to the path of the cooresponding icon image
        """
        if self.json_data.get("data_source") == "expansion":
            return QIcon(self.ludeon_icon_path)
        elif self.json_data.get("data_source") == "local":
            return QIcon(self.local_icon_path)
        elif self.json_data.get("data_source") == "workshop":
            return QIcon(self.steam_icon_path)
        else:
            logger.error(
                f"No type found for ModListItemInner with package id {self.json_data.get('packageId')}"
            )

    def resizeEvent(self, event: QResizeEvent) -> None:
        """
        When the label is resized (as the window is resized),
        also elide the label if needed.

        :param event: the resize event
        """
        self.item_width = super().width()
        text_width_needed = QRectF(
            self.font_metrics.boundingRect(self.item_name)
        ).width()
        if text_width_needed > self.item_width - 50:
            available_width = self.item_width - 50
            shortened_text = self.font_metrics.elidedText(
                self.item_name, Qt.ElideRight, int(available_width)
            )
            self.main_label.setText(str(shortened_text))
        else:
            self.main_label.setText(self.item_name)
        return super().resizeEvent(event)

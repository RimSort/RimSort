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
        csharp_icon_path: str,
        git_icon_path: str,
        local_icon_path: str,
        ludeon_icon_path: str,
        steamcmd_icon_path: str,
        steam_icon_path: str,
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
        self.list_item_name = self.json_data.get("name", "UNKNOWN")
        self.main_label = QLabel()

        # Icon paths
        self.csharp_icon_path = csharp_icon_path
        self.git_icon_path = git_icon_path
        self.local_icon_path = local_icon_path
        self.ludeon_icon_path = ludeon_icon_path
        self.steamcmd_icon_path = steamcmd_icon_path
        self.steam_icon_path = steam_icon_path

        # Visuals
        self.setToolTip(self.get_tool_tip_text())
        self.main_item_layout = QHBoxLayout()
        self.main_item_layout.setContentsMargins(0, 0, 0, 0)
        self.main_item_layout.setSpacing(0)
        self.font_metrics = QFontMetrics(self.font())

        # Icons that are conditional
        self.csharp_icon = None
        if self.json_data.get("csharp"):
            self.csharp_icon = QLabel()
            self.csharp_icon.setPixmap(
                QIcon(self.csharp_icon_path).pixmap(QSize(20, 20))
            )
            self.csharp_icon.setToolTip("Contains C# assemblies")
        self.git_icon = None
        if (
            self.json_data["data_source"] == "local"
            and self.json_data.get("git_repo")
            and not self.json_data.get("steamcmd")
        ):
            self.git_icon = QLabel()
            self.git_icon.setPixmap(QIcon(self.git_icon_path).pixmap(QSize(20, 20)))
            self.git_icon.setToolTip("Contains a git repository")
        self.steamcmd_icon = None
        if self.json_data["data_source"] == "local" and self.json_data.get("steamcmd"):
            self.steamcmd_icon = QLabel()
            self.steamcmd_icon.setPixmap(
                QIcon(self.steamcmd_icon_path).pixmap(QSize(20, 20))
            )
            self.steamcmd_icon.setToolTip("Downloaded with SteamCMD")

        # Icons by mod source
        self.mod_source_icon = None
        if not self.git_icon and not self.steamcmd_icon:
            self.mod_source_icon = QLabel()
            self.mod_source_icon.setPixmap(self.get_icon().pixmap(QSize(20, 20)))
            # Set tooltip based on mod source
            data_source = self.json_data.get("data_source")
            if data_source == "expansion":
                self.mod_source_icon.setToolTip("Official RimWorld content")
            elif data_source == "local":
                self.mod_source_icon.setToolTip("Installed locally")
            elif data_source == "workshop":
                self.mod_source_icon.setToolTip("Subscribed via Steam")

        # Warning icon hidden by default
        self.warning_icon_label = QLabel()
        self.warning_icon_label.setPixmap(
            self.style().standardIcon(QStyle.SP_MessageBoxWarning).pixmap(QSize(20, 20))
        )
        self.warning_icon_label.setHidden(True)

        self.main_label.setObjectName("ListItemLabel")
        if self.git_icon:
            self.main_item_layout.addWidget(self.git_icon, Qt.AlignRight)
        if self.steamcmd_icon:
            self.main_item_layout.addWidget(self.steamcmd_icon, Qt.AlignRight)
        if self.mod_source_icon:
            self.main_item_layout.addWidget(self.mod_source_icon, Qt.AlignRight)
        if self.csharp_icon:
            self.main_item_layout.addWidget(self.csharp_icon, Qt.AlignRight)
        self.main_item_layout.addWidget(self.main_label, Qt.AlignCenter)
        self.main_item_layout.addWidget(self.warning_icon_label, Qt.AlignRight)
        self.main_item_layout.addStretch()
        self.setLayout(self.main_item_layout)

    def count_icons(self, widget) -> int:
        count = 0
        if isinstance(widget, QLabel):
            pixmap = widget.pixmap()
            if pixmap and not pixmap.isNull():
                count += 1

        if isinstance(widget, QWidget):
            for child in widget.children():
                count += self.count_icons(child)

        return count

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

        # Count the number of QLabel widgets with QIcon and calculate total icon width
        icon_count = self.count_icons(self)
        icon_width = icon_count * 20
        self.item_width = super().width()
        text_width_needed = QRectF(
            self.font_metrics.boundingRect(self.list_item_name)
        ).width()
        if text_width_needed > self.item_width - icon_width:
            available_width = self.item_width - icon_width
            shortened_text = self.font_metrics.elidedText(
                self.list_item_name, Qt.ElideRight, int(available_width)
            )
            self.main_label.setText(str(shortened_text))
        else:
            self.main_label.setText(self.list_item_name)
        return super().resizeEvent(event)

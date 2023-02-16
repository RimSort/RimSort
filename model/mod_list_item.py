from typing import Any, Dict

from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *


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

        # Required tags
        self.name = data.get("name")
        self.author = data.get("author")
        self.package_id = data.get("packageId")
        self.description = data.get("description")
        self.supported_versions = data.get("supportedVersions")

        # Optional Tags
        self.authors = data.get("authors")
        self.url = data.get("url")
        self.descriptions_by_version = data.get("descriptionsByVersion")
        self.mod_dependencies = data.get("modDependencies")
        self.mod_dependencies_by_version = data.get("modDependenciesByVersion")
        self.load_before = data.get("loadBefore")
        self.load_before_by_version = data.get("loadBeforeByVersion")
        self.force_load_before = data.get("forceLoadBefore")
        self.load_after = data.get("loadAfter")
        self.load_after_by_version = data.get("loadAfterByVersion")
        self.force_load_after = data.get("forceLoadAfter")
        self.incompatible_with = data.get("incompatibleWith")
        self.incompatible_with_by_version = data.get("incompatibleWithByVersion")

        # Custom tags
        self.isExpansion = data.get("isExpansion")  # True if base game or DLC
        self.isWorkshop = data.get("isWorkshop") # True if workshop mod
        self.isLocal = data.get("isLocal")  # True if local mod
        self.error = data.get("error")

        # Entire data
        self.json_data = data

        # Sorting tags
        self.dependencies = data.get("dependencies")

        # Visuals
        self.setToolTip(self.get_tool_tip_text())
        self.main_item_layout = QHBoxLayout()
        self.main_item_layout.setContentsMargins(0, 0, 0, 0)
        self.main_item_layout.setSpacing(0)
        item_name = self.name

        # Icons by mod source
        self.icon_mod_source = QLabel()
        self.icon_mod_source.setAlignment(Qt.AlignLeft)
        self.pixmap = self.get_icon().pixmap(QSize(20, 20))
        self.icon_mod_source.setPixmap(self.pixmap)

        self.font_metrics = QFontMetrics(self.font())
        text_width_needed = QRectF(self.font_metrics.boundingRect(item_name)).width()
        if text_width_needed > container_width:
            available_width = container_width - 20
            shortened_text = self.font_metrics.elidedText(
                item_name, Qt.ElideRight, available_width
            )
            self.main_label = QLabel(str(shortened_text))
        else:
            self.main_label = QLabel(item_name)
        self.main_label.setObjectName("ListItemLabel")
        self.main_item_layout.addWidget(self.icon_mod_source)
        self.main_item_layout.addWidget(self.main_label)
        self.setLayout(self.main_item_layout)

    def get_tool_tip_text(self):
        name_line = f"Mod: {self.json_data['name']}\n"
        if self.json_data.get("authors"):
            list_of_authors = self.json_data.get("authors")["li"]
            authors_text = ", ".join(list_of_authors)
            author_line = f"Authors: {authors_text}\n"
        else:
            author_line = f"Authors: {self.json_data.get('author', 'UNKNOWN')}\n"
        package_id_line = f"PackageID: {self.json_data['packageId']}\n"
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
        if self.isExpansion:
            return QIcon("data/E.png")
        elif self.isWorkshop:
            return QIcon("data/S.png")
        elif self.isLocal:
            return QIcon("data/L.png")
        else:
            print("No type")
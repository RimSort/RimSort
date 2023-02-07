from typing import Any, Dict

from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *


class ModListItemInner(QWidget):
    """
    Subclass for QWidget. Used to store data for a single
    mod and display relevant data on a mod list.
    """

    def __init__(self, data: Dict[str, Any]) -> None:
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
        self.base = data.get("isBase")  # True if base game
        self.dlc = data.get("isDLC")  # True if DLC
        self.error = data.get("error")

        # Visuals
        self.main_item_layout = QHBoxLayout()
        self.main_item_layout.setContentsMargins(0, 0, 0, 0)
        self.main_item_layout.setSpacing(0)
        item_name = self.name
        if self.base:
            item_name = f"*Base* {item_name}"
        if self.dlc:
            item_name = f"*DLC* {item_name}"
        self.main_label = QLabel(item_name)
        self.main_label.setObjectName("ListItemLabel")
        self.main_item_layout.addWidget(self.main_label)
        self.setLayout(self.main_item_layout)

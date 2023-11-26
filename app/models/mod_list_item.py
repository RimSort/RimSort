import os
from functools import partial
from pathlib import Path

from loguru import logger
from typing import Optional

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QFontMetrics, QIcon, QResizeEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from app.controllers.settings_controller import SettingsController
from app.utils.app_info import AppInfo
from app.utils.metadata import MetadataManager


class ClickableQLabel(QLabel):
    clicked = Signal()

    def mousePressEvent(self, event):
        self.clicked.emit()
        super().mousePressEvent(event)


class ModListItemInner(QWidget):
    """
    Subclass for QWidget. Used to store data for a single
    mod and display relevant data on a mod list.
    """

    toggle_warning_signal = Signal(str)

    def __init__(
        self,
        settings_controller: SettingsController,
        uuid: str,
    ) -> None:
        """
        Initialize the QWidget with mod uuid. Metadata can be accessed via MetadataManager.

        All metadata tags are set to the corresponding field if it
        exists in the metadata dict. See tags:
        https://rimworldwiki.com/wiki/About.xml

        :param settings_controller: an instance of SettingsController for accessing settings
        :param uuid: str, the uuid of the mod which corresponds to a mod's metadata
        """

        super(ModListItemInner, self).__init__()

        # Cache MetadataManager instance
        self.metadata_manager = MetadataManager.instance()
        # Cache SettingsManager instance
        self.settings_controller = settings_controller

        # All data, including name, author, package id, dependencies,
        # whether the mod is a workshop mod or expansion, etc is encapsulated
        # in this variable. This is exactly equal to the dict value of a
        # single all_mods key-value
        self.uuid = uuid
        self.list_item_name = self.metadata_manager.internal_local_metadata[
            self.uuid
        ].get("name")
        self.main_label = QLabel()

        # Visuals
        self.setToolTip(self.get_tool_tip_text())
        self.main_item_layout = QHBoxLayout()
        self.main_item_layout.setContentsMargins(0, 0, 0, 0)
        self.main_item_layout.setSpacing(0)
        self.font_metrics = QFontMetrics(self.font())

        # Icons that are conditional
        self.csharp_icon = None
        self.xml_icon = None
        if self.settings_controller.settings.mod_type_filter_toggle:
            if self.metadata_manager.internal_local_metadata[self.uuid].get("csharp"):
                self.csharp_icon = QLabel()
                self.csharp_icon.setPixmap(
                    ModListIcons.csharp_icon().pixmap(QSize(20, 20))
                )
                self.csharp_icon.setToolTip(
                    "Contains custom C# assemblies (custom code)"
                )
            else:
                self.xml_icon = QLabel()
                self.xml_icon.setPixmap(ModListIcons.xml_icon().pixmap(QSize(20, 20)))
                self.xml_icon.setToolTip("Contains custom content (textures / XML)")
        self.git_icon = None
        if (
            self.metadata_manager.internal_local_metadata[self.uuid]["data_source"]
            == "local"
            and self.metadata_manager.internal_local_metadata[self.uuid].get("git_repo")
            and not self.metadata_manager.internal_local_metadata[self.uuid].get(
                "steamcmd"
            )
        ):
            self.git_icon = QLabel()
            self.git_icon.setPixmap(ModListIcons.git_icon().pixmap(QSize(20, 20)))
            self.git_icon.setToolTip("Local mod that contains a git repository")
        self.steamcmd_icon = None
        if self.metadata_manager.internal_local_metadata[self.uuid][
            "data_source"
        ] == "local" and self.metadata_manager.internal_local_metadata[self.uuid].get(
            "steamcmd"
        ):
            self.steamcmd_icon = QLabel()
            self.steamcmd_icon.setPixmap(
                ModListIcons.steamcmd_icon().pixmap(QSize(20, 20))
            )
            self.steamcmd_icon.setToolTip("Local mod that can be used with SteamCMD")
        # Warning icon hidden by default
        self.warning_icon_label = ClickableQLabel()
        self.warning_icon_label.clicked.connect(
            partial(
                self.toggle_warning_signal.emit,
                self.metadata_manager.internal_local_metadata[self.uuid]["packageid"],
            )
        )
        self.warning_icon_label.setPixmap(
            ModListIcons.warning_icon().pixmap(QSize(20, 20))
        )
        self.warning_icon_label.setHidden(True)

        # Icons by mod source
        self.mod_source_icon = None
        if not self.git_icon and not self.steamcmd_icon:
            self.mod_source_icon = QLabel()
            self.mod_source_icon.setPixmap(self.get_icon().pixmap(QSize(20, 20)))
            # Set tooltip based on mod source
            data_source = self.metadata_manager.internal_local_metadata[self.uuid].get(
                "data_source"
            )
            if data_source == "expansion":
                self.mod_source_icon.setObjectName("expansion")
                self.mod_source_icon.setToolTip(
                    "Official RimWorld content by Ludeon Studios"
                )
            elif data_source == "local":
                if self.metadata_manager.internal_local_metadata[self.uuid].get(
                    "git_repo"
                ):
                    self.mod_source_icon.setObjectName("git_repo")
                elif self.metadata_manager.internal_local_metadata[self.uuid].get(
                    "steamcmd"
                ):
                    self.mod_source_icon.setObjectName("steamcmd")
                else:
                    self.mod_source_icon.setObjectName("local")
                    self.mod_source_icon.setToolTip("Installed locally")
            elif data_source == "workshop":
                self.mod_source_icon.setObjectName("workshop")
                self.mod_source_icon.setToolTip("Subscribed via Steam")

        self.main_label.setObjectName("ListItemLabel")
        if self.git_icon:
            self.main_item_layout.addWidget(self.git_icon, Qt.AlignRight)
        if self.steamcmd_icon:
            self.main_item_layout.addWidget(self.steamcmd_icon, Qt.AlignRight)
        if self.mod_source_icon:
            self.main_item_layout.addWidget(self.mod_source_icon, Qt.AlignRight)
        if self.csharp_icon:
            self.main_item_layout.addWidget(self.csharp_icon, Qt.AlignRight)
        if self.xml_icon:
            self.main_item_layout.addWidget(self.xml_icon, Qt.AlignRight)
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
        name_line = f"Mod: {self.metadata_manager.internal_local_metadata[self.uuid].get('name')}\n"

        authors_tag = self.metadata_manager.internal_local_metadata[self.uuid].get(
            "authors"
        )

        if authors_tag and isinstance(authors_tag, dict) and authors_tag.get("li"):
            list_of_authors = authors_tag["li"]
            authors_text = ", ".join(list_of_authors)
            author_line = f"Authors: {authors_text}\n"
        else:
            author_line = f"Author: {authors_tag if authors_tag else 'Not specified'}\n"

        package_id_line = f"PackageID: {self.metadata_manager.internal_local_metadata[self.uuid].get('packageid')}\n"
        modversion_line = f"Mod Version: {self.metadata_manager.internal_local_metadata[self.uuid].get('modversion', 'Not specified')}\n"
        path_line = f"Path: {self.metadata_manager.internal_local_metadata[self.uuid].get('path')}"
        return name_line + author_line + package_id_line + modversion_line + path_line

    def get_icon(self) -> QIcon:  # type: ignore
        """
        Check custom tags added to mod metadata upon initialization, and return the corresponding
        QIcon for the mod's source type (expansion, workshop, or local mod?)

        :return: QIcon object set to the path of the corresponding icon image
        """
        if (
            self.metadata_manager.internal_local_metadata[self.uuid].get("data_source")
            == "expansion"
        ):
            return ModListIcons.ludeon_icon()
        elif (
            self.metadata_manager.internal_local_metadata[self.uuid].get("data_source")
            == "local"
        ):
            return ModListIcons.local_icon()
        elif (
            self.metadata_manager.internal_local_metadata[self.uuid].get("data_source")
            == "workshop"
        ):
            return ModListIcons.steam_icon()
        else:
            logger.error(
                f"No type found for ModListItemInner with package id {self.metadata_manager.internal_local_metadata[self.uuid].get('packageid')}"
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


class ModListIcons:
    _data_path: Path = AppInfo().theme_data_folder / "default-icons"
    _ludeon_icon_path: str = str(_data_path / "ludeon_icon.png")
    _local_icon_path: str = str(_data_path / "local_icon.png")
    _steam_icon_path: str = str(_data_path / "steam_icon.png")
    _csharp_icon_path: str = str(_data_path / "csharp.png")
    _xml_icon_path: str = str(_data_path / "xml.png")
    _git_icon_path: str = str(_data_path / "git.png")
    _steamcmd_icon_path: str = str(_data_path / "steamcmd_icon.png")
    _warning_icon_path: str = str(_data_path / "warning.png")
    _error_icon_path: str = str(_data_path / "error.png")

    _ludeon_icon: Optional[QIcon] = None
    _local_icon: Optional[QIcon] = None
    _steam_icon: Optional[QIcon] = None
    _csharp_icon: Optional[QIcon] = None
    _xml_icon: Optional[QIcon] = None
    _git_icon: Optional[QIcon] = None
    _steamcmd_icon: Optional[QIcon] = None
    _warning_icon: Optional[QIcon] = None
    _error_icon: Optional[QIcon] = None

    @classmethod
    def ludeon_icon(cls) -> QIcon:
        if cls._ludeon_icon is None:
            cls._ludeon_icon = QIcon(cls._ludeon_icon_path)
        return cls._ludeon_icon

    @classmethod
    def local_icon(cls) -> QIcon:
        if cls._local_icon is None:
            cls._local_icon = QIcon(cls._local_icon_path)
        return cls._local_icon

    @classmethod
    def steam_icon(cls) -> QIcon:
        if cls._steam_icon is None:
            cls._steam_icon = QIcon(cls._steam_icon_path)
        return cls._steam_icon

    @classmethod
    def csharp_icon(cls) -> QIcon:
        if cls._csharp_icon is None:
            cls._csharp_icon = QIcon(cls._csharp_icon_path)
        return cls._csharp_icon

    @classmethod
    def xml_icon(cls) -> QIcon:
        if cls._xml_icon is None:
            cls._xml_icon = QIcon(cls._xml_icon_path)
        return cls._xml_icon

    @classmethod
    def git_icon(cls) -> QIcon:
        if cls._git_icon is None:
            cls._git_icon = QIcon(cls._git_icon_path)
        return cls._git_icon

    @classmethod
    def steamcmd_icon(cls) -> QIcon:
        if cls._steamcmd_icon is None:
            cls._steamcmd_icon = QIcon(cls._steamcmd_icon_path)
        return cls._steamcmd_icon

    @classmethod
    def warning_icon(cls) -> QIcon:
        if cls._warning_icon is None:
            cls._warning_icon = QIcon(cls._warning_icon_path)
        return cls._warning_icon

    @classmethod
    def error_icon(cls) -> QIcon:
        if cls._error_icon is None:
            cls._error_icon = QIcon(cls._error_icon_path)
        return cls._error_icon

from functools import partial

from loguru import logger
from PySide6.QtCore import QObject, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QFontMetrics,
    QIcon,
    QResizeEvent,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QWidget,
)

from app.controllers.settings_controller import SettingsController
from app.utils.custom_list_widget_item import CustomListWidgetItem
from app.utils.custom_qlabels import ClickableQLabel
from app.utils.metadata import MetadataManager
from app.views.mods_panel_icons import ModListIcons


class ModListItemInner(QWidget):
    """
    Subclass for QWidget. Used to store data for a single
    mod and display relevant data on a mod list.
    """

    toggle_warning_signal = Signal(str, str)
    toggle_error_signal = Signal(str, str)

    def __init__(
        self,
        errors_warnings: str,
        errors: str,
        warnings: str,
        filtered: bool,
        invalid: bool,
        mismatch: bool,
        alternative: bool,
        settings_controller: SettingsController,
        uuid: str,
    ) -> None:
        """
        Initialize the QWidget with mod uuid. Metadata can be accessed via MetadataManager.

        All metadata tags are set to the corresponding field if it
        exists in the metadata dict. See tags:
        https://rimworldwiki.com/wiki/About.xml

        :param errors_warnings: a string of errors and warnings
        :param errors: a string of errors for the notification tooltip
        :param warnings: a string of warnings for the notification tooltip
        :param filtered: a bool representing whether the widget's item is filtered
        :param invalid: a bool representing whether the widget's item is an invalid mod
        :param mismatch: a bool representing whether the widget's item has a version mismatch
        :param alternative: a bool representing whether the widget's item has a recommended alternative mod
        :param settings_controller: an instance of SettingsController for accessing settings
        :param uuid: str, the uuid of the mod which corresponds to a mod's metadata
        """

        super(ModListItemInner, self).__init__()

        # Cache MetadataManager instance
        self.metadata_manager = MetadataManager.instance()
        # Cache error and warning strings for tooltips
        self.errors_warnings = errors_warnings
        self.errors = errors
        self.warnings = warnings
        # Cache filtered state of widget's item - used to determine styling of widget
        self.filtered = filtered
        # Cache invalid state of widget's item - used to determine styling of widget
        self.invalid = invalid
        # Cache mismatch state of widget's item - used to determine warning icon visibility
        self.mismatch = mismatch
        # Cache alternative state of widget's item - used to determine warning icon visibility
        self.alternative = alternative
        # Cache SettingsManager instance
        self.settings_controller = settings_controller

        # All data, including name, author, package id, dependencies,
        # whether the mod is a workshop mod or expansion, etc is encapsulated
        # in this variable. This is exactly equal to the dict value of a
        # single all_mods key-value
        self.uuid = uuid
        self.list_item_name = (
            self.metadata_manager.internal_local_metadata.get(self.uuid, {}).get("name")
            or "METADATA ERROR"
        )
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
            if (
                self.metadata_manager.internal_local_metadata.get(self.uuid, {}).get(
                    "csharp"
                )
            ) is not None:
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
                self.uuid,
            )
        )
        self.warning_icon_label.setPixmap(
            ModListIcons.warning_icon().pixmap(QSize(20, 20))
        )
        # Default to hidden to avoid showing early
        self.warning_icon_label.setHidden(True)
        # Error icon hidden by default
        self.error_icon_label = ClickableQLabel()
        self.error_icon_label.clicked.connect(
            partial(
                self.toggle_error_signal.emit,
                self.metadata_manager.internal_local_metadata[self.uuid]["packageid"],
                self.uuid,
            )
        )
        self.error_icon_label.setPixmap(ModListIcons.error_icon().pixmap(QSize(20, 20)))
        # Default to hidden to avoid showing early
        self.error_icon_label.setHidden(True)
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
        # Set label color if mod has errors/warnings
        if self.filtered:
            self.main_label.setObjectName("ListItemLabelFiltered")
        elif errors_warnings:
            self.main_label.setObjectName("ListItemLabelInvalid")
        else:
            self.main_label.setObjectName("ListItemLabel")
        # Add icons
        if self.git_icon:
            self.main_item_layout.addWidget(self.git_icon, Qt.AlignmentFlag.AlignRight)
        if self.steamcmd_icon:
            self.main_item_layout.addWidget(
                self.steamcmd_icon, Qt.AlignmentFlag.AlignRight
            )
        if self.mod_source_icon:
            self.main_item_layout.addWidget(
                self.mod_source_icon, Qt.AlignmentFlag.AlignRight
            )
        if self.csharp_icon:
            self.main_item_layout.addWidget(
                self.csharp_icon, Qt.AlignmentFlag.AlignRight
            )
        if self.xml_icon:
            self.main_item_layout.addWidget(self.xml_icon, Qt.AlignmentFlag.AlignRight)
        # Compose the layout of our widget and set it to the main layout
        self.main_item_layout.addWidget(self.main_label, Qt.AlignmentFlag.AlignCenter)
        self.main_item_layout.addWidget(
            self.warning_icon_label, Qt.AlignmentFlag.AlignRight
        )
        self.main_item_layout.addWidget(
            self.error_icon_label, Qt.AlignmentFlag.AlignRight
        )
        self.main_item_layout.addStretch()
        self.setLayout(self.main_item_layout)

        # Reveal if errors or warnings exist
        if self.warnings:
            self.warning_icon_label.setToolTip(self.warnings)
            self.warning_icon_label.setHidden(False)
        if self.errors:
            self.error_icon_label.setToolTip(self.errors)
            self.error_icon_label.setHidden(False)

    def count_icons(self, widget: QObject) -> int:
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
        metadata = self.metadata_manager.internal_local_metadata.get(self.uuid, {})

        name_line = f"Mod: {metadata.get('name', 'Not specified')}\n"

        authors_tag = metadata.get("authors")
        authors_text = (
            ", ".join(authors_tag.get("li", ["Not specified"]))
            if isinstance(authors_tag, dict)
            else authors_tag or "Not specified"
        )
        author_line = f"Authors: {authors_text}\n"

        package_id = metadata.get("packageid", "Not specified")
        package_id_line = f"PackageID: {package_id}\n"

        mod_version = metadata.get("modversion", "Not specified")
        modversion_line = f"Mod Version: {mod_version}\n"

        supported_versions_tag = metadata.get("supportedversions", {})
        supported_versions_list = supported_versions_tag.get("li")
        supported_versions_text = (
            ", ".join(supported_versions_list)
            if isinstance(supported_versions_list, list)
            else supported_versions_list or "Not specified"
        )
        supported_versions_line = f"Supported Versions: {supported_versions_text}\n"

        path = metadata.get("path", "Not specified")
        path_line = f"Path: {path}"

        return "".join(
            [
                name_line,
                author_line,
                package_id_line,
                modversion_line,
                supported_versions_line,
                path_line,
            ]
        )

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
                self.list_item_name, Qt.TextElideMode.ElideRight, int(available_width)
            )
            self.main_label.setText(str(shortened_text))
        else:
            self.main_label.setText(self.list_item_name)
        return super().resizeEvent(event)

    def repolish(self, item: CustomListWidgetItem) -> None:
        """
        Repolish the widget items
        """
        item_data = item.data(Qt.ItemDataRole.UserRole)
        error_tooltip = item_data["errors"]
        warning_tooltip = item_data["warnings"]
        # If an error exists we show an error icon with error tooltip
        # If a warning exists we show a warning icon with warning tooltip
        if error_tooltip:
            self.error_icon_label.setHidden(False)
            self.error_icon_label.setToolTip(error_tooltip)
        else:  # Hide the error icon if no error tool tip text
            self.error_icon_label.setHidden(True)
            self.error_icon_label.setToolTip("")
        if warning_tooltip:
            self.warning_icon_label.setHidden(False)
            self.warning_icon_label.setToolTip(warning_tooltip)
        else:  # Hide the warning icon if no warning tool tip text
            self.warning_icon_label.setHidden(True)
            self.warning_icon_label.setToolTip("")
        # Recalculate the widget label's styling based on item data
        widget_object_name = self.main_label.objectName()
        if item_data["filtered"]:
            new_widget_object_name = "ListItemLabelFiltered"
        elif error_tooltip or warning_tooltip:
            new_widget_object_name = "ListItemLabelInvalid"
        else:
            new_widget_object_name = "ListItemLabel"
        if widget_object_name != new_widget_object_name:
            logger.debug("Repolishing: " + new_widget_object_name)
            self.main_label.setObjectName(new_widget_object_name)
            self.main_label.style().unpolish(self.main_label)
            self.main_label.style().polish(self.main_label)

from functools import partial
from typing import Any, Literal

from loguru import logger
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.controllers.settings_controller import SettingsController
from app.utils.app_info import AppInfo
from app.utils.constants import (
    SEARCH_DATA_SOURCE_FILTER_INDEXES,
)
from app.utils.custom_qlabels import AdvancedClickableQLabel
from app.utils.event_bus import EventBus
from app.utils.metadata import MetadataManager
from app.views.mods_panel_icons import ModListIcons
from app.views.mods_panel_list_widget import ModListWidget


class ModSearchFilter:
    """Helper class to encapsulate search and filter functionality for mod lists."""

    def __init__(
        self,
        list_type: Literal["Active", "Inactive"],
        settings_controller: SettingsController,
        metadata_manager: MetadataManager,
        data_source_filter_icons: list[QIcon],
        data_source_filter_tooltips: list[str],
        data_source_filter_type_icons: list[QIcon],
        data_source_filter_type_tooltips: list[str],
        mode_filter_icon: QIcon,
        mode_filter_tooltip: str,
        mode_nofilter_icon: QIcon,
        mode_nofilter_tooltip: str,
    ) -> None:
        self.list_type = list_type
        self.settings_controller = settings_controller
        self.metadata_manager = metadata_manager

        # Filter icons and tooltips
        self.data_source_filter_icons = data_source_filter_icons
        self.data_source_filter_tooltips = data_source_filter_tooltips
        self.data_source_filter_type_icons = data_source_filter_type_icons
        self.data_source_filter_type_tooltips = data_source_filter_type_tooltips
        self.mode_filter_icon = mode_filter_icon
        self.mode_filter_tooltip = mode_filter_tooltip
        self.mode_nofilter_icon = mode_nofilter_icon
        self.mode_nofilter_tooltip = mode_nofilter_tooltip

        # Filter states
        self.filter_data_source_index = 0
        self.data_source_filter_type_index = 0
        self.search_filter_state = True

    def apply_search_and_filters(
        self,
        pattern: str,
        search_filter: QComboBox,
        mod_list: ModListWidget,
        filters_active: bool = False,
    ) -> None:
        """Apply search pattern and filters to the mod list."""
        search_filter_text = search_filter.currentText().lower()
        filter_key = {
            "name": "name",
            "packageid": "packageid",
            "author(s)": "authors",
            "publishedfileid": "publishedfileid",
        }.get(search_filter_text, "name")

        for uuid in mod_list.uuids:
            item = mod_list.item(mod_list.uuids.index(uuid))
            item_data = item.data(Qt.ItemDataRole.UserRole)
            metadata = self.metadata_manager.internal_local_metadata[uuid]

            # Apply filters based on current state
            should_filter = self._should_filter_item(
                item_data, metadata, pattern, filter_key, filters_active
            )

            # Update item visibility based on filter state
            if self.search_filter_state:
                item.setHidden(should_filter)
                item_data["hidden_by_filter"] = should_filter
            else:
                if should_filter and item.isHidden():
                    item.setHidden(False)
                    item_data["hidden_by_filter"] = False

            item_data["filtered"] = should_filter
            item.setData(Qt.ItemDataRole.UserRole, item_data)

    def _should_filter_item(
        self,
        item_data: dict[str, Any],
        metadata: dict[str, Any],
        pattern: str,
        filter_key: str,
        filters_active: bool,
    ) -> bool:
        """Determine if an item should be filtered based on current criteria."""
        # Filter invalid items if enabled in settings
        if (
            self.settings_controller.settings.hide_invalid_mods_when_filtering_toggle
            and item_data["invalid"]
            and filters_active
        ):
            return True

        # Apply search pattern filter
        if pattern and metadata.get(filter_key):
            if pattern.lower() not in str(metadata.get(filter_key)).lower():
                return True

        # Apply data source filter
        if self.filter_data_source_index > 0:  # Not "All Mods"
            data_source = self._get_data_source_filter()
            if data_source != metadata.get("data_source"):
                return True

        # Apply mod type filter
        if self.data_source_filter_type_index > 0:  # Not "All Types"
            mod_type = self._get_mod_type_filter()
            if mod_type == "csharp" and not metadata.get("csharp"):
                return True
            if mod_type == "xml" and metadata.get("csharp"):
                return True

        return False

    def _get_data_source_filter(self) -> str:
        """Get current data source filter based on index."""
        sources = ["all", "git_repo", "steamcmd"]
        return sources[self.filter_data_source_index % len(sources)]

    def _get_mod_type_filter(self) -> str:
        """Get current mod type filter based on index."""
        types = ["all", "csharp", "xml"]
        return types[self.data_source_filter_type_index % len(types)]


class ModsPanel(QWidget):
    """
    This class controls the layout and functionality for the
    active/inactive mods list panel on the GUI.
    """

    list_updated_signal = Signal()
    save_btn_animation_signal = Signal()
    check_dependencies_signal = Signal()

    def __init__(self, settings_controller: SettingsController) -> None:
        """
        Initialize the class.
        Create a ListWidget using the dict of mods. This will
        create a row for every key-value pair in the dict.
        """
        super(ModsPanel, self).__init__()

        # Cache MetadataManager instance and initialize panel
        logger.debug("Initializing ModsPanel")
        self.metadata_manager = MetadataManager.instance()
        self.settings_controller = settings_controller

        # Base layout horizontal, sub-layouts vertical
        self.panel = QHBoxLayout()
        self.active_panel = QVBoxLayout()
        self.inactive_panel = QVBoxLayout()
        # Add vertical layouts to it
        self.panel.addLayout(self.inactive_panel)
        self.panel.addLayout(self.active_panel)

        # Filter icons and tooltips
        self.data_source_filter_icons = [
            QIcon(str(AppInfo().theme_data_folder / "default-icons" / "AppIcon_b.png")),
            ModListIcons.ludeon_icon(),
            ModListIcons.local_icon(),
            ModListIcons.git_icon(),
            ModListIcons.steamcmd_icon(),
            ModListIcons.steam_icon(),
        ]
        self.data_source_filter_tooltips = [
            "Showing All Mods",
            "Showing Core and DLC",
            "Showing Local Mods",
            "Showing Git Mods",
            "Showing SteamCMD Mods",
            "Showing Steam Mods",
        ]
        self.data_source_filter_type_icons = [
            QIcon(str(AppInfo().theme_data_folder / "default-icons" / "AppIcon_b.png")),
            ModListIcons.csharp_icon(),
            ModListIcons.xml_icon(),
        ]
        self.data_source_filter_type_tooltips = [
            "Showing All Mod Types",
            "Showing C# Mods",
            "Showing XML Mods",
        ]

        self.mode_filter_icon = QIcon(
            str(AppInfo().theme_data_folder / "default-icons" / "filter.png")
        )
        self.mode_filter_tooltip = "Hide Filter Disabled"
        self.mode_nofilter_icon = QIcon(
            str(AppInfo().theme_data_folder / "default-icons" / "nofilter.png")
        )
        self.mode_nofilter_tooltip = "Hide Filter Enabled"

        # ACTIVE mod list widget
        self.active_mods_label = QLabel("Active [0]")
        self.active_mods_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.active_mods_label.setObjectName("summaryValue")
        self.active_mods_list = ModListWidget(
            list_type="Active",
            settings_controller=self.settings_controller,
        )
        # Active mods search widgets
        self.active_mods_search_layout = QHBoxLayout()
        self.initialize_active_mods_search_widgets()

        self.errors_summary_layout = QVBoxLayout()
        self.errors_summary_layout.setContentsMargins(0, 0, 0, 0)
        self.errors_summary_layout.setSpacing(2)

        # Add active mods widgets to layout
        self.active_panel.addWidget(self.active_mods_label)
        self.active_panel.addLayout(self.active_mods_search_layout)
        self.active_panel.addWidget(self.active_mods_list)
        self.active_panel.addWidget(self.errors_summary_frame)

        # Initialize inactive mods widgets
        self.inactive_mods_label = QLabel("Inactive [0]")
        self.inactive_mods_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.inactive_mods_label.setObjectName("summaryValue")
        self.inactive_mods_list = ModListWidget(
            list_type="Inactive",
            settings_controller=self.settings_controller,
        )

        # Inactive mods search layout
        self.inactive_mods_search_layout = QHBoxLayout()
        self.initialize_inactive_mods_search_widgets()

        # Add inactive mods widgets to layout
        self.inactive_panel.addWidget(self.inactive_mods_label)
        self.inactive_panel.addLayout(self.inactive_mods_search_layout)
        self.inactive_panel.addWidget(self.inactive_mods_list)

        # Connect signals and slots
        self.connect_signals()

        logger.debug("Finished ModsPanel initialization")

    def initialize_active_mods_search_widgets(self) -> None:
        """Initialize widgets for active mods search layout."""
        # Initialize errors summary frame first
        self.errors_summary_frame = QFrame()
        self.errors_summary_frame.setObjectName("errorFrame")

        self.active_mods_filter_data_source_index = 0
        self.active_mods_data_source_filter = SEARCH_DATA_SOURCE_FILTER_INDEXES[
            self.active_mods_filter_data_source_index
        ]
        self.active_mods_filter_data_source_button = QToolButton()
        self.active_mods_filter_data_source_button.setIcon(
            self.data_source_filter_icons[self.active_mods_filter_data_source_index]
        )
        self.active_mods_filter_data_source_button.setToolTip(
            self.data_source_filter_tooltips[self.active_mods_filter_data_source_index]
        )
        self.active_mods_filter_data_source_button.clicked.connect(
            self.on_active_mods_search_data_source_filter
        )
        self.active_data_source_filter_type_index = 0
        self.active_mods_data_source_filter_type = SEARCH_DATA_SOURCE_FILTER_INDEXES[
            self.active_data_source_filter_type_index
        ]
        self.active_data_source_filter_type_button = QToolButton()
        self.active_data_source_filter_type_button.setIcon(
            self.data_source_filter_type_icons[
                self.active_data_source_filter_type_index
            ]
        )
        self.active_data_source_filter_type_button.setToolTip(
            self.data_source_filter_type_tooltips[
                self.active_data_source_filter_type_index
            ]
        )
        self.active_data_source_filter_type_button.clicked.connect(
            self.on_active_mods_search_data_source_filter_type
        )
        self.active_mods_search_filter_state = True
        self.active_mods_search_mode_filter_button = QToolButton()
        self.active_mods_search_mode_filter_button.setIcon(self.mode_filter_icon)
        self.active_mods_search_mode_filter_button.setToolTip(self.mode_filter_tooltip)
        self.active_mods_search_mode_filter_button.clicked.connect(
            self.on_active_mods_mode_filter_toggle
        )
        self.active_mods_search = QLineEdit()
        self.active_mods_search.setClearButtonEnabled(True)
        self.active_mods_search.textChanged.connect(self.on_active_mods_search)
        self.active_mods_search.inputRejected.connect(self.on_active_mods_search_clear)
        self.active_mods_search.setPlaceholderText("Search by...")
        self.active_mods_search_clear_button = self.active_mods_search.findChild(
            QToolButton
        )
        if not isinstance(self.active_mods_search_clear_button, QToolButton):
            raise TypeError("Could not find QToolButton in QLineEdit")
        self.active_mods_search_clear_button.setEnabled(True)
        self.active_mods_search_clear_button.clicked.connect(
            self.on_active_mods_search_clear
        )
        self.active_mods_search_filter: QComboBox = QComboBox()
        self.active_mods_search_filter.setObjectName("MainUI")
        self.active_mods_search_filter.setMaximumWidth(125)
        self.active_mods_search_filter.addItems(
            ["Name", "PackageId", "Author(s)", "PublishedFileId"]
        )
        # Active mods search layouts
        self.active_mods_search_layout.addWidget(
            self.active_mods_filter_data_source_button
        )
        if self.settings_controller.settings.mod_type_filter_toggle:
            self.active_mods_search_layout.addWidget(
                self.active_data_source_filter_type_button
            )
        self.active_mods_search_layout.addWidget(
            self.active_mods_search_mode_filter_button
        )
        self.active_mods_search_layout.addWidget(self.active_mods_search, 45)
        self.active_mods_search_layout.addWidget(self.active_mods_search_filter, 70)
        # Active mods list Errors/warnings widgets
        self.errors_summary_layout = QVBoxLayout()
        self.errors_summary_layout.setContentsMargins(0, 0, 0, 0)
        self.errors_summary_layout.setSpacing(2)
        # Create horizontal layout for warnings and errors
        self.warnings_errors_layout = QHBoxLayout()
        self.warnings_errors_layout.setSpacing(2)
        self.warnings_icon: QLabel = QLabel()
        self.warnings_icon.setPixmap(ModListIcons.warning_icon().pixmap(QSize(20, 20)))
        self.warnings_text: AdvancedClickableQLabel = AdvancedClickableQLabel(
            "0 warnings"
        )
        self.warnings_text.setObjectName("summaryValue")
        self.warnings_text.setToolTip("Click to only show mods with warnings")
        self.errors_icon: QLabel = QLabel()
        self.errors_icon.setPixmap(ModListIcons.error_icon().pixmap(QSize(20, 20)))
        self.errors_text: AdvancedClickableQLabel = AdvancedClickableQLabel("0 errors")
        self.errors_text.setObjectName("summaryValue")
        self.errors_text.setToolTip("Click to only show mods with errors")
        self.warnings_layout = QHBoxLayout()
        self.warnings_layout.addWidget(self.warnings_icon, 1)
        self.warnings_layout.addWidget(self.warnings_text, 99)
        self.errors_layout = QHBoxLayout()
        self.errors_layout.addWidget(self.errors_icon, 1)
        self.errors_layout.addWidget(self.errors_text, 99)
        self.warnings_errors_layout.addLayout(self.warnings_layout, 50)
        self.warnings_errors_layout.addLayout(self.errors_layout, 50)

        # Add warnings/errors layout to main vertical layout
        self.errors_summary_layout.addLayout(self.warnings_errors_layout)

        # Create and add Use This Instead button
        self.use_this_instead_button = QPushButton('Check "Use This Instead" Database')
        self.use_this_instead_button.setObjectName("useThisInsteadButton")
        self.use_this_instead_button.clicked.connect(
            EventBus().use_this_instead_clicked.emit
        )
        self.errors_summary_layout.addWidget(self.use_this_instead_button)

        # Create and add Check Dependencies button
        self.check_dependencies_button: QPushButton = QPushButton("Check Dependencies")
        self.check_dependencies_button.setObjectName("MainUI")
        self.errors_summary_layout.addWidget(self.check_dependencies_button)
        self.check_dependencies_button.clicked.connect(
            self.check_dependencies_signal.emit
        )

        # Add to the outer frame
        self.errors_summary_frame.setLayout(self.errors_summary_layout)
        self.errors_summary_frame.setHidden(True)

    def initialize_inactive_mods_search_widgets(self) -> None:
        """Initialize widgets for inactive mods search layout."""
        self.inactive_mods_filter_data_source_index = 0
        self.inactive_mods_data_source_filter = SEARCH_DATA_SOURCE_FILTER_INDEXES[
            self.inactive_mods_filter_data_source_index
        ]
        self.inactive_mods_filter_data_source_button = QToolButton()
        self.inactive_mods_filter_data_source_button.setIcon(
            self.data_source_filter_icons[self.inactive_mods_filter_data_source_index]
        )
        self.inactive_mods_filter_data_source_button.setToolTip(
            self.data_source_filter_tooltips[
                self.inactive_mods_filter_data_source_index
            ]
        )
        self.inactive_mods_filter_data_source_button.clicked.connect(
            self.on_inactive_mods_search_data_source_filter
        )
        self.inactive_data_source_filter_type_index = 0
        self.inactive_mods_data_source_filter_type = SEARCH_DATA_SOURCE_FILTER_INDEXES[
            self.inactive_data_source_filter_type_index
        ]
        self.inactive_data_source_filter_type_button = QToolButton()
        self.inactive_data_source_filter_type_button.setIcon(
            self.data_source_filter_type_icons[
                self.inactive_data_source_filter_type_index
            ]
        )
        self.inactive_data_source_filter_type_button.setToolTip(
            self.data_source_filter_type_tooltips[
                self.inactive_data_source_filter_type_index
            ]
        )
        self.inactive_data_source_filter_type_button.clicked.connect(
            self.on_inactive_mods_search_data_source_filter_type
        )
        self.inactive_mods_search_filter_state = True
        self.inactive_mods_search_mode_filter_button = QToolButton()
        self.inactive_mods_search_mode_filter_button.setIcon(self.mode_filter_icon)
        self.inactive_mods_search_mode_filter_button.setToolTip(
            self.mode_filter_tooltip
        )
        self.inactive_mods_search_mode_filter_button.clicked.connect(
            self.on_inactive_mods_mode_filter_toggle
        )
        self.inactive_mods_search = QLineEdit()
        self.inactive_mods_search.setClearButtonEnabled(True)
        self.inactive_mods_search.textChanged.connect(self.on_inactive_mods_search)
        self.inactive_mods_search.inputRejected.connect(
            self.on_inactive_mods_search_clear
        )
        self.inactive_mods_search.setPlaceholderText("Search by...")
        self.inactive_mods_search_clear_button = self.inactive_mods_search.findChild(
            QToolButton
        )
        if not isinstance(self.inactive_mods_search_clear_button, QToolButton):
            raise TypeError("Could not find QToolButton in QLineEdit")
        self.inactive_mods_search_clear_button.setEnabled(True)
        self.inactive_mods_search_clear_button.clicked.connect(
            self.on_inactive_mods_search_clear
        )
        self.inactive_mods_search_filter: QComboBox = QComboBox()
        self.inactive_mods_search_filter.setObjectName("MainUI")
        self.inactive_mods_search_filter.setMaximumWidth(140)
        self.inactive_mods_search_filter.addItems(
            ["Name", "PackageId", "Author(s)", "PublishedFileId"]
        )
        self.inactive_mods_search_layout.addWidget(
            self.inactive_mods_filter_data_source_button
        )
        if self.settings_controller.settings.mod_type_filter_toggle:
            self.inactive_mods_search_layout.addWidget(
                self.inactive_data_source_filter_type_button
            )
        self.inactive_mods_search_layout.addWidget(
            self.inactive_mods_search_mode_filter_button
        )
        self.inactive_mods_search_layout.addWidget(self.inactive_mods_search, 45)
        self.inactive_mods_search_layout.addWidget(self.inactive_mods_search_filter, 70)

        # Adding Completer.
        # self.completer = QCompleter(self.active_mods_list.get_list_items())
        # self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        # self.active_mods_search.setCompleter(self.completer)
        # self.inactive_mods_search.setCompleter(self.completer)

        # Connect signals and slots

    def connect_signals(self) -> None:
        self.active_mods_list.list_update_signal.connect(
            self.on_active_mods_list_updated
        )
        self.inactive_mods_list.list_update_signal.connect(
            self.on_inactive_mods_list_updated
        )
        self.active_mods_list.recalculate_warnings_signal.connect(
            partial(self.recalculate_list_errors_warnings, list_type="Active")
        )
        self.inactive_mods_list.recalculate_warnings_signal.connect(
            partial(self.recalculate_list_errors_warnings, list_type="Inactive")
        )

    def mod_list_updated(
        self, count: str, list_type: str, recalculate_list_errors_warnings: bool = True
    ) -> None:
        # If count is 'drop', it indicates that the update was just a drag and drop within the list
        if count != "drop":
            logger.info(f"{list_type} mod count changed to: {count}")
            self.update_count(list_type=list_type)
        # Signal save button animation
        self.save_btn_animation_signal.emit()
        if recalculate_list_errors_warnings:
            # Update the mod list widget errors and warnings
            self.recalculate_list_errors_warnings(list_type=list_type)

    def on_active_mods_list_updated(self, count: str) -> None:
        self.mod_list_updated(count=count, list_type="Active")

    def on_active_mods_search(self, pattern: str) -> None:
        """Handle text changes in the active mods search field.

        Args:
            pattern: The current search pattern text
        """
        self.signal_search_and_filters(list_type="Active", pattern=pattern)

    def on_active_mods_search_clear(self: "ModsPanel") -> None:
        """Clear the active mods search field and reset filters."""
        self.signal_clear_search(list_type="Active")

    def on_active_mods_search_data_source_filter(self: "ModsPanel") -> None:
        """Handle data source filter button click for active mods."""
        self.signal_search_source_filter(list_type="Active")

    def on_active_mods_search_data_source_filter_type(self) -> None:
        self.apply_mods_filter_type(list_type="Active")

    def on_active_mods_mode_filter_toggle(self) -> None:
        self.signal_search_mode_filter(list_type="Active")

    def on_inactive_mods_list_updated(self, count: str) -> None:
        self.mod_list_updated(count=count, list_type="Inactive")

    def on_inactive_mods_search(self, pattern: str) -> None:
        """Handle text changes in the inactive mods search field.

        Args:
            pattern: The current search pattern text
        """
        self.signal_search_and_filters(list_type="Inactive", pattern=pattern)

    def on_inactive_mods_search_clear(self: "ModsPanel") -> None:
        """Clear the inactive mods search field and reset filters."""
        self.signal_clear_search(list_type="Inactive")

    def on_inactive_mods_search_data_source_filter(self: "ModsPanel") -> None:
        """Handle data source filter button click for inactive mods."""
        self.signal_search_source_filter(list_type="Inactive")

    def on_inactive_mods_search_data_source_filter_type(self) -> None:
        self.apply_mods_filter_type(list_type="Inactive")

    def on_inactive_mods_mode_filter_toggle(self) -> None:
        self.signal_search_mode_filter(list_type="Inactive")

    def on_mod_created(self, uuid: str) -> None:
        self.inactive_mods_list.append_new_item(uuid)

    def apply_mods_filter_type(self, list_type: str) -> None:
        if list_type not in ["Active", "Inactive"]:
            raise ValueError(f"Invalid list type: {list_type}")

        # Define the mod types
        mod_types = ["csharp", "xml"]
        source_filter_index: int = (
            self.active_data_source_filter_type_index
            if list_type == "Active"
            else self.inactive_data_source_filter_type_index
        )

        if list_type == "Active":
            button = self.active_data_source_filter_type_button
            search = self.active_mods_search
            source_index = source_filter_index
        elif list_type == "Inactive":
            button = self.inactive_data_source_filter_type_button
            search = self.inactive_mods_search
            source_index = source_filter_index
        else:
            raise NotImplementedError(f"Unknown list type: {list_type}")

        # Update the filter index
        if source_index < (len(self.data_source_filter_type_icons) - 1):
            source_index += 1
        else:
            source_index = 0

        button.setIcon(self.data_source_filter_type_icons[source_index])
        button.setToolTip(self.data_source_filter_type_tooltips[source_index])

        # Update the relevant index for the list type
        if list_type == "Active":
            self.active_data_source_filter_type_index = source_index
            self.active_mods_data_source_filter_type = (
                SEARCH_DATA_SOURCE_FILTER_INDEXES[source_index]
            )
        elif list_type == "Inactive":
            self.inactive_data_source_filter_type_index = source_index
            self.inactive_mods_data_source_filter_type = (
                SEARCH_DATA_SOURCE_FILTER_INDEXES[source_index]
            )

        mod_list = (
            self.active_mods_list if list_type == "Active" else self.inactive_mods_list
        )

        # Apply filtering based on the selected type
        for uuid in mod_list.uuids:
            item = mod_list.item(mod_list.uuids.index(uuid))
            item_data = item.data(Qt.ItemDataRole.UserRole)

            # Determine the mod type
            mod_type = (
                "csharp"
                if self.metadata_manager.internal_local_metadata.get(uuid, {}).get(
                    "csharp"
                )
                else "xml"
            )
            if mod_type and mod_types:
                item.setData(Qt.ItemDataRole.UserRole, item_data)

        if source_index == 0:
            filters_active = False
        else:
            filters_active = True
        # Trigger search and filters
        self.signal_search_and_filters(
            list_type=list_type,
            pattern=search.text(),
            filters_active=filters_active,
        )

    def on_mod_deleted(self, uuid: str) -> None:
        if uuid in self.active_mods_list.uuids:
            index = self.active_mods_list.uuids.index(uuid)
            self.active_mods_list.takeItem(index)
            self.active_mods_list.uuids.pop(index)
            self.update_count(list_type="Active")
        elif uuid in self.inactive_mods_list.uuids:
            index = self.inactive_mods_list.uuids.index(uuid)
            self.inactive_mods_list.takeItem(index)
            self.inactive_mods_list.uuids.pop(index)
            self.update_count(list_type="Inactive")

    def on_mod_metadata_updated(self, uuid: str) -> None:
        if uuid in self.active_mods_list.uuids:
            self.active_mods_list.rebuild_item_widget_from_uuid(uuid=uuid)
        elif uuid in self.inactive_mods_list.uuids:
            self.inactive_mods_list.rebuild_item_widget_from_uuid(uuid=uuid)

    def recalculate_list_errors_warnings(self, list_type: str) -> None:
        if list_type == "Active":
            # Check if all visible items have their widgets loaded
            self.active_mods_list.check_widgets_visible()
            # Calculate internal errors and warnings for all mods in the respective mod list
            total_error_text, total_warning_text, num_errors, num_warnings = (
                self.active_mods_list.recalculate_internal_errors_warnings()
            )
            # Calculate total errors and warnings and set the text and tool tip for the summary
            if total_error_text or total_warning_text or num_errors or num_warnings:
                self.errors_summary_frame.setHidden(False)
                padding = " "
                self.warnings_text.setText(f"{padding}{num_warnings} warning(s)")
                self.errors_text.setText(f"{padding}{num_errors} error(s)")
                self.errors_icon.setToolTip(
                    total_error_text.lstrip() if total_error_text else ""
                )
                self.warnings_icon.setToolTip(
                    total_warning_text.lstrip() if total_warning_text else ""
                )
            else:  # Hide the summary if there are no errors or warnings
                self.errors_summary_frame.setHidden(True)
                self.warnings_text.setText("0 warnings")
                self.errors_text.setText("0 errors")
                self.errors_icon.setToolTip("")
                self.warnings_icon.setToolTip("")
            # First time, and when Refreshing, the slot will evaluate false and do nothing.
            # The purpose of this is for the _do_save_animation slot in the main_content_panel
            EventBus().list_updated_signal.emit()
        else:
            # Check if all visible items have their widgets loaded
            self.inactive_mods_list.check_widgets_visible()
            # Calculate internal errors and warnings for all mods in the respective mod list
            self.inactive_mods_list.recalculate_internal_errors_warnings()

    def signal_clear_search(
        self, list_type: str, recalculate_list_errors_warnings: bool = True
    ) -> None:
        if list_type == "Active":
            self.active_mods_search.clear()
            self.signal_search_and_filters(
                list_type=list_type,
                pattern="",
                recalculate_list_errors_warnings=recalculate_list_errors_warnings,
            )
            self.active_mods_search.clearFocus()
        elif list_type == "Inactive":
            self.inactive_mods_search.clear()
            self.signal_search_and_filters(
                list_type=list_type,
                pattern="",
                recalculate_list_errors_warnings=recalculate_list_errors_warnings,
            )
            self.inactive_mods_search.clearFocus()

    def signal_search_and_filters(
        self,
        list_type: str,
        pattern: str,
        filters_active: bool = False,
        recalculate_list_errors_warnings: bool = True,
    ) -> None:
        if list_type not in ["Active", "Inactive"]:
            raise ValueError(f"Invalid list type: {list_type}")

        if not isinstance(pattern, str):
            pattern = str(pattern)
        """
        Performs a search and/or applies filters based on the given parameters.

        Called anytime the search bar text changes or the filters change.

        Args:
            list_type (str): The type of list to search within (Active or Inactive).
            pattern (str): The pattern to search for.
            filters_active (bool): If any filter is active (inc. pattern search).
            recalculate_list_errors_warnings (bool): If the list errors and warnings should be recalculated, defaults to True.
        """

        _filter = None
        filter_state = None  # The 'Hide Filter' state
        source_filter = None
        uuids = None
        # Notify controller when search bar text or any filters change
        if list_type == "Active":
            EventBus().filters_changed_in_active_modlist.emit()
        elif list_type == "Inactive":
            EventBus().filters_changed_in_inactive_modlist.emit()
        # Determine which list to filter
        if list_type == "Active":
            _filter = self.active_mods_search_filter
            filter_state = self.active_mods_search_filter_state
            source_filter = self.active_mods_data_source_filter
            uuids = self.active_mods_list.uuids
        elif list_type == "Inactive":
            _filter = self.inactive_mods_search_filter
            filter_state = self.inactive_mods_search_filter_state
            source_filter = self.inactive_mods_data_source_filter
            uuids = self.inactive_mods_list.uuids
        else:
            raise NotImplementedError(f"Unknown list type: {list_type}")
        # Evaluate the search filter state for the list
        search_filter = None
        if _filter.currentText() == "Name":
            search_filter = "name"
        elif _filter.currentText() == "PackageId":
            search_filter = "packageid"
        elif _filter.currentText() == "Author(s)":
            search_filter = "authors"
        elif _filter.currentText() == "PublishedFileId":
            search_filter = "publishedfileid"
        # Filter the list using any search and filter state
        for uuid in uuids:
            item = (
                self.active_mods_list.item(uuids.index(uuid))
                if list_type == "Active"
                else self.inactive_mods_list.item(uuids.index(uuid))
            )
            if item is None:
                continue
            item_data = item.data(Qt.ItemDataRole.UserRole)
            metadata = self.metadata_manager.internal_local_metadata[uuid]
            if pattern != "":
                filters_active = True
            # Hide invalid items if enabled in settings
            if self.settings_controller.settings.hide_invalid_mods_when_filtering_toggle:
                invalid = item_data["invalid"]
                # TODO: I dont think filtered should be set at all for invalid items... I misunderstood what it represents
                if invalid and filters_active:
                    item_data["filtered"] = True
                    item.setHidden(True)
                    continue
                elif invalid and not filters_active:
                    item_data["filtered"] = False
                    item.setHidden(False)
            # Check if the item is filtered
            item_filtered = item_data["filtered"]
            # Check if the item should be filtered or not based on search filter
            if (
                pattern
                and metadata.get(search_filter)
                and pattern.lower() not in str(metadata.get(search_filter)).lower()
            ):
                item_filtered = True
            elif source_filter == "all":  # or data source
                item_filtered = False
            elif source_filter == "git_repo":
                item_filtered = not metadata.get("git_repo")
            elif source_filter == "steamcmd":
                item_filtered = not metadata.get("steamcmd")
            elif source_filter != metadata.get("data_source"):
                item_filtered = True

            type_filter_index = (
                self.active_data_source_filter_type_index
                if list_type == "Active"
                else self.inactive_data_source_filter_type_index
            )

            if type_filter_index == 1 and not metadata.get("csharp"):
                item_filtered = True
            elif type_filter_index == 2 and metadata.get("csharp"):
                item_filtered = True

            # Check if the item should be filtered or hidden based on filter state
            if filter_state:
                item.setHidden(item_filtered)
                if item_filtered:
                    item_data["hidden_by_filter"] = True
                    item_filtered = False
                else:
                    item_data["hidden_by_filter"] = False
            else:
                if item_filtered and item.isHidden():
                    item.setHidden(False)
                    item_data["hidden_by_filter"] = False
            # Update item data
            item_data["filtered"] = item_filtered
            item.setData(Qt.ItemDataRole.UserRole, item_data)
        self.mod_list_updated(
            str(len(uuids)),
            list_type,
            recalculate_list_errors_warnings=recalculate_list_errors_warnings,
        )

    def signal_search_mode_filter(self, list_type: str) -> None:
        if list_type == "Active":
            # Toggle the mode filter state
            self.active_mods_search_filter_state = (
                not self.active_mods_search_filter_state
            )
            # Update the icon based on the current state
            if self.active_mods_search_filter_state:
                self.active_mods_search_mode_filter_button.setIcon(
                    self.mode_filter_icon
                )  # Active state icon
                self.active_mods_search_mode_filter_button.setToolTip(
                    self.mode_filter_tooltip
                )  # Active state tooltip
            else:
                self.active_mods_search_mode_filter_button.setIcon(
                    self.mode_nofilter_icon
                )  # Inactive state icon
                self.active_mods_search_mode_filter_button.setToolTip(
                    self.mode_nofilter_tooltip
                )  # Inactive state tooltip
            pattern = self.active_mods_search.text()
        elif list_type == "Inactive":
            # Toggle the mode filter state
            self.inactive_mods_search_filter_state = (
                not self.inactive_mods_search_filter_state
            )
            # Update the icon based on the current state
            if self.inactive_mods_search_filter_state:
                self.inactive_mods_search_mode_filter_button.setIcon(
                    self.mode_filter_icon
                )  # Active state icon
                self.inactive_mods_search_mode_filter_button.setToolTip(
                    self.mode_filter_tooltip
                )  # Active state tooltip
            else:
                self.inactive_mods_search_mode_filter_button.setIcon(
                    self.mode_nofilter_icon
                )  # Inactive state icon
                self.inactive_mods_search_mode_filter_button.setToolTip(
                    self.mode_nofilter_tooltip
                )  # Inactive state tooltip
            pattern = self.inactive_mods_search.text()
        else:
            raise NotImplementedError(f"Unknown list type: {list_type}")

        self.signal_search_and_filters(list_type=list_type, pattern=pattern)

    def signal_search_source_filter(self, list_type: str) -> None:
        if list_type == "Active":
            button = self.active_mods_filter_data_source_button
            search = self.active_mods_search
            source_index: int = self.active_mods_filter_data_source_index
        elif list_type == "Inactive":
            button = self.inactive_mods_filter_data_source_button
            search = self.inactive_mods_search
            source_index = self.inactive_mods_filter_data_source_index
        else:
            raise NotImplementedError(f"Unknown list type: {list_type}")
        # Indexes by the icon
        if source_index < (len(self.data_source_filter_icons) - 1):
            source_index += 1
        else:
            source_index = 0
        button.setIcon(self.data_source_filter_icons[source_index])
        button.setToolTip(self.data_source_filter_tooltips[source_index])
        if list_type == "Active":
            self.active_mods_filter_data_source_index = source_index
            self.active_mods_data_source_filter = SEARCH_DATA_SOURCE_FILTER_INDEXES[
                source_index
            ]
        elif list_type == "Inactive":
            self.inactive_mods_filter_data_source_index = source_index
            self.inactive_mods_data_source_filter = SEARCH_DATA_SOURCE_FILTER_INDEXES[
                source_index
            ]
        if source_index == 0:
            filters_active = False
        else:
            filters_active = True
        # Filter widgets by data source, while preserving any active search pattern
        self.signal_search_and_filters(
            list_type=list_type, pattern=search.text(), filters_active=filters_active
        )

    def update_count(self, list_type: str) -> None:
        # Calculate filtered items
        label = (
            self.active_mods_label
            if list_type == "Active"
            else self.inactive_mods_label
        )
        search = (
            self.active_mods_search
            if list_type == "Active"
            else self.inactive_mods_search
        )
        uuids = (
            self.active_mods_list.uuids
            if list_type == "Active"
            else self.inactive_mods_list.uuids
        )
        num_filtered = 0
        num_unfiltered = 0
        for uuid in uuids:
            item = (
                self.active_mods_list.item(uuids.index(uuid))
                if list_type == "Active"
                else self.inactive_mods_list.item(uuids.index(uuid))
            )
            if item is None:
                continue
            item_data = item.data(Qt.ItemDataRole.UserRole)
            item_filtered = item_data["filtered"]

            if item.isHidden() or item_filtered:
                num_filtered += 1
            else:
                num_unfiltered += 1
        if search.text():
            label.setText(
                f"{list_type} [{num_unfiltered}/{num_filtered + num_unfiltered}]"
            )
        elif num_filtered > 0:
            # If any filter is active, show how many mods are displayed out of total
            label.setText(
                f"{list_type} [{num_unfiltered}/{num_filtered + num_unfiltered}]"
            )
        else:
            label.setText(f"{list_type} [{num_filtered + num_unfiltered}]")

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from enum import Enum
from functools import partial
from typing import Any, Callable, Sequence, TypeVar

from loguru import logger
from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QKeyEvent, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLayout,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from app.controllers.metadata_controller import MetadataController
from app.models.metadata.metadata_structure import AboutXmlMod, ListedMod, ModType
from app.models.operation_mode import OperationMode
from app.models.settings import Settings
from app.utils.button_factory import ButtonConfig, ButtonFactory, ButtonType
from app.utils.event_bus import EventBus
from app.utils.generic import platform_specific_open
from app.utils.mod_info import ModInfo
from app.utils.mod_utils import get_mod_path_from_pfid, resolve_aux_timestamps
from app.views.deletion_menu import ModDeletionMenu
from app.views.mod_info_panel import ClickablePathLabel

# By default, we assume Stretch for all columns.
# Tuples should be used if this should be overridden
HeaderColumn = str | tuple[str, QHeaderView.ResizeMode]


@dataclass
class UIElements:
    """Dataclass to group UI elements for better organization."""

    title: QLabel
    details_label: QLabel
    editor_select_all_button: QPushButton
    editor_cancel_button: QPushButton


@dataclass
class Layouts:
    """Dataclass to group layout elements for better organization."""

    upper_layout: QVBoxLayout
    lower_layout: QVBoxLayout
    details_layout: QVBoxLayout
    editor_layout: QVBoxLayout
    editor_actions_layout: QHBoxLayout
    editor_checkbox_actions_layout: QHBoxLayout
    editor_main_actions_layout: QHBoxLayout
    editor_exit_actions_layout: QHBoxLayout


class ColumnIndex(Enum):
    """Enumeration for table column indices to eliminate magic numbers."""

    CHECKBOX = 0
    NAME = 1
    AUTHOR = 2
    PACKAGE_ID = 3
    PUBLISHED_FILE_ID = 4
    SUPPORTED_VERSIONS = 5
    MOD_DOWNLOADED = 6
    UPDATED_ON_WORKSHOP = 7
    SOURCE = 8
    PATH = 9
    WORKSHOP_PAGE = 10


class BaseModsPanel(QWidget):
    """
    Base class used for multiple panels that display a list of mods.
    """

    # Type hints for instance variables
    metadata_controller: MetadataController
    settings: Any
    editor_model: QStandardItemModel
    editor_table_view: QTableView
    ui_elements: UIElements
    layouts: Layouts

    # Common column definitions for standardization
    COL_MOD_NAME = "Name"
    COL_AUTHOR = "Author"
    COL_PACKAGE_ID = "Package ID"
    COL_PUBLISHED_FILE_ID = "Published File Id"
    COL_SUPPORTED_VERSIONS = "Supported Versions"
    COL_MOD_DOWNLOADED = "Mod Downloaded"
    COL_UPDATED_ON_WORKSHOP = "Updated on Workshop"
    COL_SOURCE = "Source"
    COL_PATH = "Path"
    COL_WORKSHOP_PAGE = "Workshop Page"

    def _setup_metadata(self) -> None:
        """Set up metadata controller and settings controller."""
        self.metadata_controller = self._metadata_controller
        self.settings = self.metadata_controller.settings
        self.metadata_controller.metadata_refreshed.connect(
            self._populate_from_metadata
        )

    def _get_steam_client_integration_enabled(self) -> bool:
        """
        Get whether Steam client integration is enabled.

        Returns:
            True if Steam client integration is enabled, False otherwise.
        """
        return self.settings.instances[
            self.settings.current_instance
        ].steam_client_integration

    def _setup_ui_elements(
        self,
        object_name: str,
        window_title: str,
        title_text: str,
        details_text: str,
    ) -> None:
        """Set up basic UI elements like title and details."""
        self.installEventFilter(self)
        self.setObjectName(object_name)
        self.ui_elements.title = QLabel(title_text)
        self.ui_elements.title.setObjectName("baseModsPanelTitle")
        self.ui_elements.title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.ui_elements.details_label = QLabel(details_text)
        self.ui_elements.details_label.setObjectName("baseModsPanelDetails")
        self.ui_elements.details_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.setWindowTitle(window_title)

    def _setup_layout_structure(self) -> None:
        """Set up the main layout structure."""
        self.layouts.details_layout.addWidget(self.ui_elements.details_label)
        self.layouts.upper_layout.addLayout(self.layouts.details_layout)

    def _setup_table_and_model(
        self,
        additional_columns: Sequence[HeaderColumn],
        sorting_enabled: bool = False,
    ) -> None:
        """
        Set up the complete table model and view with headers.

        This unified method initializes the QStandardItemModel, QTableView, and all headers
        in one consistent operation, preventing configuration conflicts or partial initialization.

        Args:
            additional_columns: List of column definitions (names or tuples of name/ResizeMode)
            sorting_enabled: Whether column sorting is enabled (default: False)
        """
        # Set up model with header labels
        self.editor_model = QStandardItemModel(0, len(additional_columns) + 1)
        editor_header_labels = ["✔"] + [
            col[0] if isinstance(col, tuple) else col for col in additional_columns
        ]
        self.editor_model.setHorizontalHeaderLabels(editor_header_labels)

        # Set up table view
        self.editor_table_view = QTableView()
        self.editor_table_view.setModel(self.editor_model)
        self.editor_table_view.setSortingEnabled(sorting_enabled)
        self.editor_table_view.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.editor_table_view.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection
        )
        self.editor_table_view.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )

        # Set up headers - checkbox column resizes to contents
        header = self.editor_table_view.horizontalHeader()
        header.setSectionResizeMode(
            ColumnIndex.CHECKBOX.value, QHeaderView.ResizeMode.ResizeToContents
        )

        # Additional columns: use specified ResizeMode or default to Stretch
        for column_index, column in enumerate(additional_columns):
            if isinstance(column, tuple):
                resize_mode = column[1]
            else:
                resize_mode = QHeaderView.ResizeMode.Stretch
            header.setSectionResizeMode(
                ColumnIndex.CHECKBOX.value + column_index + 1, resize_mode
            )

        # Set vertical header to resize to contents
        self.editor_table_view.verticalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )

    def _setup_action_buttons(self) -> None:
        """Set up the action buttons layout."""
        self.layouts.editor_actions_layout.addLayout(
            self.layouts.editor_checkbox_actions_layout
        )
        self.layouts.editor_actions_layout.addStretch(25)
        self.layouts.editor_actions_layout.addLayout(
            self.layouts.editor_main_actions_layout
        )
        self.layouts.editor_actions_layout.addStretch(25)
        self.layouts.editor_actions_layout.addLayout(
            self.layouts.editor_exit_actions_layout
        )

        self.layouts.editor_checkbox_actions_layout.addWidget(
            self.ui_elements.editor_select_all_button
        )

        self.ui_elements.editor_cancel_button.clicked.connect(self.close)
        self.layouts.editor_exit_actions_layout.addWidget(
            self.ui_elements.editor_cancel_button
        )

        self.layouts.editor_layout.addWidget(self.editor_table_view)
        self.layouts.editor_layout.addLayout(self.layouts.editor_actions_layout)

    def _setup_main_layout(self) -> None:
        """Set up the main layout structure."""
        layout = QVBoxLayout()
        layout.addWidget(self.ui_elements.title)
        layout.addLayout(self.layouts.upper_layout)
        layout.addLayout(self.layouts.lower_layout)

        self.layouts.lower_layout.addLayout(self.layouts.editor_layout)
        self.setLayout(layout)
        # TODO: let user configure window launch state and size from settings controller
        self.resize(900, 600)

    def _setup_table(self, additional_columns: Sequence[HeaderColumn]) -> None:
        """Set up the table configuration."""
        pass  # Table setup is already done in _setup_ui

    def _setup_buttons(self) -> None:
        """Set up buttons if needed."""
        pass  # Buttons are set up in _setup_ui

    def _initialize_components(self) -> None:
        """Initialize core components."""
        self._setup_metadata()

    def _setup_components(
        self,
        object_name: str,
        window_title: str,
        title_text: str,
        details_text: str,
        additional_columns: Sequence[HeaderColumn],
    ) -> None:
        """Set up UI and table components."""
        self._setup_ui_elements(object_name, window_title, title_text, details_text)
        self._setup_layout_structure()
        self._setup_table_and_model(additional_columns)
        self._setup_action_buttons()
        self._setup_main_layout()
        self._setup_table(additional_columns)
        self._setup_buttons()

    def _initialize_ui_elements(self) -> None:
        """Initialize UI elements dataclasses."""
        factory = self.get_button_factory()
        self.ui_elements = UIElements(
            title=QLabel(),
            details_label=QLabel(),
            editor_select_all_button=factory.create_select_all_button(),
            editor_cancel_button=QPushButton(self.tr("Do nothing and exit")),
        )
        self.ui_elements.editor_cancel_button.setObjectName("dangerButton")

    def _initialize_layouts(self) -> None:
        """Initialize layout dataclasses."""
        self.layouts = Layouts(
            upper_layout=QVBoxLayout(),
            lower_layout=QVBoxLayout(),
            details_layout=QVBoxLayout(),
            editor_layout=QVBoxLayout(),
            editor_actions_layout=QHBoxLayout(),
            editor_checkbox_actions_layout=QHBoxLayout(),
            editor_main_actions_layout=QHBoxLayout(),
            editor_exit_actions_layout=QHBoxLayout(),
        )

    def __init__(
        self,
        object_name: str,
        window_title: str,
        title_text: str,
        details_text: str,
        additional_columns: Sequence[HeaderColumn],
        metadata_controller: MetadataController,
    ):
        super().__init__()
        self._metadata_controller = metadata_controller
        self._initialize_ui_elements()
        self._initialize_layouts()
        self._initialize_components()
        self._setup_components(
            object_name, window_title, title_text, details_text, additional_columns
        )

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.KeyPress:
            key_event = QKeyEvent(event)  # type: ignore
            if key_event.key() == Qt.Key.Key_Escape:
                # Don't close AcfLogReader on Escape key (it's a persistent view)
                if self.__class__.__name__ != "AcfLogReader":
                    self.close()
                return True

        return super().eventFilter(watched, event)

    def _add_row(
        self,
        items: list[QStandardItem],
        default_checkbox_state: bool = False,
    ) -> None:
        items = [
            QStandardItem(),
        ] + items
        self.editor_model.appendRow(items)
        checkbox_index = items[0].index()
        checkbox = QCheckBox()
        checkbox.setObjectName("selectCheckbox")
        checkbox.setChecked(default_checkbox_state)
        # Set the checkbox as the index widget
        self.editor_table_view.setIndexWidget(checkbox_index, checkbox)

    def _set_all_checkbox_rows(self, value: bool) -> None:
        # Iterate through the editor's rows
        for row in range(self.editor_model.rowCount()):
            # If an existing row is found, setChecked the value
            checkbox = self.editor_table_view.indexWidget(
                self.editor_model.item(row, 0).index()
            )
            if isinstance(checkbox, QCheckBox):
                checkbox.setChecked(value)

    def _row_count(self) -> int:
        return self.editor_model.rowCount()

    def _clear_table_model(self) -> None:
        """Clear all rows from the table model."""
        self.editor_model.removeRows(0, self.editor_model.rowCount())

    def _update_mods_from_table(
        self,
        pfid_column: int,
        mode: OperationMode,
        steamworks_cmd: str = "",
        completed: Callable[[], None] | None = None,
    ) -> None:
        """
        Update mods from table by collecting PFIDs and triggering appropriate operations.

        Filters out empty Publish File IDs which can occur when MissingModsPrompt
        doesn't have published_file_id for mods in the table. This prevents crashes
        in steamworks API calls.

        Args:
            pfid_column: Column index for Publish File IDs
            mode: Operation mode (OperationMode.STEAMCMD or OperationMode.STEAM)
            steamworks_cmd: Steamworks command to execute (only used when mode is STEAM).
                Valid values: "subscribe", "resubscribe", "unsubscribe".
                Ignored for OperationMode.STEAMCMD.
            completed: Optional callback to run on completion
        """
        # Check for mods without Publish Field ID and notify user if needed
        self._check_missing_publish_field_id_notification()

        steamcmd_pfids, steam_pfids = self._collect_pfids_by_mode(pfid_column, mode)
        filtered_steamcmd_pfids = self._filter_empty_pfids(steamcmd_pfids)

        if filtered_steamcmd_pfids:
            self._delete_selected_mods(pfid_column, OperationMode.STEAMCMD)
            EventBus().do_steamcmd_download.emit(filtered_steamcmd_pfids)

        if steam_pfids:
            self._emit_steamworks_api_call(steamworks_cmd, steam_pfids)

        if completed:
            completed()

        # Close the panel window after triggering operations
        # Don't close AcfLogReader (it's a persistent view, not a dialog)
        if self.__class__.__name__ != "AcfLogReader":
            self.close()

    def _collect_pfids_by_mode(
        self, pfid_column: int, mode: OperationMode
    ) -> tuple[list[str], list[str]]:
        pfid_fn = self._get_selected_text_by_column(pfid_column)
        pfids = [(pfid, mode) for pfid in self._run_for_selected_rows(pfid_fn)]

        steamcmd_pfids = [pfid for pfid, m in pfids if m == OperationMode.STEAMCMD]
        steam_pfids = [pfid for pfid, m in pfids if m == OperationMode.STEAM]
        return steamcmd_pfids, steam_pfids

    def _filter_empty_pfids(self, pfids: list[str]) -> list[str]:
        """
        Filter out empty Publish File IDs from the list.

        Args:
            pfids: List of PFID strings to filter

        Returns:
            List of non-empty PFID strings
        """
        return [pfid for pfid in pfids if pfid.strip()]

    def _emit_steamworks_api_call(self, command: str, steam_pfids: list[str]) -> None:
        """
        Emit steamworks API call with the given command and PFIDs.

        Converts PFIDs to integers and filters out empty values. All calls are routed
        through the animated handler for consistent UI feedback, validation, and safety checks.

        Args:
            command: Steamworks command to execute (subscribe, resubscribe, unsubscribe, launch_game_process, etc.)
            steam_pfids: List of Publish File ID strings to process
        """
        if not command:
            logger.warning("Attempted to emit steamworks API call with empty command")
            return

        filtered_pfids = [int(pfid) for pfid in steam_pfids if pfid.strip()]

        if not filtered_pfids:
            return

        logger.warning(
            f"Queuing '{command}' action for {len(filtered_pfids)} mods via Steamworks API"
        )
        EventBus().do_steamworks_api_call.emit([command, filtered_pfids])

    def _create_update_callback(
        self,
        pfid_column: int,
        mode: OperationMode,
        steamworks_cmd: str | None = None,
        completion_callback: Callable[[], None] | None = None,
    ) -> Callable[[], None]:
        """
        Factory method for creating mod update operation callbacks.

        Args:
            pfid_column: Column index for Publish File IDs
            mode: Operation mode (OperationMode.STEAMCMD or OperationMode.STEAM)
            steamworks_cmd: Steamworks command to execute (only used for STEAM mode).
                Valid values: "subscribe", "resubscribe", "unsubscribe"
            completion_callback: Optional callback to run after completion

        Returns:
            Callback function for update button
        """
        # Use provided steamworks_cmd or empty string (only used for STEAM mode)
        cmd = steamworks_cmd or ""
        return partial(
            self._update_mods_from_table,
            pfid_column,
            mode,
            cmd,
            completed=completion_callback,
        )

    def clear_layout(self, layout: QLayout) -> None:
        while layout.count():
            child = layout.takeAt(0)
            if child is None:
                continue
            widget = child.widget()
            if widget is not None:
                widget.deleteLater()

    def _row_is_checked(self, row: int) -> bool:
        checkbox = self.editor_table_view.indexWidget(
            self.editor_model.item(row, 0).index()
        )
        return isinstance(checkbox, QCheckBox) and checkbox.isChecked()

    def _get_selected_row_indices(self) -> set[int]:
        """
        Get the set of selected row indices.

        Returns:
            Set of row indices that are checked.
        """
        return {
            row
            for row in range(self.editor_model.rowCount())
            if self._row_is_checked(row)
        }

    T = TypeVar("T")

    def _run_for_selected_rows(self, fn: Callable[[int], T]) -> list[T]:
        return [fn(row) for row in self._get_selected_row_indices()]

    def _get_selected_text_by_column(self, column: int) -> Callable[[int], str]:
        def __selected_text_by_column(row: int) -> str:
            item = self.editor_model.item(row, column)
            if item is None:
                return ""
            combo_box = self.editor_table_view.indexWidget(item.index())
            if not isinstance(combo_box, QComboBox):
                return item.text()
            else:
                return combo_box.currentText()

        return __selected_text_by_column

    def _resolve_mode_getter(
        self, mode: OperationMode | str | int
    ) -> Callable[[int], str]:
        """
        Resolve a mode value getter function for the given mode parameter.

        Handles multiple mode type representations (enum, string, int) and returns
        a callable that provides the mode value for any given row.

        Args:
            mode: Operation mode as OperationMode enum, string, or column index (int).

        Returns:
            A callable that takes a row index and returns the mode string value.
        """
        if isinstance(mode, OperationMode):
            # Return constant function for enum mode
            mode_value = mode.value
            return lambda _: mode_value
        elif isinstance(mode, int):
            # Return column text getter for int (column index)
            return self._get_selected_text_by_column(mode)
        else:
            # Return constant function for string mode
            return lambda _: mode

    def _delete_selected_mods(
        self, pfid_column: int, mode: OperationMode | str | int
    ) -> None:
        delete_before_update_state = self.settings.steamcmd_delete_before_update
        if delete_before_update_state:
            pfid_fn = self._get_selected_text_by_column(pfid_column)
            get_mode = self._resolve_mode_getter(mode)

            pfid_mode_pairs = self._run_for_selected_rows(
                lambda row: (pfid_fn(row), get_mode(row))
            )
            for pfid, mod_mode in pfid_mode_pairs:
                if mod_mode == OperationMode.STEAMCMD.value:
                    mod_path = get_mod_path_from_pfid(pfid)
                    if mod_path and os.path.exists(mod_path):
                        try:
                            shutil.rmtree(mod_path)
                        except Exception as e:
                            logger.error(
                                f"Error deleting mod directory {mod_path}: {e}"
                            )

    def _configure_button(
        self,
        button: QPushButton,
        text: str,
        object_name: str,
        callback: Callable[[], None] | None = None,
    ) -> None:
        """
        Configure a button with common properties.

        Args:
            button: The button to configure.
            text: Button text.
            object_name: Object name for the button.
            callback: Optional callback for the clicked signal.
        """
        button.setText(text)
        button.setObjectName(object_name)
        if callback is not None:
            button.clicked.connect(callback)

    def _create_workshop_button(
        self, url: str, object_name: str = "workshopButton"
    ) -> QPushButton:
        """
        Create a standardized workshop button that opens the Steam Workshop page.

        Args:
            url: The full URL to the Steam Workshop page.
            object_name: The object name for the button widget (default: "workshopButton").

        Returns:
            QPushButton: Configured button that opens the workshop page when clicked.
        """
        button = QPushButton()
        self._configure_button(
            button,
            self.tr("Open Page"),
            object_name,
            partial(platform_specific_open, url),
        )
        return button

    def _create_path_link(self, path: str, object_name: str = "pathLink") -> QLabel:
        """
        Create a clickable label that opens the mod path when clicked.

        Args:
            path: The file system path to open.
            object_name: The object name for the label widget (default: "pathLink").

        Returns:
            QLabel: Configured label that displays the path as clickable text.
        """
        label = ClickablePathLabel()
        label.setPath(path)
        label.setObjectName(object_name)
        return label

    def _create_deletion_button(
        self,
        settings: Settings,
        get_selected_mod_metadata: Callable[[], list[dict[str, Any]]],
        completion_callback: Callable[[], None] | None,
        menu_title: str,
        enable_delete_mod: bool = True,
        enable_delete_keep_dds: bool = False,
        enable_delete_dds_only: bool = False,
        enable_delete_and_unsubscribe: bool = False,
        enable_delete_and_resubscribe: bool = False,
    ) -> QPushButton:
        """
        Create a standardized deletion button with menu.

        Args:
            settings: The settings model instance.
            get_selected_mod_metadata: Function to get selected mod metadata.
            menu_title: Title for the deletion menu.
            completion_callback: Callback after deletion completes.
            enable_delete_mod: Enable delete mod option.
            enable_delete_keep_dds: Enable delete mod but keep DDS option.
            enable_delete_dds_only: Enable delete DDS only option.
            enable_delete_and_unsubscribe: Enable delete and unsubscribe option.
            enable_delete_and_resubscribe: Enable delete and resubscribe option.

        Returns:
            QPushButton: Configured deletion button with dropdown menu.
        """
        # Check if Steam client integration is enabled
        steam_client_integration_enabled = settings.instances[
            settings.current_instance
        ].steam_client_integration

        button = QPushButton()
        button.setText(self.tr("Delete"))
        button.setObjectName("dangerButton")
        deletion_menu = ModDeletionMenu(
            settings=settings,
            get_selected_mod_metadata=get_selected_mod_metadata,
            metadata_controller=self.metadata_controller,
            completion_callback=completion_callback,
            menu_title=menu_title,
            enable_delete_mod=enable_delete_mod,
            enable_delete_keep_dds=enable_delete_keep_dds,
            enable_delete_dds_only=enable_delete_dds_only,
            enable_delete_and_unsubscribe=steam_client_integration_enabled,
            enable_delete_and_resubscribe=steam_client_integration_enabled,
        )
        button.setMenu(deletion_menu)
        button.clicked.connect(
            lambda: deletion_menu.exec(button.mapToGlobal(button.rect().bottomLeft()))
        )
        return button

    def _setup_buttons_from_config(self, button_configs: list[ButtonConfig]) -> None:
        """
        Set up buttons from a list of button configurations.

        Args:
            button_configs: List of ButtonConfig objects defining the buttons to create.
        """
        factory = self.get_button_factory()
        for config in button_configs:
            button = self._create_button_from_config_with_factory(config, factory)
            if button:
                self.layouts.editor_main_actions_layout.addWidget(button)

    def _create_button_from_config(self, config: ButtonConfig) -> QWidget | None:
        """
        Create a button from a single button configuration.

        Args:
            config: ButtonConfig object defining the button to create.

        Returns:
            The created button widget, or None if creation failed.
        """
        factory = self.get_button_factory()
        return self._create_button_from_config_with_factory(config, factory)

    def _create_button_from_config_with_factory(
        self, config: ButtonConfig, factory: ButtonFactory
    ) -> QWidget | None:
        """
        Create a button from a single button configuration using a factory.

        Args:
            config: ButtonConfig object defining the button to create.
            factory: ButtonFactory instance to create buttons.

        Returns:
            The created button widget, or None if creation failed.
        """
        if config.button_type == ButtonType.REFRESH:
            return self._create_refresh_button_from_config(config, factory)
        elif config.button_type == ButtonType.STEAMCMD:
            return self._create_steamcmd_button_from_config(config, factory)
        elif config.button_type == ButtonType.STEAM:
            return self._create_steam_button_from_config(config, factory)
        elif config.button_type == ButtonType.DELETE:
            return self._create_delete_button_from_config(config, factory)
        elif config.button_type == ButtonType.CUSTOM:
            return self._create_custom_button_from_config(config, factory)

        return None

    def _create_refresh_button_from_config(
        self, config: ButtonConfig, factory: ButtonFactory
    ) -> QWidget | None:
        """Create a refresh button from config."""
        return factory.create_refresh_button(config.custom_callback)

    def _create_steamcmd_button_from_config(
        self, config: ButtonConfig, factory: ButtonFactory
    ) -> QWidget | None:
        """Create a SteamCMD button from config."""
        if config.pfid_column is not None:
            return factory.create_steamcmd_button(config.pfid_column)
        return None

    def _create_steam_button_from_config(
        self, config: ButtonConfig, factory: ButtonFactory
    ) -> QWidget | None:
        """Create a Steam button from config."""
        if config.pfid_column is not None:
            return factory.create_steam_button(
                config.pfid_column, config.completion_callback
            )
        return None

    def _create_delete_button_from_config(
        self, config: ButtonConfig, factory: ButtonFactory
    ) -> QWidget | None:
        """Create a delete button from config."""
        if config.menu_title is not None:
            return factory.create_delete_button(
                config.menu_title,
                config.completion_callback,
                config.enable_delete_mod,
                config.enable_delete_keep_dds,
                config.enable_delete_dds_only,
                config.enable_delete_and_unsubscribe,
                config.enable_delete_and_resubscribe,
            )
        return None

    def _create_custom_button_from_config(
        self, config: ButtonConfig, factory: ButtonFactory
    ) -> QWidget | None:
        """Create a custom button from config."""
        if config.custom_callback is not None:
            return factory.create_custom_button(config.text, config.custom_callback)
        return None

    def _create_custom_button(
        self, text: str, callback: Callable[[], None]
    ) -> QPushButton:
        """
        Create a custom button with text and callback.

        Args:
            text: Button text
            callback: Function to call when button is clicked

        Returns:
            Configured custom button
        """
        button = QPushButton(text)
        button.setObjectName("primaryButton")
        button.clicked.connect(callback)
        return button

    # ===== CENTRALIZED METADATA HANDLING =====

    def _get_key_from_row(self, row: int, name_column: int = 1) -> str | None:
        """
        Extract the mod path key from a table row's name column.

        Args:
            row: Row index to extract key from
            name_column: Column index containing the name item with key data

        Returns:
            Path key string if found, None otherwise
        """
        try:
            if row >= self.editor_model.rowCount():
                return None

            name_item = self.editor_model.item(row, name_column)
            if name_item is None:
                return None

            return name_item.data(Qt.ItemDataRole.UserRole)
        except Exception as e:
            logger.warning(f"Error accessing key from row {row}: {e}")
            return None

    def _get_selected_mod_metadata(self) -> list[dict[str, Any]]:
        """
        Get metadata for selected mods in the table.

        Returns a list of compat dicts with keys expected by ModDeletionMenu.
        Note: the "uuid" key is a legacy name; the value is the mod path key.

        Returns:
            List of ModMetadata compat dicts for selected mods
        """
        selected_mods: list[dict[str, Any]] = []
        try:
            for row in range(self.editor_model.rowCount()):
                if self._row_is_checked(row):
                    path = self._get_key_from_row(row)
                    if path:
                        mod = self.metadata_controller.get_mod(path)
                        if mod is not None:
                            compat: dict[str, Any] = {
                                "path": str(mod.mod_path) if mod.mod_path else "",
                                "uuid": path,
                                "name": mod.name or "",
                                "publishedfileid": mod.published_file_id or "",
                                "steamcmd": mod.mod_type == ModType.STEAM_CMD,
                            }
                            if mod.mod_type == ModType.LUDEON:
                                compat["data_source"] = "expansion"
                            elif mod.mod_type == ModType.STEAM_WORKSHOP:
                                compat["data_source"] = "workshop"
                            elif mod.mod_type == ModType.LOCAL:
                                compat["data_source"] = "local"
                            else:
                                compat["data_source"] = str(mod.mod_type.value)
                            if isinstance(mod, AboutXmlMod):
                                compat["packageid"] = str(mod.package_id)
                            selected_mods.append(compat)
        except Exception as e:
            logger.warning(f"Error getting selected mod metadata: {e}")
        return selected_mods

    def _refresh_metadata_and_panel(self) -> None:
        """
        Standard refresh method called manually or after deletion operations.
        Refreshes the metadata cache and repopulates the table.

        This refreshes the metadata cache and repopulates the table with the updated mod data.
        ``_populate_from_metadata`` is triggered automatically via
        ``metadata_refreshed`` signal.
        """
        logger.warning("Refreshing metadata and repopulating table")
        # Refresh the metadata to reflect deletion changes
        self.metadata_controller.refresh_metadata()

    def get_button_factory(self) -> ButtonFactory:
        """Get a button factory instance for this panel."""
        return ButtonFactory(self)

    # ===== UTILITY METHOD CONSOLIDATION =====

    def _add_workshop_button_to_row(
        self, row_items: list[QStandardItem], pfid: str, workshop_column: int
    ) -> QPushButton:
        """
        Add a workshop button to a specific column in a row.

        Args:
            row_items: List of QStandardItem for the row
            pfid: Published file ID for the workshop URL
            workshop_column: Column index for the workshop button

        Returns:
            The created workshop button
        """
        workshop_item = row_items[workshop_column]
        workshop_button = self._create_workshop_button(
            f"https://steamcommunity.com/sharedfiles/filedetails/?id={pfid}",
            "workshopButton",
        )
        self.editor_table_view.setIndexWidget(workshop_item.index(), workshop_button)
        return workshop_button

    def _add_combo_box_to_row(
        self,
        row_items: list[QStandardItem],
        combo_column: int,
        items: list[str] | None = None,
    ) -> QComboBox:
        """
        Add a combo box to a specific column in a row.

        Args:
            row_items: List of QStandardItem for the row
            combo_column: Column index for the combo box
            items: Optional list of items to add to the combo box

        Returns:
            The created combo box
        """
        combo_item = row_items[combo_column]
        combo_box = QComboBox()
        combo_box.setEditable(True)
        combo_box.setObjectName("variantComboBox")
        if items:
            combo_box.addItems(items)
        self.editor_table_view.setIndexWidget(combo_item.index(), combo_box)
        return combo_box

    # ===== NEW HELPER METHODS FOR REFACTORING =====

    def _add_mod_row(
        self,
        mod_info: "ModInfo",
        additional_items: list[QStandardItem] | None = None,
        default_checkbox_state: bool = False,
    ) -> None:
        """
        Standardized method to add a mod row to the table.

        Args:
            mod_info: ModInfo object containing mod data
            additional_items: Optional additional QStandardItem objects for extra columns
            default_checkbox_state: Default state for the checkbox
        """
        # Base columns that all panels use
        base_items = [
            QStandardItem(mod_info.name),
            QStandardItem(mod_info.authors),
            QStandardItem(mod_info.packageid),
            QStandardItem(mod_info.published_file_id),
            QStandardItem(mod_info.supported_versions),
            QStandardItem(mod_info.downloaded_time),
            QStandardItem(mod_info.updated_on_workshop),
            QStandardItem(mod_info.source),
            QStandardItem(""),  # Path will be displayed via widget
        ]

        # Add workshop page column
        workshop_item = QStandardItem()
        base_items.append(workshop_item)

        # Add any additional columns specific to the panel
        if additional_items:
            base_items.extend(additional_items)

        # Set path key on name item for metadata lookup
        if mod_info.key:
            base_items[0].setData(mod_info.key, Qt.ItemDataRole.UserRole)

        self._add_row(base_items, default_checkbox_state)

        # Add path link to the path column (index 9) only if path exists and row is not blank
        if mod_info.path and mod_info.path.strip():
            path_link = self._create_path_link(mod_info.path, "pathLink")
            self.editor_table_view.setIndexWidget(base_items[8].index(), path_link)

        # Add workshop button to the workshop column only if published_file_id exists
        if mod_info.published_file_id and mod_info.published_file_id.strip():
            workshop_button = self._create_workshop_button(
                mod_info.workshop_url, "workshopButton"
            )
            self.editor_table_view.setIndexWidget(
                workshop_item.index(), workshop_button
            )

    def _add_group_header_row(self, header_text: str) -> None:
        """
        Add a group header row to the table.

        Args:
            header_text: Text for the header row
        """
        header_item = QStandardItem(header_text)
        header_item.setData(None, Qt.ItemDataRole.UserRole)

        # Create empty items for other columns
        empty_items = [
            QStandardItem("") for _ in range(self.editor_model.columnCount() - 1)
        ]
        items = [header_item] + empty_items

        self.editor_model.appendRow(items)

    def _extract_mod_info_from_metadata(
        self, key: str | None, metadata: dict[str, Any] | ListedMod
    ) -> ModInfo:
        """
        Extract ModInfo from metadata dictionary or ListedMod object.

        Args:
            key: Path key of the mod in metadata
            metadata: Metadata dictionary or ListedMod instance

        Returns:
            ModInfo object
        """
        if isinstance(metadata, ListedMod):
            # Look up aux timestamps so the mod list can show accurate
            # download / workshop-update times even when the metadata dict
            # path wasn't built from filter_eligible_mods_for_update.
            acf_touched: int | None = None
            ext_updated: int | None = None
            if key is not None:
                _, aux_entry = self.metadata_controller.get_metadata_with_path(key)
                acf_touched, ext_updated = resolve_aux_timestamps(aux_entry)
            mod_info = ModInfo.from_listed_mod(
                metadata,
                acf_time_touched=acf_touched,
                external_time_updated=ext_updated,
            )
            mod_info.key = key
            return mod_info
        return ModInfo.from_metadata(key, metadata)

    def _resolve_path_key(self, path: str) -> str | None:
        """
        Verify a mod path exists in metadata and return it as a key.

        Args:
            path: Mod path to verify

        Returns:
            The path if found in metadata, None otherwise
        """
        if self.metadata_controller.has_mod(path):
            return path
        return None

    def _reconfigure_table_sorting(self, sorting_enabled: bool) -> None:
        """
        Reconfigure table sorting after initialization (if needed).

        Most cases should configure sorting in _setup_table_and_model() instead.

        Args:
            sorting_enabled: Whether sorting is enabled
        """
        self.editor_table_view.setSortingEnabled(sorting_enabled)

    def _populate_from_metadata(self) -> None:
        """Populate the table from metadata. Must be implemented by subclasses."""
        raise NotImplementedError("Subclasses must implement _populate_from_metadata")

    def _populate_mods(
        self,
        groups: dict[str, list[tuple[str, dict[str, Any] | ListedMod]]],
        add_group_headers: bool = False,
    ) -> None:
        """
        Populate the table with mod groups.

        Args:
            groups: Dictionary of groups, where key is group name, value is list of (path_key, metadata) tuples.
            add_group_headers: Whether to add header rows for each group.
        """
        self._clear_table_model()

        for group_key, mod_list in groups.items():
            if add_group_headers and group_key:
                self._add_group_header_row(group_key)

            for path_key, metadata in mod_list:
                try:
                    mod_info = self._extract_mod_info_from_metadata(path_key, metadata)
                except (ValueError, TypeError) as e:
                    logger.warning(
                        f"Skipping mod {path_key}: failed to extract metadata ({e})"
                    )
                    continue
                self._add_mod_row(mod_info)

    def _get_standard_mod_columns(self) -> list[HeaderColumn]:
        """
        Get the standard list of columns for displaying mod information.

        Returns:
            List of standard column definitions.
        """
        return [
            self.tr(self.COL_MOD_NAME),
            self.tr(self.COL_AUTHOR),
            self.tr(self.COL_PACKAGE_ID),
            self.tr(self.COL_PUBLISHED_FILE_ID),
            self.tr(self.COL_SUPPORTED_VERSIONS),
            self.tr(self.COL_MOD_DOWNLOADED),
            self.tr(self.COL_UPDATED_ON_WORKSHOP),
            self.tr(self.COL_SOURCE),
            self.tr(self.COL_PATH),
            self.tr(self.COL_WORKSHOP_PAGE),
        ]

    def _get_base_button_configs(self) -> list[ButtonConfig]:
        """
        Get base button configurations that are common across panels.

        Returns:
            List of base ButtonConfig objects for refresh and SteamCMD.
        """
        return [
            ButtonConfig(
                button_type=ButtonType.REFRESH,
                custom_callback=self._refresh_metadata_and_panel,
            ),
            ButtonConfig(
                button_type=ButtonType.STEAMCMD,
                pfid_column=ColumnIndex.PUBLISHED_FILE_ID.value,
            ),
        ]

    def _extend_button_configs_with_steam_actions(
        self, button_configs: list[ButtonConfig]
    ) -> list[ButtonConfig]:
        """
        Extend button configurations with Steam client actions if integration is enabled.

        Args:
            button_configs: List of button configurations to extend.

        Returns:
            Extended list of button configurations.
        """
        steam_client_integration_enabled = self._get_steam_client_integration_enabled()
        if steam_client_integration_enabled:
            button_configs.append(
                ButtonConfig(
                    button_type=ButtonType.STEAM,
                    pfid_column=ColumnIndex.PUBLISHED_FILE_ID.value,
                ),
            )
        return button_configs

    def _create_delete_button_config(
        self, menu_title: str, enable_delete_and_unsubscribe: bool = True
    ) -> ButtonConfig:
        """
        Create a delete button configuration with standard settings.

        Args:
            menu_title: Title for the deletion menu.
            enable_delete_and_unsubscribe: Whether to enable delete and unsubscribe option.

        Returns:
            ButtonConfig for delete button.
        """
        steam_client_integration_enabled = self._get_steam_client_integration_enabled()
        return ButtonConfig(
            button_type=ButtonType.DELETE,
            text=self.tr("Delete"),
            pfid_column=ColumnIndex.PUBLISHED_FILE_ID.value,
            get_selected_mod_metadata=self._get_selected_mod_metadata,
            completion_callback=self._refresh_metadata_and_panel,
            menu_title=menu_title,
            enable_delete_mod=True,
            enable_delete_keep_dds=False,
            enable_delete_dds_only=False,
            enable_delete_and_unsubscribe=enable_delete_and_unsubscribe
            and steam_client_integration_enabled,
            enable_delete_and_resubscribe=enable_delete_and_unsubscribe
            and steam_client_integration_enabled,
        )

    def _check_missing_publish_field_id_notification(self) -> None:
        """
        Check if selected mods are missing Publish Field IDs and show notification.
        Works with all BaseModsPanel subclasses by checking for empty published_file_id in table data.
        """
        selected_indices = self._get_selected_row_indices()
        if not selected_indices:
            return

        # Check if subclass has missing_publishfieldid_mods attribute (for explicit tracking)
        missing_publishfieldid_mods = getattr(self, "missing_publishfieldid_mods", None)
        use_explicit_mode = missing_publishfieldid_mods is not None

        missing_pfid_mods = [
            self.editor_model.item(row, 1).text()
            for row in selected_indices
            if self._row_has_missing_pfid(
                row, missing_publishfieldid_mods, use_explicit_mode
            )
            and self.editor_model.item(row, 1) is not None
        ]

        if missing_pfid_mods:
            self._show_missing_pfid_notification(missing_pfid_mods)

    def _row_has_missing_pfid(
        self,
        row: int,
        missing_publishfieldid_mods: list[str] | None,
        use_explicit_mode: bool,
    ) -> bool:
        """Check if a mod at given row has missing Publish Field ID."""
        if use_explicit_mode:
            key = self._get_key_from_row(row)
            return bool(
                key
                and missing_publishfieldid_mods
                and key in missing_publishfieldid_mods
            )
        else:
            pfid_item = self.editor_model.item(row, ColumnIndex.PUBLISHED_FILE_ID.value)
            return bool(pfid_item and not pfid_item.text().strip())

    def _show_missing_pfid_notification(self, missing_pfid_mods: list[str]) -> None:
        """Show notification about mods without Publish Field ID."""
        show_message = getattr(self, "_show_message", None)
        if not show_message:
            return

        mod_list = "\n".join([f"• {name}" for name in missing_pfid_mods])
        message = (
            "The following selected mods do not have a Publish Field ID "
            "and cannot be updated via Steam Workshop:\n\n"
            f"{mod_list}\n\n"
            "Only mods with valid Publish Field IDs will be updated."
        )
        show_message("Missing Publish Field ID", message, "warning")

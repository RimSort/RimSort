import os
import shutil
from functools import partial
from typing import Callable, Self, TypeVar, Union

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
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

from app.utils.event_bus import EventBus
from app.utils.metadata import MetadataManager
from app.utils.mod_utils import get_mod_path_from_pfid

# By default, we assume Stretch for all columns.
# Tuples should be used if this should be overridden
HeaderColumn = str | tuple[str, QHeaderView.ResizeMode]


# class BaseModPanelCheckbox(QStandardItem):
#     def __init__(self, uuid: str, default_checkbox_state: bool = False) -> None:
#         super().__init__()
#         self.uuid = uuid
#         self.checkbox = QCheckBox()
#         self.checkbox.setObjectName("selectCheckbox")
#         self.checkbox.setChecked(default_checkbox_state)


class BaseModsPanel(QWidget):
    """
    Base class used for multiple panels that display a list of mods.
    """

    def __init__(
        self,
        object_name: str,
        window_title: str,
        title_text: str,
        details_text: str,
        additional_columns: list[HeaderColumn],
    ):
        super().__init__()
        # Utility and Setup
        self.metadata_manager = MetadataManager.instance()
        self.settings_controller = self.metadata_manager.settings_controller

        # Start of UI
        self.installEventFilter(self)
        self.setObjectName(object_name)
        self.title = QLabel(title_text)
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.editor_model: QStandardItemModel

        # CONTAINER LAYOUTS
        self.upper_layout = QVBoxLayout()
        self.lower_layout = QVBoxLayout()
        layout = QVBoxLayout()

        # SUB LAYOUTS
        self.details_layout = QVBoxLayout()
        self.editor_layout = QVBoxLayout()
        self.editor_actions_layout = QHBoxLayout()
        self.editor_checkbox_actions_layout = QHBoxLayout()
        self.editor_main_actions_layout = QHBoxLayout()
        self.editor_exit_actions_layout = QHBoxLayout()

        self.editor_actions_layout.addLayout(self.editor_checkbox_actions_layout)
        self.editor_actions_layout.addStretch(25)
        self.editor_actions_layout.addLayout(self.editor_main_actions_layout)
        self.editor_actions_layout.addStretch(25)
        self.editor_actions_layout.addLayout(self.editor_exit_actions_layout)

        # DETAILS WIDGETS
        self.details_label = QLabel(details_text)
        self.details_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # EDITOR MODEL
        self.editor_model = QStandardItemModel(0, len(additional_columns) + 1)
        editor_header_labels = [
            "✔",
        ] + list(map(lambda x: x[0] if isinstance(x, tuple) else x, additional_columns))
        self.editor_model.setHorizontalHeaderLabels(editor_header_labels)

        # EDITOR WIDGETS
        # Create the table view and set the model
        self.editor_table_view = QTableView()
        self.editor_table_view.setModel(self.editor_model)
        self.editor_table_view.setSortingEnabled(True)  # Enable sorting on the columns
        self.editor_table_view.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.editor_table_view.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection
        )

        self.editor_table_view.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )

        for column_index, column in enumerate(additional_columns):
            self.editor_table_view.horizontalHeader().setSectionResizeMode(
                column_index + 1,
                column[1]
                if isinstance(column, tuple)
                else QHeaderView.ResizeMode.Stretch,
            )

        self.editor_deselect_all_button = QPushButton(self.tr("Deselect all"))
        self.editor_deselect_all_button.clicked.connect(
            partial(self._set_all_checkbox_rows, False)
        )
        self.editor_checkbox_actions_layout.addWidget(self.editor_deselect_all_button)

        self.editor_select_all_button = QPushButton(self.tr("Select all"))
        self.editor_select_all_button.clicked.connect(
            partial(self._set_all_checkbox_rows, True)
        )
        self.editor_checkbox_actions_layout.addWidget(self.editor_select_all_button)

        self.editor_cancel_button = QPushButton(self.tr("Do nothing and exit"))
        self.editor_cancel_button.clicked.connect(self.close)
        self.editor_exit_actions_layout.addWidget(self.editor_cancel_button)

        # Build the details layout
        self.details_layout.addWidget(self.details_label)

        # Build the editor layouts
        self.editor_layout.addWidget(self.editor_table_view)
        self.editor_layout.addLayout(self.editor_actions_layout)

        # Add our widget layouts to the containers
        self.upper_layout.addLayout(self.details_layout)
        self.lower_layout.addLayout(self.editor_layout)

        # Add our layouts to the main layout
        layout.addWidget(self.title)
        layout.addLayout(self.upper_layout)
        layout.addLayout(self.lower_layout)

        # Put it all together
        self.setWindowTitle(window_title)
        self.setLayout(layout)

        # Set the window size
        self.resize(900, 600)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.KeyPress and event.type() == Qt.Key.Key_Escape:
            self.close()
            return True

        return super().eventFilter(watched, event)

    def _add_row(
        self,
        items: list[QStandardItem],
        defaultCheckboxState: bool = False,
    ) -> None:
        items = [
            QStandardItem(),
        ] + items
        self.editor_model.appendRow(items)
        checkbox_index = items[0].index()
        checkbox = QCheckBox()
        checkbox.setObjectName("selectCheckbox")
        checkbox.setChecked(defaultCheckboxState)
        # Set the checkbox as the index widget
        self.editor_table_view.setIndexWidget(checkbox_index, checkbox)

    def _set_all_checkbox_rows(self, value: bool) -> None:
        # Iterate through the editor's rows
        for row in range(self.editor_model.rowCount()):
            if self.editor_model.item(row):  # If there is a row at current index
                # If an existing row is found, setChecked the value
                checkbox = self.editor_table_view.indexWidget(
                    self.editor_model.item(row, 0).index()
                )
                if isinstance(checkbox, QCheckBox):
                    checkbox.setChecked(value)

    def _row_count(self) -> int:
        return self.editor_model.rowCount()

    def _update_mods_from_table(
        self,
        pfid_column: int,
        mode: Union[str, int],
        steamworks_cmd: str = "resubscribe",
        completed: Callable[[Self], None] = lambda self: (self.close(), None)[1],
    ) -> None:
        steamcmd_publishedfileids = []
        steam_publishedfileids = []
        pfids: list[tuple[str, str]]
        pfid_fn = self._get_selected_text_by_column(pfid_column)
        if isinstance(mode, str):
            pfids = [(pfid, mode) for pfid in self._run_for_selected_rows(pfid_fn)]
        elif isinstance(mode, int):
            mode_fn = self._get_selected_text_by_column(mode)
            pfids = self._run_for_selected_rows(
                lambda row: (pfid_fn(row), mode_fn(row))
            )

        for publishedfileid, mode in pfids:
            if mode == "SteamCMD":
                steamcmd_publishedfileids.append(publishedfileid)
                # Call to delete selected mods before update
                self._delete_selected_mods(pfid_column, mode)
            elif mode == "Steam":
                steam_publishedfileids.append(publishedfileid)

        # If we have any SteamCMD mods designated to be updated
        if len(steamcmd_publishedfileids) > 0:
            EventBus().do_steamcmd_download.emit(steamcmd_publishedfileids)
        # If we have any Steam mods designated to be updated
        if len(steam_publishedfileids) > 0:
            EventBus().do_steamworks_api_call.emit(
                [
                    steamworks_cmd,
                    [eval(str_pfid) for str_pfid in steam_publishedfileids],
                ]
            )
        completed(self)

    def _steamworks_cmd_for_all(
        self,
        pfid_column: int,
        steamworks_cmd: str = "resubscribe",
        completed: Callable[[Self], None] = lambda self: (self.close(), None)[1],
    ) -> None:
        self._set_all_checkbox_rows(True)
        self._update_mods_from_table(pfid_column, "Steam", steamworks_cmd, completed)

    def clear_layout(self, layout: QLayout) -> None:
        while layout.count():
            child = layout.takeAt(0)
            widget = child.widget()
            if widget is not None:
                widget.setParent(None)

    def _row_is_checked(self, row: int) -> bool:
        checkbox = self.editor_table_view.indexWidget(
            self.editor_model.item(row, 0).index()
        )
        return isinstance(checkbox, QCheckBox) and checkbox.isChecked()

    T = TypeVar("T")

    def _run_for_selected_rows(self, fn: Callable[[int], T]) -> list[T]:
        ret = []
        for row in range(self.editor_model.rowCount()):
            if self._row_is_checked(row):
                ret.append(fn(row))
        return ret

    def _get_selected_text_by_column(self, column: int) -> Callable[[int], str]:
        def __selected_text_by_column(row: int) -> str:
            combo_box = self.editor_table_view.indexWidget(
                self.editor_model.item(row, column).index()
            )
            if not isinstance(combo_box, QComboBox):
                return self.editor_model.item(row, column).text()
            else:
                return combo_box.currentText()

        return __selected_text_by_column

    def _delete_selected_mods(self, pfid_column: int, mode: str | int) -> None:
        delete_before_update_state = (
            self.settings_controller.settings.steamcmd_delete_before_update
        )
        if delete_before_update_state:
            pfid_fn = self._get_selected_text_by_column(pfid_column)
            mode_fn = (
                self._get_selected_text_by_column(mode)
                if isinstance(mode, int)
                else lambda _: mode
            )
            pfid_mode_pairs = self._run_for_selected_rows(
                lambda row: (pfid_fn(row), mode_fn(row))
            )
            for pfid, mod_mode in pfid_mode_pairs:
                if mod_mode == "SteamCMD":
                    mod_path = get_mod_path_from_pfid(pfid)
                    if mod_path and os.path.exists(mod_path):
                        try:
                            shutil.rmtree(mod_path)
                        except Exception as e:
                            print(f"Error deleting mod directory {mod_path}: {e}")

from functools import partial

from PySide6.QtCore import QEvent, QObject, QSize, Qt, Signal
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

# By default, we assume Stretch for all columns.
# Tuples should be used if this should be overridden
HeaderColumn = str | tuple[str, QHeaderView.ResizeMode]


class BaseModsPanel(QWidget):
    """
    Base class used for multiple panels that display a list of mods.
    """

    steamcmd_downloader_signal = Signal(list)
    steamworks_subscription_signal = Signal(list)

    def __init__(
        self,
        object_name: str,
        window_title: str,
        title_text: str,
        details_text: str,
        additional_columns: list[HeaderColumn],
        minimum_size: QSize = QSize(800, 600),
    ):
        super().__init__()
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

        self.editor_deselect_all_button = QPushButton("Deselect all")
        self.editor_deselect_all_button.clicked.connect(
            partial(self._set_all_checkbox_rows, False)
        )
        self.editor_actions_layout.addWidget(self.editor_deselect_all_button)

        self.editor_select_all_button = QPushButton("Select all")
        self.editor_select_all_button.clicked.connect(
            partial(self._set_all_checkbox_rows, True)
        )
        self.editor_actions_layout.addWidget(self.editor_select_all_button)

        self.editor_actions_layout.insertStretch(2, 100)

        self.editor_cancel_button = QPushButton("Do nothing and exit")
        self.editor_cancel_button.clicked.connect(self.close)
        self.editor_actions_layout.addWidget(self.editor_cancel_button)

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
        self.setMinimumSize(minimum_size)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.KeyPress and event.type() == Qt.Key.Key_Escape:
            self.close()
            return True

        return super().eventFilter(watched, event)

    def _add_row(
        self, items: list[QStandardItem], defaultCheckboxState: bool = False
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
                assert isinstance(checkbox, QCheckBox)
                checkbox.setChecked(value)

    def _update_mods_from_table(
        self, pfid_column: int, mode: str | int, steamworks_cmd: str = "resubscribe"
    ) -> None:
        steamcmd_publishedfileids = []
        steam_publishedfileids = []
        # Iterate through the editor's rows
        for row in range(self.editor_model.rowCount()):
            if self.editor_model.item(row):  # If there is a row at current index
                # If an existing row is found, is it selected?
                checkbox = self.editor_table_view.indexWidget(
                    self.editor_model.item(row, 0).index()
                )
                assert isinstance(checkbox, QCheckBox)
                if checkbox.isChecked():
                    combo_box = self.editor_table_view.indexWidget(
                        self.editor_model.item(row, pfid_column).index()
                    )
                    if not isinstance(combo_box, QComboBox):
                        publishedfileid = self.editor_model.item(
                            row, pfid_column
                        ).text()
                    else:
                        publishedfileid = combo_box.currentText()

                    if isinstance(mode, int):
                        mode = self.editor_model.item(row, mode).text()
                    if mode == "SteamCMD":
                        steamcmd_publishedfileids.append(publishedfileid)
                    elif mode == "Steam":
                        steam_publishedfileids.append(publishedfileid)

        # If we have any SteamCMD mods designated to be updated
        if len(steamcmd_publishedfileids) > 0:
            self.steamcmd_downloader_signal.emit(steamcmd_publishedfileids)
        # If we have any Steam mods designated to be updated
        if len(steam_publishedfileids) > 0:
            self.steamworks_subscription_signal.emit(
                [
                    steamworks_cmd,
                    [eval(str_pfid) for str_pfid in steam_publishedfileids],
                ]
            )
        self.close()

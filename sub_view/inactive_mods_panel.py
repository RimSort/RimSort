from logger_tt import logger

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidgetItem,
    QToolButton,
    QVBoxLayout,
)

from model.mod_list import ModListWidget
from model.mod_list_item import ModListItemInner


class InactiveModList:
    """
    This class controls the layout and functionality for the
    inactive mods list panel on the GUI.
    """

    def __init__(self) -> None:
        """
        Initialize the class.
        Create a ListWidget using the dict of mods. This will
        create a row for every key-value pair in the dict.
        """
        logger.info("Starting InactiveModList initialization")

        # Base layout type
        self.panel = QVBoxLayout()

        # Instantiate widgets
        self.num_mods = QLabel("Inactive [0]")
        self.num_mods.setAlignment(Qt.AlignCenter)
        self.num_mods.setObjectName("summaryValue")

        # Search widgets
        # Search widgets
        self.inactive_mods_search_layout = QHBoxLayout()
        self.inactive_mods_search = QLineEdit()
        self.inactive_mods_search.setClearButtonEnabled(True)
        self.inactive_mods_search.textChanged.connect(self.signal_inactive_mods_search)
        self.inactive_mods_search.setPlaceholderText("Search inactive mods...")
        self.inactive_mods_search_clear_button = self.inactive_mods_search.findChild(
            QToolButton
        )
        self.inactive_mods_search_clear_button.setEnabled(True)
        self.inactive_mods_search_clear_button.clicked.connect(
            self.clear_inactive_mods_search
        )
        self.inactive_mods_search_filter = QComboBox()
        self.inactive_mods_search_filter.setMaximumWidth(125)
        self.inactive_mods_search_filter.addItems(
            ["PackageId", "Name", "Author(s)", "PublishedFileId"]
        )
        self.inactive_mods_search_layout.addWidget(self.inactive_mods_search, 75)
        self.inactive_mods_search_layout.addWidget(self.inactive_mods_search_filter)

        # Inactive mod list
        self.inactive_mods_list = ModListWidget()

        # Add widgets to base layout
        self.panel.addWidget(self.num_mods)
        self.panel.addLayout(self.inactive_mods_search_layout)
        self.panel.addWidget(self.inactive_mods_list)

        # Adding Completer.
        # self.completer = QCompleter(self.inactive_mods_list.get_list_items())
        # self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        # self.inactive_mods_search.setCompleter(self.completer)

        # Connect signals and slots
        self.inactive_mods_list.list_update_signal.connect(self.change_mod_num_display)

        logger.info("Finished InactiveModList initialization")

    def change_mod_num_display(self, count: str) -> None:
        if count != "drop":
            logger.info(f"Inactive mod count changed to: {count}")
            # self.num_mods.setText(f"Inactive [{count}]")
            self.update_count(self.inactive_mods_list.get_widgets_and_items())

    def clear_inactive_mods_search(self) -> None:
        self.inactive_mods_search.setText("")
        self.inactive_mods_search.clearFocus()

    def signal_inactive_mods_search(self, pattern: str) -> None:
        wni = self.inactive_mods_list.get_widgets_and_items()
        # Use the configured search filter
        if self.inactive_mods_search_filter.currentText() == "PackageId":
            search_filter = "packageId"
        elif self.inactive_mods_search_filter.currentText() == "Name":
            search_filter = "name"
        elif self.inactive_mods_search_filter.currentText() == "Author(s)":
            search_filter = "author"
        elif self.inactive_mods_search_filter.currentText() == "PublishedFileId":
            search_filter = "publishedfileid"
        for widget, item in wni:
            if (
                pattern
                and widget.json_data.get(search_filter)
                and not pattern.lower() in widget.json_data[search_filter].lower()
            ):
                item.setHidden(True)
            else:
                item.setHidden(False)
        self.update_count(wni)

    def update_count(
        self, widgets_and_items: list[tuple[ModListItemInner, QListWidgetItem]]
    ) -> None:
        num_hidden = 0
        num_visible = 0
        for w, i in widgets_and_items:
            if i.isHidden():
                num_hidden += 1
            else:
                num_visible += 1
        if self.inactive_mods_search.text():
            self.num_mods.setText(
                f"Inactive [{num_visible}/{num_hidden + num_visible}]"
            )
        else:
            self.num_mods.setText(f"Inactive [{num_hidden + num_visible}]")

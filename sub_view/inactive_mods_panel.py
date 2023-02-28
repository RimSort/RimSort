import logging

from PySide2.QtCore import Qt
from PySide2.QtWidgets import QLabel, QLineEdit, QToolButton, QVBoxLayout

from model.mod_list import ModListWidget

logger = logging.getLogger(__name__)


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

        self.inactive_mods_list = ModListWidget()

        self.inactive_mods_search = QLineEdit()
        self.inactive_mods_search.setClearButtonEnabled(True)
        self.inactive_mods_search.textChanged.connect(self.signal_inactive_mods_search)
        self.inactive_mods_search_clear_button = self.inactive_mods_search.findChild(
            QToolButton
        )
        self.inactive_mods_search_clear_button.setEnabled(True)
        self.inactive_mods_search_clear_button.clicked.connect(
            self.clear_inactive_mods_search
        )
        self.inactive_mods_search.setPlaceholderText("Search inactive mods...")

        # Add widgets to base layout
        self.panel.addWidget(self.num_mods)
        self.panel.addWidget(self.inactive_mods_search)
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

    def clear_inactive_mods_search(self):
        self.inactive_mods_search.setText("")
        self.inactive_mods_search.clearFocus()

    def signal_inactive_mods_search(self, pattern: str) -> None:
        wni = self.inactive_mods_list.get_widgets_and_items()
        for widget, item in wni:
            if (
                pattern
                and not pattern.lower() in widget.json_data["name"].lower()
                and not pattern.lower() in widget.json_data["packageId"].lower()
            ):
                item.setHidden(True)
            else:
                item.setHidden(False)
        self.update_count(wni)

    def update_count(self, widgets_and_items):
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

from functools import partial
from typing import Dict

from PySide6.QtCore import Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QToolButton, QMenu


class MultiButton(QWidget):
    def __init__(
        self,
        actions_signal: Signal,
        main_action_name: str,
        main_action_tooltip: str,
        context_menu_content: Dict[str, str],
    ):
        super().__init__()

        # Create a horizontal layout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create a QPushButton for the main action
        self.main_action = QPushButton(main_action_name, self)
        self.main_action.setToolTip(main_action_tooltip)
        layout.addWidget(self.main_action)

        # Create a QToolButton with a menu for the secondary action
        self.secondary_action = QToolButton(self)
        self.secondary_action.setIcon(QIcon(""))
        self.secondary_action.setPopupMode(QToolButton.InstantPopup)
        layout.addWidget(self.secondary_action)

        # Create the context menu
        self.createContextMenu(
            actions_signal=actions_signal, menu_content=context_menu_content
        )

        self.setLayout(layout)

    def createContextMenu(
        self, actions_signal: Signal, menu_content: Dict[str, str]
    ) -> None:
        context_menu = QMenu(self)
        for action_key, option_text in menu_content.items():
            action = context_menu.addAction(option_text)
            action.triggered.connect(partial(actions_signal.emit, action_key))
        self.secondary_action.setMenu(context_menu)

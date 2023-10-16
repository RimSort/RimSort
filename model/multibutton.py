from functools import partial
import os
from pathlib import Path
from typing import Dict

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QToolButton, QMenu


class MultiButton(QWidget):
    def __init__(
        self,
        actions_signal: Signal,
        main_action_name: str,
        main_action_tooltip: str,
        context_menu_content: Dict[str, str],
        secondary_action_icon_path=None,
    ):
        super().__init__()

        # Set the object name for styling
        self.setObjectName("MultiButton")

        # Use custom icon path, or use default kebab icons (Thanks Cousax)
        self.secondary_action_icon_path = (
            secondary_action_icon_path
            if secondary_action_icon_path
            else str(
                Path(
                    os.path.join(os.path.dirname(__file__), "../data/kebab.png")
                ).resolve()
            )
        )

        # Create a horizontal layout
        layout = QHBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create a QPushButton for the main action
        self.main_action = QPushButton(main_action_name, self)
        self.main_action.setToolTip(main_action_tooltip)
        layout.addWidget(self.main_action)

        # Create a QToolButton with a menu for the secondary action
        self.secondary_action = QToolButton(self)
        self.secondary_action.setIcon(QIcon(self.secondary_action_icon_path))
        self.secondary_action.setPopupMode(QToolButton.InstantPopup)
        # Set the style to show the icon only - we don't need the icon applied from the InstantPopup attribute
        self.secondary_action.setStyleSheet(
            "QToolButton::menu-indicator { image: none; }"
        )
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

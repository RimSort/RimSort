from functools import partial
from typing import Dict, List, Union

from PySide6.QtCore import Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QMenu,
    QPushButton,
    QToolButton,
    QWidget,
)

from app.utils.app_info import AppInfo


class MultiButton(QWidget):
    def __init__(
        self,
        main_action: Union[str, List[str]],
        main_action_tooltip: str,
        context_menu_content: Union[Dict[str, str], List[QAction]],
        actions_signal=None,
        secondary_action_icon_path=None,
    ):
        super().__init__()

        self.main_action: Union[QPushButton, QComboBox]

        # Set the object name for styling
        self.setObjectName("MultiButton")

        # Use custom icon path, or use default kebab icons (Thanks Cousax)
        self.secondary_action_icon_path = (
            secondary_action_icon_path
            if secondary_action_icon_path
            else str(AppInfo().theme_data_folder / "default-icons" / "kebab.png")
        )

        # Create a horizontal layout
        layout = QHBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        # If it's a string, make a button using the text provided
        if isinstance(main_action, str):
            # Create a QPushButton for the main action
            self.main_action = QPushButton(main_action, self)
            self.main_action.setToolTip(main_action_tooltip)
            layout.addWidget(self.main_action)
        # Otherwise, it can be a list so that the action can be a QComboBox
        elif isinstance(main_action, list):
            self.main_action = QComboBox(self)
            self.main_action.addItems(main_action)
            self.main_action.setObjectName("MainUI")
            self.main_action.setToolTip(main_action_tooltip)
            layout.addWidget(self.main_action)

        # Create a QToolButton with a menu for the secondary action
        self.secondary_action = QToolButton(self)
        self.secondary_action.setIcon(QIcon(self.secondary_action_icon_path))
        self.secondary_action.setPopupMode(QToolButton.InstantPopup)
        layout.addWidget(self.secondary_action)

        # Create the context menu
        self.createContextMenu(
            actions_signal=actions_signal, menu_content=context_menu_content
        )

        self.setLayout(layout)

    def createContextMenu(
        self,
        actions_signal: Signal,
        menu_content: Union[
            Dict[str, Union[str, QAction]], List[QAction]
        ],  # TODO 2: remove the encapsulating Union once the 1st change is complete elsewhere
    ) -> None:
        context_menu = QMenu(self)
        if isinstance(menu_content, dict):
            for action_key, option_value in menu_content.items():
                if isinstance(option_value, str):
                    action = context_menu.addAction(option_value)
                    action.triggered.connect(partial(actions_signal.emit, action_key))
                elif isinstance(option_value, QAction):
                    context_menu.addAction(option_value)
        # TODO 1: refactor items that rely on the following elif. They can use the dict now that the above elif allows adding QAction as well
        elif isinstance(menu_content, list):
            for action_obj in menu_content:
                context_menu.addAction(action_obj)
        self.secondary_action.setMenu(context_menu)

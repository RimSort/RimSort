"""
Button factory utilities for creating standardized buttons in mod panels.
"""

from dataclasses import dataclass
from typing import Any, Callable

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QPushButton, QToolButton


@dataclass
class MenuItem:
    """Represents a menu item for button configurations."""

    text: str
    callback: Callable[[], None]


class ButtonFactory:
    """Factory class for creating standardized buttons."""

    def __init__(self, panel: Any):
        self.panel = panel

    def create_refresh_button(
        self, callback: Callable[[], None] | None = None
    ) -> QPushButton:
        """Create a refresh button."""
        return self.panel._create_refresh_button(callback)

    def create_steamcmd_button(self, pfid_column: int) -> QPushButton:
        """Create a SteamCMD download button."""
        return self.panel._create_steamcmd_button(pfid_column)

    def create_subscribe_button(
        self,
        pfid_column: int,
        completion_callback: Callable[[], None] | None = None,
    ) -> QPushButton:
        """Create a subscribe button."""
        return self.panel._create_subscribe_button(pfid_column, completion_callback)

    def create_unsubscribe_button(
        self,
        pfid_column: int,
        completion_callback: Callable[[], None] | None = None,
    ) -> QPushButton:
        """Create an unsubscribe button."""
        return self.panel._create_unsubscribe_button(pfid_column, completion_callback)

    def create_delete_button(
        self,
        menu_title: str,
        completion_callback: Callable[[], None] | None = None,
        enable_delete_mod: bool = True,
        enable_delete_keep_dds: bool = False,
        enable_delete_dds_only: bool = False,
        enable_delete_and_unsubscribe: bool = False,
        enable_delete_and_resubscribe: bool = False,
    ) -> QPushButton:
        """Create a deletion button with menu."""
        return self.panel._create_deletion_button(
            self.panel.settings_controller,
            self.panel._get_selected_mod_metadata,
            completion_callback,
            menu_title,
            enable_delete_mod,
            enable_delete_keep_dds,
            enable_delete_dds_only,
            enable_delete_and_unsubscribe,
            enable_delete_and_resubscribe,
        )

    def create_custom_button(
        self, text: str, callback: Callable[[], None]
    ) -> QPushButton:
        """Create a custom button."""
        button = QPushButton(text)
        button.clicked.connect(callback)
        return button

    def create_select_button(
        self, text: str, menu_items: list[MenuItem]
    ) -> QToolButton:
        """Create a select button with dropdown menu."""
        button = QToolButton()
        button.setText(text)
        menu = QMenu(button)
        for menu_item in menu_items:
            action = QAction(menu_item.text, self.panel)
            action.triggered.connect(menu_item.callback)
            menu.addAction(action)
        button.setMenu(menu)
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        return button

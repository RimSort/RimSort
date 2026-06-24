"""
Button factory utilities for creating standardized buttons in mod panels.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QPushButton

from app.models.operation_mode import OperationMode


class ButtonType(Enum):
    """Enumeration of button types for standardized button creation."""

    REFRESH = "refresh"
    STEAMCMD = "steamcmd"
    STEAM = "steam"
    DELETE = "delete"

    CUSTOM = "custom"


@dataclass
class ButtonConfig:
    """Configuration for creating standardized buttons."""

    button_type: ButtonType
    text: str = ""
    pfid_column: int | None = None
    completion_callback: Callable[[], None] | None = None
    menu_items: list[MenuItem] | None = None
    get_selected_mod_metadata: Callable[[], list[dict[str, Any]]] | None = None
    menu_title: str | None = None
    enable_delete_mod: bool = True
    enable_delete_keep_dds: bool = False
    enable_delete_dds_only: bool = False
    enable_delete_and_unsubscribe: bool = True
    enable_delete_and_resubscribe: bool = False
    custom_callback: Callable[[], None] | None = None


@dataclass
class MenuItem:
    """Represents a menu item for button configurations."""

    text: str
    callback: Callable[[], None]


class ButtonFactory:
    """Factory class for creating standardized buttons."""

    def __init__(self, panel: Any):
        self.panel = panel

    def create_dropdown_button(
        self,
        text: str,
        object_name: str,
        menu_items: list[tuple[str, Callable[[], None]]],
    ) -> QPushButton:
        """Create a QPushButton with a dropdown menu."""
        button = QPushButton()
        button.setText(self.panel.tr(text))
        button.setObjectName(object_name)
        menu = QMenu(button)
        for label, callback in menu_items:
            action = QAction(self.panel.tr(label), self.panel)
            action.triggered.connect(callback)
            menu.addAction(action)
        button.setMenu(menu)
        button.clicked.connect(
            lambda: menu.exec(button.mapToGlobal(button.rect().bottomLeft()))
        )
        return button

    def create_refresh_button(
        self, callback: Callable[[], None] | None = None
    ) -> QPushButton:
        """Create a refresh button."""
        button = QPushButton()
        button.setText(self.panel.tr("Refresh"))
        button.setObjectName("primaryButton")
        if callback:
            button.clicked.connect(callback)
        return button

    def create_steamcmd_button(self, pfid_column: int) -> QPushButton:
        """Create a SteamCMD button with dropdown menu."""
        return self.create_dropdown_button(
            "SteamCMD",
            "actionButton",
            [
                (
                    "Download with SteamCMD",
                    self.panel._create_update_callback(
                        pfid_column, OperationMode.STEAMCMD
                    ),
                ),
            ],
        )

    def create_select_all_button(self) -> QPushButton:
        """Create a button with Select all/Deselect all dropdown."""
        return self.create_dropdown_button(
            "Select",
            "actionButton",
            [
                ("Select all", lambda: self.panel._set_all_checkbox_rows(True)),
                ("Deselect all", lambda: self.panel._set_all_checkbox_rows(False)),
            ],
        )

    def create_steam_button(
        self,
        pfid_column: int,
        completion_callback: Callable[[], None] | None = None,
    ) -> QPushButton:
        """Create a Steam button with subscribe/unsubscribe dropdown."""
        return self.create_dropdown_button(
            "Steam",
            "actionButton",
            [
                (
                    "Subscribe selected",
                    self.panel._create_update_callback(
                        pfid_column,
                        OperationMode.STEAM,
                        "subscribe",
                        completion_callback,
                    ),
                ),
                (
                    "Unsubscribe selected",
                    self.panel._create_update_callback(
                        pfid_column,
                        OperationMode.STEAM,
                        "unsubscribe",
                        completion_callback,
                    ),
                ),
            ],
        )

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
            self.panel.settings,
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
        button.setObjectName("primaryButton")
        button.clicked.connect(callback)
        return button

"""
Global variables for the application.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.controllers.settings_controller import SettingsController
    from app.views.main_window import MainWindow

MAIN_WINDOW: "MainWindow | None" = None
SETTINGS_CONTROLLER: "SettingsController | None" = None

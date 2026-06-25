"""
Global variables for the application.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.settings import Settings
    from app.views.main_window import MainWindow

MAIN_WINDOW: "MainWindow | None" = None
SETTINGS: "Settings | None" = None

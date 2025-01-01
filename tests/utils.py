"""Common test utilities and imports"""

from typing import Optional, Set

from PySide6.QtWidgets import QApplication

from app.controllers.file_search_controller import FileSearchController
from app.models.settings import Settings
from app.views.file_search_dialog import FileSearchDialog


def create_test_app() -> QApplication:
    """Create a QApplication instance for testing"""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def setup_test_controller(
    mods_path: str,
    active_mod_ids: Optional[Set[str]] = None,
    scope: str = "all mods",
) -> FileSearchController:
    """Set up a FileSearchController for testing"""
    # ensure we have a QApplication instance
    create_test_app()
    dialog = FileSearchDialog()
    settings = Settings()

    class TestInstance:
        def __init__(self, local_folder: str):
            self.local_folder = local_folder
            self.workshop_folder = None
            self.config_folder = None

    settings.instances = {"test": TestInstance(mods_path)}
    settings.current_instance = "test"

    controller = FileSearchController(settings, dialog)
    if active_mod_ids is not None:
        controller.set_active_mod_ids(active_mod_ids)

    return controller

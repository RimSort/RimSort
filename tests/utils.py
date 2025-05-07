"""Common test utilities and imports"""

from typing import Optional

from PySide6.QtWidgets import QApplication

from app.controllers.file_search_controller import FileSearchController
from app.controllers.settings_controller import SettingsController
from app.models.instance import Instance
from app.models.settings import Settings
from app.views.file_search_dialog import FileSearchDialog
from app.views.settings_dialog import SettingsDialog


def create_test_app() -> QApplication:
    """
    Create a QApplication instance for testing.

    Returns:
        QApplication: The QApplication instance for testing.

    Raises:
        RuntimeError: If an existing application instance is not of type QApplication.
    """
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    elif not isinstance(app, QApplication):
        raise RuntimeError("Expected QApplication instance, got QCoreApplication.")
    return app


def setup_test_controller(
    mods_path: str,
    active_mod_ids: Optional[set[str]] = None,
    scope: str = "all mods",
) -> FileSearchController:
    """
    Set up a FileSearchController for testing.

    Args:
        mods_path (str): Path to the mods directory.
        active_mod_ids (Optional[Set[str]]): Set of active mod IDs for filtering.
        scope (str): Search scope (e.g., "all mods", "active mods").

    Returns:
        FileSearchController: Configured FileSearchController instance for testing.
    """
    # ensure we have a QApplication instance
    create_test_app()
    dialog = FileSearchDialog()
    settings = Settings()

    class TestInstance(Instance):
        def __init__(self) -> None:
            super().__init__()
            self.local_folder = ""
            self.workshop_folder = ""
            self.config_folder = ""

    settings.instances = {"test": TestInstance()}
    settings.current_instance = "test"

    settings_dialog = SettingsDialog()
    settings_controller = SettingsController(model=settings, view=settings_dialog)
    controller = FileSearchController(
        settings=settings, settings_controller=settings_controller, dialog=dialog
    )
    if active_mod_ids is not None:
        controller.set_active_mod_ids(active_mod_ids)

    return controller

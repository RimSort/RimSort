"""Shared fixtures for settings tab controller tests."""

from typing import Generator
from unittest.mock import MagicMock, patch

import pytest

from app.controllers.settings_tabs.sorting_tab_controller import SortingTabController
from app.models.settings import Settings


@pytest.fixture()
def _mock_settings_deps() -> Generator[None, None, None]:
    """Patch QApplication and AppInfo so Settings() can be instantiated in tests."""
    with (
        patch("app.models.settings.QApplication") as mock_qapp,
        patch("app.models.settings.AppInfo") as mock_app_info,
    ):
        mock_qapp.font.return_value.family.return_value = "monospace"
        mock_app_info.return_value.app_storage_folder = MagicMock()
        mock_app_info.return_value.app_settings_file = MagicMock()
        yield


@pytest.fixture()
def sorting_tab(
    _mock_settings_deps: None,
) -> tuple[SortingTabController, Settings, MagicMock]:
    """Create a SortingTabController with a fresh Settings model and mock dialog."""
    settings = Settings()
    dialog = MagicMock()
    controller = SortingTabController(settings, dialog)
    return controller, settings, dialog

"""Shared fixtures for settings tab controller tests."""

from unittest.mock import MagicMock

import pytest

from app.controllers.settings_tabs.sorting_tab_controller import SortingTabController
from app.models.settings import Settings


@pytest.fixture()
def sorting_tab(
    _mock_settings_deps: None,
) -> tuple[SortingTabController, Settings, MagicMock]:
    """Create a SortingTabController with a fresh Settings model and mock dialog."""
    settings = Settings()
    dialog = MagicMock()
    controller = SortingTabController(settings, dialog)
    return controller, settings, dialog

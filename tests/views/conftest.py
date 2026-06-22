"""Shared fixtures for view and widget tests."""

from __future__ import annotations

import sys
import uuid as uuid_module
from types import ModuleType
from typing import TYPE_CHECKING, Any, Union
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QCoreApplication, QObject
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QMainWindow

from app.controllers.settings_controller import SettingsController
from app.models.instance import Instance
from app.models.settings import Settings

# Ensure the steamworks module is mockable for the MainWindow import chain.
# This must run at import time, before any test imports MainWindow.
if "steamworks" not in sys.modules:
    sys.modules["steamworks"] = ModuleType("steamworks")
    sys.modules["steamworks"].STEAMWORKS = MagicMock()  # type: ignore[attr-defined]

if TYPE_CHECKING:
    from app.views.main_window import MainWindow


def make_stub_main_window(metadata_controller: MagicMock | None = None) -> MainWindow:
    """Create a MainWindow instance without running MainWindow.__init__.

    Calls QMainWindow.__init__ to satisfy the C++ side (Shiboken),
    then attaches the minimal attributes that downstream methods expect.
    """
    from app.views.main_window import MainWindow

    instance = MainWindow.__new__(MainWindow)
    QMainWindow.__init__(instance)
    instance.main_content_panel = MagicMock()
    instance.watchdog_event_handler = None
    instance.metadata_controller = metadata_controller or MagicMock()
    return instance


@pytest.fixture
def mock_settings_controller(
    tmp_path: Any,
    mock_app_info: None,
    fresh_event_bus: None,
    qapp: Union[QApplication, QCoreApplication],
) -> MagicMock:
    """MagicMock(spec=SettingsController) with a real Settings model."""
    settings = Settings()

    instance = Instance(
        name="Default",
        game_folder=str(tmp_path / "game"),
        config_folder=str(tmp_path / "config"),
        local_folder=str(tmp_path / "local_mods"),
        workshop_folder=str(tmp_path / "workshop"),
    )
    QObject.__setattr__(settings, "instances", {"Default": instance})
    QObject.__setattr__(settings, "current_instance", "Default")

    controller = MagicMock(spec=SettingsController)
    controller.settings = settings
    controller.active_instance = instance
    return controller


def make_mod_data(
    name: str = "Test Mod",
    package_id: str = "test.author.testmod",
    uuid: str | None = None,
    data_source: str = "local",
    authors: str = "Test Author",
    path: str = "/fake/mods/TestMod",
    publishedfileid: str = "",
    version: str = "1.0",
    supported_versions: list[str] | None = None,
    dependencies: list[Any] | None = None,
    load_after: list[Any] | None = None,
    load_before: list[Any] | None = None,
    incompatibilities: list[str] | None = None,
    csharp: bool | None = None,
    git_repo: bool = False,
    steamcmd: bool = False,
    invalid: bool = False,
    url: str = "",
    description: str = "A test mod.",
    mod_color: QColor | None = None,
) -> dict[str, Any]:
    """Factory for mod metadata dicts (legacy format, used by context menu code)."""
    if uuid is None:
        uuid = str(uuid_module.uuid4())

    return {
        "uuid": uuid,
        "name": name,
        "packageid": package_id,
        "authors": authors,
        "path": path,
        "data_source": data_source,
        "publishedfileid": publishedfileid,
        "version": version,
        "supported_versions": supported_versions or ["1.5"],
        "dependencies": dependencies or [],
        "loadTheseBefore": load_before or [],
        "loadTheseAfter": load_after or [],
        "incompatibilities": incompatibilities or [],
        "csharp": csharp,
        "git_repo": git_repo,
        "steamcmd": steamcmd,
        "invalid": invalid,
        "url": url,
        "description": description,
        "mod_color": mod_color,
        "alternative": None,
    }

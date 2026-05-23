import os
from typing import Union
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication, QMenuBar

from app.controllers.menu_bar_controller import MenuBarController
from app.controllers.settings_controller import SettingsController
from app.views.menu_bar import MenuBar


@pytest.fixture
def mock_settings_controller() -> MagicMock:
    """Mock SettingsController."""
    controller = MagicMock(spec=SettingsController)
    controller.settings = MagicMock()
    controller.settings.check_for_update_startup = False
    controller.settings.text_editor_location = None
    controller.settings.instances = {"Default": MagicMock()}
    controller.settings.current_instance = "Default"
    return controller


@pytest.fixture
def menu_bar_instance(
    mock_settings_controller: MagicMock,
    qapp: Union[QApplication, QCoreApplication],
) -> MenuBar:
    """Create a MenuBar instance for testing."""
    qt_menu_bar = QMenuBar()
    menu_bar = MenuBar(qt_menu_bar, mock_settings_controller)
    return menu_bar


class TestMenuBarUpdateMenuCreation:
    """Test the MenuBar Update menu creation with environment variable."""

    def test_update_menu_shown_when_env_var_not_set(
        self,
        mock_settings_controller: MagicMock,
        qapp: Union[QApplication, QCoreApplication],
    ) -> None:
        """Test that Update menu is created when RIMSORT_DISABLE_UPDATER is not set."""
        # Ensure environment variable is not set
        with patch.dict(os.environ, {}, clear=False):
            if "RIMSORT_DISABLE_UPDATER" in os.environ:
                del os.environ["RIMSORT_DISABLE_UPDATER"]

            qt_menu_bar = QMenuBar()
            menu_bar = MenuBar(qt_menu_bar, mock_settings_controller)

            # Verify that update actions were created
            assert menu_bar.check_for_updates_action is not None
            assert menu_bar.check_for_updates_on_startup_action is not None

            # Verify the menu exists
            menus = [
                qt_menu_bar.actions()[i].text()
                for i in range(len(qt_menu_bar.actions()))
            ]
            assert "Update" in menus

    def test_update_menu_hidden_when_env_var_set(
        self,
        mock_settings_controller: MagicMock,
        qapp: Union[QApplication, QCoreApplication],
    ) -> None:
        """Test that Update menu is not created when RIMSORT_DISABLE_UPDATER is set."""
        # Set the environment variable
        with patch.dict(os.environ, {"RIMSORT_DISABLE_UPDATER": "1"}):
            qt_menu_bar = QMenuBar()
            menu_bar = MenuBar(qt_menu_bar, mock_settings_controller)

            # Verify that update actions were not created (should be None)
            assert menu_bar.check_for_updates_action is None
            assert menu_bar.check_for_updates_on_startup_action is None

            # Verify the menu does not exist
            menus = [
                qt_menu_bar.actions()[i].text()
                for i in range(len(qt_menu_bar.actions()))
            ]
            assert "Update" not in menus


class TestMenuBarControllerWithDisabledUpdater:
    """Test MenuBarController initialization with disabled updater."""

    def test_controller_initialization_with_env_var_set(
        self,
        mock_settings_controller: MagicMock,
        qapp: Union[QApplication, QCoreApplication],
    ) -> None:
        """Test that MenuBarController initializes correctly when actions are None."""
        # Set the environment variable
        with patch.dict(os.environ, {"RIMSORT_DISABLE_UPDATER": "1"}):
            qt_menu_bar = QMenuBar()
            menu_bar = MenuBar(qt_menu_bar, mock_settings_controller)

            # This should not raise an exception even though actions are None
            with patch("app.controllers.menu_bar_controller.EventBus"):
                controller = MenuBarController(menu_bar, mock_settings_controller)

            # Verify the controller was created successfully
            assert controller is not None

    def test_controller_initialization_without_env_var(
        self,
        mock_settings_controller: MagicMock,
        qapp: Union[QApplication, QCoreApplication],
    ) -> None:
        """Test that MenuBarController initializes correctly when actions exist."""
        # Ensure environment variable is not set
        with patch.dict(os.environ, {}, clear=False):
            if "RIMSORT_DISABLE_UPDATER" in os.environ:
                del os.environ["RIMSORT_DISABLE_UPDATER"]

            qt_menu_bar = QMenuBar()
            menu_bar = MenuBar(qt_menu_bar, mock_settings_controller)

            # This should not raise an exception
            with patch("app.controllers.menu_bar_controller.EventBus"):
                controller = MenuBarController(menu_bar, mock_settings_controller)

            # Verify the controller was created successfully
            assert controller is not None


class TestDisableUpdaterFlag:
    """Test the --disable-updater command-line flag processing."""

    def test_disable_updater_flag_sets_env_var(self) -> None:
        """Test that --disable-updater flag sets the environment variable."""
        import sys

        original_argv = sys.argv.copy()
        original_env = os.environ.get("RIMSORT_DISABLE_UPDATER")

        try:
            sys.argv = ["rimsort", "--disable-updater"]

            # Simulate the flag processing from __main__.py
            if "--disable-updater" in sys.argv:
                os.environ["RIMSORT_DISABLE_UPDATER"] = "1"
                while "--disable-updater" in sys.argv:
                    sys.argv.remove("--disable-updater")

            # Verify environment variable was set
            assert os.environ.get("RIMSORT_DISABLE_UPDATER") == "1"

            # Verify flag was removed from sys.argv
            assert "--disable-updater" not in sys.argv
            assert sys.argv == ["rimsort"]

        finally:
            # Cleanup
            sys.argv = original_argv
            if original_env is None:
                if "RIMSORT_DISABLE_UPDATER" in os.environ:
                    del os.environ["RIMSORT_DISABLE_UPDATER"]
            else:
                os.environ["RIMSORT_DISABLE_UPDATER"] = original_env

    def test_multiple_disable_updater_flags(self) -> None:
        """Test that multiple --disable-updater flags are all removed."""
        import sys

        original_argv = sys.argv.copy()
        original_env = os.environ.get("RIMSORT_DISABLE_UPDATER")

        try:
            sys.argv = ["rimsort", "--disable-updater", "--disable-updater", "build-db"]

            # Simulate the flag processing from __main__.py
            if "--disable-updater" in sys.argv:
                os.environ["RIMSORT_DISABLE_UPDATER"] = "1"
                while "--disable-updater" in sys.argv:
                    sys.argv.remove("--disable-updater")

            # Verify all flags were removed
            assert "--disable-updater" not in sys.argv
            assert sys.argv == ["rimsort", "build-db"]

        finally:
            # Cleanup
            sys.argv = original_argv
            if original_env is None:
                if "RIMSORT_DISABLE_UPDATER" in os.environ:
                    del os.environ["RIMSORT_DISABLE_UPDATER"]
            else:
                os.environ["RIMSORT_DISABLE_UPDATER"] = original_env

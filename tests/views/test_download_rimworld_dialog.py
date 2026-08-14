"""Tests for the Download RimWorld Version dialog."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Union
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from app.services.version_data_service import RimWorldVersion

if TYPE_CHECKING:
    from app.views.download_rimworld_dialog import DownloadRimWorldDialog


@pytest.fixture
def mock_version_service() -> MagicMock:
    service = MagicMock()
    service.get_platform_key.return_value = "win64"
    service.get_available_versions.return_value = [
        RimWorldVersion(
            manifest_id="abc123",
            version_string="1.5.0",
            status="release",
            dlcs={"royalty": "def456"},
        ),
        RimWorldVersion(
            manifest_id="xyz789",
            version_string="1.4.0",
            status="release",
            dlcs={},
        ),
    ]
    service.get_depot_id.side_effect = lambda item, platform: {
        ("base_game", "win64"): 294100,
        ("royalty", "win64"): 294110,
    }.get((item, platform))
    return service


@pytest.fixture
def dialog(
    mock_version_service: MagicMock,
    qapp: Union[QApplication, QCoreApplication],
) -> DownloadRimWorldDialog:
    with patch(
        "app.views.download_rimworld_dialog.VersionDataService",
        return_value=mock_version_service,
    ):
        from app.views.download_rimworld_dialog import DownloadRimWorldDialog

        return DownloadRimWorldDialog()


class TestDialogInitialization:
    def test_creates_service(self, dialog: Any) -> None:
        assert dialog.version_service is not None

    def test_loads_versions_into_combo(self, dialog: Any) -> None:
        assert dialog.version_combo.count() == 2
        assert dialog.version_combo.currentText() == "1.5.0 (release)"

    def test_path_edit_starts_empty(self, dialog: Any) -> None:
        assert dialog.path_edit.text() == ""

    def test_username_edit_starts_empty(self, dialog: Any) -> None:
        assert dialog.username_edit.text() == ""


class TestDownloadValidation:
    def test_requires_version_selection(self, dialog: Any) -> None:
        dialog.version_combo.setCurrentIndex(-1)
        with patch("app.views.download_rimworld_dialog.show_warning") as mock_warn:
            dialog._on_download()
            mock_warn.assert_called_once()

    def test_requires_destination_path(self, dialog: Any) -> None:
        with patch("app.views.download_rimworld_dialog.show_warning") as mock_warn:
            dialog._on_download()
            args = mock_warn.call_args[0]
            assert "destination" in args[1].lower()

    def test_requires_steam_username(self, dialog: Any) -> None:
        dialog.path_edit.setText("C:/games/rimworld")
        with patch("app.views.download_rimworld_dialog.show_warning") as mock_warn:
            dialog._on_download()
            args = mock_warn.call_args[0]
            assert "username" in args[1].lower()

    def test_shows_steamcmd_warning_when_not_setup(self, dialog: Any) -> None:
        dialog.path_edit.setText("C:/games/rimworld")
        dialog.username_edit.setText("testuser")
        mock_steamcmd = MagicMock()
        mock_steamcmd.setup = False
        with (
            patch(
                "app.views.download_rimworld_dialog.SteamcmdInterface.instance",
                return_value=mock_steamcmd,
            ),
            patch("app.views.download_rimworld_dialog.show_warning") as mock_warn,
        ):
            dialog._on_download()
            args = mock_warn.call_args[0]
            assert "SteamCMD" in args[1]

    def test_starts_download_when_all_prerequisites_met(self, dialog: Any) -> None:
        dialog.path_edit.setText("C:/games/rimworld")
        dialog.username_edit.setText("testuser")
        mock_steamcmd = MagicMock()
        mock_steamcmd.setup = True
        with (
            patch(
                "app.views.download_rimworld_dialog.SteamcmdInterface.instance",
                return_value=mock_steamcmd,
            ),
            patch("app.views.download_rimworld_dialog.show_warning") as mock_warn,
            patch("app.views.download_rimworld_dialog.QMessageBox") as mock_msgbox,
        ):
            dialog._on_download()
            mock_steamcmd.download_game_version.assert_called_once()
            assert mock_msgbox.information.called
            mock_warn.assert_not_called()

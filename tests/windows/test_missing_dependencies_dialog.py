from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QLabel, QPushButton, QWidget
from pytestqt.qtbot import QtBot

from app.services.dependency_resolver import DepResolveResult
from app.windows.missing_dependencies_dialog import MissingDependenciesDialog

_LOCAL_DEPS_SUMMARY = {
    "active.mod": {
        "satisfied": set(),
        "local": {"dep.local"},
        "download": set(),
    }
}
_LOCAL_MISSING_DEPS = {"active.mod": {"dep.local"}}


@pytest.fixture
def metadata_controller() -> MagicMock:
    controller = MagicMock()
    controller.get_mod_name_from_package_id.side_effect = lambda pkg_id: pkg_id
    return controller


@pytest.fixture
def dialog(
    metadata_controller: MagicMock, qtbot: QtBot
) -> MissingDependenciesDialog:
    missing_dialog = MissingDependenciesDialog(metadata_controller)
    qtbot.addWidget(missing_dialog)
    return missing_dialog


def _find_button(parent: QWidget, text: str) -> QPushButton:
    for button in parent.findChildren(QPushButton):
        if button.text() == text:
            return button
    raise AssertionError(f"Button {text!r} not found")


def test_show_dialog_is_non_modal_and_returns_selected(
    dialog: MissingDependenciesDialog,
) -> None:
    def accept_with_selection() -> None:
        dialog.checkboxes["dep.local"].setChecked(True)
        dialog.accept()

    QTimer.singleShot(100, accept_with_selection)

    selected = dialog.show_dialog(_LOCAL_DEPS_SUMMARY, _LOCAL_MISSING_DEPS)

    assert dialog.windowModality() == Qt.WindowModality.NonModal
    assert selected == {"dep.local"}


def test_show_dialog_reject_returns_empty(dialog: MissingDependenciesDialog) -> None:
    QTimer.singleShot(100, dialog.reject)

    selected = dialog.show_dialog(_LOCAL_DEPS_SUMMARY, _LOCAL_MISSING_DEPS)

    assert selected == set()


class TestMissingDependenciesDialogPopulate:
    def test_empty_deps_summary_shows_message(
        self, dialog: MissingDependenciesDialog
    ) -> None:
        dialog._populate_dependencies({})

        item = dialog.scroll_layout.itemAt(0)
        assert item is not None
        widget = item.widget()
        assert isinstance(widget, QLabel)
        assert "No dependencies found" in widget.text()

    def test_download_with_workshop_id_enables_download_button(
        self, dialog: MissingDependenciesDialog, qtbot: QtBot
    ) -> None:
        dep_resolve = {
            "author.missing": DepResolveResult(
                package_id="author.missing",
                workshop_id="12345",
                workshop_url="https://steamcommunity.com/sharedfiles/filedetails/?id=12345",
                source="steam_db",
            )
        }
        deps_summary = {
            "active.mod": {
                "satisfied": set(),
                "local": set(),
                "download": {"author.missing"},
            }
        }

        dialog._dep_resolve = dep_resolve
        dialog._populate_dependencies(deps_summary)

        download_btn = _find_button(dialog, "Download")
        open_btn = _find_button(dialog, "Open Workshop")

        assert download_btn.isEnabled()
        assert open_btn.isEnabled()

        with qtbot.waitSignal(dialog.download_requested, timeout=1000) as blocker:
            qtbot.mouseClick(download_btn, Qt.MouseButton.LeftButton)  # type: ignore[no-untyped-call]

        assert blocker.args == ["12345"]

    def test_download_without_workshop_id_disables_download_button(
        self, dialog: MissingDependenciesDialog,
    ) -> None:
        deps_summary = {
            "active.mod": {
                "satisfied": set(),
                "local": set(),
                "download": {"author.unknown"},
            }
        }

        dialog._dep_resolve = {
            "author.unknown": DepResolveResult(
                package_id="author.unknown",
                workshop_id=None,
                workshop_url=None,
                source="none",
            )
        }
        dialog._populate_dependencies(deps_summary)

        download_btn = _find_button(dialog, "Download")
        open_btn = _find_button(dialog, "Open Workshop")

        assert not download_btn.isEnabled()
        assert open_btn.isEnabled()

        hints = dialog.findChildren(QLabel, "missingWorkshopHint")
        assert len(hints) == 1
        assert "Workshop ID not found" in hints[0].text()

from unittest.mock import MagicMock

from PySide6.QtCore import Qt, QTimer
from pytestqt.qtbot import QtBot

from app.windows.missing_dependencies_dialog import MissingDependenciesDialog


def test_show_dialog_is_non_modal_and_returns_selected(qtbot: QtBot) -> None:
    metadata_controller = MagicMock()
    metadata_controller.get_mod_name_from_package_id.side_effect = lambda pkg_id: pkg_id

    dialog = MissingDependenciesDialog(metadata_controller)
    qtbot.addWidget(dialog)

    deps_summary = {
        "active.mod": {
            "satisfied": set(),
            "local": {"dep.local"},
            "download": set(),
        }
    }
    missing_deps = {"active.mod": {"dep.local"}}

    def accept_with_selection() -> None:
        dialog.checkboxes["dep.local"].setChecked(True)
        dialog.accept()

    QTimer.singleShot(100, accept_with_selection)

    selected = dialog.show_dialog(deps_summary, missing_deps)

    assert dialog.windowModality() == Qt.WindowModality.NonModal
    assert selected == {"dep.local"}


def test_show_dialog_reject_returns_empty(qtbot: QtBot) -> None:
    metadata_controller = MagicMock()
    metadata_controller.get_mod_name_from_package_id.side_effect = lambda pkg_id: pkg_id

    dialog = MissingDependenciesDialog(metadata_controller)
    qtbot.addWidget(dialog)

    deps_summary = {
        "active.mod": {
            "satisfied": set(),
            "local": {"dep.local"},
            "download": set(),
        }
    }
    missing_deps = {"active.mod": {"dep.local"}}

    QTimer.singleShot(100, dialog.reject)

    selected = dialog.show_dialog(deps_summary, missing_deps)

    assert selected == set()

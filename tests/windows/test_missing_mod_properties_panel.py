import sys
from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette, QStandardItem
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox
from pytestqt.qtbot import QtBot

from app.models.metadata.metadata_structure import AboutXmlMod, CaseInsensitiveStr
from app.utils.constants import DEFAULT_MISSING_PACKAGEID
from app.utils.ignore_manager import IgnoreManager
from app.windows.missing_mod_properties_panel import MissingModPropertiesPanel


@pytest.fixture(params=[True, False], ids=["RimPy", "themes-disabled"])
def themed_app(qapp: QApplication, request: pytest.FixtureRequest) -> Generator[bool]:
    original_style = qapp.style().objectName()
    original_palette = QPalette(qapp.palette())
    original_stylesheet = qapp.styleSheet()
    qapp.setStyleSheet("")
    qapp.setStyle("Fusion")
    palette = qapp.style().standardPalette()
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#000000"))
    palette.setColor(QPalette.ColorRole.Window, QColor("#efefef"))
    qapp.setPalette(palette)
    themed = bool(request.param)
    if themed:
        stylesheet = Path(__file__).resolve().parents[2] / "themes/RimPy/style.qss"
        qapp.setStyleSheet(stylesheet.read_text())
    yield themed
    qapp.setStyleSheet("")
    qapp.setStyle(original_style)
    qapp.setPalette(original_palette)
    qapp.setStyleSheet(original_stylesheet)


@pytest.fixture
def message_boxes(
    monkeypatch: pytest.MonkeyPatch,
) -> list[QMessageBox]:
    boxes: list[QMessageBox] = []

    def capture(box: QMessageBox) -> int:
        box.ensurePolished()
        boxes.append(box)
        return int(QMessageBox.StandardButton.Ok)

    def block_static_dialog(*args: object, **kwargs: object) -> None:
        pytest.fail("Static message boxes bypass the themed dialogue background")

    monkeypatch.setattr(QMessageBox, "exec", capture)
    for method in ("information", "warning", "critical"):
        monkeypatch.setattr(QMessageBox, method, block_static_dialog)
    return boxes


@pytest.fixture
def panel(qtbot: QtBot) -> MissingModPropertiesPanel:
    controller = MagicMock()
    controller.mods_metadata = {}
    widget = MissingModPropertiesPanel([], [], controller)
    qtbot.addWidget(widget)
    return widget


@pytest.mark.parametrize(
    ("scenario", "title", "icon", "text"),
    [
        (
            "missing-id",
            "Cannot Add",
            QMessageBox.Icon.Warning,
            "These mods need valid Package IDs first:<br>• Synthetic Mod",
        ),
        (
            "valid-id",
            "Success",
            QMessageBox.Icon.Information,
            "Mods added to ignore list. Panel will refresh.",
        ),
        (
            "no-selection",
            "No Selection",
            QMessageBox.Icon.Information,
            "Please select mods to add to the ignore list.",
        ),
        (
            "save-failure",
            "Error",
            QMessageBox.Icon.Critical,
            "Error adding mods to ignore list: synthetic write error",
        ),
    ],
)
def test_ignore_list_messages_are_readable(
    panel: MissingModPropertiesPanel,
    themed_app: bool,
    message_boxes: list[QMessageBox],
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
    title: str,
    icon: QMessageBox.Icon,
    text: str,
) -> None:
    package_id = "diagnostic.synthetic"
    if scenario != "no-selection":
        if scenario == "missing-id":
            package_id = DEFAULT_MISSING_PACKAGEID
        mod = AboutXmlMod(
            name="Synthetic Mod", package_id=CaseInsensitiveStr(package_id)
        )
        panel.metadata_controller.mods_metadata["synthetic-key"] = mod
        item = QStandardItem(mod.name)
        item.setData("synthetic-key", Qt.ItemDataRole.UserRole)
        panel._add_row([item], default_checkbox_state=True)

    if scenario == "save-failure":

        def fail_save(mods: list[str] | set[str]) -> bool:
            raise OSError("synthetic write error")

        monkeypatch.setattr(IgnoreManager, "add_ignored_mods", fail_save)

    panel._add_to_ignore_list()

    assert len(message_boxes) == 1
    box = message_boxes[0]
    assert box.parentWidget() is panel
    assert box.objectName() == "dialogue"
    if sys.platform != "darwin":
        assert box.windowTitle() == panel.tr(title)
    assert box.icon() == icon
    assert text in box.text()
    assert box.standardButtons() == QMessageBox.StandardButton.Ok
    label = box.findChild(QLabel, "qt_msgbox_label")
    assert label is not None
    palette = label.palette()
    foreground = palette.color(QPalette.ColorRole.WindowText).name()
    background = box.palette().color(QPalette.ColorRole.Window).name()
    assert (foreground, background) == (
        ("#e6edf3", "#1b2838") if themed_app else ("#000000", "#efefef")
    )
    assert IgnoreManager.load_ignored_mods() == (
        {package_id} if scenario == "valid-id" else set()
    )

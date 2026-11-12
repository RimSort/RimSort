from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QMainWindow,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from pytestqt.qtbot import QtBot

from app.views.player_log_tab import PlayerLogTab

pytestmark = pytest.mark.usefixtures("mock_metadata_controller")


@pytest.fixture(params=["none", "RimPy"])
def player_log_widget(
    request: pytest.FixtureRequest,
    qapp: QApplication,
    mock_settings_controller: MagicMock,
) -> Generator[PlayerLogTab]:
    original_style = qapp.style().objectName()
    original_stylesheet = qapp.styleSheet()
    qapp.setStyle("Fusion")
    stylesheet = ""
    if request.param == "RimPy":
        stylesheet = '* { font-family: "Tahoma"; font-size: 12px; }'
        stylesheet += (
            Path(__file__).resolve().parents[2] / "themes" / "RimPy" / "style.qss"
        ).read_text(encoding="utf-8")
    qapp.setStyleSheet(stylesheet)
    settings = mock_settings_controller.settings
    settings.auto_load_player_log_on_startup = False
    tab = PlayerLogTab(settings)
    yield tab
    qapp.setStyle(original_style)
    qapp.setStyleSheet(original_stylesheet)


def test_hidden_player_log_does_not_force_window_taller(
    qapp: QApplication, qtbot: QtBot, player_log_widget: PlayerLogTab
) -> None:
    window = QMainWindow()
    qtbot.addWidget(window)
    tabs = QTabWidget()
    main_tab = QWidget()
    layout = QVBoxLayout(main_tab)
    layout.addStretch()
    buttons = [QPushButton(text) for text in ("Refresh", "Sort", "Save")]
    button_layout = QHBoxLayout()
    for button in buttons:
        button_layout.addWidget(button)
    layout.addLayout(button_layout)
    tabs.addTab(main_tab, "Main")
    tabs.addTab(player_log_widget, "Player Log")
    window.setCentralWidget(tabs)
    window.resize(1366, 680)
    window.show()
    qapp.processEvents()

    assert tabs.currentWidget() is main_tab
    assert player_log_widget.isHidden()
    assert window.minimumSizeHint().height() <= 680
    assert window.height() <= 680
    for button in buttons:
        assert window.rect().contains(button.mapTo(window, QPoint(0, button.height())))

    tabs.setCurrentWidget(player_log_widget)
    qapp.processEvents()
    assert window.height() <= 680
    tabs.setCurrentWidget(main_tab)
    qapp.processEvents()
    assert window.height() <= 680


def test_player_log_controls_remain_reachable_in_short_window(
    qapp: QApplication, qtbot: QtBot, player_log_widget: PlayerLogTab
) -> None:
    host = QWidget()
    qtbot.addWidget(host)
    tab = player_log_widget
    tab.setParent(host)
    host.resize(1000, 400)
    host.show()
    tab.resize(1000, 400)
    tab.show()
    qapp.processEvents()

    assert tab.minimumSizeHint().height() <= 400
    assert tab.height() == 400
    scroll_area = tab.left_scroll_area
    assert scroll_area.verticalScrollBar().maximum() > 0
    scroll_to_end = next(
        button
        for button in tab.nav_group.findChildren(QPushButton)
        if button.text() == "Scroll to End"
    )
    scroll_area.ensureWidgetVisible(scroll_to_end)
    qapp.processEvents()
    viewport = scroll_area.viewport()
    assert viewport.rect().contains(
        QRect(scroll_to_end.mapTo(viewport, QPoint()), scroll_to_end.size())
    )
    tab.log_display.setPlainText("\n".join(str(line) for line in range(200)))
    tab.log_display.moveCursor(QTextCursor.MoveOperation.Start)
    QTest.mouseClick(scroll_to_end, Qt.MouseButton.LeftButton)
    assert tab.log_display.textCursor().atEnd()

    # A child widget can test tall allocations even on a small desktop.
    tab.resize(1366, 1200)
    qapp.processEvents()
    assert tab.height() == 1200
    assert scroll_area.verticalScrollBar().maximum() == 0
    assert 350 <= scroll_area.width() <= 500


@pytest.mark.parametrize(
    ("is_waylith", "expected_subdir"),
    [(False, ""), (True, "Logs")],
    ids=["unity_pre_1_7", "waylith_1_7_plus"],
)
def test_get_player_log_path_respects_waylith(
    mock_settings_controller: MagicMock,
    mock_metadata_controller: MagicMock,
    tmp_path: Path,
    is_waylith: bool,
    expected_subdir: str,
) -> None:
    settings = mock_settings_controller.settings
    settings.instances[settings.current_instance].config_folder = str(
        tmp_path / "config"
    )
    mock_metadata_controller.is_waylith = is_waylith

    player_log = tmp_path / expected_subdir / "Player.log"
    player_log.parent.mkdir(parents=True, exist_ok=True)
    player_log.write_text("log")

    tab = PlayerLogTab(settings)

    assert tab._get_player_log_path() == player_log


def test_get_player_log_path_none_when_missing(
    mock_settings_controller: MagicMock,
    mock_metadata_controller: MagicMock,
    tmp_path: Path,
) -> None:
    settings = mock_settings_controller.settings
    settings.instances[settings.current_instance].config_folder = str(
        tmp_path / "config"
    )
    mock_metadata_controller.is_waylith = True

    tab = PlayerLogTab(settings)

    assert tab._get_player_log_path() is None

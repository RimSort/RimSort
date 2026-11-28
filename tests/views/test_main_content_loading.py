from collections.abc import Generator
from pathlib import Path
from threading import Event

import pytest
from PySide6.QtCore import QPoint, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from pytestqt.qtbot import QtBot

from app.models.animations import LoadingAnimation
from app.views.main_content_panel import MainContent


@pytest.fixture(params=["none", "RimPy"])
def loading_window(
    request: pytest.FixtureRequest,
    qapp: QApplication,
    qtbot: QtBot,
    main_content: tuple[MainContent, list[bool]],
) -> Generator[tuple[QMainWindow, MainContent, QPushButton]]:
    original_style = qapp.style().objectName()
    original_stylesheet = qapp.styleSheet()
    qapp.setStyle("Fusion")
    stylesheet = ""
    if request.param == "RimPy":
        stylesheet = "* { font-size: 12px; }" + (
            Path(__file__).resolve().parents[2] / "themes/RimPy/style.qss"
        ).read_text(encoding="utf-8")
    qapp.setStyleSheet(stylesheet)
    content, _ = main_content
    window = QMainWindow()
    qtbot.addWidget(window)
    central = QWidget()
    layout = QVBoxLayout(central)
    layout.addWidget(content.main_layout_frame)
    buttons = QHBoxLayout()
    refresh = QPushButton("Refresh")
    buttons.addWidget(refresh)
    layout.addLayout(buttons)
    window.setCentralWidget(central)
    window.resize(1200, 400)
    window.show()
    qapp.processEvents()
    yield window, content, refresh
    window.close()
    qapp.setStyle(original_style)
    qapp.setStyleSheet(original_stylesheet)


@pytest.mark.parametrize("long_text", [False, True])
def test_loading_preserves_window_size(
    loading_window: tuple[QMainWindow, MainContent, QPushButton],
    qtbot: QtBot,
    long_text: bool,
) -> None:
    window, content, refresh = loading_window
    original_size = window.size()
    original_state = window.windowState()
    assert original_size.height() == 400
    expected = {"parsed": True}
    release = Event()
    samples: list[tuple[int, int]] = []

    def target() -> dict[str, bool]:
        assert release.wait(5)
        return expected

    def inspect_animation() -> None:
        try:
            qtbot.waitUntil(
                lambda: any(
                    widget.isVisible()
                    for widget in window.findChildren(LoadingAnimation)
                )
            )
            animation = next(
                widget
                for widget in window.findChildren(LoadingAnimation)
                if widget.isVisible()
            )
            qtbot.waitUntil(lambda: animation.movie.currentFrameNumber() > 0)
            samples.append(window.size().toTuple())
            assert window.size() == original_size
            assert window.windowState() == original_state
            pixmap = animation.label.pixmap()
            assert pixmap is not None and not pixmap.isNull()
            assert pixmap.width() == pixmap.height()
            assert pixmap.width() <= animation.label.width()
            assert pixmap.height() <= animation.label.height()
            caption = next(
                widget
                for widget in window.findChildren(QLabel, "loadingAnimationString")
                if widget.isVisible()
            )
            assert window.rect().contains(caption.mapTo(window, QPoint()))
            assert window.rect().contains(
                caption.mapTo(window, QPoint(caption.width(), caption.height()))
            )
            assert window.rect().contains(
                refresh.mapTo(window, QPoint(0, refresh.height()))
            )
        finally:
            release.set()

    gif = Path(__file__).resolve().parents[2] / "themes/default-icons/rimsort.gif"
    text = "Scanning mod sources and populating metadata..."
    if long_text:
        text = " ".join([text] * 8)
    for _ in range(2):
        release.clear()
        QTimer.singleShot(0, inspect_animation)
        result = content.do_threaded_loading_animation(str(gif), target, text)
        assert result is expected
        assert window.size() == original_size
        assert window.windowState() == original_state
        assert content.mod_info_panel.info_panel_frame.isVisible()
        assert content._active_loading_loop is None
    assert len(samples) == 2

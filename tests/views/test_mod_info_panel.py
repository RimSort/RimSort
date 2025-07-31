# jscpd:ignore-file
from typing import Any
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import Qt

from app.views.mod_info_panel import ClickablePathLabel


@pytest.fixture
def label(qtbot: Any) -> ClickablePathLabel:
    lbl = ClickablePathLabel()
    qtbot.addWidget(lbl)
    return lbl


def test_initialization(label: ClickablePathLabel) -> None:
    assert label.clickable is True
    assert label.cursor().shape() == Qt.CursorShape.PointingHandCursor
    assert label.styleSheet() == "text-decoration: underline;"
    assert label.path == ""
    assert label.text() == ""
    assert label.toolTip() == ""


def test_set_path(label: ClickablePathLabel) -> None:
    test_path = "/test/path"
    label.setPath(test_path)
    assert label.path == test_path
    assert label.text() == test_path
    assert label.toolTip() == f"Click to open folder: {test_path}"

    label.setPath("")
    assert label.path == ""
    assert label.text() == ""
    assert label.toolTip() == ""

    label.setPath(None)
    assert label.path == ""
    assert label.text() == ""
    assert label.toolTip() == ""


def test_set_clickable(label: ClickablePathLabel) -> None:
    label.setClickable(False)
    assert label.clickable is False
    assert label.cursor().shape() == Qt.CursorShape.ArrowCursor

    label.setClickable(True)
    assert label.clickable is True
    assert label.cursor().shape() == Qt.CursorShape.PointingHandCursor


def test_mouse_press_event_open_folder(label: ClickablePathLabel, monkeypatch: Any, qtbot: Any) -> None:
    test_path = "/test/path"
    label.setPath(test_path)

    mock_path = MagicMock()
    mock_path.exists.return_value = True
    mock_path.is_dir.return_value = True
    monkeypatch.setattr("app.views.mod_info_panel.Path", lambda p: mock_path)

    mock_open = MagicMock()
    monkeypatch.setattr("app.views.mod_info_panel.platform_specific_open", mock_open)

    mock_logger = MagicMock()
    monkeypatch.setattr("app.views.mod_info_panel.logger", mock_logger)

    # Simulate left mouse click via pytest-qt
    qtbot.mouseClick(label, Qt.MouseButton.LeftButton)

    mock_open.assert_called_once_with(test_path)
    mock_logger.info.assert_called_once_with(f"Opening mod folder: {test_path}")


def test_mouse_press_event_folder_not_exist(label: ClickablePathLabel, monkeypatch: Any, qtbot: Any) -> None:
    test_path = "/test/path"
    label.setPath(test_path)

    mock_path = MagicMock()
    mock_path.exists.return_value = False
    monkeypatch.setattr("app.views.mod_info_panel.Path", lambda p: mock_path)

    mock_open = MagicMock()
    monkeypatch.setattr("app.views.mod_info_panel.platform_specific_open", mock_open)

    mock_logger = MagicMock()
    monkeypatch.setattr("app.views.mod_info_panel.logger", mock_logger)

    # Simulate left mouse click via pytest-qt
    qtbot.mouseClick(label, Qt.MouseButton.LeftButton)

    mock_open.assert_not_called()
    mock_logger.warning.assert_called_once_with(f"Mod folder does not exist: {test_path}")


def test_mouse_press_event_not_folder(label: ClickablePathLabel, monkeypatch: Any, qtbot: Any) -> None:
    test_path = "/test/file.txt"
    label.setPath(test_path)

    mock_path = MagicMock()
    mock_path.exists.return_value = True
    mock_path.is_dir.return_value = False
    monkeypatch.setattr("app.views.mod_info_panel.Path", lambda p: mock_path)

    mock_open = MagicMock()
    monkeypatch.setattr("app.views.mod_info_panel.platform_specific_open", mock_open)

    mock_logger = MagicMock()
    monkeypatch.setattr("app.views.mod_info_panel.logger", mock_logger)

    # Simulate left mouse click via pytest-qt
    qtbot.mouseClick(label, Qt.MouseButton.LeftButton)

    mock_open.assert_not_called()
    mock_logger.warning.assert_called_once_with(f"Path is not a directory: {test_path}")


def test_mouse_press_event_exception(label: ClickablePathLabel, monkeypatch: Any, qtbot: Any) -> None:
    test_path = "/test/path"
    label.setPath(test_path)

    mock_path = MagicMock()
    mock_path.exists.side_effect = Exception("Test exception")
    monkeypatch.setattr("app.views.mod_info_panel.Path", lambda p: mock_path)

    mock_logger = MagicMock()
    monkeypatch.setattr("app.views.mod_info_panel.logger", mock_logger)

    # Simulate left mouse click via pytest-qt
    qtbot.mouseClick(label, Qt.MouseButton.LeftButton)

    mock_logger.error.assert_called_once_with(f"Failed to open mod folder {test_path}: Test exception")


def test_mouse_press_event_not_left_button(label: ClickablePathLabel, monkeypatch: Any, qtbot: Any) -> None:
    test_path = "/test/path"
    label.setPath(test_path)

    mock_open = MagicMock()
    monkeypatch.setattr("app.views.mod_info_panel.platform_specific_open", mock_open)

    # Simulate right mouse click via pytest-qt
    qtbot.mouseClick(label, Qt.MouseButton.RightButton)

    mock_open.assert_not_called()


def test_mouse_press_event_not_clickable(label: ClickablePathLabel, monkeypatch: Any, qtbot: Any) -> None:
    test_path = "/test/path"
    label.setPath(test_path)
    label.setClickable(False)

    mock_open = MagicMock()
    monkeypatch.setattr("app.views.mod_info_panel.platform_specific_open", mock_open)

    # Simulate left mouse click via pytest-qt
    qtbot.mouseClick(label, Qt.MouseButton.LeftButton)

    mock_open.assert_not_called()


def test_mouse_press_event_no_path(label: ClickablePathLabel, monkeypatch: Any, qtbot: Any) -> None:
    label.setPath("")

    mock_open = MagicMock()
    monkeypatch.setattr("app.views.mod_info_panel.platform_specific_open", mock_open)

    # Simulate left mouse click via pytest-qt
    qtbot.mouseClick(label, Qt.MouseButton.LeftButton)

    mock_open.assert_not_called() 
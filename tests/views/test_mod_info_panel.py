from typing import Any, Tuple
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import Qt

from app.views.mod_info_panel import ClickablePathLabel


@pytest.fixture
def label(qtbot: Any) -> ClickablePathLabel:
    """Create a ClickablePathLabel instance for testing.
    
    Args:
        qtbot: Pytest-Qt bot for widget testing.
        
    Returns:
        ClickablePathLabel: A configured label instance for testing.
    """
    lbl = ClickablePathLabel()
    qtbot.addWidget(lbl)
    return lbl


def test_initialization(label: ClickablePathLabel) -> None:
    """Test that ClickablePathLabel initializes with correct default values.
    
    Args:
        label: The ClickablePathLabel instance to test.
    """
    assert label.clickable is True
    assert label.cursor().shape() == Qt.CursorShape.PointingHandCursor
    assert label.styleSheet() == "text-decoration: underline;"
    assert label.path == ""
    assert label.text() == ""
    assert label.toolTip() == ""


def test_set_path(label: ClickablePathLabel) -> None:
    """Test setting and clearing the path property.
    
    Args:
        label: The ClickablePathLabel instance to test.
    """
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
    """Test enabling and disabling clickable behavior.
    
    Args:
        label: The ClickablePathLabel instance to test.
    """
    label.setClickable(False)
    assert label.clickable is False
    assert label.cursor().shape() == Qt.CursorShape.ArrowCursor

    label.setClickable(True)
    assert label.clickable is True
    assert label.cursor().shape() == Qt.CursorShape.PointingHandCursor


@pytest.fixture
def mocked_env(monkeypatch: Any) -> Tuple[MagicMock, MagicMock, MagicMock]:
    """Create mocked environment for path-related tests.
    
    Args:
        monkeypatch: Pytest monkeypatch fixture.
        
    Returns:
        Tuple containing mocked Path, platform_specific_open, and logger objects.
    """
    mock_path = MagicMock()
    monkeypatch.setattr("app.views.mod_info_panel.Path", lambda p: mock_path)
    mock_open = MagicMock()
    monkeypatch.setattr("app.views.mod_info_panel.platform_specific_open", mock_open)
    mock_logger = MagicMock()
    monkeypatch.setattr("app.views.mod_info_panel.logger", mock_logger)
    return mock_path, mock_open, mock_logger


@pytest.mark.parametrize(
    "exists_return, is_dir_return, exists_side_effect, expected_open, expected_log_level, expected_log_msg",
    [
        (True, True, None, "/test/path", "info", "Opening mod folder: /test/path"),
        (False, None, None, None, "warning", "Mod folder does not exist: /test/path"),
        (True, False, None, None, "warning", "Path is not a directory: /test/path"),
        (None, None, Exception("Test exception"), None, "error", "Failed to open mod folder /test/path: Test exception"),
    ]
)
def test_mouse_press_path_scenarios(
    label: ClickablePathLabel,
    mocked_env: Tuple[MagicMock, MagicMock, MagicMock],
    qtbot: Any,
    exists_return: Any,
    is_dir_return: Any,
    exists_side_effect: Any,
    expected_open: Any,
    expected_log_level: Any,
    expected_log_msg: Any,
) -> None:
    """Test various path scenarios when clicking the label.
    
    This test covers different path validation scenarios:
    - Valid directory path (should open folder)
    - Non-existent path (should log warning)
    - File path instead of directory (should log warning)
    - Exception during path validation (should log error)
    
    Args:
        label: The ClickablePathLabel instance to test.
        mocked_env: Tuple of mocked objects (path, open, logger).
        qtbot: Pytest-Qt bot for widget testing.
        exists_return: Return value for Path.exists().
        is_dir_return: Return value for Path.is_dir().
        exists_side_effect: Side effect for Path.exists() (for exceptions).
        expected_open: Expected path to be opened, or None if no open expected.
        expected_log_level: Expected log level (info, warning, error).
        expected_log_msg: Expected log message.
    """
    mock_path, mock_open, mock_logger = mocked_env
    test_path = "/test/path"
    label.setPath(test_path)
    
    # Configure mock behavior based on test parameters
    if exists_return is not None:
        mock_path.exists.return_value = exists_return
    if is_dir_return is not None:
        mock_path.is_dir.return_value = is_dir_return
    if exists_side_effect is not None:
        mock_path.exists.side_effect = exists_side_effect
    
    # Simulate left mouse click
    qtbot.mouseClick(label, Qt.MouseButton.LeftButton)
    
    # Verify expected behavior
    if expected_open:
        mock_open.assert_called_once_with(expected_open)
    else:
        mock_open.assert_not_called()
    if expected_log_level:
        getattr(mock_logger, expected_log_level).assert_called_once_with(expected_log_msg)


def test_mouse_press_event_not_left_button(label: ClickablePathLabel, mocked_env: Tuple[MagicMock, MagicMock, MagicMock], qtbot: Any) -> None:
    """Test that right mouse button clicks are ignored.
    
    Args:
        label: The ClickablePathLabel instance to test.
        mocked_env: Tuple of mocked objects (path, open, logger).
        qtbot: Pytest-Qt bot for widget testing.
    """
    _, mock_open, _ = mocked_env
    test_path = "/test/path"
    label.setPath(test_path)
    qtbot.mouseClick(label, Qt.MouseButton.RightButton)
    mock_open.assert_not_called()


def test_mouse_press_event_not_clickable(label: ClickablePathLabel, mocked_env: Tuple[MagicMock, MagicMock, MagicMock], qtbot: Any) -> None:
    """Test that clicks are ignored when label is not clickable.
    
    Args:
        label: The ClickablePathLabel instance to test.
        mocked_env: Tuple of mocked objects (path, open, logger).
        qtbot: Pytest-Qt bot for widget testing.
    """
    _, mock_open, _ = mocked_env
    test_path = "/test/path"
    label.setPath(test_path)
    label.setClickable(False)
    qtbot.mouseClick(label, Qt.MouseButton.LeftButton)
    mock_open.assert_not_called()


def test_mouse_press_event_no_path(label: ClickablePathLabel, mocked_env: Tuple[MagicMock, MagicMock, MagicMock], qtbot: Any) -> None:
    """Test that clicks are ignored when no path is set.
    
    Args:
        label: The ClickablePathLabel instance to test.
        mocked_env: Tuple of mocked objects (path, open, logger).
        qtbot: Pytest-Qt bot for widget testing.
    """
    _, mock_open, _ = mocked_env
    label.setPath("")
    qtbot.mouseClick(label, Qt.MouseButton.LeftButton)
    mock_open.assert_not_called() 
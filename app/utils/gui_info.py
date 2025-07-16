from pathlib import Path
from typing import List, Optional

from loguru import logger
from PySide6.QtCore import QMargins, QSize
from PySide6.QtGui import (
    QCursor,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QPixmap,
    QScreen,
)
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from app.models.settings import Settings


class GUIInfo:
    """
    A singleton class to store and provide common GUI information.

    This class provides a central location for storing common GUI-related
    properties such as fonts, margins, and other display attributes. It
    implements the Singleton design pattern to ensure that only one instance
    of the class exists throughout the application.
    """

    _instance: "None | GUIInfo" = None

    def __new__(cls) -> "GUIInfo":
        """
        Ensure only one instance of GUIInfo is created (Singleton pattern).

        Returns:
            GUIInfo: The single instance of the GUIInfo class.
        """
        if not cls._instance:
            cls._instance = super(GUIInfo, cls).__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """
        Initialize the GUIInfo instance with default values.

        This method initializes various GUI-related properties only once,
        even if multiple initializations are attempted.
        """
        if hasattr(self, "_is_initialized") and self._is_initialized:
            return

        self._default_font: QFont = QApplication.font()

        self._emphasis_font: QFont = QFont(self._default_font)
        self._emphasis_font.setWeight(QFont.Weight.Bold)

        self._smaller_font: QFont = QFont(self._default_font)
        self._smaller_font.setPointSize(self._smaller_font.pointSize() - 1)

        self._default_font_line_height: int = QFontMetrics(
            self._default_font
        ).lineSpacing()
        self._default_font_average_char_width: int = QFontMetrics(
            self._default_font
        ).averageCharWidth()

        self._text_field_margins: QMargins = QMargins(4, 4, 4, 4)

        icon_path = "themes/default-icons/AppIcon_alt.ico"
        if Path(icon_path).exists():
            self._app_icon = QPixmap(icon_path)
        else:
            self._app_icon = QPixmap()

        self._is_initialized: bool = True

    def _get_screen_and_dpr(self) -> tuple[Optional[QScreen], float]:
        """
        Helper method to get the current screen under the cursor and its device pixel ratio.

        Returns:
            tuple[Optional[QScreen], float]: The screen object and its device pixel ratio.
        """
        screen = (
            QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        )
        device_pixel_ratio = (
            screen.devicePixelRatio()
            if screen and hasattr(screen, "devicePixelRatio")
            else 1.0
        )
        return screen, device_pixel_ratio

    def set_window_size(self) -> tuple[int, int, int, int]:
        """
        Calculate the recommended window size and position, DPI-aware and clamped to the correct screen.
        This method is robust for high-DPI and multi-monitor setups.

        Returns:
            tuple[int, int, int, int]: The x position, y position, width, and height for the window.
        """
        screen, device_pixel_ratio = self._get_screen_and_dpr()
        if not screen:
            # Fallback to safe defaults
            window_width, window_height = 800, 600
            x_position, y_position = 100, 100
        else:
            screen_geometry = screen.availableGeometry()
            # Calculate size before DPI scaling
            raw_width = int(screen_geometry.width() * 0.6)
            raw_height = int(screen_geometry.height() * 0.6)
            # Apply DPI scaling before clamping
            scaled_width = int(raw_width / device_pixel_ratio)
            scaled_height = int(raw_height / device_pixel_ratio)
            # Clamp to min/max reasonable values
            min_width, min_height = 800, 600
            max_width, max_height = screen_geometry.width(), screen_geometry.height()
            window_width = min(max(scaled_width, min_width), max_width)
            window_height = min(max(scaled_height, min_height), max_height)
            # Center the window on the screen
            x_position = int(
                screen_geometry.x() + (screen_geometry.width() - window_width) / 2
            )
            y_position = int(
                screen_geometry.y() + (screen_geometry.height() - window_height) / 2
            )
        return x_position, y_position, window_width, window_height

    def get_window_geometry(self) -> tuple[int, int, int, int]:
        """
        Get window geometry (x, y, width, height) using saved settings if valid and visible,
        else fallback to default window size. Always reloads settings from disk.
        Handles high-DPI and multi-monitor setups robustly.

        Returns:
            tuple[int, int, int, int]: The x position, y position, width, and height for the window.
        """
        settings = Settings()
        settings.load()
        screen, device_pixel_ratio = self._get_screen_and_dpr()
        if not screen:
            return self.set_window_size()
        screen_geometry = screen.availableGeometry()
        # Validate settings with fallback defaults
        min_width, min_height = 800, 600
        valid = (
            settings.window_width >= min_width
            and settings.window_height >= min_height
            and settings.window_width <= screen_geometry.width()
            and settings.window_height <= screen_geometry.height()
            and screen_geometry.contains(settings.window_x, settings.window_y)
        )
        if not valid:
            logger.warning(
                f"Window geometry invalid or out of bounds: x={settings.window_x}, y={settings.window_y}, width={settings.window_width}, height={settings.window_height}. Falling back to default size."
            )
        if valid:
            # Clamp width/height to available screen
            width = min(settings.window_width, screen_geometry.width())
            height = min(settings.window_height, screen_geometry.height())
            # Clamp position to visible area
            x = max(
                screen_geometry.x(),
                min(settings.window_x, screen_geometry.right() - width),
            )
            y = max(
                screen_geometry.y(),
                min(settings.window_y, screen_geometry.bottom() - height),
            )
            # Adjust for DPI scaling if needed
            width = int(width / device_pixel_ratio)
            height = int(height / device_pixel_ratio)
            return x, y, width, height
        else:
            return self.set_window_size()

    def get_panel_size(self) -> QSize:
        """
        Adjust the size hint when resizing.

        Returns:
            QSize: The size of the panel.
        """
        settings = Settings()
        # Load Settings
        settings.load()
        # Get settings values with fallback defaults
        width = getattr(settings, "panel_width", 800)
        height = getattr(settings, "panel_height", 600)
        if not isinstance(width, int) or width <= 0:
            width = 800
        if not isinstance(height, int) or height <= 0:
            height = 600
        # Return adjusted size
        return QSize(width, height)

    @property
    def default_font(self) -> QFont:
        """
        Get the default font used in the application.

        Returns:
            QFont: The default font.
        """
        return self._default_font

    @property
    def emphasis_font(self) -> QFont:
        """
        Get a bolder version of the default font for emphasis.

        Returns:
            QFont: The emphasis font.
        """
        return self._emphasis_font

    @property
    def smaller_font(self) -> QFont:
        """
        Get the smaller version of the default font.

        Returns:
            QFont: The smaller font.
        """
        return self._smaller_font

    @property
    def default_font_line_height(self) -> int:
        """
        Get the line height of the default font.

        Returns:
            int: The line height of the default font.
        """
        return self._default_font_line_height

    @property
    def default_font_average_char_width(self) -> int:
        """
        Get the average character width of the default font.

        Returns:
            int: The average character width of the default font.
        """
        return self._default_font_average_char_width

    @property
    def text_field_margins(self) -> QMargins:
        """
        Get the margins for text fields.

        Returns:
            QMargins: The margins for text fields.
        """
        return self._text_field_margins

    @property
    def app_icon(self) -> QPixmap:
        """
        Get the application icon.

        Returns:
            QPixmap: The application icon.
        """
        return self._app_icon


def show_dialogue_conditional(
    title: str,
    text: str,
    icon: str = "question",
    buttons: Optional[List[str]] = None,
    default_button: Optional[str] = None,
) -> bool:
    """Show a dialog with Yes/No buttons and return True if Yes was clicked"""
    msg_box = QMessageBox()
    msg_box.setWindowTitle(title)
    msg_box.setText(text)

    # Set icon
    if icon == "warning":
        msg_box.setIcon(QMessageBox.Icon.Warning)
    elif icon == "error":
        msg_box.setIcon(QMessageBox.Icon.Critical)
    elif icon == "info":
        msg_box.setIcon(QMessageBox.Icon.Information)
    else:
        msg_box.setIcon(QMessageBox.Icon.Question)

    # Set buttons
    if not buttons:
        buttons = ["Yes", "No"]
    button_map = {
        "Yes": QMessageBox.StandardButton.Yes,
        "No": QMessageBox.StandardButton.No,
        "Ok": QMessageBox.StandardButton.Ok,
        "Cancel": QMessageBox.StandardButton.Cancel,
    }
    for button in buttons:
        msg_box.addButton(button_map[button])

    # Set default button
    if default_button:
        msg_box.setDefaultButton(button_map[default_button])

    return msg_box.exec() == QMessageBox.StandardButton.Yes


def show_dialogue_file(
    title: str,
    directory: str,
    file_type: str = "File",
    file_filter: str = "",
    is_save: bool = False,
) -> Optional[str]:
    """Show a file dialog and return the selected path"""
    dialog = QFileDialog()
    dialog.setWindowTitle(title)
    dialog.setDirectory(directory)

    if file_type == "Directory":
        dialog.setFileMode(QFileDialog.FileMode.Directory)
        dialog.setOption(QFileDialog.Option.ShowDirsOnly, True)
        if dialog.exec():
            return dialog.selectedFiles()[0]
    else:
        if is_save:
            file_path, _ = QFileDialog.getSaveFileName(
                parent=None, caption=title, dir=directory, filter=file_filter
            )
            return file_path if file_path else None
        else:
            dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
            if file_filter:
                dialog.setNameFilter(file_filter)
            if dialog.exec():
                return dialog.selectedFiles()[0]

    return None

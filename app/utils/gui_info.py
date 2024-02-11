from typing import Optional

from PySide6.QtCore import QMargins
from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import QApplication


class GUIInfo:
    """
    A singleton class to store and provide common GUI information.

    This class provides a central location for storing common GUI-related
    properties such as fonts, margins, and other display attributes. It
    implements the Singleton design pattern to ensure that only one instance
    of the class exists throughout the application.
    """

    _instance: Optional["GUIInfo"] = None

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

        # Get default font from QApplication
        self._default_font: QFont = QApplication.font()

        # Create an emphasis font by making a bolder version of the default font
        self._emphasis_font: QFont = QFont(self._default_font)
        self._emphasis_font.setWeight(QFont.Weight.Bold)

        # Create a smaller version of the default font
        self._smaller_font: QFont = QFont(self._default_font)
        self._smaller_font.setPointSize(self._smaller_font.pointSize() - 1)

        # Calculate line height and average character width of the default font
        self._default_font_line_height: int = QFontMetrics(
            self._default_font
        ).lineSpacing()
        self._default_font_average_char_width: int = QFontMetrics(
            self._default_font
        ).averageCharWidth()

        # Define default margins for text fields
        self._text_field_margins: QMargins = QMargins(4, 4, 4, 4)

        # Set initialization flag to True
        self._is_initialized: bool = True

    @property
    def default_font(self) -> QFont:
        """
        Get the default font used in the application.
        """
        return self._default_font

    @property
    def emphasis_font(self) -> QFont:
        """
        Get a bolder version of the default font for emphasis.
        """
        return self._emphasis_font

    @property
    def smaller_font(self) -> QFont:
        """
        Get the smaller version of the default font.
        """
        return self._smaller_font

    @property
    def default_font_line_height(self) -> int:
        """
        Get the line height of the default font.
        """
        return self._default_font_line_height

    @property
    def default_font_average_char_width(self) -> int:
        """
        Get the average character width of the default font.
        """
        return self._default_font_average_char_width

    @property
    def text_field_margins(self) -> QMargins:
        """
        Get the margins for text fields.
        """
        return self._text_field_margins

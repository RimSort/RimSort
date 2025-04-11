from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QLabel

"""
All types of custom QLabels are implemented here.
"""


class ClickableQLabel(QLabel):
    """
    Basic implementation of a clickable QLabel.

    Emits 'clicked' signal when clicked on.
    """

    clicked = Signal()

    def mousePressEvent(self, ev: QMouseEvent) -> None:
        self.clicked.emit()
        super().mousePressEvent(ev)


class AdvancedClickableQLabel(QLabel):
    """
    Advanced implementation of a clickable QLabel.

    Emits 'clicked' signal when clicked on.

    Changes background to indicate the label is currently active/clicked. (on/off behavior)
    """

    clicked = Signal()

    def __init__(self, *args: Any) -> None:
        super().__init__(*args)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.is_clicked = False
        self.clicked.connect(self.handle_label_clicked)
        self.update_style()

    def mousePressEvent(self, ev: QMouseEvent) -> None:
        self.clicked.emit()
        super().mousePressEvent(ev)

    def handle_label_clicked(self) -> None:
        self.is_clicked = not self.is_clicked
        self.update_style()

    def get_clicked(self) -> bool:
        """
        Returns the current state of the label.
        """
        return self.is_clicked

    def update_style(self) -> None:
        """
        Updates the label's style based on the 'is_clicked' attribute.

        If the label is clicked, the backround color is changed to indicate it's active.

        If the label is not clicked, the background color is transparent(Default).
        """
        if self.is_clicked:
            self.setStyleSheet("""
                QLabel {
                    background-color: #4C5A73;
                    border-radius: 4px;
                    }
            """)
        else:
            self.setStyleSheet("""
                QLabel {
                    background-color: transparent;
                    border-radius: 4px;
                }
            """)

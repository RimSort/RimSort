from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QLabel


class AdvancedClickableQLabel(QLabel):
    clicked = Signal()

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)
        self.is_clicked = False
        self.update_style()

    def mousePressEvent(self, ev: QMouseEvent) -> None:
        self.clicked.emit()
        super().mousePressEvent(ev)
        self.is_clicked = not self.is_clicked
        self.update_style()
        
    def update_style(self):
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
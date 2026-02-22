from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QMouseEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QWidget,
)


class _ClickableArrow(QLabel):
    """Small arrow label that emits a signal when clicked."""

    clicked = Signal()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            return
        super().mousePressEvent(event)


class DividerItemInner(QWidget):
    """Widget displayed inside a list item to represent a named, collapsible divider."""

    toggle_signal = Signal(str)

    def __init__(self, uuid: str, name: str, collapsed: bool = False) -> None:
        super().__init__()
        self.uuid = uuid
        self._collapsed = collapsed

        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setObjectName("DividerItemInner")

        layout = QHBoxLayout()
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)

        self.arrow_label = _ClickableArrow()
        self.arrow_label.setFixedWidth(16)
        self.arrow_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.arrow_label.clicked.connect(lambda: self.toggle_signal.emit(self.uuid))
        self._update_arrow()
        layout.addWidget(self.arrow_label)

        self.name_label = QLabel(name)
        self.name_label.setObjectName("DividerNameLabel")
        font = self.name_label.font()
        font.setBold(True)
        font.setPointSize(font.pointSize() + 1)
        self.name_label.setFont(font)
        layout.addWidget(self.name_label)

        self.count_label = QLabel()
        self.count_label.setObjectName("DividerCountLabel")
        count_font = QFont(self.count_label.font())
        count_font.setItalic(True)
        self.count_label.setFont(count_font)
        layout.addWidget(self.count_label)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(line)

        self.setLayout(layout)

        self.setStyleSheet(
            "#DividerItemInner { background: rgba(100, 149, 237, 40); border-radius: 3px; }"
        )

    def set_collapsed(self, collapsed: bool) -> None:
        self._collapsed = collapsed
        self._update_arrow()

    def set_name(self, name: str) -> None:
        self.name_label.setText(name)

    def set_mod_count(self, count: int) -> None:
        self.count_label.setText(f"({count} mods)")

    def _update_arrow(self) -> None:
        self.arrow_label.setText("\u25B6" if self._collapsed else "\u25BC")

    def set_selected(self, selected: bool) -> None:
        pass

from typing import Optional

from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *


class ProxyStyle(QProxyStyle):
    """
    Subclass for QProxyStyle. Used for overriding some default
    styling elements.
    """

    def __init__(self) -> None:
        """Initialize the QProxyStyle."""
        super(ProxyStyle, self).__init__()

    def drawPrimitive(
        self,
        element: QStyle.PrimitiveElement,
        option: QStyleOption,
        painter: QPainter,
        widget: Optional[QWidget] = ...,
    ) -> None:
        """
        Overries the primitive-element-drawer. Currently used to
        change how the drag/drop indicator for QListWidgetItems looks like.
        """
        if element == QStyle.PE_IndicatorItemViewItemDrop:
            pen = QPen(Qt.cyan)
            pen.setWidth(1)
            painter.setPen(pen)
            if option.rect:
                painter.drawLine(option.rect.topLeft(), option.rect.topRight())
        else:
            return super().drawPrimitive(element, option, painter, widget)

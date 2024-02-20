from PySide6.QtCore import Qt
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import QLabel


class ImageLabel(QLabel):
    """
    Subclass for QLabel. Used to display the mod preview image
    and can scale as the user resizes the window.
    """

    def __init__(self) -> None:
        """Initialize QLabel normally."""
        super(ImageLabel, self).__init__()

    def resizeEvent(self, event: QResizeEvent) -> None:
        """
        When the label is resized (as the window is resized),
        also resize the image (if it exists).

        :param event: the resize event
        """
        if self.pixmap() is not None:
            self.setPixmap(
                self.pixmap().scaled(
                    self.size(),
                    Qt.KeepAspectRatio,  # SmoothTransformation is heftier, but we can afford it.
                    Qt.SmoothTransformation,  # FastTransformation or something just as crappy is the default
                )
            )
        return super().resizeEvent(event)

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap, QResizeEvent
from PySide6.QtWidgets import QLabel


class ImageLabel(QLabel):
    """
    Subclass for QLabel. Used to display the mod preview image
    and can scale as the user resizes the window.
    """

    def __init__(self) -> None:
        """Initialize QLabel normally."""
        super(ImageLabel, self).__init__()
        self._original_pixmap: QPixmap | None = None

    def setPixmap(self, pixmap: QPixmap | QImage) -> None:
        """
        Set the pixmap and store the original for scaling.

        :param pixmap: the original pixmap or image to display
        """
        if isinstance(pixmap, QPixmap):
            self._original_pixmap = pixmap
            scaled_pixmap = pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            super().setPixmap(scaled_pixmap)
        else:
            # If a QImage is provided, convert it to QPixmap
            pixmap_converted = QPixmap.fromImage(pixmap)
            self._original_pixmap = pixmap_converted
            scaled_pixmap = pixmap_converted.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            super().setPixmap(scaled_pixmap)

    def resizeEvent(self, event: QResizeEvent) -> None:
        """
        When the label is resized (as the window is resized),
        also resize the image (if it exists) based on the original image.

        :param event: the resize event
        """
        if self._original_pixmap is not None:
            scaled_pixmap = self._original_pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            super(ImageLabel, self).setPixmap(scaled_pixmap)
        return super().resizeEvent(event)

import traceback
from typing import Any, Callable

from loguru import logger
from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QMovie
from PySide6.QtWidgets import (
    QGraphicsOpacityEffect,
    QLabel,
    QVBoxLayout,
    QWidget,
)


class AnimationLabel(QLabel):
    """
    Subclass for QLabel. Displays fading text on the bottom
    status panel.
    """

    def __init__(self) -> None:
        """
        Prepare the QLabel to have its opacity
        changed through a timed animation.
        """
        super(AnimationLabel, self).__init__()
        self.effect = QGraphicsOpacityEffect()
        self.effect.setOpacity(0)
        self.setGraphicsEffect(self.effect)
        self.animation = QPropertyAnimation(self.effect, b"opacity")
        self.timer = QTimer()
        self.timer.setInterval(1000)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.fade)

    def fade(self) -> None:
        """
        Start an animation for fading out the text.
        """
        self.animation.stop()
        self.animation.setDuration(300)
        self.animation.setStartValue(1)
        self.animation.setEndValue(0)
        self.animation.setEasingCurve(QEasingCurve.Type.Linear)
        self.animation.start()

    def start_pause_fade(self, text: str) -> None:
        """
        Start the timer for calling the fade animation.
        The text should be displayed normally for 5 seconds,
        after which the fade animation is called.

        :param text: the string to display and fade
        """
        self.clear()
        if self.timer.isActive():
            self.timer.stop()
            self.animation.stop()
        self.setText(text)
        self.effect.setOpacity(1)
        self.setGraphicsEffect(self.effect)
        self.timer.start(5000)


class LoadingAnimation(QWidget):
    finished = Signal()

    def __init__(self, gif_path: str, target: Callable[..., Any]):
        super().__init__()
        logger.debug("Initializing LoadingAnimation")

        # Store data
        self.animation_finished = False
        self.data: dict[Any, Any] = {}

        # Setup thread
        self.gif_path = gif_path
        self._thread = WorkThread(parent=self, target=target)
        self._thread.data_ready.connect(self.handle_data)
        self._thread.finished.connect(self.prepare_stop_animation)
        self._thread.start()

        # Window properties
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        # Label and layout
        self._layout = QVBoxLayout(self)
        self.movie = QMovie(self.gif_path)
        self.movie.frameChanged.connect(self.check_animation_stop)
        self.movie.start()

        self.label = QLabel()
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setMovie(self.movie)
        self._layout.addWidget(self.label)
        self.setLayout(self._layout)

        logger.debug("Finished LoadingAnimation initialization")

    def check_animation_stop(self, frameNumber: int) -> None:
        """Checks if the animation should stop."""
        if self.animation_finished and frameNumber == self.movie.frameCount() - 1:
            logger.debug("Animation is finished")
            self.stop_animation()

    def handle_data(self, data: dict[Any, Any]) -> None:
        """Handle data received from thread."""
        if data:
            logger.debug(f"Received {type(data)} from thread")
            self.data = data

    def prepare_stop_animation(self) -> None:
        """Prepare to stop the animation."""
        # Set flag when thread finished
        logger.debug("Flagging animation to complete")
        self.animation_finished = True

    def stop_animation(self) -> None:
        """Stop the animation."""
        logger.debug("Stopping animation")
        # Stop animation
        self.label.clear()
        self.movie.stop()
        self.finished.emit()
        self.close()


class WorkThread(QThread):
    data_ready = Signal(object)

    def __init__(self, target: Callable[..., Any], parent: Any = None) -> None:
        QThread.__init__(self)
        self.data = None
        self.target = target

    def run(self) -> None:
        try:
            self.data = self.target()
        except Exception as e:
            logger.error(f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}")
        logger.debug("WorkThread completed, returning to main thread")
        self.data_ready.emit(self.data)

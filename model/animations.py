from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QTimer, QThread, Qt, Signal
from PySide6.QtGui import QMovie, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsOpacityEffect,
    QLabel,
    QVBoxLayout,
    QWidget,
)
from typing import Callable


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
        self.timer = QTimer(interval=1000, singleShot=True)
        self.timer.timeout.connect(self.fade)

    def fade(self) -> None:
        """
        Start an animation for fading out the text.
        """
        self.animation.stop()
        self.animation.setDuration(300)
        self.animation.setStartValue(1)
        self.animation.setEndValue(0)
        self.animation.setEasingCurve(QEasingCurve.Linear)
        self.animation.start()

    def start_pause_fade(self, text: str) -> None:
        """
        Start the timer for calling the fade animation.
        The text should be displayed normally for 5 seconds,
        after which the fade animation is called.

        :param text: the string to display and fade
        """
        if self.timer.isActive:
            self.timer.stop()
            self.animation.stop()
        self.setText(text)
        self.effect.setOpacity(1)
        self.setGraphicsEffect(self.effect)
        self.timer.start(5000)


class LoadingAnimation(QWidget):
    def __init__(self, gif_path: str, target: Callable):
        super().__init__()

        # Setup thread
        self.gif_path = gif_path
        self.thread = WorkThread(target=target)
        self.thread.animation_stopped.connect(self.stop_animation)
        # Window properties
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowModality(Qt.ApplicationModal)
        # Label and layout
        layout = QVBoxLayout(self)
        self.movie = QMovie(self.gif_path)
        self.movie.start()
        self.label = QLabel(alignment=Qt.AlignCenter)
        self.label.setMovie(self.movie)
        layout.addWidget(self.label)
        self.setLayout(layout)

    def showEvent(self, event):
        super().showEvent(event)
        # Start the thread when widget is shown
        self.thread.start()

    def stop_animation(self):
        # Stop animation when thread finished
        self.label.clear()
        self.movie.stop()
        self.thread = None
        self.close()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.drawPixmap(self.rect(), self.movie.currentPixmap())


class WorkThread(QThread):
    animation_stopped = Signal()

    def __init__(self, target: Callable):
        QThread.__init__(self)
        self.target = target

    def run(self):
        self.target()
        self.animation_stopped.emit()

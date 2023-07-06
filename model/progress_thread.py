from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QMovie, QPainter
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget
from typing import Callable


class ProgressAnimation(QWidget):
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

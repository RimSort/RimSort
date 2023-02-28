from PySide2.QtCore import QPropertyAnimation, QTimer, QEasingCurve
from PySide2.QtWidgets import QLabel, QGraphicsOpacityEffect


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
        The text should be displayed normally for 2 seconds,
        after which the fade animation is called.

        :param text: the string to display and fade
        """
        if self.timer.isActive:
            self.timer.stop()
            self.animation.stop()
        self.setText(text)
        self.effect.setOpacity(1)
        self.setGraphicsEffect(self.effect)
        self.timer.start(2000)

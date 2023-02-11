from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *


class ScrollLabel(QScrollArea):
    """
    Subclass for QScrollArea. Creates a read-only
    text box that scrolls. Used specifically for the description
    part of the mod ifo panel.
    """

    def __init__(self):
        """
        Initialize the class.
        """
        super(ScrollLabel, self).__init__()

        # Enable styling
        self.setObjectName("descriptionWidget")

        # Enabling scrolling
        self.setWidgetResizable(True)

        # QFrame to store content
        self.content = QFrame(self)
        self.content.setObjectName("descriptionContent")
        self.setWidget(self.content)

        # Layout to add label to
        self.main_layout = QVBoxLayout(self.content)
        self.main_layout.setContentsMargins(
            0, 0, 0, 0
        )  # Right margin is overwritten in styles

        # Label to store text
        self.label = QLabel(self.content)
        self.label.setObjectName("descriptionLabel")
        self.label.setAlignment(Qt.AlignLeft | Qt.AlignTop)

        # Making label multi-line
        self.label.setWordWrap(True)

        # Adding label to the layout
        self.main_layout.addWidget(self.label)

    def setText(self, text):
        self.label.setText(text)

    def text(self):
        get_text = self.label.text()
        return get_text

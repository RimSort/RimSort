from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *


class ScrollLabel(QScrollArea):
    # constructor
    def __init__(self, *args, **kwargs):
        QScrollArea.__init__(self, *args, **kwargs)

        # making widget resizable
        self.setWidgetResizable(True)

        self.setObjectName("descriptionWidget")

        # making qwidget object
        content = QFrame(self)
        content.setObjectName("descriptionContent")
        self.setWidget(content)

        # vertical box layout
        lay = QVBoxLayout(content)
        lay.setContentsMargins(0,0,0,0) # Right margin is overwritten in styles

        # creating label
        self.label = QLabel(content)
        self.label.setObjectName("descriptionLabel")

        # setting alignment to the text
        self.label.setAlignment(Qt.AlignLeft | Qt.AlignTop)

        # making label multi-line
        self.label.setWordWrap(True)

        # adding label to the layout
        lay.addWidget(self.label)

    # the setText method
    def setText(self, text):
        # setting text to the label
        self.label.setText(text)

    def text(self):
        # getting text of the label
        get_text = self.label.text()

        # return the text
        return get_text

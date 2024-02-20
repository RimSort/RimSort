from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QScrollArea, QVBoxLayout
from loguru import logger


class ScrollLabel(QScrollArea):
    """
    Subclass for QScrollArea. Creates a read-only
    text box that scrolls. Used specifically for the description
    part of the mod info panel.
    """

    def __init__(self) -> None:
        """
        Initialize the class.
        """
        logger.debug("Initializing ScrollLabel")
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
        self.label.setAlignment(Qt.AlignTop)

        # Making label multi-line
        self.label.setWordWrap(True)

        # Adding label to the layout
        self.main_layout.addWidget(self.label)

        logger.debug("Finished ScrollLabel initialization")

    def setText(self, text: str) -> None:
        self.label.setText(text)

    def text(self) -> str:
        get_text = self.label.text()
        return get_text

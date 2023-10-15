from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QToolButton, QMenu, QWidget
from PySide6.QtGui import QIcon

class MultiButton(QWidget):
    def __init__(self, main_action_name: str, secondary_action_icon_path: str):
        super().__init__()

        # Create a horizontal layout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create a QPushButton
        self.main_action = QPushButton(main_action_name, self)
        layout.addWidget(self.main_action)

        # Create a QToolButton with a menu
        self.secondary_action = QToolButton(self)
        self.secondary_action.setIcon(QIcon(secondary_action_icon_path))
        self.secondary_action.setPopupMode(QToolButton.InstantPopup)
        self.menu = QMenu(self)
        self.secondary_action.setMenu(self.menu)
        layout.addWidget(self.secondary_action)

        self.setLayout(layout)

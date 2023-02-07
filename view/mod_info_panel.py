from typing import Any, Dict, List

from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *


class ModInfo:
    """
    This class controls the layout and functionality for the
    mod information panel on the GUI.
    """

    def __init__(self) -> None:
        """
        Initialize the class.
        """

        # Base layout type
        self.panel = QVBoxLayout()

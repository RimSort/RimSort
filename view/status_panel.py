from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *

from model.animation_label import AnimationLabel


class Status:
    """
    This class controls the layout and functionality for
    the status panel on the bottom of the GUI.
    """

    def __init__(self) -> None:
        """
        Initialize the status panel. Construct the layout,
        add the single text widget.
        """
        # Frame contains base layout to allow for styling
        self.frame = QFrame()
        self.frame.setObjectName("StatusPanel")

        # Base layout
        self._panel = QHBoxLayout()
        self._panel.setContentsMargins(10,1,0,2)

        # Adding layout to frame
        self.frame.setLayout(self._panel)

        # Instantiate widgets
        self.status_text = AnimationLabel()
        self.status_text.setObjectName("StatusLabel")

        # Add widgets to base layout
        self._panel.addWidget(self.status_text)

    @property
    def panel(self):
        return self._panel

    def actions_slot(self, action: str) -> None:
        """
        Slot connecting to the action panel's `actions_signal`.
        Responsible for displaying the action that was just
        triggered on the bottom status bar and fading the text
        after some time.

        :param action: the specific action being triggered
        """
        if action == "clear":
            self.status_text.start_pause_fade("Cleared active mods")
        if action == "restore":
            self.status_text.start_pause_fade("Restored mod list to last saved ModsConfig.xml state")
        if action == "sort":
            self.status_text.start_pause_fade("Sorted active mod list")
        if action == "import":
            self.status_text.start_pause_fade("Imported mod list from external file")
        if action == "export":
            self.status_text.start_pause_fade("Exported active mods to external file")
        if action == "save":
            self.status_text.start_pause_fade("Active mods saved into ModsConfig.xml")
        if action == "run":
            self.status_text.start_pause_fade("Starting RimWorld")

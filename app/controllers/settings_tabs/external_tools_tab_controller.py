from pathlib import Path
from typing import Callable

from PySide6.QtCore import Slot

from app.controllers.settings_tabs.base_tab_controller import BaseTabController
from app.models.settings import Settings
from app.views.dialogue import show_dialogue_file
from app.views.settings_dialog import SettingsDialog


class ExternalToolsTabController(BaseTabController):
    """Controller for the External Tools settings tab.

    Manages: text editor command location and its additional arguments.
    """

    def __init__(
        self,
        settings: Settings,
        dialog: SettingsDialog,
        last_file_dialog_path: str,
        on_path_selected: Callable[[str], None],
    ) -> None:
        super().__init__(settings, dialog)
        self._last_file_dialog_path = last_file_dialog_path
        self._on_path_selected = on_path_selected

    def connect_signals(self) -> None:
        self.dialog.text_editor_location_choose_button.clicked.connect(
            self._on_text_editor_location_choose
        )

    def update_view_from_model(self) -> None:
        self.dialog.text_editor_location.setText(self.settings.text_editor_location)
        self.dialog.text_editor_folder_arg.setText(self.settings.text_editor_folder_arg)
        self.dialog.text_editor_file_arg.setText(self.settings.text_editor_file_arg)

    def update_model_from_view(self) -> None:
        self.settings.text_editor_location = self.dialog.text_editor_location.text()
        self.settings.text_editor_folder_arg = self.dialog.text_editor_folder_arg.text()
        self.settings.text_editor_file_arg = self.dialog.text_editor_file_arg.text()

    @Slot()
    def _on_text_editor_location_choose(self) -> None:
        text_editor_location = show_dialogue_file(
            mode="open",
            caption="Select Text Editor Command",
            _dir=str(self._last_file_dialog_path),
        )
        if not text_editor_location:
            return

        self.dialog.text_editor_location.setText(text_editor_location)
        self._on_path_selected(str(Path(text_editor_location).parent))

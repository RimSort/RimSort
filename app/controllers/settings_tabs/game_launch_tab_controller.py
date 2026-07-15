from PySide6.QtCore import Slot

from app.controllers.settings_tabs.base_tab_controller import BaseTabController
from app.models.settings import Settings
from app.views.settings_dialog import SettingsDialog


class GameLaunchTabController(BaseTabController):
    """Controller for the Game Launch settings tab.

    Manages: Steam protocol launch toggle, run arguments text field.
    """

    def __init__(
        self,
        settings: Settings,
        dialog: SettingsDialog,
    ) -> None:
        super().__init__(settings, dialog)

    def connect_signals(self) -> None:
        self.dialog.run_args.textChanged.connect(self._on_run_args_text_changed)

    def update_view_from_model(self) -> None:
        instance = self.settings.instances[self.settings.current_instance]

        self.dialog.launch_via_steam_protocol_checkbox.setChecked(
            instance.launch_via_steam_protocol
        )
        self.dialog.run_args_group.setEnabled(not instance.launch_via_steam_protocol)

        self.dialog.run_args.setText(instance.run_args)
        self.dialog.run_args.setCursorPosition(0)

    def update_model_from_view(self) -> None:
        self.settings.instances[
            self.settings.current_instance
        ].launch_via_steam_protocol = (
            self.dialog.launch_via_steam_protocol_checkbox.isChecked()
        )

        self.settings.instances[
            self.settings.current_instance
        ].run_args = self.dialog.run_args.text()

    @Slot(str)
    def _on_run_args_text_changed(self, text: str = "") -> None:
        self.settings.instances[self.settings.current_instance].run_args = text
        self.settings.save()

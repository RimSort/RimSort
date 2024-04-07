from PySide6.QtCore import QObject, Slot

from app.utils.event_bus import EventBus
from app.utils.metadata import MetadataManager
from app.views.main_window import MainWindow


class MainWindowController(QObject):
    def __init__(self, view: MainWindow) -> None:
        super().__init__()

        self.main_window = view

        # Create a list of buttons
        self.buttons = [
            self.main_window.refresh_button,
            self.main_window.clear_button,
            self.main_window.sort_button,
            self.main_window.save_button,
            self.main_window.run_button,
        ]

        # Connect signals to slots
        self.connect_signals()

    def connect_signals(self) -> None:
        # Connect buttons to EventBus signals
        for button, signal in zip(
            self.buttons,
            [
                EventBus().do_refresh_mods_lists,
                EventBus().do_clear_active_mods_list,
                EventBus().do_sort_active_mods_list,
                EventBus().do_save_active_mods_list,
                EventBus().do_run_game,
            ],
        ):
            button.clicked.connect(signal.emit)

        # Connect EventBus signals to slots
        EventBus().do_refresh_button_set_default.connect(
            self.on_do_refresh_button_set_default
        )
        EventBus().do_refresh_button_unset_default.connect(
            self.on_do_refresh_button_unset_default
        )
        EventBus().do_save_button_set_default.connect(
            self.on_do_save_button_set_default
        )
        EventBus().do_save_button_unset_default.connect(
            self.on_do_save_button_unset_default
        )
        EventBus().refresh_started.connect(self.on_refresh_started)
        EventBus().refresh_finished.connect(self.on_refresh_finished)

    @Slot()
    def on_do_refresh_button_set_default(self) -> None:
        self.set_default_button(self.main_window.refresh_button)

    @Slot()
    def on_do_refresh_button_unset_default(self) -> None:
        self.unset_default_buttons()

    @Slot()
    def on_do_save_button_set_default(self) -> None:
        self.set_default_button(self.main_window.save_button)

    @Slot()
    def on_do_save_button_unset_default(self) -> None:
        self.unset_default_buttons()

    @Slot()
    def on_refresh_started(self) -> None:
        self.set_buttons_enabled(False)

    @Slot()
    def on_refresh_finished(self) -> None:
        self.set_buttons_enabled(True)
        self.main_window.game_version_label.setText(
            "RimWorld version " + MetadataManager.instance().game_version
        )

    def set_default_button(self, button):
        for btn in self.buttons:
            btn.setDefault(btn is button)

    def unset_default_buttons(self):
        for btn in self.buttons:
            btn.setDefault(False)

    def set_buttons_enabled(self, enabled: bool) -> None:
        for btn in self.buttons:
            btn.setEnabled(enabled)

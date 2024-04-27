from loguru import logger

from PySide6.QtCore import QObject, Slot
from PySide6.QtWidgets import QPushButton

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
            self.main_window.restore_button,
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
                EventBus().do_restore_active_mods_list,
                EventBus().do_sort_active_mods_list,
                EventBus().do_save_active_mods_list,
                EventBus().do_run_game,
            ],
        ):
            button.clicked.connect(signal.emit)

        # Connect EventBus signals to slots
        EventBus().do_button_animation.connect(self.on_button_animation)
        EventBus().do_save_button_animation_stop.connect(
            self.on_save_button_animation_stop
        )
        EventBus().list_updated_signal.connect(
            self.on_save_button_animation_start
        )  # Save btn animation
        EventBus().refresh_started.connect(self.on_refresh_started)
        EventBus().refresh_finished.connect(self.on_refresh_finished)

    @Slot()
    def on_button_animation(self, button: QPushButton) -> None:
        button.setObjectName(
            "%s" % ("" if button.objectName() == "indicator" else "indicator")
        )
        button.style().unpolish(button)
        button.style().polish(button)

    @Slot()
    def on_refresh_started(self) -> None:
        self.set_buttons_enabled(False)

    @Slot()
    def on_refresh_finished(self) -> None:
        self.set_buttons_enabled(True)
        self.main_window.game_version_label.setText(
            "RimWorld version " + MetadataManager.instance().game_version
        )

    @Slot()
    def on_save_button_animation_start(self) -> None:
        logger.debug(
            "Active mods list has been updated. Managing save button animation state."
        )
        active_mods_uuids = (
            self.main_window.main_content_panel.mods_panel.active_mods_list.uuids
        )
        if (
            # Compare current active list with last save to see if the list has changed
            self.main_window.main_content_panel.mods_panel.active_mods_list.uuids
            != self.main_window.main_content_panel.active_mods_uuids_last_save
        ):
            if not self.main_window.save_button_flashing_animation.isActive():
                logger.debug("Starting save button animation")
                self.main_window.save_button_flashing_animation.start(
                    500
                )  # Blink every 500 milliseconds
        else:
            if self.main_window.save_button_flashing_animation.isActive():
                logger.debug("Stopping save button animation")
                self.main_window.save_button_flashing_animation.stop()
                self.main_window.save_button.setObjectName("")
                self.main_window.save_button.style().unpolish(
                    self.main_window.save_button
                )
                self.main_window.save_button.style().polish(
                    self.main_window.save_button
                )

    @Slot()
    def on_save_button_animation_stop(self) -> None:
        # Stop the save button from blinking if it is blinking
        if self.main_window.save_button_flashing_animation.isActive():
            self.main_window.save_button_flashing_animation.stop()
            self.main_window.save_button.setObjectName("")
            self.main_window.save_button.style().unpolish(self.main_window.save_button)
            self.main_window.save_button.style().polish(self.main_window.save_button)

    def set_buttons_enabled(self, enabled: bool) -> None:
        for btn in self.buttons:
            btn.setEnabled(enabled)

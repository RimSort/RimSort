from PySide6.QtCore import QObject, Slot

from app.utils.event_bus import EventBus
from app.utils.metadata import MetadataManager
from app.views.main_window import MainWindow


class MainWindowController(QObject):
    def __init__(self, view: MainWindow) -> None:
        super().__init__()

        self.main_window = view

        EventBus().do_refresh_button_set_default.connect(
            self._on_do_refresh_button_set_default
        )
        EventBus().do_refresh_button_unset_default.connect(
            self._on_do_refresh_button_unset_default
        )

        EventBus().do_save_button_set_default.connect(
            self._on_do_save_button_set_default
        )
        EventBus().do_save_button_unset_default.connect(
            self._on_do_save_button_unset_default
        )

        self.main_window.refresh_button.clicked.connect(
            EventBus().do_refresh_mods_lists.emit
        )
        self.main_window.clear_button.clicked.connect(
            EventBus().do_clear_active_mods_list.emit
        )
        self.main_window.sort_button.clicked.connect(
            EventBus().do_sort_active_mods_list.emit
        )
        self.main_window.save_button.clicked.connect(
            EventBus().do_save_active_mods_list.emit
        )
        self.main_window.run_button.clicked.connect(EventBus().do_run_game.emit)

        EventBus().refresh_started.connect(self._on_refresh_started)
        EventBus().refresh_finished.connect(self._on_refresh_finished)

    @Slot()
    def _on_do_refresh_button_set_default(self) -> None:
        self.main_window.refresh_button.setDefault(True)
        self.main_window.clear_button.setDefault(False)
        self.main_window.sort_button.setDefault(False)
        self.main_window.save_button.setDefault(False)
        self.main_window.run_button.setDefault(False)

    @Slot()
    def _on_do_refresh_button_unset_default(self) -> None:
        self.main_window.refresh_button.setDefault(False)
        self.main_window.clear_button.setDefault(False)
        self.main_window.sort_button.setDefault(False)
        self.main_window.save_button.setDefault(False)
        self.main_window.run_button.setDefault(False)

    @Slot()
    def _on_do_save_button_set_default(self) -> None:
        self.main_window.refresh_button.setDefault(False)
        self.main_window.clear_button.setDefault(False)
        self.main_window.sort_button.setDefault(False)
        self.main_window.save_button.setDefault(True)
        self.main_window.run_button.setDefault(False)

    @Slot()
    def _on_do_save_button_unset_default(self) -> None:
        self.main_window.refresh_button.setDefault(False)
        self.main_window.clear_button.setDefault(False)
        self.main_window.sort_button.setDefault(False)
        self.main_window.save_button.setDefault(False)
        self.main_window.run_button.setDefault(False)

    @Slot()
    def _on_refresh_started(self) -> None:
        self.main_window.refresh_button.setEnabled(False)
        self.main_window.clear_button.setEnabled(False)
        self.main_window.sort_button.setEnabled(False)
        self.main_window.save_button.setEnabled(False)
        self.main_window.run_button.setEnabled(False)

    @Slot()
    def _on_refresh_finished(self) -> None:
        self.main_window.refresh_button.setEnabled(True)
        self.main_window.clear_button.setEnabled(True)
        self.main_window.sort_button.setEnabled(True)
        self.main_window.save_button.setEnabled(True)
        self.main_window.run_button.setEnabled(True)

        self.main_window.game_version_label.setText(
            "RimWorld version " + MetadataManager.instance().game_version
        )

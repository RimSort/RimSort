from PySide6.QtCore import QObject, Slot

from util.event_bus import EventBus
from view.main_window import MainWindow


class MainWindowController(QObject):
    def __init__(self, view: MainWindow) -> None:
        super().__init__()

        self.main_window = view

        EventBus().do_set_main_window_widgets_enabled.connect(
            self._on_do_set_main_window_widgets_enabled
        )

    @Slot(bool)
    def _on_do_set_main_window_widgets_enabled(self, enabled: bool) -> None:
        self.main_window.refresh_button.setEnabled(enabled)
        self.main_window.clear_button.setEnabled(enabled)
        self.main_window.sort_button.setEnabled(enabled)
        self.main_window.save_button.setEnabled(enabled)
        self.main_window.run_button.setEnabled(enabled)

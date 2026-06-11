from app.controllers.settings_tabs.base_tab_controller import BaseTabController
from app.models.settings import Settings
from app.views.settings_dialog import SettingsDialog


class WindowLayoutTabController(BaseTabController):
    """Controller for the Window Launch State settings tab.

    Manages: main window launch state, browser window launch state,
    settings window custom size, and dialogue positioning constraint.
    """

    def __init__(
        self,
        settings: Settings,
        dialog: SettingsDialog,
    ) -> None:
        super().__init__(settings, dialog)

    def connect_signals(self) -> None:
        # Main window radio buttons toggle custom size spinboxes
        self.dialog.main_launch_maximized_radio.toggled.connect(
            self.dialog.disable_main_custom_size_spinboxes
        )
        self.dialog.main_launch_normal_radio.toggled.connect(
            self.dialog.disable_main_custom_size_spinboxes
        )
        self.dialog.main_launch_custom_radio.toggled.connect(
            self.dialog.enable_main_custom_size_spinboxes
        )
        # Browser window radio buttons toggle custom size spinboxes
        self.dialog.browser_launch_maximized_radio.toggled.connect(
            self.dialog.disable_browser_custom_size_spinboxes
        )
        self.dialog.browser_launch_normal_radio.toggled.connect(
            self.dialog.disable_browser_custom_size_spinboxes
        )
        self.dialog.browser_launch_custom_radio.toggled.connect(
            self.dialog.enable_browser_custom_size_spinboxes
        )

        # Settings Window (only custom option, spinboxes always enabled)
        self.dialog.settings_custom_width_spinbox.setEnabled(True)
        self.dialog.settings_custom_height_spinbox.setEnabled(True)

    def update_view_from_model(self) -> None:
        # Dialogue positioning
        self.dialog.constrain_dialogues_to_main_window_monitor_checkbox.setChecked(
            self.settings.constrain_dialogues_to_main_window_monitor
        )

        # Main Window launch state
        main_state = self.settings.main_window_launch_state
        if main_state == "maximized":
            self.dialog.main_launch_maximized_radio.setChecked(True)
            self.dialog.disable_main_custom_size_spinboxes()
        elif main_state == "normal":
            self.dialog.main_launch_normal_radio.setChecked(True)
            self.dialog.disable_main_custom_size_spinboxes()
        elif main_state == "custom":
            self.dialog.main_launch_custom_radio.setChecked(True)
            self.dialog.enable_main_custom_size_spinboxes()
            min_size, max_size = 400, 1600
            width = self.settings.main_window_custom_width
            height = self.settings.main_window_custom_height
            if not (min_size <= width <= max_size):
                width = 900
            if not (min_size <= height <= max_size):
                height = 600
            self.dialog.main_custom_width_spinbox.setValue(width)
            self.dialog.main_custom_height_spinbox.setValue(height)
        else:
            self.dialog.main_launch_maximized_radio.setChecked(True)

        # Browser Window launch state
        browser_state = self.settings.browser_window_launch_state
        if browser_state == "maximized":
            self.dialog.browser_launch_maximized_radio.setChecked(True)
            self.dialog.disable_browser_custom_size_spinboxes()
        if browser_state == "normal":
            self.dialog.browser_launch_normal_radio.setChecked(True)
            self.dialog.disable_browser_custom_size_spinboxes()
        elif browser_state == "custom":
            self.dialog.browser_launch_custom_radio.setChecked(True)
            self.dialog.enable_browser_custom_size_spinboxes()
            min_size, max_size = 400, 1600
            width = self.settings.browser_window_custom_width
            height = self.settings.browser_window_custom_height
            if not (min_size <= width <= max_size):
                width = 900
            if not (min_size <= height <= max_size):
                height = 600
            self.dialog.browser_custom_width_spinbox.setValue(width)
            self.dialog.browser_custom_height_spinbox.setValue(height)
        else:
            self.dialog.browser_launch_maximized_radio.setChecked(True)

        # Settings Window (only custom option)
        self.dialog.settings_custom_width_spinbox.setValue(
            self.settings.settings_window_custom_width
        )
        self.dialog.settings_custom_height_spinbox.setValue(
            self.settings.settings_window_custom_height
        )

    def update_model_from_view(self) -> None:
        # Dialogue positioning
        self.settings.constrain_dialogues_to_main_window_monitor = (
            self.dialog.constrain_dialogues_to_main_window_monitor_checkbox.isChecked()
        )

        # Main Window
        if self.dialog.main_launch_maximized_radio.isChecked():
            self.settings.main_window_launch_state = "maximized"
        elif self.dialog.main_launch_normal_radio.isChecked():
            self.settings.main_window_launch_state = "normal"
        elif self.dialog.main_launch_custom_radio.isChecked():
            self.settings.main_window_launch_state = "custom"
            self.settings.main_window_custom_width = (
                self.dialog.main_custom_width_spinbox.value()
            )
            self.settings.main_window_custom_height = (
                self.dialog.main_custom_height_spinbox.value()
            )
        else:
            self.settings.main_window_launch_state = "maximized"

        # Browser Window
        if self.dialog.browser_launch_maximized_radio.isChecked():
            self.settings.browser_window_launch_state = "maximized"
        elif self.dialog.browser_launch_normal_radio.isChecked():
            self.settings.browser_window_launch_state = "normal"
        elif self.dialog.browser_launch_custom_radio.isChecked():
            self.settings.browser_window_launch_state = "custom"
            self.settings.browser_window_custom_width = (
                self.dialog.browser_custom_width_spinbox.value()
            )
            self.settings.browser_window_custom_height = (
                self.dialog.browser_custom_height_spinbox.value()
            )
        else:
            self.settings.browser_window_launch_state = "maximized"

        # Settings Window (only custom option)
        self.settings.settings_window_custom_width = (
            self.dialog.settings_custom_width_spinbox.value()
        )
        self.settings.settings_window_custom_height = (
            self.dialog.settings_custom_height_spinbox.value()
        )

from loguru import logger
from PySide6.QtCore import Slot

from app.controllers.language_controller import LanguageController
from app.controllers.settings_tabs.base_tab_controller import BaseTabController
from app.controllers.theme_controller import ThemeController
from app.models.settings import Settings
from app.utils.generic import platform_specific_open
from app.views.settings_dialog import SettingsDialog


class AppearanceTabController(BaseTabController):
    """Controller for the Appearance settings tab.

    Manages: theme settings, font settings, language selection,
    main/browser/settings window launch states, and dialogue positioning.
    """

    def __init__(
        self,
        settings: Settings,
        dialog: SettingsDialog,
    ) -> None:
        super().__init__(settings, dialog)
        self._theme_controller = ThemeController()
        self._language_controller = LanguageController()

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

        # Settings Window (modal dialog — spinboxes always enabled)
        self.dialog.settings_custom_width_spinbox.setEnabled(True)
        self.dialog.settings_custom_height_spinbox.setEnabled(True)

        # Theme location open button
        self.dialog.theme_location_open_button.clicked.connect(
            self._on_theme_location_open_button_clicked
        )

    def update_view_from_model(self) -> None:
        # Theme
        self.dialog.enable_themes_checkbox.setChecked(self.settings.enable_themes)
        self._theme_controller.populate_themes_combobox(self.dialog.themes_combobox)
        self._theme_controller.setup_theme_dialog(self.dialog, self.settings)

        # Language
        self._language_controller.populate_languages_combobox(
            self.dialog.language_combobox
        )
        self._language_controller.setup_language_dialog(self.dialog, self.settings)

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

        # Settings Window (only custom option — modal dialog)
        self.dialog.settings_custom_width_spinbox.setValue(
            self.settings.settings_window_custom_width
        )
        self.dialog.settings_custom_height_spinbox.setValue(
            self.settings.settings_window_custom_height
        )

    def update_model_from_view(self) -> None:
        # Theme
        self.settings.enable_themes = self.dialog.enable_themes_checkbox.isChecked()
        self.settings.theme_name = self.dialog.themes_combobox.currentText()

        # Font
        self.settings.font_family = self.dialog.font_family_combobox.currentText()
        self.settings.font_size = self.dialog.font_size_spinbox.value()

        # Language
        self.settings.language = self.dialog.language_combobox.currentData()

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

        # Settings Window (only custom option — modal dialog)
        self.settings.settings_window_custom_width = (
            self.dialog.settings_custom_width_spinbox.value()
        )
        self.settings.settings_window_custom_height = (
            self.dialog.settings_custom_height_spinbox.value()
        )

    @Slot()
    def _on_theme_location_open_button_clicked(self) -> None:
        selected_theme_name = self.dialog.themes_combobox.currentText()
        logger.info(f"Opening theme location: {selected_theme_name}")
        stylesheet_path = self._theme_controller.get_theme_stylesheet_path(
            selected_theme_name
        )

        if stylesheet_path and stylesheet_path.exists():
            platform_specific_open(stylesheet_path.parent)
        else:
            logger.warning(
                f"Failed to open theme location: {stylesheet_path} not found or does not exist"
            )

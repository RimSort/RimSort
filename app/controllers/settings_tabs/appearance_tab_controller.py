from loguru import logger
from PySide6.QtCore import Slot
from PySide6.QtWidgets import QFileDialog

from app.controllers.language_controller import LanguageController
from app.controllers.settings_tabs.base_tab_controller import BaseTabController
from app.controllers.theme_controller import ThemeController
from app.models.settings import Settings
from app.utils.generic import platform_specific_open, restart_application
from app.utils.gui_info import show_dialogue_conditional
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

        # Profile format change: two confirm dialogs, decline reverts
        self.dialog.profile_format_combobox.currentIndexChanged.connect(
            self._on_profile_format_changed
        )

        # Categories file browse button
        self.dialog.categories_file_browse_button.clicked.connect(
            self._on_categories_file_browse_clicked
        )

        # Modern UI theme settings: ONE Confirm applies the whole block
        # and offers the restart
        self.dialog.modern_theme_confirm_button.clicked.connect(
            self._on_modern_theme_confirm_clicked
        )

    def update_view_from_model(self) -> None:
        # Profile
        profiles = [
            self.dialog.profile_format_combobox.itemText(i)
            for i in range(self.dialog.profile_format_combobox.count())
        ]
        if self.settings.profile_format in profiles:
            self.dialog.profile_format_combobox.setCurrentText(
                self.settings.profile_format
            )
        for slot, combobox in enumerate(self.dialog.active_columns_comboboxes):
            column = (
                self.settings.active_columns[slot]
                if slot < len(self.settings.active_columns)
                else "None"
            )
            if combobox.findText(column) >= 0:
                combobox.setCurrentText(column)
        self.dialog.categories_file_input.setText(self.settings.categories_file)
        row_style = "Striped" if self.settings.modern_ui_striped_rows else "Plain"
        if self.dialog.modern_row_style_combobox.findText(row_style) >= 0:
            self.dialog.modern_row_style_combobox.setCurrentText(row_style)
        category_style = (
            "Neon" if self.settings.modern_ui_category_style == "neon" else "Solid"
        )
        if self.dialog.modern_category_style_combobox.findText(category_style) >= 0:
            self.dialog.modern_category_style_combobox.setCurrentText(category_style)
        category_align = {
            "left": "Left",
            "center": "Center",
            "right": "Right",
        }.get(self.settings.modern_ui_category_text_align, "Center")
        if self.dialog.modern_category_align_combobox.findText(category_align) >= 0:
            self.dialog.modern_category_align_combobox.setCurrentText(category_align)
        active_style = (
            "Double Gradient"
            if self.settings.modern_ui_active_mod_style == "double_gradient"
            else "Default"
        )
        if self.dialog.modern_active_style_combobox.findText(active_style) >= 0:
            self.dialog.modern_active_style_combobox.setCurrentText(active_style)

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
        elif browser_state == "normal":
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
        # Profile
        self.settings.profile_format = self.dialog.profile_format_combobox.currentText()
        self.settings.active_columns = [
            combobox.currentText() for combobox in self.dialog.active_columns_comboboxes
        ]
        self.settings.categories_file = self.dialog.categories_file_input.text()
        self.settings.modern_ui_striped_rows = (
            self.dialog.modern_row_style_combobox.currentText() == "Striped"
        )
        self.settings.modern_ui_category_style = (
            "neon"
            if self.dialog.modern_category_style_combobox.currentText() == "Neon"
            else "solid"
        )
        self.settings.modern_ui_category_text_align = {
            "Left": "left",
            "Center": "center",
            "Right": "right",
        }.get(self.dialog.modern_category_align_combobox.currentText(), "center")
        self.settings.modern_ui_active_mod_style = (
            "double_gradient"
            if self.dialog.modern_active_style_combobox.currentText()
            == "Double Gradient"
            else "default"
        )

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

    @Slot()
    def _on_profile_format_changed(self, index: int) -> None:
        """Changing the profile sets it as the default automatically, then
        offers to restart so it applies immediately."""
        new_profile = self.dialog.profile_format_combobox.itemText(index)
        if new_profile == self.settings.profile_format:
            # Fired by view sync, not a user change
            return

        self.settings.profile_format = new_profile
        self.settings.save()

        if show_dialogue_conditional(
            title=self.dialog.tr("Profile Changed"),
            text=self.dialog.tr(
                f"Your profile is now {new_profile}. Restart RimSort now to apply it?"
            ),
            icon="info",
        ):
            logger.info(f"Profile set to {new_profile}; restarting application")
            restart_application()
        else:
            logger.info(f"Profile set to {new_profile}; applies on next launch")

    @Slot()
    def _on_modern_theme_confirm_clicked(self) -> None:
        """ONE Confirm for the whole Modern UI theme settings block:
        applies every selection at once and offers the restart (her
        ruling - a dialog per selection isn't practical)."""
        self.update_model_from_view()
        self.settings.save()
        logger.info("Modern UI theme settings applied")
        self._offer_restart(
            "Theme Settings Changed",
            "Your Modern UI theme settings have been updated.",
        )

    def _offer_restart(self, title: str, message: str) -> None:
        """The shared restart question for Modern UI theme settings."""
        if show_dialogue_conditional(
            title=self.dialog.tr(title),
            text=self.dialog.tr(f"{message} Restart RimSort now to apply it?"),
            icon="info",
        ):
            logger.info(f"{title}; restarting application")
            restart_application()

    @Slot()
    def _on_categories_file_browse_clicked(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self.dialog,
            self.dialog.tr("Select categories file"),
            "",
            self.dialog.tr("JSON files (*.json);;All files (*)"),
        )
        if path:
            self.dialog.categories_file_input.setText(path)

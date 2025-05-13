from pathlib import Path
from typing import Optional

from loguru import logger
from PySide6.QtWidgets import QApplication, QComboBox

from app.models.settings import Settings
from app.utils.app_info import AppInfo
from app.views import dialogue
from app.views.settings_dialog import SettingsDialog


class ThemeController:
    def __init__(self, default_theme: str = "RimPy") -> None:
        """Initialize the ThemeController with a default theme.

        Args:
            default_theme (str): The name of the default theme. Defaults to "RimPy".
        """
        self.app_info = AppInfo()
        self.app_instance = QApplication.instance()
        logger.info("Initializing ThemeController")
        self.default_theme = default_theme
        self.themes = self._get_supported_themes()
        logger.info(f"Supported themes: {self.themes}")
        self.theme_stylesheets_folder = [
            self.app_info.theme_storage_folder,
            self.app_info.theme_data_folder,
        ]
        self.font_family = "Tahoma"
        self.font_size = "12"

    def _get_supported_themes(self) -> set[str]:
        """Retrieves a set of supported themes from the theme data and storage folders."""
        theme_data_folders = self._get_theme_names_from_folder(
            self.app_info.theme_data_folder
        )
        theme_storage_folders = self._get_theme_names_from_folder(
            self.app_info.theme_storage_folder
        )
        supported_themes = theme_data_folders | theme_storage_folders
        logger.info(f"Supported themes retrieved: {supported_themes}")
        logger.debug(
            f"Checking theme folders: {[self.app_info.theme_data_folder, self.app_info.theme_storage_folder]}"
        )
        return supported_themes

    def _get_theme_names_from_folder(self, folder: Path) -> set[str]:
        """Helper method to get theme names from a specified folder.

        Args:
            folder (Path): The folder to search for themes.

        Returns:
            set[str]: A set of theme names found in the folder.
        """
        supported_themes = set()
        if folder.exists():
            for subfolder in folder.iterdir():
                if subfolder.is_dir() and (subfolder / "style.qss").exists():
                    supported_themes.add(subfolder.name)
                    logger.info(
                        f"Found theme with stylesheet in {folder}: {subfolder.name}"
                    )
        else:
            logger.warning(f"Folder does not exist: {folder}")
        return supported_themes

    def load_theme(self, theme_name: str) -> Optional[str]:
        """Load the specified theme.

        Args:
            theme_name (str): The name of the theme to load.

        Returns:
            Optional[str]: The stylesheet content if loaded successfully, None otherwise.
        """
        if not theme_name:
            logger.error("Attempted to load an empty theme name")
            return None

        if theme_name in self.themes:
            logger.info(f"Loading theme: {theme_name}")
            stylesheet_path = self.get_theme_stylesheet_path(theme_name)
            if stylesheet_path:
                try:
                    with open(stylesheet_path, "r") as f:
                        raw_stylesheet = f.read()
                        font_style = f"""
                        * {{
                            font-family: "{self.font_family}";
                            font-size: {self.font_size}px;
                        }}
                        """
                        # return f.read()
                        return font_style + raw_stylesheet
                except Exception as e:
                    logger.error(f"Error loading theme: {e}")
        else:
            logger.error(f"Attempted to load unsupported theme: {theme_name}")

        # Fallback to default theme
        if theme_name != self.default_theme:
            logger.info(f"Falling back to default theme: {self.default_theme}")
            return self.load_theme(self.default_theme)
        return None

    def set_font(self, family: str, size: int) -> None:
        self.font_family = family
        self.font_size = size


    def get_theme_stylesheet_path(self, theme_name: str) -> Optional[Path]:
        """Returns the path to the stylesheet for the specified theme.

        Args:
            theme_name (str): The name of the theme.

        Returns:
            Optional[Path]: The path to the stylesheet if found, None otherwise.
        """
        logger.info(f"Searching for stylesheet for theme: {theme_name}")
        for folder in self.theme_stylesheets_folder:
            potential_path = folder / theme_name / "style.qss"
            logger.debug(f"Checking for stylesheet at: {potential_path}")
            if potential_path.exists():
                logger.info(
                    f"Found stylesheet for theme '{theme_name}' at: {potential_path}"
                )
                return potential_path
        logger.error(f"Stylesheet path does not exist for theme '{theme_name}'")
        dialogue.show_warning(
            title="Theme path Error",
            text=f"Stylesheet path does not exist for theme '{theme_name}' Resetting to default theme '{self.default_theme}'.",
        )
        return None

    def apply_selected_theme(
        self, enable_themes: bool, selected_theme_name: str
    ) -> None:
        """Apply the selected theme without restarting the application.

        Args:
            enable_themes (bool): Flag to enable themes.
            selected_theme_name (str): The name of the theme to apply.
        """
        if not isinstance(self.app_instance, QApplication):
            logger.warning("Application instance is not a QApplication.")
            return

        if enable_themes:
            stylesheet = self.load_theme(selected_theme_name)
            if stylesheet:
                self.app_instance.setStyleSheet(stylesheet)
                logger.info(f"Applied theme: {selected_theme_name}")
            else:
                logger.warning(
                    f"Failed to apply theme: {selected_theme_name},"
                    f"Resetting to default theme: {self.default_theme}"
                )
                dialogue.show_warning(
                    title="Theme Error",
                    text=f"Failed to apply theme: {selected_theme_name},"
                    f"Resetting to default theme: {self.default_theme}",
                )
                self.reset_to_default_theme()
        else:
            # If themes are disabled, Set Fusion theme
            self.set_fusion_theme()

    def reset_to_default_theme(self) -> None:
        """Reset the application to the default theme."""
        if isinstance(self.app_instance, QApplication):
            logger.info("Resetting to default theme")
            stylesheet = self.load_theme(self.default_theme)
            if stylesheet:
                self.app_instance.setStyleSheet(stylesheet)
            else:
                logger.error(f"Failed to load default theme: {self.default_theme}")

    def set_fusion_theme(self) -> None:
        """Applies when themes are disabled."""
        if isinstance(self.app_instance, QApplication):
            logger.info("Themes disabled, setting Fusion theme")
            self.app_instance.setStyleSheet("")  # Clear any existing stylesheets
            self.app_instance.setStyle("Fusion")

    def populate_themes_combobox(self, combobox: QComboBox) -> None:
        """Populate the themes combobox with available themes."""
        combobox.clear()
        available_themes = list(self._get_supported_themes())
        combobox.addItems(available_themes)

    def setup_theme_dialog(
        self, settings_dialog: "SettingsDialog", settings: "Settings"
    ) -> None:
        """
        Set up the settings dialog with current settings.
        Reloading settings is required since ThemeController will reset to RimPy if the theme is invalid.
        """
        settings_dialog.enable_themes_checkbox.setChecked(settings.enable_themes)
        if settings.enable_themes:
            # Set the current theme in the combobox
            current_theme_name = settings.theme_name
            current_index = settings_dialog.themes_combobox.findText(current_theme_name)
            current_font_family = settings.font_family
            current_font_size = settings.font_size
            current_font_family_index = settings_dialog.font_family_combobox.findText(current_font_family)
            settings_dialog.font_size_spinbox.setValue(current_font_size)
            if current_font_family_index != -1:
                settings_dialog.font_family_combobox.setCurrentIndex(current_font_family_index)
            else:
                settings_dialog.font_family_combobox.setCurrentIndex(-1)
            if current_index != -1:
                settings_dialog.themes_combobox.setCurrentIndex(current_index)
            else:
                # Fallback to default theme
                default_theme = self.default_theme
                logger.warning(
                    f"Resetting to '{default_theme}' theme due to missing or invalid theme: {current_theme_name}"
                )
                settings.theme_name = default_theme
                current_index = settings_dialog.themes_combobox.findText(default_theme)
                settings.save()
                self.apply_selected_theme(settings.enable_themes, default_theme)
        else:
            self.set_fusion_theme()
            logger.info(
                "Themes disabled, setting Fusion theme. Please enable themes to apply a theme."
            )

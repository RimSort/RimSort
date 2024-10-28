from pathlib import Path
from typing import Optional

from loguru import logger

from app.utils.app_info import AppInfo
from app.views import dialogue


class ThemeController:
    def __init__(self, default_theme: str = "RimPy") -> None:
        self.app_info = AppInfo()
        logger.info("Initializing ThemeController")
        self.default_theme = default_theme
        self.themes = self.get_supported_themes()
        logger.info(f"Supported themes: {self.themes}")
        self.theme_stylesheets_folder = [
            self.app_info.theme_storage_folder,
            self.app_info.theme_data_folder,
        ]

    def get_supported_themes(self) -> set[str]:
        """Retrieves a list of supported themes from the theme data and storage folders."""
        if not hasattr(self, "_supported_themes"):
            theme_data_folders = self.get_theme_names_from_folder(
                self.app_info.theme_data_folder
            )
            theme_storage_folders = self.get_theme_names_from_folder(
                self.app_info.theme_storage_folder
            )
            self._supported_themes = theme_data_folders | theme_storage_folders
            logger.info(f"Supported themes retrieved: {self._supported_themes}")
            logger.info(
                f"Checking theme folders: {[self.app_info.theme_data_folder, self.app_info.theme_storage_folder]}"
            )
        return self._supported_themes

    def get_theme_names_from_folder(self, folder: Path) -> set[str]:
        """Helper method to get theme names from a specified folder."""
        supported_themes = set()
        if folder.exists():
            for subfolder in folder.iterdir():
                if subfolder.is_dir():
                    stylesheet_path = subfolder / "style.qss"
                    if stylesheet_path.exists():
                        supported_themes.add(subfolder.name)
                        logger.info(
                            f"Found theme with stylesheet in {folder}: {subfolder.name}"
                        )
        return supported_themes

    def load_theme(self, theme_name: str) -> Optional[str]:
        """Load the specified theme."""
        if theme_name in self.themes:
            logger.info(f"Loading theme: {theme_name}")
            stylesheet_path = self.get_theme_stylesheet_path(theme_name)
            if stylesheet_path:
                try:
                    with open(stylesheet_path, "r") as f:
                        stylesheet = f.read()
                    return stylesheet
                except Exception as e:
                    logger.error(f"Error loading theme: {e}")
                    return None
            else:
                logger.error(f"Stylesheet not found for theme: {theme_name}")
                return None
        else:
            logger.error(f"Attempted to load unsupported theme: {theme_name}")
            # Revert and attempt to load the default theme
            return self.load_theme(self.default_theme)

    def get_theme_stylesheet_path(self, theme_name: str) -> Optional[Path]:
        """Returns the path to the stylesheet for the specified theme."""
        logger.info(f"Searching for stylesheet for theme: {theme_name}")

        # Initialize a variable to hold the path
        stylesheet_path = None

        for folder in self.theme_stylesheets_folder:
            # Construct the stylesheet path
            potential_path = folder / theme_name / "style.qss"
            logger.debug(f"Checking for stylesheet at: {potential_path}")

            if potential_path.exists():
                logger.info(
                    f"Found stylesheet for theme '{theme_name}' at: {potential_path}"
                )
                return potential_path  # Return as soon as we find it

            # Update stylesheet_path to the last checked path
            stylesheet_path = potential_path

        # If stylesheet not found, log an error and return None
        logger.error(
            f"Stylesheet path does not exist for theme '{theme_name}': {stylesheet_path}"
        )
        dialogue.show_warning(
            title="Theme path Error",
            text=f"Stylesheet path does not exist for theme '{theme_name}': {stylesheet_path}",
        )
        return None

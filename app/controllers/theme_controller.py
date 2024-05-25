from pathlib import Path
from typing import Optional

from loguru import logger

from app.utils.app_info import AppInfo

THEME_FOLDERS = [AppInfo().theme_data_folder, AppInfo().theme_storage_folder]


class Themes:
    def __init__(self, theme_name: Optional[str] = None):
        self.theme_name = theme_name or self.get_default_theme_name()
        self.validate_theme()

    def get_default_theme_name(self) -> str:
        """
        Get the default theme name by scanning the theme data folder.
        """
        for themes in THEME_FOLDERS:
            for folder in themes.iterdir():
                if folder.is_dir():
                    return folder.name
        return "RimPy"  # Fallback to "RimPy" if no theme folders are found

    def validate_theme(self) -> None:
        supported_themes = [
            folder.name
            for folder in AppInfo().theme_data_folder.iterdir()
            if folder.is_dir()
        ] + [
            folder.name
            for folder in AppInfo().theme_storage_folder.iterdir()
            if folder.is_dir()
        ]

        if self.theme_name not in supported_themes:
            # If applied Theme is Missing or Invalid, default to "RimPy"
            self.theme_name = "RimPy"
            logger.warning(
                f"Stylesheet file is Missing or Invalid in '{THEME_FOLDERS}', Applying '{self.theme_name}' Theme."
            )

    def style_sheet(self) -> str:
        theme_data_folder_path = (
            AppInfo().theme_data_folder / self.theme_name / "style.qss"
        )
        theme_storage_folder_path = (
            AppInfo().theme_storage_folder / self.theme_name / "style.qss"
        )

        if theme_data_folder_path.exists():
            stylesheet_path = theme_data_folder_path
        elif theme_storage_folder_path.exists():
            stylesheet_path = theme_storage_folder_path
        else:
            # If No Theme is Found, Including Default Theme, Avoid Crash
            logger.error(
                f"Stylesheet file including Default Theme not found in '{THEME_FOLDERS}', Applying '{self.theme_name}' Theme"
            )
            return ""

        if (
            stylesheet_path.exists()
            and stylesheet_path == theme_data_folder_path
            or theme_storage_folder_path
        ):
            return stylesheet_path.read_text()
        else:
            # If No Theme is Found, Including Default Theme, Avoid Crash
            logger.error(
                f"Stylesheet file including Default Theme not found in '{THEME_FOLDERS}', Applying '{self.theme_name}' Theme"
            )
            return ""

    # TODO: Add support for custom icons
    def theme_icon(self, icon_name: str) -> Path:
        theme_data_folder_path = AppInfo().theme_data_folder / self.theme_name / "icons"
        theme_storage_folder_path = (
            AppInfo().theme_storage_folder / self.theme_name / "icons"
        )

        if theme_data_folder_path.exists():
            icon_folder_path = theme_data_folder_path
        elif theme_storage_folder_path.exists():
            icon_folder_path = theme_storage_folder_path
        else:
            # If No icon is Found, Including Default Icon, Avoid Crash
            logger.error(
                f"Icon folder including Default Icons not found in '{THEME_FOLDERS}', Applying '{self.theme_name}' Icons"
            )
            return ""

        if (
            icon_folder_path.exists()
            and icon_folder_path == theme_data_folder_path
            or theme_storage_folder_path
        ):
            return icon_folder_path.read_text()
        else:
            # If No icon is Found, Including Default Icon, Avoid Crash
            logger.error(
                f"Icon folder including Default Icons not found in '{THEME_FOLDERS}', Applying '{self.theme_name}' Icons"
            )
            return ""

        icon_path = icon_folder_path / f"{icon_name}.png"

    @classmethod
    def get_available_themes(cls) -> list[Path]:
        """
        Get a list of available themes from theme data folders.
        """
        available_themes = []
        for theme_path in THEME_FOLDERS:
            for folder in theme_path.iterdir():
                if folder.is_dir():
                    stylesheet_path = folder / "style.qss"
                    if stylesheet_path.exists():
                        available_themes.append(folder)
                    else:
                        logger.warning(
                            f"Skipping folder '{folder.name}' in `{theme_path}' as it doesn't contain a valid stylesheet."
                        )

        return available_themes

from pathlib import Path

from loguru import logger
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication, QComboBox

from app.models.settings import Settings
from app.utils.app_info import AppInfo
from app.utils.generic import restart_application
from app.views import dialogue
from app.views.settings_dialog import SettingsDialog


class LanguageController:
    def __init__(self, default_language: str = "en_US") -> None:
        """Initialize the LanguageController with a default language.

        Args:
            default_language (str): The name of the default language. Defaults to "en".
        """
        self.app_info = AppInfo()
        self.app_instance = QApplication.instance()
        logger.info("Initializing LanguageController")
        self.default_language = default_language
        self._language_data_folder = self.app_info.language_data_folder
        self.languages = self._get_supported_languages()
        logger.info(f"Supported languages: {self.languages}")

    def _get_supported_languages(self) -> set[str]:
        language_names = self._get_language_names_from_folder(
            self._language_data_folder
        )
        logger.info(f"Supported languages retrieved: {language_names}")
        logger.debug(f"Checking language folders: {[self._language_data_folder]}")

        return language_names

    def _get_language_names_from_folder(self, folder: Path) -> set[str]:
        """Helper method to get language names from a specified folder.

        Args:
            folder (Path): The folder to search for languages.

        Returns:
            set[str]: A set of language names found in the folder.
        """
        supported_languages = set()
        if folder.exists():
            for file in folder.glob("*.qm"):
                if file.is_file():
                    language_name = file.stem
                    supported_languages.add(language_name)
                    logger.info(f"Found language: {language_name} in {folder}")
        return supported_languages

    def populate_languages_combobox(self, combox: QComboBox) -> None:
        """Populate a QComboBox with supported languages."""
        combox.clear()
        language_map = {
            "en_US": "English",
            "es_ES": "Español",
            "fr_FR": "Français",
            "de_DE": "Deutsch",
            "zh_CN": "简体中文",
            "ja_JP": "日本語",
            "ru_RU": "Русский",
            "tr_TR": "Türkçe",
            "pt_BR": "Português (Brasil)",
            "zh_TW": "正體中文",
        }
        available_languages = self.languages
        for lang_code in available_languages:
            display_name = language_map.get(lang_code, lang_code)
            combox.addItem(display_name, lang_code)

    def setup_language_dialog(
        self, settings_dialog: "SettingsDialog", settings: "Settings"
    ) -> None:
        """
        Set up the settings dialog with current settings and connect language change signal.
        """
        current_language = settings.language
        current_index = settings_dialog.language_combobox.findData(current_language)
        if current_index != -1:
            settings_dialog.language_combobox.setCurrentIndex(current_index)
        else:
            settings_dialog.language_combobox.setCurrentIndex(
                settings_dialog.language_combobox.findData(self.default_language)
            )

        settings_dialog.language_combobox.activated.connect(
            lambda: self._on_language_changed(settings_dialog, settings)
        )

    def _on_language_changed(
        self, settings_dialog: "SettingsDialog", settings: "Settings"
    ) -> None:
        """Handle language change and prompt user to restart."""
        new_language = settings_dialog.language_combobox.currentData()
        if new_language != settings.language:
            settings.language = new_language
            settings.save()

            answer = dialogue.show_dialogue_conditional(
                title=self.tr("Language Changed"),
                text=self.tr("The language has been updated."),
                information=self.tr(
                    "Restart the application to apply the change. Restart now?"
                ),
                button_text_override=[
                    self.tr("Restart"),
                ],
            )

            if answer == QCoreApplication.translate("LanguageController", "Restart"):
                logger.info("User chose to restart the application.")
                restart_application()

    def tr(self, text: str) -> str:
        return QCoreApplication.translate("LanguageController", text)

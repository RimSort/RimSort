import sys
from dataclasses import dataclass
from json import JSONDecodeError
from pathlib import Path

from loguru import logger
from PySide6.QtCore import QObject, Slot
from PySide6.QtWidgets import QApplication, QLineEdit, QMessageBox

from app.controllers.theme_controller import ThemeController
from app.models.settings import Instance, Settings
from app.utils.constants import SortMethod
from app.utils.event_bus import EventBus
from app.utils.generic import platform_specific_open
from app.utils.system_info import SystemInfo
from app.views.dialogue import (
    BinaryChoiceDialog,
    show_dialogue_file,
    show_settings_error,
)
from app.views.settings_dialog import SettingsDialog


class SettingsController(QObject):
    """
    Controller class to manage interactions with the `Settings` model.

    The `SettingsController` class provides a clear interface for working with the `Settings` model.
    It ensures that the associated settings model is loaded upon initialization.

    Attributes:
        settings (Settings): The underlying settings model managed by this controller.
        settings_dialog (SettingsDialog): The settings dialog managed by this controller.

    Examples:
        >>> settings_model = Settings()
        >>> controller = SettingsController(settings_model)
        >>> controller.settings.some_property
    """

    def __init__(self, model: Settings, view: SettingsDialog) -> None:
        """
        Initialize the `SettingsController` with the given `Settings` model and `SettingsDialog` view.

        Upon initialization, the provided settings model's `load` method is called to ensure
        that the settings are loaded and available for use. The view is also initialized with values
        from the settings model.

        Args:
            model (Settings): The settings model to be managed by this controller.
            view (SettingsDialog): The settings dialog to be managed by this controller.
        """
        super().__init__()

        self.settings = model
        self.settings_dialog = view

        self._last_file_dialog_path = str(Path.home())

        # Initialize the settings dialog from the settings model

        self._update_view_from_model()

        # Wire up the settings dialog's global buttons

        self.settings_dialog.global_reset_to_defaults_button.clicked.connect(
            self._on_global_reset_to_defaults_button_clicked
        )

        self.settings_dialog.global_cancel_button.clicked.connect(
            self._on_global_cancel_button_clicked
        )

        self.settings_dialog.global_ok_button.clicked.connect(
            self._on_global_ok_button_clicked
        )

        # Locations tab
        self.settings_dialog.game_location.textChanged.connect(
            self._on_game_location_text_changed
        )
        self.settings_dialog.game_location_open_button.clicked.connect(
            self._on_game_location_open_button_clicked
        )
        self.settings_dialog.game_location_choose_button.clicked.connect(
            self._on_game_location_choose_button_clicked
        )
        self.settings_dialog.game_location_clear_button.clicked.connect(
            self._on_game_location_clear_button_clicked
        )

        self.settings_dialog.config_folder_location.textChanged.connect(
            self._on_config_folder_location_text_changed
        )
        self.settings_dialog.config_folder_location_open_button.clicked.connect(
            self._on_config_folder_location_open_button_clicked
        )
        self.settings_dialog.config_folder_location_choose_button.clicked.connect(
            self._on_config_folder_location_choose_button_clicked
        )
        self.settings_dialog.config_folder_location_clear_button.clicked.connect(
            self._on_config_folder_location_clear_button_clicked
        )

        self.settings_dialog.steam_mods_folder_location.textChanged.connect(
            self._on_steam_mods_folder_location_text_changed
        )
        self.settings_dialog.steam_mods_folder_location_open_button.clicked.connect(
            self._on_steam_mods_folder_location_open_button_clicked
        )
        self.settings_dialog.steam_mods_folder_location_choose_button.clicked.connect(
            self._on_steam_mods_folder_location_choose_button_clicked
        )
        self.settings_dialog.steam_mods_folder_location_clear_button.clicked.connect(
            self._on_steam_mods_folder_location_clear_button_clicked
        )

        self.settings_dialog.local_mods_folder_location.textChanged.connect(
            self._on_local_mods_folder_location_text_changed
        )
        self.settings_dialog.local_mods_folder_location_open_button.clicked.connect(
            self._on_local_mods_folder_location_open_button_clicked
        )
        self.settings_dialog.local_mods_folder_location_choose_button.clicked.connect(
            self._on_local_mods_folder_location_choose_button_clicked
        )
        self.settings_dialog.local_mods_folder_location_clear_button.clicked.connect(
            self._on_local_mods_folder_location_clear_button_clicked
        )

        self.settings_dialog.locations_clear_button.clicked.connect(
            self._on_locations_clear_button_clicked
        )

        self.settings_dialog.locations_autodetect_button.clicked.connect(
            self._on_locations_autodetect_button_clicked
        )

        # Wire up the Databases tab buttons

        self.settings_dialog.community_rules_db_none_radio.clicked.connect(
            self._on_community_rules_db_radio_clicked
        )
        self.settings_dialog.community_rules_db_github_radio.clicked.connect(
            self._on_community_rules_db_radio_clicked
        )
        self.settings_dialog.community_rules_db_local_file_radio.clicked.connect(
            self._on_community_rules_db_radio_clicked
        )

        self.settings_dialog.community_rules_db_local_file_choose_button.clicked.connect(
            self._on_community_rules_db_local_file_choose_button_clicked
        )
        self.settings_dialog.community_rules_db_github_upload_button.clicked.connect(
            EventBus().do_upload_community_rules_db_to_github
        )
        self.settings_dialog.community_rules_db_github_download_button.clicked.connect(
            EventBus().do_download_community_rules_db_from_github
        )

        self.settings_dialog.steam_workshop_db_none_radio.clicked.connect(
            self._on_steam_workshop_db_radio_clicked
        )
        self.settings_dialog.steam_workshop_db_github_radio.clicked.connect(
            self._on_steam_workshop_db_radio_clicked
        )
        self.settings_dialog.steam_workshop_db_local_file_radio.clicked.connect(
            self._on_steam_workshop_db_radio_clicked
        )

        self.settings_dialog.steam_workshop_db_local_file_choose_button.clicked.connect(
            self._on_steam_workshop_db_local_file_choose_button_clicked
        )
        self.settings_dialog.steam_workshop_db_github_upload_button.clicked.connect(
            EventBus().do_upload_steam_workshop_db_to_github
        )
        self.settings_dialog.steam_workshop_db_github_download_button.clicked.connect(
            EventBus().do_download_steam_workshop_db_from_github
        )

        # Build DB tab
        self.settings_dialog.db_builder_download_all_mods_via_steamcmd_button.clicked.connect(
            self._on_db_builder_download_all_mods_via_steamcmd_button_clicked
        )
        self.settings_dialog.db_builder_download_all_mods_via_steam_button.clicked.connect(
            self._on_db_builder_download_all_mods_via_steam_button_clicked
        )
        self.settings_dialog.db_builder_compare_databases_button.clicked.connect(
            self._on_db_builder_compare_databases_button_clicked
        )
        self.settings_dialog.db_builder_merge_databases_button.clicked.connect(
            self._on_db_builder_merge_databases_button_clicked
        )
        self.settings_dialog.db_builder_build_database_button.clicked.connect(
            self._on_db_builder_build_database_button_clicked
        )

        # SteamCMD tab
        self.settings_dialog.steamcmd_install_location_choose_button.clicked.connect(
            self._on_steamcmd_install_location_choose_button_clicked
        )
        self.settings_dialog.steamcmd_clear_depot_cache_button.clicked.connect(
            self._on_steamcmd_clear_depot_cache_button_clicked
        )
        self.settings_dialog.steamcmd_import_acf_button.clicked.connect(
            self._on_steamcmd_import_acf_button_clicked
        )
        self.settings_dialog.steamcmd_delete_acf_button.clicked.connect(
            self._on_steamcmd_delete_acf_button_clicked
        )
        self.settings_dialog.steamcmd_install_button.clicked.connect(
            self._on_steamcmd_install_button_clicked
        )

        # Theme tab
        self.settings_dialog.theme_location_open_button.clicked.connect(
            self._on_theme_location_open_button_clicked
        )

        # Connect signals from dialogs
        EventBus().reset_settings_file.connect(self._do_reset_settings_file)

        self._load_settings()

    def _load_settings(self) -> None:
        logger.info("Attempting to load settings from settings file")
        try:
            self.settings.load()
        except JSONDecodeError:
            logger.error("Unable to parse settings file")
            show_settings_error()

    def get_mod_paths(self) -> list[str]:
        """
        Get the mod paths for the current instance. Return the Default instance if the current instance is not found.
        """
        return [
            str(
                Path(
                    self.settings.instances[self.settings.current_instance].game_folder
                )
                / "Data"
            ),
            str(
                Path(
                    self.settings.instances[self.settings.current_instance].local_folder
                )
            ),
            str(
                Path(
                    self.settings.instances[
                        self.settings.current_instance
                    ].workshop_folder
                )
            ),
        ]

    def resolve_data_source(self, path: str) -> str | None:
        """
        Resolve the data source for the provided path string.
        """
        # Pathlib the provided path string
        sanitized_path = Path(path)
        # Grab paths from Settings
        expansions_path = (
            Path(self.settings.instances[self.settings.current_instance].game_folder)
            / "Data"
        )
        local_path = Path(
            self.settings.instances[self.settings.current_instance].local_folder
        )
        workshop_path = Path(
            self.settings.instances[self.settings.current_instance].workshop_folder
        )
        # Validate data source, then emit if path is valid and not mapped
        if sanitized_path.parent == expansions_path:
            return "expansion"
        elif sanitized_path.parent == local_path:
            return "local"
        elif sanitized_path.parent == workshop_path:
            return "workshop"
        else:
            return None

    def show_settings_dialog(self, tab_name: str = "") -> None:
        """
        Update the view from the model and show the settings dialog.
        """
        self._update_view_from_model()
        if tab_name:
            self.settings_dialog.switch_to_tab(tab_name)
        self.settings_dialog.show()

    def create_instance(
        self,
        instance_name: str,
        game_folder: str = "",
        config_folder: str = "",
        local_folder: str = "",
        workshop_folder: str = "",
        run_args: list[str] = [],
        steamcmd_install_path: str = "",
        steam_client_integration: bool = False,
    ) -> None:
        """
        Create and set the instance.
        """
        instance = Instance(
            name=instance_name,
            game_folder=game_folder,
            config_folder=config_folder,
            local_folder=local_folder,
            workshop_folder=workshop_folder,
            run_args=run_args,
            steamcmd_install_path=steamcmd_install_path,
            steam_client_integration=steam_client_integration,
        )

        self.set_instance(instance)

    def set_instance(self, instance: Instance) -> None:
        """
        Set the instance with the provided instance.
        """
        self.settings.instances[instance.name] = instance

    @property
    def active_instance(self) -> Instance:
        """
        Get the active instance.
        """
        return self.settings.instances[self.settings.current_instance]

    def _update_view_from_model(self) -> None:
        """
        Update the view from the settings model.
        """

        # Locations tab
        self.settings_dialog.game_location.setText(
            str(self.settings.instances[self.settings.current_instance].game_folder)
        )
        self.settings_dialog.game_location.setCursorPosition(0)
        self.settings_dialog.game_location_open_button.setEnabled(
            self.settings_dialog.game_location.text() != ""
        )

        self.settings_dialog.config_folder_location.setText(
            str(self.settings.instances[self.settings.current_instance].config_folder)
        )
        self.settings_dialog.config_folder_location.setCursorPosition(0)
        self.settings_dialog.config_folder_location_open_button.setEnabled(
            self.settings_dialog.config_folder_location.text() != ""
        )

        self.settings_dialog.steam_mods_folder_location.setText(
            str(self.settings.instances[self.settings.current_instance].workshop_folder)
        )
        self.settings_dialog.steam_mods_folder_location.setCursorPosition(0)
        self.settings_dialog.steam_mods_folder_location_open_button.setEnabled(
            self.settings_dialog.steam_mods_folder_location.text() != ""
        )

        self.settings_dialog.local_mods_folder_location.setText(
            str(self.settings.instances[self.settings.current_instance].local_folder)
        )
        self.settings_dialog.local_mods_folder_location.setCursorPosition(0)
        self.settings_dialog.local_mods_folder_location_open_button.setEnabled(
            self.settings_dialog.local_mods_folder_location.text() != ""
        )

        # Databases tab
        if self.settings.external_community_rules_metadata_source == "None":
            self.settings_dialog.community_rules_db_none_radio.setChecked(True)
            self.settings_dialog.community_rules_db_github_url.setEnabled(False)
            self.settings_dialog.community_rules_db_github_download_button.setEnabled(
                False
            )
            self.settings_dialog.community_rules_db_local_file.setEnabled(False)
            self.settings_dialog.community_rules_db_local_file_choose_button.setEnabled(
                False
            )
        elif (
            self.settings.external_community_rules_metadata_source
            == "Configured git repository"
        ):
            self.settings_dialog.community_rules_db_github_radio.setChecked(True)
            self.settings_dialog.community_rules_db_github_url.setEnabled(True)
            self.settings_dialog.community_rules_db_github_download_button.setEnabled(
                True
            )
            self.settings_dialog.community_rules_db_local_file.setEnabled(False)
            self.settings_dialog.community_rules_db_local_file_choose_button.setEnabled(
                False
            )
        elif (
            self.settings.external_community_rules_metadata_source
            == "Configured file path"
        ):
            self.settings_dialog.community_rules_db_local_file_radio.setChecked(True)
            self.settings_dialog.community_rules_db_github_url.setEnabled(False)
            self.settings_dialog.community_rules_db_github_download_button.setEnabled(
                False
            )
            self.settings_dialog.community_rules_db_local_file.setEnabled(True)
            self.settings_dialog.community_rules_db_local_file_choose_button.setEnabled(
                True
            )
        self.settings_dialog.community_rules_db_local_file.setText(
            self.settings.external_community_rules_file_path
        )
        self.settings_dialog.community_rules_db_local_file.setCursorPosition(0)
        self.settings_dialog.community_rules_db_github_url.setText(
            self.settings.external_community_rules_repo
        )
        self.settings_dialog.community_rules_db_github_url.setCursorPosition(0)
        if self.settings.external_steam_metadata_source == "None":
            self.settings_dialog.steam_workshop_db_none_radio.setChecked(True)
            self.settings_dialog.steam_workshop_db_github_url.setEnabled(False)
            self.settings_dialog.steam_workshop_db_github_download_button.setEnabled(
                False
            )
            self.settings_dialog.steam_workshop_db_local_file.setEnabled(False)
            self.settings_dialog.steam_workshop_db_local_file_choose_button.setEnabled(
                False
            )
        elif (
            self.settings.external_steam_metadata_source == "Configured git repository"
        ):
            self.settings_dialog.steam_workshop_db_github_radio.setChecked(True)
            self.settings_dialog.steam_workshop_db_github_url.setEnabled(True)
            self.settings_dialog.steam_workshop_db_github_download_button.setEnabled(
                True
            )
            self.settings_dialog.steam_workshop_db_local_file.setEnabled(False)
            self.settings_dialog.steam_workshop_db_local_file_choose_button.setEnabled(
                False
            )
        elif self.settings.external_steam_metadata_source == "Configured file path":
            self.settings_dialog.steam_workshop_db_local_file_radio.setChecked(True)
            self.settings_dialog.steam_workshop_db_github_url.setEnabled(False)
            self.settings_dialog.steam_workshop_db_github_download_button.setEnabled(
                False
            )
            self.settings_dialog.steam_workshop_db_local_file.setEnabled(True)
            self.settings_dialog.steam_workshop_db_local_file_choose_button.setEnabled(
                True
            )
        self.settings_dialog.steam_workshop_db_local_file.setText(
            self.settings.external_steam_metadata_file_path
        )
        self.settings_dialog.steam_workshop_db_local_file.setCursorPosition(0)
        self.settings_dialog.steam_workshop_db_github_url.setText(
            self.settings.external_steam_metadata_repo
        )
        self.settings_dialog.steam_workshop_db_github_url.setCursorPosition(0)
        self.settings_dialog.database_expiry.setText(str(self.settings.database_expiry))

        # Sorting tab
        if self.settings.sorting_algorithm == SortMethod.ALPHABETICAL:
            self.settings_dialog.sorting_alphabetical_radio.setChecked(True)
        elif self.settings.sorting_algorithm == SortMethod.TOPOLOGICAL:
            self.settings_dialog.sorting_topological_radio.setChecked(True)

        # Database Builder tab
        if self.settings.db_builder_include == "all_mods":
            self.settings_dialog.db_builder_include_all_radio.setChecked(True)
        elif self.settings.db_builder_include == "no_local":
            self.settings_dialog.db_builder_include_no_local_radio.setChecked(True)
        self.settings_dialog.db_builder_query_dlc_checkbox.setChecked(
            self.settings.build_steam_database_dlc_data
        )
        self.settings_dialog.db_builder_update_instead_of_overwriting_checkbox.setChecked(
            self.settings.build_steam_database_update_toggle
        )
        self.settings_dialog.db_builder_steam_api_key.setText(
            self.settings.steam_apikey
        )

        # SteamCMD tab
        self.settings_dialog.steamcmd_validate_downloads_checkbox.setChecked(
            self.settings.steamcmd_validate_downloads
        )
        self.settings_dialog.steamcmd_auto_clear_depot_cache_checkbox.setChecked(
            self.settings.instances[
                self.settings.current_instance
            ].steamcmd_auto_clear_depot_cache
        )
        self.settings_dialog.steamcmd_install_location.setText(
            str(
                self.settings.instances[
                    self.settings.current_instance
                ].steamcmd_install_path
            )
        )

        # todds tab
        if self.settings.todds_preset == "optimized":
            self.settings_dialog.todds_preset_combobox.setCurrentIndex(0)
        else:
            self.settings_dialog.todds_preset_combobox.setCurrentIndex(0)
        if self.settings.todds_active_mods_target:
            self.settings_dialog.todds_active_mods_only_radio.setChecked(True)
        else:
            self.settings_dialog.todds_all_mods_radio.setChecked(True)
        self.settings_dialog.todds_dry_run_checkbox.setChecked(
            self.settings.todds_dry_run
        )
        self.settings_dialog.todds_overwrite_checkbox.setChecked(
            self.settings.todds_overwrite
        )

        # Themes tab
        self.settings_dialog.enable_themes_checkbox.setChecked(
            self.settings.enable_themes
        )
        self._on_theme_setup_dialog()

        # Advanced tab
        self.settings_dialog.debug_logging_checkbox.setChecked(
            self.settings.debug_logging_enabled
        )
        self.settings_dialog.watchdog_checkbox.setChecked(self.settings.watchdog_toggle)
        self.settings_dialog.mod_type_filter_checkbox.setChecked(
            self.settings.mod_type_filter_toggle
        )
        self.settings_dialog.show_duplicate_mods_warning_checkbox.setChecked(
            self.settings.duplicate_mods_warning
        )
        self.settings_dialog.show_mod_updates_checkbox.setChecked(
            self.settings.steam_mods_update_check
        )
        steam_client_integration = self.settings.instances[
            self.settings.current_instance
        ].steam_client_integration
        # Weird workaround since the return is a string sometimes apparently
        self.settings_dialog.steam_client_integration_checkbox.setChecked(
            True if steam_client_integration is True else False
        )
        self.settings_dialog.download_missing_mods_checkbox.setChecked(
            self.settings.try_download_missing_mods
        )
        self.settings_dialog.render_unity_rich_text_checkbox.setChecked(
            self.settings.render_unity_rich_text
        )
        self.settings_dialog.github_username.setText(self.settings.github_username)
        self.settings_dialog.github_username.setCursorPosition(0)
        self.settings_dialog.github_token.setText(self.settings.github_token)
        self.settings_dialog.github_token.setCursorPosition(0)

        run_args_str = ",".join(
            self.settings.instances[self.settings.current_instance].run_args
        )
        self.settings_dialog.run_args.setText(run_args_str)
        self.settings_dialog.run_args.setCursorPosition(0)
        self.settings_dialog.run_args.textChanged.connect(
            self._on_run_args_text_changed
        )

    def _update_model_from_view(self) -> None:
        """
        Update the settings model from the view.
        """

        # Locations tab
        self.settings.instances[
            self.settings.current_instance
        ].game_folder = self.settings_dialog.game_location.text()

        self.settings.instances[
            self.settings.current_instance
        ].config_folder = self.settings_dialog.config_folder_location.text()

        self.settings.instances[
            self.settings.current_instance
        ].workshop_folder = self.settings_dialog.steam_mods_folder_location.text()

        self.settings.instances[
            self.settings.current_instance
        ].local_folder = self.settings_dialog.local_mods_folder_location.text()

        # Databases tab
        if self.settings_dialog.community_rules_db_none_radio.isChecked():
            self.settings.external_community_rules_metadata_source = "None"
        elif self.settings_dialog.community_rules_db_local_file_radio.isChecked():
            self.settings.external_community_rules_metadata_source = (
                "Configured file path"
            )
        elif self.settings_dialog.community_rules_db_github_radio.isChecked():
            self.settings.external_community_rules_metadata_source = (
                "Configured git repository"
            )
        self.settings.external_community_rules_file_path = (
            self.settings_dialog.community_rules_db_local_file.text()
        )
        self.settings.external_community_rules_repo = (
            self.settings_dialog.community_rules_db_github_url.text()
        )
        if self.settings_dialog.steam_workshop_db_none_radio.isChecked():
            self.settings.external_steam_metadata_source = "None"
        elif self.settings_dialog.steam_workshop_db_local_file_radio.isChecked():
            self.settings.external_steam_metadata_source = "Configured file path"
        elif self.settings_dialog.steam_workshop_db_github_radio.isChecked():
            self.settings.external_steam_metadata_source = "Configured git repository"
        self.settings.external_steam_metadata_repo = (
            self.settings_dialog.steam_workshop_db_github_url.text()
        )
        self.settings.external_steam_metadata_file_path = (
            self.settings_dialog.steam_workshop_db_local_file.text()
        )
        self.settings.database_expiry = int(self.settings_dialog.database_expiry.text())

        # Sorting tab
        if self.settings_dialog.sorting_alphabetical_radio.isChecked():
            self.settings.sorting_algorithm = SortMethod.ALPHABETICAL
        elif self.settings_dialog.sorting_topological_radio.isChecked():
            self.settings.sorting_algorithm = SortMethod.TOPOLOGICAL

        # Database Builder tab
        if self.settings_dialog.db_builder_include_all_radio.isChecked():
            self.settings.db_builder_include = "all_mods"
        elif self.settings_dialog.db_builder_include_no_local_radio.isChecked():
            self.settings.db_builder_include = "no_local"
        self.settings.build_steam_database_dlc_data = (
            self.settings_dialog.db_builder_query_dlc_checkbox.isChecked()
        )
        self.settings.build_steam_database_update_toggle = self.settings_dialog.db_builder_update_instead_of_overwriting_checkbox.isChecked()
        self.settings.steam_apikey = (
            self.settings_dialog.db_builder_steam_api_key.text()
        )

        # SteamCMD tab
        self.settings.steamcmd_validate_downloads = (
            self.settings_dialog.steamcmd_validate_downloads_checkbox.isChecked()
        )
        self.settings.instances[
            self.settings.current_instance
        ].steamcmd_auto_clear_depot_cache = (
            self.settings_dialog.steamcmd_auto_clear_depot_cache_checkbox.isChecked()
        )
        self.settings.instances[
            self.settings.current_instance
        ].steamcmd_install_path = self.settings_dialog.steamcmd_install_location.text()

        # todds tab
        if self.settings_dialog.todds_preset_combobox.currentIndex() == 0:
            self.settings.todds_preset = "optimized"
        else:
            self.settings.todds_preset = "optimized"
        if self.settings_dialog.todds_active_mods_only_radio.isChecked():
            self.settings.todds_active_mods_target = True
        elif self.settings_dialog.todds_all_mods_radio.isChecked():
            self.settings.todds_active_mods_target = False
        self.settings.todds_dry_run = (
            self.settings_dialog.todds_dry_run_checkbox.isChecked()
        )
        self.settings.todds_overwrite = (
            self.settings_dialog.todds_overwrite_checkbox.isChecked()
        )

        # Themes tab
        self.settings.enable_themes = (
            self.settings_dialog.enable_themes_checkbox.isChecked()
        )
        # get theme names from theme combobox and set theme name in settings
        self.settings.theme_name = self.settings_dialog.themes_combobox.currentText()

        # Advanced tab
        self.settings.debug_logging_enabled = (
            self.settings_dialog.debug_logging_checkbox.isChecked()
        )
        self.settings.watchdog_toggle = (
            self.settings_dialog.watchdog_checkbox.isChecked()
        )
        self.settings.mod_type_filter_toggle = (
            self.settings_dialog.mod_type_filter_checkbox.isChecked()
        )
        self.settings.duplicate_mods_warning = (
            self.settings_dialog.show_duplicate_mods_warning_checkbox.isChecked()
        )
        self.settings.steam_mods_update_check = (
            self.settings_dialog.show_mod_updates_checkbox.isChecked()
        )
        self.settings.instances[
            self.settings.current_instance
        ].steam_client_integration = (
            self.settings_dialog.steam_client_integration_checkbox.isChecked()
        )
        self.settings.try_download_missing_mods = (
            self.settings_dialog.download_missing_mods_checkbox.isChecked()
        )
        self.settings.render_unity_rich_text = (
            self.settings_dialog.render_unity_rich_text_checkbox.isChecked()
        )
        self.settings.github_username = self.settings_dialog.github_username.text()
        self.settings.github_token = self.settings_dialog.github_token.text()
        run_args_str = ",".join(
            self.settings.instances[self.settings.current_instance].run_args
        )
        self.settings_dialog.run_args.setText(run_args_str)

    @Slot()
    def _on_global_reset_to_defaults_button_clicked(self) -> None:
        """
        Reset the settings to their default values.
        """
        answer = BinaryChoiceDialog(
            title="Reset to defaults",
            text="Are you sure you want to reset all settings to their default values?",
        )
        if not answer.exec_is_positive():
            return

        self.settings = Settings()
        self._update_view_from_model()

    @Slot()
    def _on_global_cancel_button_clicked(self) -> None:
        """
        Close the settings dialog without saving the settings.
        """
        self.settings_dialog.close()
        self._update_view_from_model()

    @Slot()
    def _on_global_ok_button_clicked(self) -> None:
        """
        Close the settings dialog, update the model from the view, and save the settings.
        """
        self.settings_dialog.close()
        self._update_model_from_view()
        self.settings.save()

    @Slot()
    def _on_game_location_text_changed(self) -> None:
        self.settings_dialog.game_location_open_button.setEnabled(
            self.settings_dialog.game_location.text() != ""
        )

    @Slot()
    def _on_game_location_open_button_clicked(self) -> None:
        platform_specific_open(self.settings_dialog.game_location.text())

    @Slot()
    def _on_game_location_choose_button_clicked(self) -> None:
        """
        Open a file dialog to select the game location and handle the result.
        """
        if SystemInfo().operating_system == SystemInfo.OperatingSystem.MACOS:
            game_location = self._on_game_location_choose_button_clicked_macos()
        else:
            game_location = self._on_game_location_choose_button_clicked_non_macos()
        if game_location is None:
            return
        self.settings_dialog.game_location.setText(str(game_location))
        self._last_file_dialog_path = str(game_location)

    def _on_game_location_choose_button_clicked_macos(self) -> Path | None:
        """
        Open a directory dialog to select the game location for macOS and handle the result.
        """
        game_location = show_dialogue_file(
            mode="open_dir",
            caption="Select Game Location",
            _dir=str(self._last_file_dialog_path),
        )
        if not game_location:
            return None

        return Path(game_location)

    def _on_game_location_choose_button_clicked_non_macos(self) -> Path | None:
        """
        Open a directory dialog to select the game location and handle the result.
        """
        game_location = show_dialogue_file(
            mode="open_dir",
            caption="Select Game Location",
            _dir=str(self._last_file_dialog_path),
        )
        if not game_location:
            return None

        return Path(game_location).resolve()

    @Slot()
    def _on_game_location_clear_button_clicked(self) -> None:
        self.settings_dialog.game_location.setText("")

    @Slot()
    def _on_config_folder_location_text_changed(self) -> None:
        self.settings_dialog.config_folder_location_open_button.setEnabled(
            self.settings_dialog.config_folder_location.text() != ""
        )

    @Slot()
    def _on_config_folder_location_open_button_clicked(self) -> None:
        platform_specific_open(self.settings_dialog.config_folder_location.text())

    @Slot()
    def _on_config_folder_location_choose_button_clicked(self) -> None:
        """
        Open a directory dialog to select the config folder and handle the result.
        """
        config_folder_location = show_dialogue_file(
            mode="open_dir",
            caption="Select Config Folder",
            _dir=str(self._last_file_dialog_path),
        )
        if not config_folder_location:
            return

        self.settings_dialog.config_folder_location.setText(config_folder_location)
        self._last_file_dialog_path = str(Path(config_folder_location).parent)

    @Slot()
    def _on_config_folder_location_clear_button_clicked(self) -> None:
        self.settings_dialog.config_folder_location.setText("")

    @Slot()
    def _on_steam_mods_folder_location_text_changed(self) -> None:
        self.settings_dialog.steam_mods_folder_location_open_button.setEnabled(
            self.settings_dialog.steam_mods_folder_location.text() != ""
        )

    @Slot()
    def _on_steam_mods_folder_location_open_button_clicked(self) -> None:
        platform_specific_open(self.settings_dialog.steam_mods_folder_location.text())

    @Slot()
    def _on_steam_mods_folder_location_choose_button_clicked(self) -> None:
        """
        Open a directory dialog to select the Steam mods folder and handle the result.
        """
        steam_mods_folder_location = show_dialogue_file(
            mode="open_dir",
            caption="Select Steam Mods Folder",
            _dir=str(self._last_file_dialog_path),
        )
        if not steam_mods_folder_location:
            return

        self.settings_dialog.steam_mods_folder_location.setText(
            steam_mods_folder_location
        )
        self._last_file_dialog_path = str(Path(steam_mods_folder_location).parent)

    @Slot()
    def _on_steam_mods_folder_location_clear_button_clicked(self) -> None:
        self.settings_dialog.steam_mods_folder_location.setText("")

    @Slot()
    def _on_local_mods_folder_location_text_changed(self) -> None:
        self.settings_dialog.local_mods_folder_location_open_button.setEnabled(
            self.settings_dialog.local_mods_folder_location.text() != ""
        )

    @Slot()
    def _on_local_mods_folder_location_open_button_clicked(self) -> None:
        platform_specific_open(self.settings_dialog.local_mods_folder_location.text())

    @Slot()
    def _on_local_mods_folder_location_choose_button_clicked(self) -> None:
        """
        Open a directory dialog to select the local mods folder and handle the result.
        """
        local_mods_folder_location = show_dialogue_file(
            mode="open_dir",
            caption="Select Local Mods Folder",
            _dir=str(self._last_file_dialog_path),
        )
        if not local_mods_folder_location:
            return

        self.settings_dialog.local_mods_folder_location.setText(
            local_mods_folder_location
        )
        self._last_file_dialog_path = str(Path(local_mods_folder_location).parent)

    @Slot()
    def _on_local_mods_folder_location_clear_button_clicked(self) -> None:
        self.settings_dialog.local_mods_folder_location.setText("")

    @Slot()
    def _on_locations_clear_button_clicked(
        self, skip_confirmation: bool = False
    ) -> None:
        """
        Clear the settings dialog's location fields.
        """
        if not skip_confirmation:
            answer = BinaryChoiceDialog(
                title="Clear all locations",
                text="Are you sure you want to clear all locations?",
            )
            if not answer.exec_is_positive():
                return

        self.settings_dialog.game_location.setText("")
        self.settings_dialog.config_folder_location.setText("")
        self.settings_dialog.steam_mods_folder_location.setText("")
        self.settings_dialog.local_mods_folder_location.setText("")

    @Slot()
    def _on_locations_autodetect_button_clicked(self) -> None:
        """
        This function tries to autodetect Rimworld paths based on the
        defaults typically found per-platform, and set them in the client.
        """
        logger.info("USER ACTION: starting autodetect paths")

        os_paths: tuple[Path, Path, Path]  # Initialize os_paths
        if SystemInfo().operating_system == SystemInfo.OperatingSystem.MACOS:
            os_paths = self.__get_darwin_paths()
            logger.info(f"Running on MacOS with the following paths: {os_paths}")
        elif SystemInfo().operating_system == SystemInfo.OperatingSystem.LINUX:
            os_paths = self.__get_debian_paths()
            logger.info(f"Running on Linux with the following paths: {os_paths}")
        elif sys.platform == "win32":
            os_paths = self.__get_windows_paths()
            logger.info(f"Running on Windows with the following paths: {os_paths}")
        else:
            logger.error("Attempting to autodetect paths on an unknown system")
            return

        @dataclass
        class _PathGroup:
            folder: Path
            settings_line: QLineEdit
            name: str

        path_groups = [
            _PathGroup(os_paths[0], self.settings_dialog.game_location, "game"),
            _PathGroup(
                os_paths[1], self.settings_dialog.config_folder_location, "config"
            ),
            _PathGroup(
                os_paths[2],
                self.settings_dialog.steam_mods_folder_location,
                "workshop mods",
            ),
            _PathGroup(
                os_paths[0] / "Mods",
                self.settings_dialog.local_mods_folder_location,
                "local mods",
            ),
        ]

        for group in path_groups:
            if group.folder.exists():
                logger.info(
                    f"Auto-detected {group.name} folder path exists: {group.folder}"
                )
                if not group.settings_line.text():
                    logger.info(
                        f"No value set currently for {group.name} folder. Overwriting with auto-detected path"
                    )
                    group.settings_line.setText(str(group.folder))
                else:
                    logger.info(f"Value already set for {group.name} folder. Passing")
            else:
                logger.warning(
                    f"Auto-detected {group.name} folder path does not exist: {group.folder}"
                )

    def __get_darwin_paths(self) -> tuple[Path, Path, Path]:
        """
        Get the default paths for macOS.

        Returns:
            tuple[Path, Path, Path]: game_folder, config_folder, steam_mods_folder
        """
        user_home = Path.home()
        game_folder = Path(
            f"/{user_home}/Library/Application Support/Steam/steamapps/common/Rimworld/RimworldMac.app"
        )
        config_folder = Path(
            f"/{user_home}/Library/Application Support/Rimworld/Config"
        )
        steam_mods_folder = Path(
            f"/{user_home}/Library/Application Support/Steam/steamapps/workshop/content/294100"
        )

        return game_folder, config_folder, steam_mods_folder

    def __get_debian_paths(self) -> tuple[Path, Path, Path]:
        """
        Get the default paths for Debian-based Linux distributions.

        Returns:
            tuple[Path, Path, Path]: game_folder, config_folder, steam_mods_folder
        """
        user_home = Path.home()
        debian_path = user_home / ".steam/debian-installation"
        if not debian_path.exists():
            steam_path = user_home / ".steam/steam"
            debian_path = steam_path / "steamapps/common/RimWorld"
        game_folder = debian_path / "steamapps/common/RimWorld"
        config_folder = (
            user_home
            / ".config/unity3d/Ludeon Studios/RimWorld by Ludeon Studios/Config"
        )
        steam_mods_folder = debian_path / "steamapps/workshop/content/294100"

        return game_folder, config_folder, steam_mods_folder

    def __get_windows_paths(self) -> tuple[Path, Path, Path]:
        """
        Get the default paths for Windows.

        Returns:
            tuple[Path, Path, Path]: game_folder, config_folder, steam_mods_folder
        """
        if sys.platform == "win32":
            user_home = Path.home()
            steam_folder = "C:/Program Files (x86)/Steam"
            from app.utils.win_find_steam import find_steam_folder

            steam_folder, found = find_steam_folder()

            if not found:
                logger.error(
                    "[win32] Could not find Steam folder. Using fallback assumptions"
                )
                steam_folder = "C:/Program Files (x86)/Steam"

            game_folder = Path(f"{steam_folder}/steamapps/common/Rimworld")
            config_folder = Path(
                f"{user_home}/AppData/LocalLow/Ludeon Studios/RimWorld by Ludeon Studios/Config"
            )
            steam_mods_folder = Path(
                f"{steam_folder}/steamapps/workshop/content/294100"
            )

            return game_folder, config_folder, steam_mods_folder
        else:
            raise ValueError("This function should only be called on Windows")

    @Slot(bool)
    def _on_community_rules_db_radio_clicked(self, checked: bool = True) -> None:
        """
        This function handles the community rules db radio buttons. Clicking one button
        enables the associated widgets and disables the other widgets.
        """
        if (
            self.sender() == self.settings_dialog.community_rules_db_none_radio
            and checked
        ):
            self.settings_dialog.community_rules_db_github_url.setEnabled(False)
            self.settings_dialog.community_rules_db_github_download_button.setEnabled(
                False
            )
            self.settings_dialog.community_rules_db_local_file.setEnabled(False)
            self.settings_dialog.community_rules_db_local_file_choose_button.setEnabled(
                False
            )
            app_instance = QApplication.instance()
            if isinstance(app_instance, QApplication):
                focused_widget = app_instance.focusWidget()
                if focused_widget is not None:
                    focused_widget.clearFocus()
            return

        if (
            self.sender() == self.settings_dialog.community_rules_db_github_radio
            and checked
        ):
            self.settings_dialog.community_rules_db_github_url.setEnabled(True)
            self.settings_dialog.community_rules_db_github_download_button.setEnabled(
                True
            )
            self.settings_dialog.community_rules_db_local_file.setEnabled(False)
            self.settings_dialog.community_rules_db_local_file_choose_button.setEnabled(
                False
            )
            self.settings_dialog.community_rules_db_github_url.setFocus()
            return

        if (
            self.sender() == self.settings_dialog.community_rules_db_local_file_radio
            and checked
        ):
            self.settings_dialog.community_rules_db_github_url.setEnabled(False)
            self.settings_dialog.community_rules_db_github_download_button.setEnabled(
                False
            )
            self.settings_dialog.community_rules_db_local_file.setEnabled(True)
            self.settings_dialog.community_rules_db_local_file_choose_button.setEnabled(
                True
            )
            self.settings_dialog.community_rules_db_local_file.setFocus()
            return

    @Slot()
    def _on_community_rules_db_local_file_choose_button_clicked(self) -> None:
        """
        Open a file dialog to select the community rules database and handle the result.
        """
        community_rules_db_location = show_dialogue_file(
            mode="open",
            caption="Select Community Rules Database",
            _dir=str(self._last_file_dialog_path),
        )
        if not community_rules_db_location:
            return

        self.settings_dialog.community_rules_db_local_file.setText(
            community_rules_db_location
        )
        self._last_file_dialog_path = str(Path(community_rules_db_location).parent)

    @Slot(bool)
    def _on_steam_workshop_db_radio_clicked(self, checked: bool = True) -> None:
        """
        This function handles the Steam workshop db radio buttons. Clicking one button
        enables the associated widgets and disables the other widgets.
        """
        if (
            self.sender() == self.settings_dialog.steam_workshop_db_none_radio
            and checked
        ):
            self.settings_dialog.steam_workshop_db_github_url.setEnabled(False)
            self.settings_dialog.steam_workshop_db_github_download_button.setEnabled(
                False
            )
            self.settings_dialog.steam_workshop_db_local_file.setEnabled(False)
            self.settings_dialog.steam_workshop_db_local_file_choose_button.setEnabled(
                False
            )
            app_instance = QApplication.instance()
            if isinstance(app_instance, QApplication):
                focused_widget = app_instance.focusWidget()
                if focused_widget is not None:
                    focused_widget.clearFocus()
            return

        if (
            self.sender() == self.settings_dialog.steam_workshop_db_github_radio
            and checked
        ):
            self.settings_dialog.steam_workshop_db_github_url.setEnabled(True)
            self.settings_dialog.steam_workshop_db_github_download_button.setEnabled(
                True
            )
            self.settings_dialog.steam_workshop_db_local_file.setEnabled(False)
            self.settings_dialog.steam_workshop_db_local_file_choose_button.setEnabled(
                False
            )
            self.settings_dialog.steam_workshop_db_github_url.setFocus()
            return

        if (
            self.sender() == self.settings_dialog.steam_workshop_db_local_file_radio
            and checked
        ):
            self.settings_dialog.steam_workshop_db_github_url.setEnabled(False)
            self.settings_dialog.steam_workshop_db_github_download_button.setEnabled(
                False
            )
            self.settings_dialog.steam_workshop_db_local_file.setEnabled(True)
            self.settings_dialog.steam_workshop_db_local_file_choose_button.setEnabled(
                True
            )
            self.settings_dialog.steam_workshop_db_local_file.setFocus()
            return

    @Slot()
    def _on_steam_workshop_db_local_file_choose_button_clicked(self) -> None:
        """
        Open a file dialog to select the Steam workshop database and handle the result.
        """
        steam_workshop_db_location = show_dialogue_file(
            mode="open",
            caption="Select Steam Workshop Database",
            _dir=str(self._last_file_dialog_path),
        )
        if not steam_workshop_db_location:
            return

        self.settings_dialog.steam_workshop_db_local_file.setText(
            steam_workshop_db_location
        )
        self._last_file_dialog_path = str(Path(steam_workshop_db_location).parent)

    @Slot()
    def _on_steamcmd_install_location_choose_button_clicked(self) -> None:
        """
        Open a file dialog to select the Steamcmd install location and handle the result.
        """
        steamcmd_install_location = show_dialogue_file(
            mode="open_dir",
            caption="Select Steamcmd Install Location",
            _dir=str(self._last_file_dialog_path),
        )
        if not steamcmd_install_location:
            return

        self.settings_dialog.steamcmd_install_location.setText(
            steamcmd_install_location
        )
        self._last_file_dialog_path = str(Path(steamcmd_install_location).parent)

    @Slot()
    def _on_steamcmd_clear_depot_cache_button_clicked(self) -> None:
        EventBus().do_clear_steamcmd_depot_cache.emit()

    @Slot()
    def _on_steamcmd_import_acf_button_clicked(self) -> None:
        """
        Handle the Steamcmd import ACF button click.
        """
        self.settings_dialog.global_ok_button.click()
        EventBus().do_import_acf.emit()

    @Slot()
    def _on_steamcmd_delete_acf_button_clicked(self) -> None:
        """
        Handle the Steamcmd delete ACF button click.
        """
        self.settings_dialog.global_ok_button.click()
        EventBus().do_delete_acf.emit()

    @Slot()
    def _on_steamcmd_install_button_clicked(self) -> None:
        """
        Handle the Steamcmd install button click.
        """
        self.settings_dialog.global_ok_button.click()
        EventBus().do_install_steamcmd.emit()

    @Slot()
    def _on_db_builder_download_all_mods_via_steamcmd_button_clicked(self) -> None:
        """
        Build the Steam Workshop database of all mods using steamcmd.
        """
        confirm_diag = BinaryChoiceDialog(
            "Confirm Build Database (SteamCMD)",
            "Are you sure you want to download all mods via SteamCMD and build the Steam Workshop database?",
            (
                "For most users this is not necessary as the GitHub SteamDB is adequate. Building the database may take a long time. "
                "This process downloads all mods (not just your own) from the Steam Workshop. "
                "This can be a large amount of data and take a long time. Are you sure you want to continue?"
            ),
            icon=QMessageBox.Icon.Warning,
        )

        if not confirm_diag.exec_is_positive():
            return

        self.settings_dialog.global_ok_button.click()
        EventBus().do_download_all_mods_via_steamcmd.emit()

    @Slot()
    def _on_db_builder_download_all_mods_via_steam_button_clicked(self) -> None:
        """
        Build the Steam Workshop database of all mods using steam.
        """
        confirm_diag = BinaryChoiceDialog(
            "Confirm Build Database (Steam Download)",
            "Are you sure you want to download all mods via Steam and build the Steam Workshop database?",
            (
                "For most users this is not necessary as the GitHub SteamDB is adequate. Building the database may take a long time. "
                "This process will subscribe to and download all mods from the Steam Workshop (not just your own). "
                "This can be a large amount of data and take a long time. Are you sure you want to continue?"
                ""
            ),
            icon=QMessageBox.Icon.Warning,
        )

        if not confirm_diag.exec_is_positive():
            return

        self.settings_dialog.global_ok_button.click()
        EventBus().do_download_all_mods_via_steam.emit()

    @Slot()
    def _on_db_builder_compare_databases_button_clicked(self) -> None:
        """
        Compare the Steam Workshop database.
        """
        self.settings_dialog.global_ok_button.click()
        EventBus().do_compare_steam_workshop_databases.emit()

    @Slot()
    def _on_db_builder_merge_databases_button_clicked(self) -> None:
        """
        Merge the Steam Workshop database.
        """
        self.settings_dialog.global_ok_button.click()
        EventBus().do_merge_steam_workshop_databases.emit()

    @Slot()
    def _on_db_builder_build_database_button_clicked(self) -> None:
        """
        Build the Steam Workshop database.
        """
        confirm_diag = BinaryChoiceDialog(
            title="Confirm Build Database",
            text="Are you sure you want to build the Steam Workshop database?",
            information=(
                "For most users this is not necessary as the GitHub SteamDB is adequate. Building the database may take a long time. "
                "Depending on your settings, it may also crawl through the entirety of the steam workshop via the webAPI. "
                "This can be a large amount of data and take a long time. Are you sure you want to continue?"
            ),
            icon=QMessageBox.Icon.Warning,
        )

        if not confirm_diag.exec_is_positive():
            return

        self.settings_dialog.global_ok_button.click()
        EventBus().do_build_steam_workshop_database.emit()

    @Slot(str)
    def _on_run_args_text_changed(self, text: str = "") -> None:
        run_args_list = text.split(",")
        self.settings.instances[self.settings.current_instance].run_args = run_args_list
        self.settings.save()

    @Slot()
    def _do_reset_settings_file(self) -> None:
        logger.info("Resetting settings file and retrying load")
        self.settings.save()
        self._load_settings()

    @Slot()
    def _on_theme_setup_dialog(self) -> None:
        """
        Set up the settings dialog with current settings.
        Reloading settings is required since ThemeController will resets to RimPy, if theme is invalid
        """
        self._load_settings()  # Required to detect theme change
        self.settings_dialog.enable_themes_checkbox.setChecked(
            self.settings.enable_themes
        )
        # Set the current theme in the combobox
        current_theme_name = self.settings.theme_name
        current_index = self.settings_dialog.themes_combobox.findText(
            current_theme_name
        )
        if current_index != -1:
            current_index = self.settings_dialog.themes_combobox.findText(
                current_theme_name
            )
            self.settings_dialog.themes_combobox.setCurrentIndex(current_index)
        else:
            logger.warning(
                f"Resetting to 'RimPy' theme due to missing or invalid theme: {current_theme_name}"
            )
            # If ThemeController fails resetting to RimPy
            self.settings.theme_name = "RimPy"
            self.settings.save()

    @Slot()
    def _on_theme_location_open_button_clicked(self) -> None:
        # Retrieve the selected theme name from the combobox
        selected_theme_name = self.settings_dialog.themes_combobox.currentText()
        logger.info(f"Opening theme location: {selected_theme_name}")
        # Initialize the ThemeController with the selected theme name
        theme_controller = ThemeController(selected_theme_name)
        # Retrieve the stylesheet path for the selected theme
        stylesheet_path = theme_controller.get_theme_stylesheet_path(
            selected_theme_name
        )
        if stylesheet_path is not None:
            platform_specific_open(stylesheet_path.parent)

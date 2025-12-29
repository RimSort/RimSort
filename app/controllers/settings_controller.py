import sys
from dataclasses import dataclass
from json import JSONDecodeError
from pathlib import Path

from loguru import logger
from PySide6.QtCore import QObject, Slot
from PySide6.QtWidgets import QApplication, QLineEdit, QMessageBox
from sqlalchemy import text

from app.controllers.instance_controller import InstanceController
from app.controllers.language_controller import LanguageController
from app.controllers.metadata_db_controller import AuxMetadataController
from app.controllers.theme_controller import ThemeController
from app.models.settings import Instance, Settings
from app.utils.acf_utils import validate_acf_file_exists
from app.utils.constants import DEFAULT_INSTANCE_NAME, SortMethod
from app.utils.event_bus import EventBus
from app.utils.generic import (
    find_steam_rimworld,
    get_path_up_to_string,
    platform_specific_open,
    validate_game_executable,
)
from app.utils.system_info import SystemInfo
from app.views.dialogue import (
    BinaryChoiceDialog,
    show_dialogue_file,
    show_settings_error,
    show_warning,
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

        self.theme_controller = ThemeController()

        self.language_controller = LanguageController()

        self.app_instance = QApplication.instance()

        self.change_mod_coloring_mode = False

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

        # Connect launch state radio buttons to update spinbox enabled/disabled state
        # Main Window
        self.settings_dialog.main_launch_maximized_radio.toggled.connect(
            self.settings_dialog.disable_main_custom_size_spinboxes
        )
        self.settings_dialog.main_launch_normal_radio.toggled.connect(
            self.settings_dialog.disable_main_custom_size_spinboxes
        )
        self.settings_dialog.main_launch_custom_radio.toggled.connect(
            self.settings_dialog.enable_main_custom_size_spinboxes
        )
        # Browser Window
        self.settings_dialog.browser_launch_maximized_radio.toggled.connect(
            self.settings_dialog.disable_browser_custom_size_spinboxes
        )
        self.settings_dialog.browser_launch_normal_radio.toggled.connect(
            self.settings_dialog.disable_browser_custom_size_spinboxes
        )
        self.settings_dialog.browser_launch_custom_radio.toggled.connect(
            self.settings_dialog.enable_browser_custom_size_spinboxes
        )

        # Settings Window (only custom option, spinboxes always enabled)
        self.settings_dialog.settings_custom_width_spinbox.setEnabled(True)
        self.settings_dialog.settings_custom_height_spinbox.setEnabled(True)

        # Advanced: wiring for save-comparison indicator toggle
        try:
            self.settings_dialog.show_save_comparison_indicators_checkbox.toggled.connect(
                self._on_toggle_show_save_comparison_indicators
            )
        except Exception:
            pass

        # Sorting: wiring for inactive mods sorting checkbox
        self.settings_dialog.enable_inactive_mods_sorting_checkbox.toggled.connect(
            self._on_enable_inactive_mods_sorting_checkbox_toggled
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

        # Instance folder location (custom override)
        try:
            self.settings_dialog.instance_folder_location_choose_button.clicked.connect(
                self._on_instance_folder_location_choose_button_clicked
            )
            self.settings_dialog.instance_folder_location_clear_button.clicked.connect(
                self._on_instance_folder_location_clear_button_clicked
            )
        except AttributeError:
            # Buttons may not exist if UI hasn't been updated yet
            pass

        self.settings_dialog.locations_clear_button.clicked.connect(
            self._on_locations_clear_button_clicked
        )

        self.settings_dialog.locations_autodetect_button.clicked.connect(
            self._on_locations_autodetect_button_clicked
        )

        # Game Launch tab
        self.settings_dialog.run_args.textChanged.connect(
            self._on_run_args_text_changed
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

        # Cross Version DB tab
        self.settings_dialog.no_version_warning_db_none_radio.clicked.connect(
            self._on_no_version_warning_db_radio_clicked
        )
        self.settings_dialog.no_version_warning_db_github_radio.clicked.connect(
            self._on_no_version_warning_db_radio_clicked
        )
        self.settings_dialog.no_version_warning_db_local_file_radio.clicked.connect(
            self._on_no_version_warning_db_radio_clicked
        )

        self.settings_dialog.no_version_warning_db_local_file_choose_button.clicked.connect(
            self._on_no_version_warning_db_local_file_choose_button_clicked
        )
        self.settings_dialog.no_version_warning_db_github_upload_button.clicked.connect(
            EventBus().do_upload_no_version_warning_db_to_github
        )
        self.settings_dialog.no_version_warning_db_github_download_button.clicked.connect(
            EventBus().do_download_no_version_warning_db_from_github
        )

        self.settings_dialog.use_this_instead_db_none_radio.clicked.connect(
            self._on_use_this_instead_db_radio_clicked
        )
        self.settings_dialog.use_this_instead_db_github_radio.clicked.connect(
            self._on_use_this_instead_db_radio_clicked
        )
        self.settings_dialog.use_this_instead_db_local_file_radio.clicked.connect(
            self._on_use_this_instead_db_radio_clicked
        )

        self.settings_dialog.use_this_instead_db_local_file_choose_button.clicked.connect(
            self._on_use_this_instead_db_local_file_choose_button_clicked
        )
        self.settings_dialog.use_this_instead_db_github_upload_button.clicked.connect(
            EventBus().do_upload_use_this_instead_db_to_github
        )
        self.settings_dialog.use_this_instead_db_github_download_button.clicked.connect(
            EventBus().do_download_use_this_instead_db_from_github
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

        # Other External Tools Tab
        self.settings_dialog.text_editor_location_choose_button.clicked.connect(
            self._on_text_editor_location_choose_button_clicked
        )

        # Theme tab
        self.settings_dialog.theme_location_open_button.clicked.connect(
            self._on_theme_location_open_button_clicked
        )

        # Advanced tab
        self.settings_dialog.color_background_instead_of_text_checkbox.stateChanged.connect(
            self._on_use_background_coloring_checkbox_changed
        )

        # Performance tab
        self._enable_aux_db_performance_mode()
        self.settings_dialog.aux_db_performance_mode.stateChanged.connect(
            self._enable_aux_db_performance_mode
        )

        EventBus().settings_have_changed.connect(self._handle_mod_coloring_mode_changed)

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
        except Exception as e:
            logger.error(f"Failed to load settings: {e}")
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
        # Apply custom size for settings window
        custom_width = self.settings.settings_window_custom_width
        custom_height = self.settings.settings_window_custom_height
        self.settings_dialog.resize(custom_width, custom_height)
        if tab_name:
            self.settings_dialog.switch_to_tab(tab_name)
        self.settings_dialog.show()

    @Slot(bool)
    def _on_toggle_show_save_comparison_indicators(self, checked: bool) -> None:
        # Update model immediately for live UI response
        self.settings.show_save_comparison_indicators = checked
        self.settings.save()

    @Slot(bool)
    def _on_enable_inactive_mods_sorting_checkbox_toggled(self, checked: bool) -> None:
        """
        Enable or disable the inactive mods sorting group box based on the checkbox state.
        """
        self.settings_dialog.inactive_mods_sorting_group_box.setEnabled(checked)

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
        instance_folder_override: str = "",
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
            instance_folder_override=instance_folder_override,
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
        self.settings_dialog.steam_client_integration_checkbox.setChecked(
            self.settings.instances[
                self.settings.current_instance
            ].steam_client_integration
        )
        # Enable/disable Steam mods location fields based on checkbox state
        checked = self.settings_dialog.steam_client_integration_checkbox.isChecked()
        self.settings_dialog.steam_mods_folder_location.setEnabled(checked)
        self.settings_dialog.steam_mods_folder_location_open_button.setEnabled(checked)
        self.settings_dialog.steam_mods_folder_location_choose_button.setEnabled(
            checked
        )
        self.settings_dialog.steam_mods_folder_location_clear_button.setEnabled(checked)

        # Instance folder location (custom override)
        # Only enable for Default instance
        is_default_instance = self.settings.current_instance == DEFAULT_INSTANCE_NAME
        self.settings_dialog.instance_folder_location.setText(
            self.settings.instances[
                self.settings.current_instance
            ].instance_folder_override
        )
        self.settings_dialog.instance_folder_location.setCursorPosition(0)
        self.settings_dialog.instance_folder_location.setEnabled(is_default_instance)
        self.settings_dialog.instance_folder_location_choose_button.setEnabled(
            is_default_instance
        )
        self.settings_dialog.instance_folder_location_clear_button.setEnabled(
            is_default_instance
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
        self.settings_dialog.aux_db_time_limit.setText(
            str(self.settings.aux_db_time_limit)
        )
        self.settings_dialog.aux_db_time_limit.setEnabled(
            self.settings.enable_aux_db_behavior_editing
        )

        # Cross Version DB Tab
        if self.settings.external_no_version_warning_metadata_source == "None":
            self.settings_dialog.no_version_warning_db_none_radio.setChecked(True)
            self.settings_dialog.no_version_warning_db_github_url.setEnabled(False)
            self.settings_dialog.no_version_warning_db_github_download_button.setEnabled(
                False
            )
            self.settings_dialog.no_version_warning_db_local_file.setEnabled(False)
            self.settings_dialog.no_version_warning_db_local_file_choose_button.setEnabled(
                False
            )
        elif (
            self.settings.external_no_version_warning_metadata_source
            == "Configured git repository"
        ):
            self.settings_dialog.no_version_warning_db_github_radio.setChecked(True)
            self.settings_dialog.no_version_warning_db_github_url.setEnabled(True)
            self.settings_dialog.no_version_warning_db_github_download_button.setEnabled(
                True
            )
            self.settings_dialog.no_version_warning_db_local_file.setEnabled(False)
            self.settings_dialog.no_version_warning_db_local_file_choose_button.setEnabled(
                False
            )
        elif (
            self.settings.external_no_version_warning_metadata_source
            == "Configured file path"
        ):
            self.settings_dialog.no_version_warning_db_local_file_radio.setChecked(True)
            self.settings_dialog.no_version_warning_db_github_url.setEnabled(False)
            self.settings_dialog.no_version_warning_db_github_download_button.setEnabled(
                False
            )
            self.settings_dialog.no_version_warning_db_local_file.setEnabled(True)
            self.settings_dialog.no_version_warning_db_local_file_choose_button.setEnabled(
                True
            )
        self.settings_dialog.no_version_warning_db_local_file.setText(
            self.settings.external_no_version_warning_file_path
        )
        self.settings_dialog.no_version_warning_db_local_file.setCursorPosition(0)
        self.settings_dialog.no_version_warning_db_github_url.setText(
            self.settings.external_no_version_warning_repo_path
        )
        self.settings_dialog.no_version_warning_db_github_url.setCursorPosition(0)

        if self.settings.external_use_this_instead_metadata_source == "None":
            self.settings_dialog.use_this_instead_db_none_radio.setChecked(True)
            self.settings_dialog.use_this_instead_db_github_url.setEnabled(False)
            self.settings_dialog.use_this_instead_db_github_download_button.setEnabled(
                False
            )
            self.settings_dialog.use_this_instead_db_local_file.setEnabled(False)
            self.settings_dialog.use_this_instead_db_local_file_choose_button.setEnabled(
                False
            )
        elif (
            self.settings.external_use_this_instead_metadata_source
            == "Configured git repository"
        ):
            self.settings_dialog.use_this_instead_db_github_radio.setChecked(True)
            self.settings_dialog.use_this_instead_db_github_url.setEnabled(True)
            self.settings_dialog.use_this_instead_db_github_download_button.setEnabled(
                True
            )
            self.settings_dialog.use_this_instead_db_local_file.setEnabled(False)
            self.settings_dialog.use_this_instead_db_local_file_choose_button.setEnabled(
                False
            )
        elif (
            self.settings.external_use_this_instead_metadata_source
            == "Configured file path"
        ):
            self.settings_dialog.use_this_instead_db_local_file_radio.setChecked(True)
            self.settings_dialog.use_this_instead_db_github_url.setEnabled(False)
            self.settings_dialog.use_this_instead_db_github_download_button.setEnabled(
                False
            )
            self.settings_dialog.use_this_instead_db_local_file.setEnabled(True)
            self.settings_dialog.use_this_instead_db_local_file_choose_button.setEnabled(
                True
            )
        self.settings_dialog.use_this_instead_db_local_file.setText(
            self.settings.external_use_this_instead_file_path
        )
        self.settings_dialog.use_this_instead_db_local_file.setCursorPosition(0)
        self.settings_dialog.use_this_instead_db_github_url.setText(
            self.settings.external_use_this_instead_repo_path
        )
        self.settings_dialog.use_this_instead_db_github_url.setCursorPosition(0)

        # Sorting tab
        if self.settings.sorting_algorithm == SortMethod.ALPHABETICAL:
            self.settings_dialog.sorting_alphabetical_radio.setChecked(True)
        elif self.settings.sorting_algorithm == SortMethod.TOPOLOGICAL:
            self.settings_dialog.sorting_topological_radio.setChecked(True)
        # Use dependencies for sorting checkbox
        if self.settings.use_moddependencies_as_loadTheseBefore:
            (
                self.settings_dialog.use_moddependencies_as_loadTheseBefore.setChecked(
                    True
                )
            )
        # Use alternativePackageIds as satisfying dependencies
        if self.settings.use_alternative_package_ids_as_satisfying_dependencies:
            self.settings_dialog.use_alternative_package_ids_as_satisfying_dependencies_checkbox.setChecked(
                True
            )
        # Set dependencies checkbox
        self.settings_dialog.check_deps_checkbox.setChecked(
            self.settings.check_dependencies_on_sort
        )
        # Prefer versioned About.xml tags over base tags
        if self.settings.prefer_versioned_about_tags:
            self.settings_dialog.prefer_versioned_about_tags_checkbox.setChecked(True)
        # Download missing mods checkbox
        self.settings_dialog.download_missing_mods_checkbox.setChecked(
            self.settings.try_download_missing_mods
        )
        # Duplicate mod notification checkbox
        self.settings_dialog.show_duplicate_mods_warning_checkbox.setChecked(
            self.settings.duplicate_mods_warning
        )
        # Mod type filter checkbox
        self.settings_dialog.mod_type_filter_checkbox.setChecked(
            self.settings.mod_type_filter
        )
        # Hide invalid mod filtering checkbox
        self.settings_dialog.hide_invalid_mods_when_filtering_checkbox.setChecked(
            self.settings.hide_invalid_mods_when_filtering
        )
        # Inactive mods sorting options checkbox
        self.settings_dialog.enable_inactive_mods_sorting_checkbox.setChecked(
            self.settings.inactive_mods_sorting
        )
        # Enable/disable the inactive mods sorting group box based on the checkbox state
        self.settings_dialog.inactive_mods_sorting_group_box.setEnabled(
            self.settings.inactive_mods_sorting
        )
        # Save inactive mods sort state
        self.settings_dialog.save_inactive_mods_sort_state_checkbox.setChecked(
            self.settings.save_inactive_mods_sort_state
        )

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
        self.settings_dialog.steamcmd_delete_before_update_checkbox.setChecked(
            self.settings.steamcmd_delete_before_update
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
            self.settings_dialog.todds_preset_optimized_radio.setChecked(True)
            self.settings_dialog.todds_custom_command_lineedit.setEnabled(False)
        elif self.settings.todds_preset == "custom":
            self.settings_dialog.todds_preset_custom_radio.setChecked(True)
            self.settings_dialog.todds_custom_command_lineedit.setEnabled(True)
        else:
            self.settings_dialog.todds_preset_optimized_radio.setChecked(True)
            self.settings_dialog.todds_custom_command_lineedit.setEnabled(False)
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
        self.settings_dialog.todds_custom_command_lineedit.setText(
            self.settings.todds_custom_command
        )
        self.settings_dialog.auto_delete_orphaned_dds_checkbox.setChecked(
            self.settings.auto_delete_orphaned_dds
        )

        # External Tools Tab
        self.settings_dialog.text_editor_location.setText(
            self.settings.text_editor_location
        )
        self.settings_dialog.text_editor_folder_arg.setText(
            self.settings.text_editor_folder_arg
        )
        self.settings_dialog.text_editor_file_arg.setText(
            self.settings.text_editor_file_arg
        )

        # Themes tab
        self.settings_dialog.enable_themes_checkbox.setChecked(
            self.settings.enable_themes
        )
        self.theme_controller.populate_themes_combobox(
            self.settings_dialog.themes_combobox
        )
        self.theme_controller.setup_theme_dialog(self.settings_dialog, self.settings)

        self.language_controller.populate_languages_combobox(
            self.settings_dialog.language_combobox
        )
        self.language_controller.setup_language_dialog(
            self.settings_dialog, self.settings
        )

        # Advanced tab values
        try:
            self.settings_dialog.show_save_comparison_indicators_checkbox.setChecked(
                self.settings.show_save_comparison_indicators
            )
        except Exception:
            pass

        # Launch State tab
        # Dialogue positioning
        self.settings_dialog.constrain_dialogues_to_main_window_monitor_checkbox.setChecked(
            self.settings.constrain_dialogues_to_main_window_monitor
        )

        # Windows launch state
        # Main Window
        main_window_launch_state = self.settings.main_window_launch_state
        if main_window_launch_state == "maximized":
            self.settings_dialog.main_launch_maximized_radio.setChecked(True)
            self.settings_dialog.disable_main_custom_size_spinboxes()
        elif main_window_launch_state == "normal":
            self.settings_dialog.main_launch_normal_radio.setChecked(True)
            self.settings_dialog.disable_main_custom_size_spinboxes()
        elif main_window_launch_state == "custom":
            self.settings_dialog.main_launch_custom_radio.setChecked(True)
            self.settings_dialog.enable_main_custom_size_spinboxes()
            # Validate main window custom width and height before setting
            min_size, max_size = 400, 1600
            width = self.settings.main_window_custom_width
            height = self.settings.main_window_custom_height
            if not (min_size <= width <= max_size):
                width = 900
            if not (min_size <= height <= max_size):
                height = 600
            self.settings_dialog.main_custom_width_spinbox.setValue(width)
            self.settings_dialog.main_custom_height_spinbox.setValue(height)
        else:
            self.settings_dialog.main_launch_maximized_radio.setChecked(True)
        # Browser Window
        browser_window_launch_state = self.settings.browser_window_launch_state
        if browser_window_launch_state == "maximized":
            self.settings_dialog.browser_launch_maximized_radio.setChecked(True)
            self.settings_dialog.disable_browser_custom_size_spinboxes()
        if browser_window_launch_state == "normal":
            self.settings_dialog.browser_launch_normal_radio.setChecked(True)
            self.settings_dialog.disable_browser_custom_size_spinboxes()
        elif browser_window_launch_state == "custom":
            self.settings_dialog.browser_launch_custom_radio.setChecked(True)
            self.settings_dialog.enable_browser_custom_size_spinboxes()
            # Validate custom width and height before setting
            min_size, max_size = 400, 1600
            width = self.settings.browser_window_custom_width
            height = self.settings.browser_window_custom_height
            if not (min_size <= width <= max_size):
                width = 900
            if not (min_size <= height <= max_size):
                height = 600
            self.settings_dialog.browser_custom_width_spinbox.setValue(width)
            self.settings_dialog.browser_custom_height_spinbox.setValue(height)
        else:
            self.settings_dialog.browser_launch_maximized_radio.setChecked(True)

        # Settings Window (only custom option)
        self.settings_dialog.settings_custom_width_spinbox.setValue(
            self.settings.settings_window_custom_width
        )
        self.settings_dialog.settings_custom_height_spinbox.setValue(
            self.settings.settings_window_custom_height
        )

        # Advanced tab
        self.settings_dialog.debug_logging_checkbox.setChecked(
            self.settings.debug_logging_enabled
        )
        self.settings_dialog.watchdog_checkbox.setChecked(self.settings.watchdog_toggle)
        self.settings_dialog.backup_saves_on_launch_checkbox.setChecked(
            self.settings.backup_saves_on_launch
        )
        self.settings_dialog.auto_backup_retention_count_spinbox.setValue(
            self.settings.auto_backup_retention_count
        )
        self.settings_dialog.auto_backup_compression_count_spinbox.setValue(
            self.settings.auto_backup_compression_count
        )
        self.settings_dialog.color_background_instead_of_text_checkbox.setChecked(
            self.settings.color_background_instead_of_text_toggle
        )
        # Clear button behavior
        self.settings_dialog.clear_moves_dlc_checkbox.setChecked(
            self.settings.clear_moves_dlc
        )
        self.settings_dialog.show_mod_updates_checkbox.setChecked(
            self.settings.steam_mods_update_check
        )
        self.settings_dialog.render_unity_rich_text_checkbox.setChecked(
            self.settings.render_unity_rich_text
        )
        self.settings_dialog.update_databases_on_startup_checkbox.setChecked(
            self.settings.update_databases_on_startup
        )
        self.settings_dialog.auto_launch_steam_checkbox.setChecked(
            self.settings.auto_launch_steam
        )

        self.settings_dialog.enable_backup_before_update_checkbox.setChecked(
            self.settings.enable_backup_before_update
        )
        self.settings_dialog.max_backups_spinbox.setValue(self.settings.max_backups)
        self.settings_dialog.enable_aux_db_behavior_editing.setChecked(
            self.settings.enable_aux_db_behavior_editing
        )
        self.settings_dialog.aux_db_performance_mode.setChecked(
            self.settings.enable_aux_db_performance_mode
        )
        self.settings_dialog.rentry_auth_code.setText(self.settings.rentry_auth_code)
        self.settings_dialog.rentry_auth_code.setCursorPosition(0)
        self.settings_dialog.github_username.setText(self.settings.github_username)
        self.settings_dialog.github_username.setCursorPosition(0)
        self.settings_dialog.github_token.setText(self.settings.github_token)
        self.settings_dialog.github_token.setCursorPosition(0)

        # Migrate old comma-separated format to new space-separated format if needed
        run_args_list = self._migrate_run_args(
            self.settings.instances[self.settings.current_instance].run_args
        )
        # Save migrated format back to settings
        if (
            run_args_list
            != self.settings.instances[self.settings.current_instance].run_args
        ):
            self.settings.instances[
                self.settings.current_instance
            ].run_args = run_args_list
            self.settings.save()
            logger.info(f"Saved migrated run_args: {run_args_list}")

        # Extract command string from single-element list
        run_args_str = run_args_list[0] if run_args_list else ""
        self.settings_dialog.run_args.setText(run_args_str)
        self.settings_dialog.run_args.setCursorPosition(0)

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
        self.settings.instances[
            self.settings.current_instance
        ].steam_client_integration = (
            self.settings_dialog.steam_client_integration_checkbox.isChecked()
        )

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

        # Cross Version Databases Tab
        if self.settings_dialog.no_version_warning_db_none_radio.isChecked():
            self.settings.external_no_version_warning_metadata_source = "None"
        elif self.settings_dialog.no_version_warning_db_local_file_radio.isChecked():
            self.settings.external_no_version_warning_metadata_source = (
                "Configured file path"
            )
        elif self.settings_dialog.no_version_warning_db_github_radio.isChecked():
            self.settings.external_no_version_warning_metadata_source = (
                "Configured git repository"
            )
        self.settings.external_no_version_warning_file_path = (
            self.settings_dialog.no_version_warning_db_local_file.text()
        )
        self.settings.external_no_version_warning_repo_path = (
            self.settings_dialog.no_version_warning_db_github_url.text()
        )

        if self.settings_dialog.use_this_instead_db_none_radio.isChecked():
            self.settings.external_use_this_instead_metadata_source = "None"
        elif self.settings_dialog.use_this_instead_db_local_file_radio.isChecked():
            self.settings.external_use_this_instead_metadata_source = (
                "Configured file path"
            )
        elif self.settings_dialog.use_this_instead_db_github_radio.isChecked():
            self.settings.external_use_this_instead_metadata_source = (
                "Configured git repository"
            )
        self.settings.external_use_this_instead_file_path = (
            self.settings_dialog.use_this_instead_db_local_file.text()
        )
        self.settings.external_use_this_instead_repo_path = (
            self.settings_dialog.use_this_instead_db_github_url.text()
        )
        try:
            self.settings.aux_db_time_limit = int(
                self.settings_dialog.aux_db_time_limit.text()
            )
        except Exception:
            logger.warning("Failed setting Aux DB time limit, falling back to -1")
            self.settings.aux_db_time_limit = -1

        # Sorting tab
        if self.settings_dialog.sorting_alphabetical_radio.isChecked():
            self.settings.sorting_algorithm = SortMethod.ALPHABETICAL
        elif self.settings_dialog.sorting_topological_radio.isChecked():
            self.settings.sorting_algorithm = SortMethod.TOPOLOGICAL

        # Use moddependencies as loadTheseBefore
        self.settings.use_moddependencies_as_loadTheseBefore = (
            self.settings_dialog.use_moddependencies_as_loadTheseBefore.isChecked()
        )
        # Use alternativePackageIds as satisfying dependencies
        self.settings.use_alternative_package_ids_as_satisfying_dependencies = self.settings_dialog.use_alternative_package_ids_as_satisfying_dependencies_checkbox.isChecked()
        # Set dependencies checkbox
        self.settings.check_dependencies_on_sort = (
            self.settings_dialog.check_deps_checkbox.isChecked()
        )
        # Prefer versioned About.xml tags over base tags
        self.settings.prefer_versioned_about_tags = (
            self.settings_dialog.prefer_versioned_about_tags_checkbox.isChecked()
        )
        # Download missing mods checkbox
        self.settings.try_download_missing_mods = (
            self.settings_dialog.download_missing_mods_checkbox.isChecked()
        )
        # Duplicate mod notification checkbox
        self.settings.duplicate_mods_warning = (
            self.settings_dialog.show_duplicate_mods_warning_checkbox.isChecked()
        )
        # Mod type filter checkbox
        self.settings.mod_type_filter = (
            self.settings_dialog.mod_type_filter_checkbox.isChecked()
        )
        # Hide invalid mod filtering checkbox
        self.settings.hide_invalid_mods_when_filtering = (
            self.settings_dialog.hide_invalid_mods_when_filtering_checkbox.isChecked()
        )
        # Inactive mods sorting options checkbox
        self.settings.inactive_mods_sorting = (
            self.settings_dialog.enable_inactive_mods_sorting_checkbox.isChecked()
        )
        # Save inactive mods sort state
        self.settings.save_inactive_mods_sort_state = (
            self.settings_dialog.save_inactive_mods_sort_state_checkbox.isChecked()
        )

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
        self.settings.steamcmd_delete_before_update = (
            self.settings_dialog.steamcmd_delete_before_update_checkbox.isChecked()
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
        if self.settings_dialog.todds_preset_optimized_radio.isChecked():
            self.settings.todds_preset = "optimized"
        if self.settings_dialog.todds_preset_custom_radio.isChecked():
            self.settings.todds_preset = "custom"
            self.settings.todds_custom_command = (
                self.settings_dialog.todds_custom_command_lineedit.text()
            )
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
        self.settings.auto_delete_orphaned_dds = (
            self.settings_dialog.auto_delete_orphaned_dds_checkbox.isChecked()
        )

        # Other External Tools Tab
        self.settings.text_editor_location = (
            self.settings_dialog.text_editor_location.text()
        )
        self.settings.text_editor_folder_arg = (
            self.settings_dialog.text_editor_folder_arg.text()
        )
        self.settings.text_editor_file_arg = (
            self.settings_dialog.text_editor_file_arg.text()
        )

        # Themes tab
        self.settings.enable_themes = (
            self.settings_dialog.enable_themes_checkbox.isChecked()
        )
        self.settings.theme_name = self.settings_dialog.themes_combobox.currentText()

        self.settings.font_family = (
            self.settings_dialog.font_family_combobox.currentText()
        )
        self.settings.font_size = self.settings_dialog.font_size_spinbox.value()
        self.settings.language = self.settings_dialog.language_combobox.currentData()

        # Launch State tab
        # Dialogue positioning
        self.settings.constrain_dialogues_to_main_window_monitor = self.settings_dialog.constrain_dialogues_to_main_window_monitor_checkbox.isChecked()

        # Windows launch state
        # Main Window
        if self.settings_dialog.main_launch_maximized_radio.isChecked():
            self.settings.main_window_launch_state = "maximized"
        elif self.settings_dialog.main_launch_normal_radio.isChecked():
            self.settings.main_window_launch_state = "normal"
        elif self.settings_dialog.main_launch_custom_radio.isChecked():
            self.settings.main_window_launch_state = "custom"
            self.settings.main_window_custom_width = (
                self.settings_dialog.main_custom_width_spinbox.value()
            )
            self.settings.main_window_custom_height = (
                self.settings_dialog.main_custom_height_spinbox.value()
            )
        else:
            self.settings.main_window_launch_state = "maximized"
        # Browser Window
        if self.settings_dialog.browser_launch_maximized_radio.isChecked():
            self.settings.browser_window_launch_state = "maximized"
        elif self.settings_dialog.browser_launch_normal_radio.isChecked():
            self.settings.browser_window_launch_state = "normal"
        elif self.settings_dialog.browser_launch_custom_radio.isChecked():
            self.settings.browser_window_launch_state = "custom"
            self.settings.browser_window_custom_width = (
                self.settings_dialog.browser_custom_width_spinbox.value()
            )
            self.settings.browser_window_custom_height = (
                self.settings_dialog.browser_custom_height_spinbox.value()
            )
        else:
            self.settings.browser_window_launch_state = "maximized"

        # Settings Window (only custom option)
        self.settings.settings_window_custom_width = (
            self.settings_dialog.settings_custom_width_spinbox.value()
        )
        self.settings.settings_window_custom_height = (
            self.settings_dialog.settings_custom_height_spinbox.value()
        )

        # Advanced tab
        self.settings.debug_logging_enabled = (
            self.settings_dialog.debug_logging_checkbox.isChecked()
        )
        self.settings.watchdog_toggle = (
            self.settings_dialog.watchdog_checkbox.isChecked()
        )
        self.settings.backup_saves_on_launch = (
            self.settings_dialog.backup_saves_on_launch_checkbox.isChecked()
        )
        self.settings.auto_backup_retention_count = (
            self.settings_dialog.auto_backup_retention_count_spinbox.value()
        )
        self.settings.auto_backup_compression_count = (
            self.settings_dialog.auto_backup_compression_count_spinbox.value()
        )
        self.settings.color_background_instead_of_text_toggle = (
            self.settings_dialog.color_background_instead_of_text_checkbox.isChecked()
        )
        # Clear button behavior
        self.settings.clear_moves_dlc = (
            self.settings_dialog.clear_moves_dlc_checkbox.isChecked()
        )
        self.settings.steam_mods_update_check = (
            self.settings_dialog.show_mod_updates_checkbox.isChecked()
        )
        self.settings.render_unity_rich_text = (
            self.settings_dialog.render_unity_rich_text_checkbox.isChecked()
        )
        self.settings.update_databases_on_startup = (
            self.settings_dialog.update_databases_on_startup_checkbox.isChecked()
        )
        self.settings.auto_launch_steam = (
            self.settings_dialog.auto_launch_steam_checkbox.isChecked()
        )

        self.settings.enable_backup_before_update = (
            self.settings_dialog.enable_backup_before_update_checkbox.isChecked()
        )
        self.settings.max_backups = self.settings_dialog.max_backups_spinbox.value()
        self.settings.enable_aux_db_behavior_editing = (
            self.settings_dialog.enable_aux_db_behavior_editing.isChecked()
        )
        self.settings.enable_aux_db_performance_mode = (
            self.settings_dialog.aux_db_performance_mode.isChecked()
        )
        self.settings.rentry_auth_code = self.settings_dialog.rentry_auth_code.text()
        self.settings.github_username = self.settings_dialog.github_username.text()
        self.settings.github_token = self.settings_dialog.github_token.text()
        # Migrate and extract command string from single-element list
        run_args_list = self._migrate_run_args(
            self.settings.instances[self.settings.current_instance].run_args
        )
        run_args_str = run_args_list[0] if run_args_list else ""
        self.settings_dialog.run_args.setText(run_args_str)

    @Slot()
    def _on_global_reset_to_defaults_button_clicked(self) -> None:
        """
        Reset the settings to their default values.
        """
        answer = BinaryChoiceDialog(
            title=self.tr("Reset to defaults"),
            text=self.tr(
                "Are you sure you want to reset all settings to their default values?"
            ),
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

    def _validate_game_location(self, game_location: str) -> bool:
        """
        Validate the game location and show a warning if invalid.

        :param game_location: Path to the game folder as a string.
        :return: True if valid, False otherwise.
        """
        if not validate_game_executable(game_location):
            QMessageBox.information(
                self.settings_dialog,
                self.tr("Invalid Game Location"),
                self.tr(
                    "The selected game folder does not contain a valid RimWorld executable. Please select a valid game location."
                ),
            )
            return False
        return True

    def _validate_config_folder_location(self, config_folder: str) -> bool:
        """
        Validate the config folder location and show a warning if invalid.

        :param config_folder: Path to the config folder as a string.
        :return: True if valid, False otherwise.
        """
        if not (Path(config_folder) / "ModsConfig.xml").exists():
            QMessageBox.warning(
                self.settings_dialog,
                self.tr("Invalid Config Folder"),
                self.tr(
                    "The selected config folder does not contain ModsConfig.xml. Please select a valid config folder."
                ),
            )
            return False
        return True

    def _check_steam_integration_validity(
        self, steam_client_integration: bool, steam_mods_location: str
    ) -> bool:
        """
        Check if Steam client integration and Steam mods location are valid.

        Validation rules:
        - If both disabled: valid
        - If steam_client_integration enabled but steam_mods_location empty: invalid
        - If steam_mods_location set: must have valid ACF file
        - If steam_mods_location set but ACF missing: invalid

        :param steam_client_integration: Whether Steam client integration is enabled.
        :param steam_mods_location: Path to the Steam mods folder.
        :return: True if valid configuration, False if invalid.
        """
        # If integration disabled, no location validation needed
        if not steam_client_integration and not steam_mods_location:
            return True

        # If integration enabled but no location, invalid
        if steam_client_integration and not steam_mods_location:
            return False

        # If location set (with or without integration), check ACF file
        if steam_mods_location:
            return validate_acf_file_exists(steam_mods_location)

        return True

    def _validate_steam_integration(self) -> bool:
        """
        Validate Steam client integration and Steam mods location configuration.
        Shows appropriate warnings if validation fails and prevents saving.

        :return: True if valid configuration, False if invalid.
        """
        steam_client_integration = (
            self.settings_dialog.steam_client_integration_checkbox.isChecked()
        )
        steam_mods_location = (
            self.settings_dialog.steam_mods_folder_location.text().strip()
        )

        if not steam_client_integration:
            QMessageBox.warning(
                self.settings_dialog,
                self.tr("Steam Client Integration Disabled"),
                self.tr(
                    "Steam client integration is disabled. Steam mods location will be cleared."
                ),
            )
            # If integration disabled, clear the steam mods location
            self.settings_dialog.steam_mods_folder_location.setText("")

        is_valid = self._check_steam_integration_validity(
            steam_client_integration, steam_mods_location
        )

        if not is_valid:
            # Disable integration checkbox and clear the mods location
            self.settings_dialog.steam_client_integration_checkbox.setChecked(False)
            self.settings_dialog.steam_mods_folder_location.setText("")

            # Determine which validation failed for appropriate error message
            if steam_client_integration and not steam_mods_location:
                QMessageBox.warning(
                    self.settings_dialog,
                    self.tr("Steam Mods Location Required"),
                    self.tr(
                        "Steam client integration requires a Steam mods location to be configured. "
                        "Steam client integration and Steam mods location have been disabled."
                    ),
                )
            elif steam_mods_location and not validate_acf_file_exists(
                steam_mods_location
            ):
                QMessageBox.warning(
                    self.settings_dialog,
                    self.tr("Steam Workshop File Not Found"),
                    self.tr(
                        "The Steam Workshop file 'appworkshop_294100.acf' was not found at the expected location. "
                        "Steam client integration and Steam mods location have been disabled. "
                        "Please ensure Steam is properly installed and has downloaded RimWorld Workshop data."
                    ),
                )
                # Clear location since ACF is missing
                self.settings_dialog.steam_mods_folder_location.setText("")

        return is_valid

    @Slot()
    def _on_global_ok_button_clicked(self) -> None:
        """
        Close the settings dialog, update the model from the view, and save the settings.
        """
        # Validate game folder if set
        game_folder_text = self.settings_dialog.game_location.text().strip()
        if game_folder_text and not self._validate_game_location(game_folder_text):
            return

        # Validate config folder if set
        config_folder_text = self.settings_dialog.config_folder_location.text().strip()
        if config_folder_text and not self._validate_config_folder_location(
            config_folder_text
        ):
            return

        # Validate Steam integration if enabled
        if self.settings_dialog.steam_client_integration_checkbox.isChecked():
            if not self._validate_steam_integration():
                return

        self.settings_dialog.close()
        self._update_model_from_view()
        self.settings.save()
        self.theme_controller.set_font(
            self.settings.font_family,
            self.settings.font_size,
        )
        self.theme_controller.apply_selected_theme(
            self.settings.enable_themes,
            self.settings.theme_name,
        )
        # Do a full refresh after updating the settings
        EventBus().do_refresh_mods_lists.emit()

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
        # Validate the selected game location immediately
        if not self._validate_game_location(str(game_location)):
            return
        self.settings_dialog.game_location.setText(str(game_location))
        self.settings_dialog.local_mods_folder_location.setText(
            str(game_location / "Mods")
        )
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
        self.settings_dialog.local_mods_folder_location.setText("")

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

        if not self._validate_config_folder_location(config_folder_location):
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
    def _on_local_mods_folder_location_text_changed(self) -> None:
        self.settings_dialog.local_mods_folder_location_open_button.setEnabled(
            self.settings_dialog.local_mods_folder_location.text() != ""
        )

    @Slot()
    def _on_local_mods_folder_location_open_button_clicked(self) -> None:
        platform_specific_open(self.settings_dialog.local_mods_folder_location.text())

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
                title=self.tr("Clear all locations"),
                text=self.tr("Are you sure you want to clear all locations?"),
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
            from app.utils.win_find_steam import find_steam_folder

            steam_folder, found = find_steam_folder()

            if not found:
                logger.error(
                    "[win32] Could not find Steam folder. Using fallback assumptions"
                )
                steam_folder = "C:/Program Files (x86)/Steam"

            game_folder: str | Path = find_steam_rimworld(steam_folder)

            # Fallback game folder
            if game_folder == "":
                game_folder = f"{steam_folder}/steamapps/common/RimWorld"
            game_folder = Path(game_folder)

            config_folder = Path(
                f"{user_home}/AppData/LocalLow/Ludeon Studios/RimWorld by Ludeon Studios/Config"
            )

            steam_mods_folder = get_path_up_to_string(
                game_folder, "common", exclude=True
            )
            if steam_mods_folder == "":
                # Fallback steam mods path
                steam_mods_folder = Path(
                    f"{steam_folder}/steamapps/workshop/content/294100"
                )
            else:
                steam_mods_folder = Path(steam_mods_folder) / "workshop/content/294100"

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
            if isinstance(self.app_instance, QApplication):
                focused_widget = self.app_instance.focusWidget()
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
            if isinstance(self.app_instance, QApplication):
                focused_widget = self.app_instance.focusWidget()
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

    @Slot(bool)
    def _on_no_version_warning_db_radio_clicked(self, checked: bool = True) -> None:
        """
        This function handles the "No Version Warning" db radio buttons. Clicking one button
        enables the associated widgets and disables the other widgets.
        """
        if (
            self.sender() == self.settings_dialog.no_version_warning_db_none_radio
            and checked
        ):
            self.settings_dialog.no_version_warning_db_github_url.setEnabled(False)
            self.settings_dialog.no_version_warning_db_github_download_button.setEnabled(
                False
            )
            self.settings_dialog.no_version_warning_db_local_file.setEnabled(False)
            self.settings_dialog.no_version_warning_db_local_file_choose_button.setEnabled(
                False
            )
            app_instance = QApplication.instance()
            if isinstance(app_instance, QApplication):
                focused_widget = app_instance.focusWidget()
                if focused_widget is not None:
                    focused_widget.clearFocus()
            return

        if (
            self.sender() == self.settings_dialog.no_version_warning_db_github_radio
            and checked
        ):
            self.settings_dialog.no_version_warning_db_github_url.setEnabled(True)
            self.settings_dialog.no_version_warning_db_github_download_button.setEnabled(
                True
            )
            self.settings_dialog.no_version_warning_db_local_file.setEnabled(False)
            self.settings_dialog.no_version_warning_db_local_file_choose_button.setEnabled(
                False
            )
            self.settings_dialog.no_version_warning_db_github_url.setFocus()
            return

        if (
            self.sender() == self.settings_dialog.no_version_warning_db_local_file_radio
            and checked
        ):
            self.settings_dialog.no_version_warning_db_github_url.setEnabled(False)
            self.settings_dialog.no_version_warning_db_github_download_button.setEnabled(
                False
            )
            self.settings_dialog.no_version_warning_db_local_file.setEnabled(True)
            self.settings_dialog.no_version_warning_db_local_file_choose_button.setEnabled(
                True
            )
            self.settings_dialog.no_version_warning_db_local_file.setFocus()
            return

    @Slot()
    def _on_no_version_warning_db_local_file_choose_button_clicked(self) -> None:
        """
        Open a file dialog to select the "No Version Warning" xml file and handle the result.
        """
        no_version_warning_db_location = show_dialogue_file(
            mode="open",
            caption="Select No Version Warning XML File",
            _dir=str(self._last_file_dialog_path),
        )
        if not no_version_warning_db_location:
            return

        self.settings_dialog.no_version_warning_db_local_file.setText(
            no_version_warning_db_location
        )
        self._last_file_dialog_path = str(Path(no_version_warning_db_location).parent)

    @Slot(bool)
    def _on_use_this_instead_db_radio_clicked(self, checked: bool = True) -> None:
        """
        This function handles the "Use This Instead" db radio buttons. Clicking one button
        enables the associated widgets and disables the other widgets.
        """
        if (
            self.sender() == self.settings_dialog.use_this_instead_db_none_radio
            and checked
        ):
            self.settings_dialog.use_this_instead_db_github_url.setEnabled(False)
            self.settings_dialog.use_this_instead_db_github_download_button.setEnabled(
                False
            )
            self.settings_dialog.use_this_instead_db_local_file.setEnabled(False)
            self.settings_dialog.use_this_instead_db_local_file_choose_button.setEnabled(
                False
            )
            app_instance = QApplication.instance()
            if isinstance(app_instance, QApplication):
                focused_widget = app_instance.focusWidget()
                if focused_widget is not None:
                    focused_widget.clearFocus()
            return

        if (
            self.sender() == self.settings_dialog.use_this_instead_db_github_radio
            and checked
        ):
            self.settings_dialog.use_this_instead_db_github_url.setEnabled(True)
            self.settings_dialog.use_this_instead_db_github_download_button.setEnabled(
                True
            )
            self.settings_dialog.use_this_instead_db_local_file.setEnabled(False)
            self.settings_dialog.use_this_instead_db_local_file_choose_button.setEnabled(
                False
            )
            self.settings_dialog.use_this_instead_db_github_url.setFocus()
            return

        if (
            self.sender() == self.settings_dialog.use_this_instead_db_local_file_radio
            and checked
        ):
            self.settings_dialog.use_this_instead_db_github_url.setEnabled(False)
            self.settings_dialog.use_this_instead_db_github_download_button.setEnabled(
                False
            )
            self.settings_dialog.use_this_instead_db_local_file.setEnabled(True)
            self.settings_dialog.use_this_instead_db_local_file_choose_button.setEnabled(
                True
            )
            self.settings_dialog.use_this_instead_db_local_file.setFocus()
            return

    @Slot()
    def _on_use_this_instead_db_local_file_choose_button_clicked(self) -> None:
        """
        Open a file dialog to select the "Use This Instead" replacements file and handle the result.
        """
        use_this_instead_db_location = show_dialogue_file(
            mode="open",
            caption='Select "Use This Instead" Replacements File',
            _dir=str(self._last_file_dialog_path),
            _filter="JSON Files (*.json *.json.gz)",
        )
        if not use_this_instead_db_location:
            return

        self.settings_dialog.use_this_instead_db_local_file.setText(
            use_this_instead_db_location
        )
        self._last_file_dialog_path = str(Path(use_this_instead_db_location).parent)

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
    def _on_text_editor_location_choose_button_clicked(self) -> None:
        """
        Open a file dialog to select the Steamcmd install location and handle the result.
        """
        text_editor_location = show_dialogue_file(
            mode="open",
            caption="Select Text Editor Command",
            _dir=str(self._last_file_dialog_path),
        )
        if not text_editor_location:
            return

        self.settings_dialog.text_editor_location.setText(text_editor_location)
        self._last_file_dialog_path = str(Path(text_editor_location).parent)

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
            title=self.tr("Confirm Build Database"),
            text=self.tr("Are you sure you want to build the Steam Workshop database?"),
            information=(
                self.tr(
                    "For most users this is not necessary as the GitHub SteamDB is adequate. Building the database may take a long time. "
                    "Depending on your settings, it may also crawl through the entirety of the steam workshop via the webAPI. "
                    "This can be a large amount of data and take a long time. Are you sure you want to continue?"
                )
            ),
            icon=QMessageBox.Icon.Warning,
        )

        if not confirm_diag.exec_is_positive():
            return

        self.settings_dialog.global_ok_button.click()
        EventBus().do_build_steam_workshop_database.emit()

    def _migrate_run_args(self, run_args: list[str]) -> list[str]:
        """
        Migrate old comma-separated run_args format to new space-separated format.

        Old format examples:
        - ["-logfile", "/tmp/log", "-popupwindow"] (multiple elements)
        - ["-logfile,/tmp/log,-popupwindow"] (single comma-separated string)

        New format:
        - ["-logfile /tmp/log -popupwindow"]

        The parser will treat this as game args (since no %command% placeholder).
        Users can later add %command%, env vars, or wrappers if desired.

        :param run_args: Current run_args list
        :return: Migrated run_args list in new format
        """
        if not run_args:
            return []

        # Single element - check if it needs migration
        if len(run_args) == 1:
            arg = run_args[0]
            # If it contains commas, migrate from comma-separated to space-separated
            if "," in arg:
                logger.info(f"Migrating comma-separated run_args: {run_args}")
                parts = [part.strip() for part in arg.split(",") if part.strip()]
                migrated = " ".join(parts)
                return [migrated]
            # Already in new format (single string, no commas)
            return run_args

        # Multiple elements - join with spaces
        logger.info(f"Migrating multi-element run_args: {run_args}")
        migrated = " ".join(run_args)
        return [migrated]

    @Slot(str)
    def _on_run_args_text_changed(self, text: str = "") -> None:
        # Store full command string as single-element list for %command% syntax
        run_args_list = [text] if text.strip() else []
        self.settings.instances[self.settings.current_instance].run_args = run_args_list
        self.settings.save()

    @Slot()
    def _on_instance_folder_location_choose_button_clicked(self) -> None:
        """Open folder dialog to select custom instance folder location."""
        # Only allow changing instance folder location for Default instance
        if self.settings.current_instance != DEFAULT_INSTANCE_NAME:
            show_warning(
                title="Cannot Modify Instance Folder",
                text="Only the Default instance can have a custom folder location.",
                information="Custom instance folder location is managed by the Default instance.",
            )
            return

        instance_folder_location = show_dialogue_file(
            mode="open_dir",
            caption="Select Instance Folder Location",
            _dir=str(self._last_file_dialog_path),
        )
        if not instance_folder_location:
            return

        # Validate the path before setting it

        test_controller = InstanceController(
            self.settings.instances[self.settings.current_instance]
        )
        test_controller.instance.instance_folder_override = instance_folder_location
        is_valid, error_msg = test_controller.validate_instance_folder_override()

        if not is_valid:
            show_warning(
                title="Invalid Instance Folder",
                text="Cannot use selected folder as instance location.",
                information=error_msg,
            )
            return

        # Update the instance and UI
        self.settings.instances[
            self.settings.current_instance
        ].instance_folder_override = instance_folder_location
        self.settings_dialog.instance_folder_location.setText(instance_folder_location)
        self._last_file_dialog_path = str(Path(instance_folder_location).parent)
        self.settings.save()

    @Slot()
    def _on_instance_folder_location_clear_button_clicked(self) -> None:
        """Clear custom instance folder and use default location."""
        # Only allow changing instance folder location for Default instance
        if self.settings.current_instance != DEFAULT_INSTANCE_NAME:
            show_warning(
                title="Cannot Modify Instance Folder",
                text="Only the Default instance can have a custom folder location.",
                information="Custom instance folder location is managed by the Default instance.",
            )
            return

        self.settings.instances[
            self.settings.current_instance
        ].instance_folder_override = ""
        self.settings_dialog.instance_folder_location.setText("")
        self.settings.save()

    @Slot()
    def _do_reset_settings_file(self) -> None:
        logger.info("Resetting settings file and retrying load")
        self.settings.save()
        self._load_settings()

    @Slot()
    def _on_theme_location_open_button_clicked(self) -> None:
        """
        Open the location of the selected theme.
        """
        selected_theme_name = self.settings_dialog.themes_combobox.currentText()
        logger.info(f"Opening theme location: {selected_theme_name}")
        stylesheet_path = self.theme_controller.get_theme_stylesheet_path(
            selected_theme_name
        )

        if stylesheet_path and stylesheet_path.exists():
            platform_specific_open(stylesheet_path.parent)
        else:
            logger.warning(
                f"Failed to open theme location: {stylesheet_path} not found or does not exist"
            )

    @Slot()
    def _on_use_background_coloring_checkbox_changed(self) -> None:
        self.change_mod_coloring_mode = not self.change_mod_coloring_mode

    @Slot()
    def _enable_aux_db_performance_mode(self) -> None:
        """
        Enable/disable the auxiliary metadata database performance mode based on the checkbox state.
        """
        aux_metadata_controller = AuxMetadataController.get_or_create_cached_instance(
            self.settings.aux_db_path
        )
        with aux_metadata_controller.Session() as session:
            if self.settings_dialog.aux_db_performance_mode.isChecked():
                session.execute(text("PRAGMA synchronous = OFF"))
                session.execute(text("PRAGMA journal_mode = MEMORY"))
            else:
                session.execute(text("PRAGMA synchronous = FULL"))
                session.execute(text("PRAGMA journal_mode = DELETE"))

            session.commit()
            session.close()

    @Slot()
    def _handle_mod_coloring_mode_changed(self) -> None:
        """
        If user changes coloring from text to background or vice versa,
        update all mod items to use that coloring mode.
        """
        if self.change_mod_coloring_mode:
            self.change_mod_coloring_mode = False
            EventBus().do_change_mod_coloring_mode.emit()

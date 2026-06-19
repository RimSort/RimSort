import sys
from dataclasses import dataclass
from json import JSONDecodeError
from pathlib import Path

from loguru import logger
from PySide6.QtCore import QObject, Slot
from PySide6.QtWidgets import QApplication, QLineEdit, QMessageBox

from app.controllers.instance_controller import InstanceController
from app.controllers.language_controller import LanguageController
from app.controllers.settings_tabs import (
    AdvancedTabController,
    AppearanceTabController,
    BaseTabController,
    DatabaseBuilderTabController,
    DatabasesTabController,
    ExternalToolsTabController,
    GameLaunchTabController,
    InternalToolsTabController,
    LocationsTabController,
    SortingTabController,
)
from app.controllers.theme_controller import ThemeController
from app.models.settings import Instance, Settings
from app.utils.acf_utils import validate_acf_file_exists
from app.utils.app_info import AppInfo
from app.utils.constants import DEFAULT_INSTANCE_NAME
from app.utils.event_bus import EventBus
from app.utils.generic import (
    extract_git_dir_name,
    find_steam_rimworld,
    get_path_up_to_string,
    validate_game_executable,
)
from app.utils.http_downloader import (
    DatabaseDownloadTask,
    DownloadResult,
    HttpDownloadWorker,
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

        self._http_download_worker: HttpDownloadWorker | None = None

        self._detected_steam_root: Path | None = None

        # Initialize per-tab controllers (registry pattern)
        self._tab_controllers: list[BaseTabController] = []

        self._sorting_tab = SortingTabController(self.settings, self.settings_dialog)
        self._tab_controllers.append(self._sorting_tab)

        self._databases_tab = DatabasesTabController(
            self.settings,
            self.settings_dialog,
            self._do_http_download_from_dialog,
        )
        self._tab_controllers.append(self._databases_tab)

        self._locations_tab = LocationsTabController(
            self.settings,
            self.settings_dialog,
            validate_game_location=self._validate_game_location,
            validate_config_folder_location=self._validate_config_folder_location,
            validate_local_mods_location=self._validate_local_mods_location,
            on_path_selected=self._on_locations_path_selected,
            on_autodetect=self._on_locations_autodetect_button_clicked,
            on_instance_folder_choose=self._on_instance_folder_location_choose_button_clicked,
            on_instance_folder_clear=self._on_instance_folder_location_clear_button_clicked,
        )
        self._tab_controllers.append(self._locations_tab)

        self._appearance_tab = AppearanceTabController(
            self.settings, self.settings_dialog
        )
        self._tab_controllers.append(self._appearance_tab)

        self._game_launch_tab = GameLaunchTabController(
            self.settings, self.settings_dialog
        )
        self._tab_controllers.append(self._game_launch_tab)

        self._internal_tools_tab = InternalToolsTabController(
            self.settings,
            self.settings_dialog,
            last_file_dialog_path=str(self._last_file_dialog_path),
            on_path_selected=self._on_locations_path_selected,
        )
        self._tab_controllers.append(self._internal_tools_tab)

        self._external_tools_tab = ExternalToolsTabController(
            self.settings,
            self.settings_dialog,
            last_file_dialog_path=str(self._last_file_dialog_path),
            on_path_selected=self._on_locations_path_selected,
        )
        self._tab_controllers.append(self._external_tools_tab)

        self._db_builder_tab = DatabaseBuilderTabController(
            self.settings,
            self.settings_dialog,
        )
        self._tab_controllers.append(self._db_builder_tab)

        self._advanced_tab = AdvancedTabController(self.settings, self.settings_dialog)
        self._tab_controllers.append(self._advanced_tab)

        for tc in self._tab_controllers:
            tc.connect_signals()

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
        self._locations_tab.update_view_from_model()

        # Game Launch tab
        self._game_launch_tab.update_view_from_model()

        # Databases tab
        self._databases_tab.update_view_from_model()

        # Sorting tab
        self._sorting_tab.update_view_from_model()

        # Database Builder tab
        self._db_builder_tab.update_view_from_model()

        # Internal Tools tab
        self._internal_tools_tab.update_view_from_model()

        # External Tools tab
        self._external_tools_tab.update_view_from_model()

        # Appearance tab
        self._appearance_tab.update_view_from_model()

        # Advanced tab
        self._advanced_tab.update_view_from_model()

    def _update_model_from_view(self) -> None:
        """
        Update the settings model from the view.
        """

        # Locations tab
        self._locations_tab.update_model_from_view()

        # Game Launch tab
        self._game_launch_tab.update_model_from_view()

        # Databases tab
        self._databases_tab.update_model_from_view()

        # Sorting tab
        self._sorting_tab.update_model_from_view()

        # Database Builder tab
        self._db_builder_tab.update_model_from_view()

        # Internal Tools tab
        self._internal_tools_tab.update_model_from_view()

        # External Tools tab
        self._external_tools_tab.update_model_from_view()

        # Appearance tab
        self._appearance_tab.update_model_from_view()

        # Advanced tab
        self._advanced_tab.update_model_from_view()

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

    def _on_locations_path_selected(self, path: str) -> None:
        """Update the last selected path for file dialog default directories."""
        self._last_file_dialog_path = path

    def _validate_game_location(self, game_folder: str) -> bool:
        """
        Validate the game location and show a warning if invalid.

        :param game_folder: Path to the game folder as a string.
        :return: True if valid, False otherwise.
        """
        if not validate_game_executable(game_folder):
            QMessageBox.information(
                self.settings_dialog,
                self.tr("Invalid Game Location"),
                self.tr(
                    "The selected game folder does not contain a valid RimWorld executable.<br><br>"
                    "Please select a valid game location.<br><br>"
                    "Windows: RimWorldWin64.exe or RimWorldWin.exe<br><br>"
                    "Mac: RimworldMac.app<br><br>"
                    "Linux: RimWorldLinux<br><br>"
                    "RimWorldWin64.exe or RimWorldWin.exe if you using windows version of the game on Linux"
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
                    "The selected config folder does not contain ModsConfig.xml.<br><br>"
                    "Please select a valid config folder.<br><br>"
                    "If you have not launched the game before,<br><br>"
                    "Please launch the game at least once to generate the necessary config files."
                ),
            )
            return False
        return True

    def _validate_local_mods_location(self, local_folder: str) -> bool:
        """
        Validate the local mods folder location and show a warning if invalid.
        The local mods folder is valid if it is a directory.

        :param local_folder: Path to the local mods folder as a string.
        :return: True if valid, False otherwise.
        """
        game_folder = self.settings.instances[
            self.settings.current_instance
        ].game_folder
        if not (Path(local_folder).is_dir()) or local_folder != str(
            Path(game_folder) / "Mods"
        ):
            QMessageBox.warning(
                self.settings_dialog,
                self.tr("Invalid Local Mods Folder"),
                self.tr(
                    "The selected local mods folder location is not a valid directory.<br><br>"
                    "Please select a valid folder for local mods.<br><br>"
                    "The local mods folder should be a 'Mods' subfolder within the game folder."
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

    def _disable_steam_integration_ui(self) -> None:
        """
        Clear all Steam integration dependent UI settings.
        Disables Steam client integration, clears workshop folder, and disables Steam protocol launch.
        """
        self.settings_dialog.steam_client_integration_checkbox.setChecked(False)
        self.settings_dialog.steam_mods_folder_location.setText("")
        self.settings_dialog.launch_via_steam_protocol_checkbox.setChecked(False)

    def _validate_steam_integration(self) -> bool:
        """
        Validate Steam client integration and Steam mods location configuration.
        Shows appropriate warnings if validation fails and prevents saving.

        Ensures that Steam protocol launch is only enabled when Steam integration is enabled.

        :return: True if valid configuration, False if invalid.
        """
        steam_client_integration = (
            self.settings_dialog.steam_client_integration_checkbox.isChecked()
        )
        steam_mods_location = (
            self.settings_dialog.steam_mods_folder_location.text().strip()
        )

        # Handle user explicitly disabling Steam integration
        if not steam_client_integration:
            QMessageBox.warning(
                self.settings_dialog,
                self.tr("Steam Client Integration Disabled"),
                self.tr(
                    "Steam client integration is disabled. Steam mods location and Steam protocol launch will be cleared."
                ),
            )
            # Clear dependent settings when integration is disabled
            self.settings_dialog.steam_mods_folder_location.setText("")
            self.settings_dialog.launch_via_steam_protocol_checkbox.setChecked(False)

        # Validate Steam integration configuration
        is_valid = self._check_steam_integration_validity(
            steam_client_integration, steam_mods_location
        )

        if not is_valid:
            # Disable all Steam integration settings if validation fails
            self._disable_steam_integration_ui()

            # Determine which validation failed for appropriate error message
            if steam_client_integration and not steam_mods_location:
                QMessageBox.warning(
                    self.settings_dialog,
                    self.tr("Steam Mods Location Required"),
                    self.tr(
                        "Steam client integration requires a Steam mods location to be configured. "
                        "Steam client integration, Steam mods location, and Steam protocol launch have been disabled."
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
                        "Steam client integration, Steam mods location, and Steam protocol launch have been disabled. "
                        "Please ensure Steam is properly installed and has downloaded RimWorld Workshop data."
                    ),
                )

        return is_valid

    @Slot()
    def _on_global_ok_button_clicked(self) -> None:
        """
        Close the settings dialog, update the model from the view, and save the settings.
        """
        # Update the model from the view before saving to ensure validation checks have the latest data
        self._update_model_from_view()

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

        # Validate local mods folder if set
        local_mods_folder_text = (
            self.settings_dialog.local_mods_folder_location.text().strip()
        )
        if local_mods_folder_text and not self._validate_local_mods_location(
            local_mods_folder_text
        ):
            return

        # Validate Steam integration if enabled
        if self.settings_dialog.steam_client_integration_checkbox.isChecked():
            if not self._validate_steam_integration():
                return

        # If all validations pass, save settings and close dialog
        self.settings.save()
        self.settings_dialog.close()
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

    @staticmethod
    def _find_steam_root(candidates: list[Path]) -> Path | None:
        """
        Find the Steam installation root from a prioritized list of candidate paths.

        A candidate is valid if it exists as a directory and contains either
        a ``steamapps/`` directory or ``config/libraryfolders.vdf``.

        :param candidates: Ordered list of candidate Steam root paths
        :return: First valid Steam root, or None if no candidate matches
        """
        for candidate in candidates:
            if not candidate.is_dir():
                logger.debug(f"Steam root candidate does not exist: {candidate}")
                continue
            has_steamapps = (candidate / "steamapps").is_dir()
            has_vdf = (candidate / "config" / "libraryfolders.vdf").is_file()
            if has_steamapps or has_vdf:
                logger.info(f"Found Steam root: {candidate}")
                return candidate
            logger.debug(
                f"Steam root candidate exists but has no steamapps/ or config/libraryfolders.vdf: {candidate}"
            )
        logger.warning("No valid Steam root found from any candidate path")
        return None

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
            os_paths = self.__get_linux_paths()
            logger.info(f"Running on Linux with the following paths: {os_paths}")
            if (
                self._detected_steam_root is not None
                and "snap" in self._detected_steam_root.parts
            ):
                show_warning(
                    title="Unsupported Steam installation",
                    text="Snap-based Steam installation detected.",
                    information=(
                        "Steam installed via Snap is not officially supported and may cause issues. "
                        "We recommend installing Steam via your distribution's native package manager "
                        "or Flatpak instead.<br><br>"
                        "Autodetection will continue, but some paths may not work correctly."
                    ),
                )
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
        Get paths for macOS. Uses VDF parsing to locate RimWorld in non-default
        Steam library folders, with hardcoded fallback.

        :return: (game_folder, config_folder, steam_mods_folder)
        """
        user_home = Path.home()
        candidates = [
            user_home / "Library" / "Application Support" / "Steam",
        ]

        steam_root = self._find_steam_root(candidates)
        self._detected_steam_root = steam_root

        if steam_root:
            game_folder_str = find_steam_rimworld(steam_root)
            if game_folder_str:
                game_folder = self._find_mac_app_bundle(Path(game_folder_str))
                logger.debug(f"VDF parsing found RimWorld at: {game_folder}")
            else:
                fallback_game_folder = steam_root / "steamapps" / "common" / "RimWorld"
                game_folder = self._find_mac_app_bundle(fallback_game_folder)
                logger.debug(
                    f"VDF parsing did not find RimWorld, using fallback_game_folder: {game_folder}"
                )

            steam_mods_folder_str = get_path_up_to_string(
                game_folder.parent, "common", exclude=True
            )
            if steam_mods_folder_str == "":
                steam_mods_folder: Path = (
                    steam_root / "steamapps" / "workshop" / "content" / "294100"
                )
            else:
                steam_mods_folder = (
                    Path(steam_mods_folder_str) / "workshop" / "content" / "294100"
                )
        else:
            fallback_game_folder = (
                user_home
                / "Library"
                / "Application Support"
                / "Steam"
                / "steamapps"
                / "common"
                / "RimWorld"
            )
            game_folder = self._find_mac_app_bundle(fallback_game_folder)
            steam_mods_folder = (
                user_home
                / "Library"
                / "Application Support"
                / "Steam"
                / "steamapps"
                / "workshop"
                / "content"
                / "294100"
            )

        config_folder = (
            user_home / "Library" / "Application Support" / "Rimworld" / "Config"
        )

        return game_folder, config_folder, steam_mods_folder

    @staticmethod
    def _find_mac_app_bundle(rimworld_dir: Path) -> Path:
        """Find the .app bundle in a RimWorld directory.

        Discovers the actual filesystem-cased name instead of hardcoding it,
        since macOS is case-insensitive but path comparisons are case-sensitive.
        """
        if rimworld_dir.is_dir():
            apps = list(rimworld_dir.glob("*.app"))
            if apps:
                return apps[0]
        return rimworld_dir / "RimWorldMac.app"

    def __get_linux_paths(self) -> tuple[Path, Path, Path]:
        """
        Get paths for Linux by discovering the Steam root across distribution methods.

        Checks Debian, native, Flatpak, and Snap Steam installations in priority
        order. Uses VDF parsing to locate RimWorld in non-default library folders.
        Detects Proton prefix for config folder.

        :return: (game_folder, config_folder, steam_mods_folder)
        """
        user_home = Path.home()
        candidates = [
            user_home / ".steam" / "debian-installation",
            user_home / ".steam" / "steam",
            user_home / ".local" / "share" / "Steam",
            user_home
            / ".var"
            / "app"
            / "com.valvesoftware.Steam"
            / ".local"
            / "share"
            / "Steam",
            user_home / "snap" / "steam" / "common" / ".local" / "share" / "Steam",
        ]

        steam_root = self._find_steam_root(candidates)
        self._detected_steam_root = steam_root

        if steam_root:
            game_folder_str = find_steam_rimworld(steam_root)
            if game_folder_str:
                game_folder = Path(game_folder_str)
                logger.debug(f"VDF parsing found RimWorld at: {game_folder}")
            else:
                game_folder = steam_root / "steamapps" / "common" / "RimWorld"
                logger.debug(
                    f"VDF parsing did not find RimWorld, using fallback: {game_folder}"
                )

            steam_mods_folder_str = get_path_up_to_string(
                game_folder, "common", exclude=True
            )
            if steam_mods_folder_str == "":
                steam_mods_folder = (
                    steam_root / "steamapps" / "workshop" / "content" / "294100"
                )
            else:
                steam_mods_folder = (
                    Path(steam_mods_folder_str) / "workshop" / "content" / "294100"
                )
        else:
            game_folder = (
                user_home / ".steam" / "steam" / "steamapps" / "common" / "RimWorld"
            )
            steam_mods_folder = (
                user_home
                / ".steam"
                / "steam"
                / "steamapps"
                / "workshop"
                / "content"
                / "294100"
            )

        # Config folder: check Proton prefix first, then native
        native_config = (
            user_home
            / ".config"
            / "unity3d"
            / "Ludeon Studios"
            / "RimWorld by Ludeon Studios"
            / "Config"
        )
        if steam_root:
            proton_config = (
                steam_root
                / "steamapps"
                / "compatdata"
                / "294100"
                / "pfx"
                / "drive_c"
                / "users"
                / "steamuser"
                / "AppData"
                / "LocalLow"
                / "Ludeon Studios"
                / "RimWorld by Ludeon Studios"
                / "Config"
            )
            if proton_config.exists():
                logger.info(f"Proton prefix detected for config: {proton_config}")
                config_folder = proton_config
            else:
                config_folder = native_config
        else:
            config_folder = native_config

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
    def _do_http_download_from_dialog(
        self, url: str, repo_url: str, display_name: str
    ) -> None:
        """Download a database via HTTP using the URL currently in the settings dialog."""
        if not url:
            show_warning(
                title="No URL configured",
                text=f"No URL is configured for {display_name}.",
                information="Please enter a URL in the text field.",
            )
            return

        repo_name = (
            extract_git_dir_name(repo_url)
            if repo_url
            else display_name.replace(" ", "-")
        )
        task = DatabaseDownloadTask(
            url=url,
            target_dir=AppInfo().databases_folder,
            repo_name=repo_name,
            display_name=display_name,
        )

        if self._http_download_worker is not None:
            try:
                self._http_download_worker.download_finished.disconnect()
                self._http_download_worker.quit()
                self._http_download_worker.wait()
            except Exception as e:
                logger.debug(f"Error during HTTP worker cleanup: {e}")
            self._http_download_worker = None

        self._http_download_worker = HttpDownloadWorker([task])
        self._http_download_worker.download_finished.connect(
            self._on_http_download_from_dialog_finished
        )
        self._http_download_worker.start()

    @Slot(dict)
    def _on_http_download_from_dialog_finished(
        self, results: dict[str, DownloadResult]
    ) -> None:
        updated = [name for name, r in results.items() if r == DownloadResult.UPDATED]
        up_to_date = [
            name for name, r in results.items() if r == DownloadResult.UP_TO_DATE
        ]
        failed = [name for name, r in results.items() if r == DownloadResult.FAILED]

        if failed:
            show_warning(
                title="Download failed",
                text=f"Failed to download: {', '.join(failed)}",
                information="Please check your internet connection and the configured URL.",
            )
        elif updated:
            show_warning(
                title="Download complete",
                text=f"Downloaded successfully: {', '.join(updated)}",
            )
        elif up_to_date:
            show_warning(
                title="Already up to date",
                text=f"Already up to date: {', '.join(up_to_date)}",
            )

        if self._http_download_worker:
            try:
                self._http_download_worker.download_finished.disconnect()
            except Exception as e:
                logger.debug(f"Error during HTTP worker cleanup: {e}")
            self._http_download_worker = None

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

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
from app.services.http_download_service import HttpDownloadService
from app.services.mod_path_service import get_mod_paths, resolve_data_source
from app.services.path_autodetect_service import PathAutodetectService
from app.utils.constants import DEFAULT_INSTANCE_NAME
from app.utils.event_bus import EventBus
from app.utils.generic import validate_game_executable
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

        self._http_download_service = HttpDownloadService()

        # Initialize per-tab controllers (registry pattern)
        self._tab_controllers: dict[str, BaseTabController] = {
            "sorting": SortingTabController(self.settings, self.settings_dialog),
            "databases": DatabasesTabController(
                self.settings,
                self.settings_dialog,
                self._http_download_service.start_download,
            ),
            "locations": LocationsTabController(
                self.settings,
                self.settings_dialog,
                validate_game_location=self._validate_game_location,
                validate_config_folder_location=self._validate_config_folder_location,
                validate_local_mods_location=self._validate_local_mods_location,
                on_path_selected=self._on_locations_path_selected,
                on_autodetect=self._on_locations_autodetect_button_clicked,
                on_instance_folder_choose=self._on_instance_folder_location_choose_button_clicked,
                on_instance_folder_clear=self._on_instance_folder_location_clear_button_clicked,
            ),
            "appearance": AppearanceTabController(self.settings, self.settings_dialog),
            "game_launch": GameLaunchTabController(self.settings, self.settings_dialog),
            "internal_tools": InternalToolsTabController(
                self.settings,
                self.settings_dialog,
                last_file_dialog_path=str(self._last_file_dialog_path),
                on_path_selected=self._on_locations_path_selected,
            ),
            "external_tools": ExternalToolsTabController(
                self.settings,
                self.settings_dialog,
                last_file_dialog_path=str(self._last_file_dialog_path),
                on_path_selected=self._on_locations_path_selected,
            ),
            "db_builder": DatabaseBuilderTabController(
                self.settings,
                self.settings_dialog,
            ),
            "advanced": AdvancedTabController(self.settings, self.settings_dialog),
        }

        for tc in self._tab_controllers.values():
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
        return get_mod_paths(self.active_instance)

    def resolve_data_source(self, path: str) -> str | None:
        return resolve_data_source(self.active_instance, path)

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
        self._show_steam_integration_warnings()

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

    def _show_steam_integration_warnings(self) -> None:
        for msg in self.settings._steam_integration_warnings:
            QMessageBox.warning(self.settings_dialog, self.tr("Steam Integration"), msg)
        self.settings._steam_integration_warnings.clear()

    def _update_view_from_model(self) -> None:
        for tc in self._tab_controllers.values():
            tc.update_view_from_model()

    def _update_model_from_view(self) -> None:
        for tc in self._tab_controllers.values():
            tc.update_model_from_view()

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

    def _validate_game_location(self, game_folder: str) -> tuple[bool, str]:
        """
        Validate the game location.

        :param game_folder: Path to the game folder as a string.
        :return: (is_valid, error_message)
        """
        if not validate_game_executable(game_folder):
            return False, self.tr(
                "The selected game folder does not contain a valid RimWorld executable.<br><br>"
                "Please select a valid game location.<br><br>"
                "Windows: RimWorldWin64.exe or RimWorldWin.exe<br><br>"
                "Mac: RimworldMac.app<br><br>"
                "Linux: RimWorldLinux<br><br>"
                "RimWorldWin64.exe or RimWorldWin.exe if you using windows version of the game on Linux"
            )
        return True, ""

    def _validate_config_folder_location(self, config_folder: str) -> tuple[bool, str]:
        """
        Validate the config folder location.

        :param config_folder: Path to the config folder as a string.
        :return: (is_valid, error_message)
        """
        if not (Path(config_folder) / "ModsConfig.xml").exists():
            return False, self.tr(
                "The selected config folder does not contain ModsConfig.xml.<br><br>"
                "Please select a valid config folder.<br><br>"
                "If you have not launched the game before,<br><br>"
                "Please launch the game at least once to generate the necessary config files."
            )
        return True, ""

    def _validate_local_mods_location(self, local_folder: str) -> tuple[bool, str]:
        """
        Validate the local mods folder location.
        The local mods folder is valid if it is a directory.

        :param local_folder: Path to the local mods folder as a string.
        :return: (is_valid, error_message)
        """
        game_folder = self.settings.instances[
            self.settings.current_instance
        ].game_folder
        if not (Path(local_folder).is_dir()) or local_folder != str(
            Path(game_folder) / "Mods"
        ):
            return False, self.tr(
                "The selected local mods folder location is not a valid directory.<br><br>"
                "Please select a valid folder for local mods.<br><br>"
                "The local mods folder should be a 'Mods' subfolder within the game folder."
            )
        return True, ""

    @Slot()
    def _on_global_ok_button_clicked(self) -> None:
        """
        Close the settings dialog, update the model from the view, and save the settings.
        """
        # Update the model from the view before saving to ensure validation checks have the latest data
        self._update_model_from_view()

        # Validate game folder if set
        game_folder_text = self.settings_dialog.game_location.text().strip()
        if game_folder_text:
            is_valid, error_msg = self._validate_game_location(game_folder_text)
            if not is_valid:
                QMessageBox.information(
                    self.settings_dialog,
                    self.tr("Invalid Game Location"),
                    error_msg,
                )
                return

        # Validate config folder if set
        config_folder_text = self.settings_dialog.config_folder_location.text().strip()
        if config_folder_text:
            is_valid, error_msg = self._validate_config_folder_location(
                config_folder_text
            )
            if not is_valid:
                QMessageBox.warning(
                    self.settings_dialog,
                    self.tr("Invalid Config Folder"),
                    error_msg,
                )
                return

        # Validate local mods folder if set
        local_mods_folder_text = (
            self.settings_dialog.local_mods_folder_location.text().strip()
        )
        if local_mods_folder_text:
            is_valid, error_msg = self._validate_local_mods_location(
                local_mods_folder_text
            )
            if not is_valid:
                QMessageBox.warning(
                    self.settings_dialog,
                    self.tr("Invalid Local Mods Folder"),
                    error_msg,
                )
                return

        # Model-level Steam integration validation (silently fixes & logs)
        if self.settings._validate_steam_integration_config():
            self._show_steam_integration_warnings()
            self._tab_controllers["locations"].update_view_from_model()
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

    @Slot()
    def _on_locations_autodetect_button_clicked(self) -> None:
        """
        This function tries to autodetect Rimworld paths based on the
        defaults typically found per-platform, and set them in the client.
        """
        logger.info("USER ACTION: starting autodetect paths")

        autodetect = PathAutodetectService()

        os_paths: tuple[Path, Path, Path]
        if SystemInfo().operating_system == SystemInfo.OperatingSystem.MACOS:
            os_paths = autodetect.get_darwin_paths()
            logger.info(f"Running on MacOS with the following paths: {os_paths}")
        elif SystemInfo().operating_system == SystemInfo.OperatingSystem.LINUX:
            os_paths = autodetect.get_linux_paths()
            logger.info(f"Running on Linux with the following paths: {os_paths}")
            if (
                autodetect.detected_steam_root is not None
                and "snap" in autodetect.detected_steam_root.parts
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
            os_paths = autodetect.get_windows_paths()
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

        for i, group in enumerate(path_groups):
            if group.folder.exists():
                logger.info(
                    f"Auto-detected {group.name} folder path exists: {group.folder}"
                )
                if not group.settings_line.text():
                    logger.info(
                        f"No value set currently for {group.name} folder. Overwriting with auto-detected path"
                    )
                    group.settings_line.setText(str(group.folder))
                    if i == 2:
                        self.settings_dialog.steam_client_integration_checkbox.setChecked(
                            True
                        )
                        self.settings_dialog.launch_via_steam_protocol_checkbox.setChecked(
                            True
                        )
                else:
                    logger.info(f"Value already set for {group.name} folder. Passing")
            else:
                logger.warning(
                    f"Auto-detected {group.name} folder path does not exist: {group.folder}"
                )

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

from json import JSONDecodeError
from pathlib import Path

from loguru import logger
from PySide6.QtCore import QObject, Slot
from PySide6.QtWidgets import QApplication

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
    SharedFileDialogState,
    SortingTabController,
)
from app.controllers.theme_controller import ThemeController
from app.models.settings import Instance, Settings
from app.utils.app_info import AppInfo
from app.utils.constants import DEFAULT_INSTANCE_NAME
from app.utils.event_bus import EventBus
from app.utils.generic import extract_git_dir_name
from app.utils.http_downloader import (
    DatabaseDownloadTask,
    DownloadResult,
    HttpDownloadWorker,
)
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

        self._file_dialog_state = SharedFileDialogState(str(Path.home()))

        self.theme_controller = ThemeController()

        self.language_controller = LanguageController()

        self.app_instance = QApplication.instance()

        self._http_download_worker: HttpDownloadWorker | None = None

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
            file_dialog_state=self._file_dialog_state,
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
            file_dialog_state=self._file_dialog_state,
        )
        self._tab_controllers.append(self._internal_tools_tab)

        self._external_tools_tab = ExternalToolsTabController(
            self.settings,
            self.settings_dialog,
            file_dialog_state=self._file_dialog_state,
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

    def create_instance(
        self,
        instance_name: str,
        game_folder: str = "",
        config_folder: str = "",
        local_folder: str = "",
        workshop_folder: str = "",
        run_args: str = "",
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

    @Slot()
    def _on_global_ok_button_clicked(self) -> None:
        """Close the settings dialog, update the model from the view, and save the settings."""
        if not all(tc.validate_before_save() for tc in self._tab_controllers):
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
            _dir=self._file_dialog_state.last_path,
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
        self._file_dialog_state.last_path = str(Path(instance_folder_location).parent)
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

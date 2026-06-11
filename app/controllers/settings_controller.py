from json import JSONDecodeError
from pathlib import Path

from loguru import logger
from PySide6.QtCore import QObject, Slot

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
from app.models.settings import Instance, Settings
from app.utils.event_bus import EventBus
from app.views.dialogue import BinaryChoiceDialog, show_settings_error
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

        # Initialize per-tab controllers (registry pattern)
        self._tab_controllers: list[BaseTabController] = []

        self._sorting_tab = SortingTabController(self.settings, self.settings_dialog)
        self._tab_controllers.append(self._sorting_tab)

        self._databases_tab = DatabasesTabController(
            self.settings,
            self.settings_dialog,
        )
        self._tab_controllers.append(self._databases_tab)

        self._locations_tab = LocationsTabController(
            self.settings,
            self.settings_dialog,
            file_dialog_state=self._file_dialog_state,
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
    def language_controller(self) -> LanguageController:
        """Delegate to AppearanceTabController (accessed by AppController)."""
        return self._appearance_tab.language_controller

    @property
    def active_instance(self) -> Instance:
        """
        Get the active instance.
        """
        return self.settings.instances[self.settings.current_instance]

    def _update_view_from_model(self) -> None:
        for tc in self._tab_controllers:
            tc.update_view_from_model()

    def _update_model_from_view(self) -> None:
        for tc in self._tab_controllers:
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

    @Slot()
    def _on_global_ok_button_clicked(self) -> None:
        """Close the settings dialog, update the model from the view, and save the settings."""
        if not all(tc.validate_before_save() for tc in self._tab_controllers):
            return

        self.settings_dialog.close()
        self._update_model_from_view()
        self.settings.save()
        self._appearance_tab.apply_theme_and_font(
            self.settings.font_family,
            self.settings.font_size,
            self.settings.enable_themes,
            self.settings.theme_name,
        )
        # Do a full refresh after updating the settings
        EventBus().do_refresh_mods_lists.emit()

    @Slot()
    def _do_reset_settings_file(self) -> None:
        logger.info("Resetting settings file and retrying load")
        self.settings.save()
        self._load_settings()

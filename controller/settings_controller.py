from PySide6.QtCore import QObject, Slot

from model.settings import Settings
from view.settings_dialog import SettingsDialog


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
        self.settings.load()

        self.settings_dialog = view

        # Initialize the settings dialog from the settings model

        self._update_view_from_model()

        # Wire up the settings dialog's signals

        self.settings_dialog.finished.connect(self._on_settings_dialog_finished)

    def show_settings_dialog(self) -> None:
        """
        Show the settings dialog.
        """
        self.settings_dialog.show()

    def _update_view_from_model(self) -> None:
        """
        Update the view from the settings model.
        """
        self.settings_dialog.game_location.setText(self.settings.game_folder)

    @Slot()
    def _on_settings_dialog_finished(self) -> None:
        """
        Close the settings dialog.
        """
        self.settings.game_folder = self.settings_dialog.game_location.text()

        self.settings.save()

        self.settings_dialog.close()

from PySide6.QtCore import QObject

from model.settings import Settings


class SettingsController(QObject):
    """
    Controller class to manage interactions with the `Settings` model.

    The `SettingsController` class provides a clear interface for working with the `Settings` model.
    It ensures that the associated settings model is loaded upon initialization.

    Attributes:
        settings (Settings): The underlying settings model managed by this controller.

    Examples:
        >>> settings_model = Settings()
        >>> controller = SettingsController(settings_model)
        >>> controller.settings.some_property
    """

    def __init__(self, model: Settings) -> None:
        """
        Initialize the `SettingsController` with the given `Settings` model.

        Upon initialization, the provided settings model's `load` method is called to ensure
        that the settings are loaded and available for use.

        Args:
            model (Settings): The settings model to be managed by this controller.
        """
        super().__init__()

        self.settings = model
        self.settings.load()

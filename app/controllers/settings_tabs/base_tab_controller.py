from abc import ABC, abstractmethod

from app.models.settings import Settings
from app.views.settings_dialog import SettingsDialog


class BaseTabController(ABC):
    """Base class for per-tab settings controllers.

    :param settings: The shared settings model.
    :param dialog: The settings dialog containing all tab widgets.
    """

    def __init__(
        self,
        settings: Settings,
        dialog: SettingsDialog,
    ) -> None:
        self.settings = settings
        self.dialog = dialog

    @abstractmethod
    def connect_signals(self) -> None:
        """Wire up all signals/slots for this tab's widgets."""

    @abstractmethod
    def update_view_from_model(self) -> None:
        """Push settings model values into this tab's widgets."""

    @abstractmethod
    def update_model_from_view(self) -> None:
        """Read this tab's widget values back into the settings model."""

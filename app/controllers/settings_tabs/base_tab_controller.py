from abc import ABC, abstractmethod
from typing import Callable, Optional

from app.models.settings import Settings
from app.views.settings_dialog import SettingsDialog


class BaseTabController(ABC):
    """Base class for per-tab settings controllers.

    :param settings: The shared settings model.
    :param dialog: The settings dialog containing all tab widgets.
    :param last_file_dialog_path: Initial file dialog directory.
    :param on_path_selected: Callback fired when a file dialog path is chosen.
    """

    def __init__(
        self,
        settings: Settings,
        dialog: SettingsDialog,
        last_file_dialog_path: Optional[str] = None,
        on_path_selected: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.settings = settings
        self.dialog = dialog
        self._last_file_dialog_path = last_file_dialog_path
        self._on_path_selected = on_path_selected

    @abstractmethod
    def connect_signals(self) -> None:
        """Wire up all signals/slots for this tab's widgets."""

    @abstractmethod
    def update_view_from_model(self) -> None:
        """Push settings model values into this tab's widgets."""

    @abstractmethod
    def update_model_from_view(self) -> None:
        """Read this tab's widget values back into the settings model."""

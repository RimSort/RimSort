from PySide6.QtCore import QObject

from app.models.settings import Settings
from app.views.settings_dialog import SettingsDialog


class SharedFileDialogState:
    """Mutable container for the last file-dialog path, shared across tab controllers."""

    def __init__(self, last_path: str) -> None:
        self.last_path = last_path


class BaseTabController(QObject):
    """Base class for per-tab settings controllers.

    :param settings: The shared settings model.
    :param dialog: The settings dialog containing all tab widgets.
    :param file_dialog_state: Shared mutable state for file dialog paths.
    """

    def __init__(
        self,
        settings: Settings,
        dialog: SettingsDialog,
        file_dialog_state: SharedFileDialogState | None = None,
    ) -> None:
        super().__init__()
        self.settings = settings
        self.dialog = dialog
        self._file_dialog_state = file_dialog_state

    def connect_signals(self) -> None:
        """Wire up all signals/slots for this tab's widgets."""
        raise NotImplementedError

    def update_view_from_model(self) -> None:
        """Push settings model values into this tab's widgets."""
        raise NotImplementedError

    def update_model_from_view(self) -> None:
        """Read this tab's widget values back into the settings model."""
        raise NotImplementedError

    def validate_before_save(self) -> bool:
        """Run validations before saving. Returns True if OK to save."""
        return True

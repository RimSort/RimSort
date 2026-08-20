from typing import Callable

from PySide6.QtCore import QObject

from app.controllers.metadata_controller import MetadataController
from app.models.settings import Settings
from app.windows.ai_assistant_panel import AiAssistantPanel


class AiAssistantController(QObject):
    def __init__(
        self,
        settings: Settings,
        metadata_controller: MetadataController,
        get_active_paths: Callable[[], list[str]],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.settings = settings
        self.metadata_controller = metadata_controller
        self._get_active_paths = get_active_paths
        self._panel: AiAssistantPanel | None = None

    def open_panel(self) -> None:
        if not self.settings.ai_assistant_enabled:
            self.settings.ai_assistant_enabled = True
        if self._panel is None:
            self._panel = AiAssistantPanel(
                self.settings,
                self.metadata_controller,
                self._get_active_paths,
                parent=None,
            )
        self._panel.show_non_modal()
        self._panel.raise_()
        self._panel.activateWindow()

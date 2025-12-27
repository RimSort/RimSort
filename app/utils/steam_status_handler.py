"""
Steam status notification handler for UI.

Handles Steam availability signals from EventBus and displays
appropriate dialogs to the user.
"""

from loguru import logger
from PySide6.QtWidgets import QWidget

from app.utils.event_bus import EventBus
from app.views.dialogue import show_warning


class SteamStatusHandler:
    """
    Handles Steam availability notifications in the UI.

    Connects to EventBus signals for Steam status and displays
    appropriate dialogs to the user when Steam is unavailable
    or operations fail.

    Example usage:
        # In MainWindowController or AppController:
        self.steam_status_handler = SteamStatusHandler(
            parent_widget=self.main_window
        )
        # Keep reference to prevent garbage collection
    """

    def __init__(self, parent_widget: QWidget | None = None) -> None:
        """
        Initialize Steam status handler.

        Connects to EventBus signals and sets up dialog parent.

        :param parent_widget: Parent widget for dialogs (typically main window)
        """
        self.parent_widget = parent_widget
        self._connect_signals()

    def _connect_signals(self) -> None:
        """Connect to EventBus signals for Steam status notifications."""
        EventBus().steam_not_running.connect(self._on_steam_not_running)
        EventBus().steam_operation_failed.connect(self._on_steam_operation_failed)

    def _on_steam_not_running(self) -> None:
        """
        Handle steam_not_running signal.

        Shows a modal warning dialog informing user that Steam is not available
        and providing troubleshooting steps.
        """
        logger.info("Showing Steam not running notification")
        show_warning(
            title="Steam Not Running",
            text="Steam client is not running or not available.",
            information=(
                "RimSort requires Steam to be running for Workshop integration.\n\n"
                "To resolve this:\n"
                "1. Start the Steam client\n"
                "2. Log in to your Steam account\n"
                "3. Restart RimSort or check Help > Check Steam Connection"
            ),
            parent=self.parent_widget,
        )

    def _on_steam_operation_failed(self, reason: str) -> None:
        """
        Handle steam_operation_failed signal.

        Shows a modal warning dialog with the specific failure reason.

        :param reason: Failure reason message from SteamworksInterface
        """
        logger.info(f"Showing Steam operation failed notification: {reason}")
        show_warning(
            title="Steam Operation Failed",
            text=reason,
            information=(
                "Please ensure Steam is running and you are logged in.\n\n"
                "Check Steam status: Help > Check Steam Connection"
            ),
            parent=self.parent_widget,
        )

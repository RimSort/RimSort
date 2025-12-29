"""
Steam status notification handler for UI.

Handles Steam availability signals from EventBus and displays
appropriate dialogs to the user.
"""

from time import sleep

from loguru import logger
from PySide6.QtWidgets import QWidget

from app.models.settings import Settings
from app.utils.event_bus import EventBus
from app.views.dialogue import show_dialogue_conditional, show_information, show_warning


class SteamStatusHandler:
    """
    Handles Steam availability notifications in the UI.

    Connects to EventBus signals for Steam status and displays
    appropriate dialogs to the user when Steam is unavailable
    or operations fail.

    Example usage:
        # In MainWindowController or AppController:
        self.steam_status_handler = SteamStatusHandler(
            settings=self.settings,
            parent_widget=self.main_window
        )
        # Keep reference to prevent garbage collection
    """

    def __init__(
        self, settings: Settings, parent_widget: QWidget | None = None
    ) -> None:
        """
        Initialize Steam status handler.

        Connects to EventBus signals and sets up dialog parent.

        :param settings: Application settings instance
        :param parent_widget: Parent widget for dialogs (typically main window)
        """
        self.parent_widget = parent_widget
        self.settings = settings
        self._connect_signals()

    def _connect_signals(self) -> None:
        """Connect to EventBus signals for Steam status notifications."""
        EventBus().steam_not_running.connect(self._on_steam_not_running)
        EventBus().steam_operation_failed.connect(self._on_steam_operation_failed)

    def _on_steam_not_running(self) -> None:
        """
        Handle steam_not_running signal.

        If auto_launch_steam is enabled, attempt to launch Steam automatically.
        Otherwise, show the standard warning dialog.
        """
        logger.info("Steam not running signal received")

        # Check if auto-launch is enabled
        if self.settings.auto_launch_steam:
            logger.info("Auto-launch Steam is enabled, attempting to launch...")
            self._attempt_auto_launch()
        else:
            logger.info("Auto-launch Steam is disabled, showing warning")
            self._show_steam_not_running_dialog()

    def _attempt_auto_launch(self) -> None:
        """
        Attempt to automatically launch Steam.

        Shows progress notification and handles timeout with user interaction.
        """
        # Import here to avoid circular dependency
        from app.utils.steam.steamworks.wrapper import (
            SteamworksInterface,
            _find_steam_executable,
            _is_steam_running,
        )

        # Check if Steam is already running (edge case)
        # Use _is_steam_running() instead of check_steam_availability() to avoid
        # triggering signals and potential infinite loops
        if _is_steam_running():
            logger.info("Steam is actually running, no need to launch")
            # Update Steamworks state
            steamworks = SteamworksInterface.instance()
            try:
                steamworks.steamworks.initialize()
                steamworks.steam_not_running = False
                logger.info("Steamworks API initialized successfully")
            except Exception as e:
                logger.warning(f"Steam running but Steamworks init failed: {e}")
            return

        # Find Steam executable
        steam_exe = _find_steam_executable()
        if not steam_exe or not steam_exe.exists():
            logger.warning("Steam executable not found, cannot auto-launch")
            self._show_steam_not_found_dialog()
            return

        # Show "launching Steam" notification
        show_information(
            title="Launching Steam",
            text="Steam client is not running. Launching Steam automatically...",
            information="Please wait while Steam starts up. This may take up to 45 seconds.",
            parent=self.parent_widget,
        )

        # Attempt launch with timeout
        success = self._launch_with_timeout()

        if success:
            logger.info("Steam launched successfully")
            show_information(
                title="Steam Ready",
                text="Steam has been launched and is now available.",
                information="You can now use Steam Workshop features.",
                parent=self.parent_widget,
            )
        else:
            logger.warning("Steam auto-launch failed or timed out")
            self._handle_launch_timeout()

    def _launch_with_timeout(self) -> bool:
        """
        Launch Steam and wait up to 45 seconds.

        :return: True if Steam became available, False otherwise
        :rtype: bool
        """
        from app.utils.steam.steamworks.wrapper import _launch_steam

        # Use _launch_steam which has built-in 45-second timeout
        return _launch_steam()

    def _handle_launch_timeout(self) -> None:
        """
        Handle the case where Steam launch times out after 45 seconds.

        Presents user with options to keep waiting or cancel.
        """
        from app.utils.steam.steamworks.wrapper import SteamworksInterface

        while True:
            # Ask user if they want to keep waiting
            keep_waiting = show_dialogue_conditional(
                title="Steam Launch Timeout",
                text=(
                    "Steam has not responded after 45 seconds.\n\n"
                    "Steam may still be starting up. Would you like to continue waiting?"
                ),
                information=(
                    "Click 'Yes' to wait another 15 seconds.\n"
                    "Click 'No' to cancel and use RimSort without Steam features."
                ),
                parent=self.parent_widget,
            )

            if not keep_waiting:
                logger.info("User chose to stop waiting for Steam")
                self._show_steam_not_running_dialog()
                return

            # Wait another 15 seconds and check
            logger.info("User chose to continue waiting for Steam...")
            sleep(15)

            steamworks = SteamworksInterface.instance()
            try:
                steamworks.steamworks.initialize()
                steamworks.steam_not_running = False
                logger.info("Steam became available during extended wait!")
                show_information(
                    title="Steam Ready",
                    text="Steam is now available!",
                    information="You can now use Steam Workshop features.",
                    parent=self.parent_widget,
                )
                return
            except Exception:
                logger.debug("Steam still not available, continuing wait loop...")
                continue

    def _show_steam_not_running_dialog(self) -> None:
        """Show the standard 'Steam not running' warning dialog."""
        show_warning(
            title="Steam Not Running",
            text="Steam client is not running or not available.",
            information=(
                "RimSort requires Steam to be running for Workshop integration.<br><br>"
                "To resolve this:<br>"
                "1. Launch Steam via Help > Launch Steam, <b>OR</b> start the Steam client manually<br>"
                "2. Log in to your Steam account<br>"
                "3. Restart RimSort or check Help > Check Steam Connection<br><br>"
                "<i>Tip: Enable 'Automatically launch Steam if not running' in Settings > Advanced to launch Steam automatically.</i>"
            ),
            parent=self.parent_widget,
        )

    def _show_steam_not_found_dialog(self) -> None:
        """Show dialog when Steam executable cannot be found."""
        show_warning(
            title="Steam Not Found",
            text="Could not locate Steam installation on your system.",
            information=(
                "RimSort cannot automatically launch Steam because the Steam "
                "executable was not found.\n\n"
                "Please ensure Steam is installed and try launching it manually."
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
                "Please ensure Steam is running and you are logged in.<br><br>"
                "Options:<br>"
                "• Launch Steam via Help > Launch Steam<br>"
                "<b>OR:</b><br>"
                "start the Steam client manually.<br>"
                "• Check Steam status: Help > Check Steam Connection<br><br>"
                "<i>Tip: Enable 'Automatically launch Steam if not running' in Settings > Advanced to launch Steam automatically.</i>"
            ),
            parent=self.parent_widget,
        )

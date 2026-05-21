"""
Steam status handler for detecting and launching the Steam client.

Provides process-based Steam detection and optional auto-launch functionality.
Does NOT interact with the Steamworks API or call SteamAPI_Init() -- only uses
OS-level process detection and subprocess launching.
"""

import subprocess
import sys
import time
from pathlib import Path

import psutil
from loguru import logger
from PySide6.QtCore import QCoreApplication, QObject, QThread, Signal

from app.models.settings import Settings
from app.utils.event_bus import EventBus
from app.views.dialogue import BinaryChoiceDialog, show_information, show_warning

_STEAM_PROCESS_NAME = "steam"
_STEAM_LAUNCH_TIMEOUT_SECONDS = 45
_STEAM_POLL_INTERVAL_SECONDS = 2.0


def _find_steam_executable() -> Path | None:
    """
    Locate the Steam executable using platform-specific heuristics.

    Checks common installation paths per platform. Does not search the
    entire filesystem.

    :return: Path to the Steam executable, or None if not found.
    """
    candidates: list[Path] = []

    if sys.platform == "darwin":
        candidates = [
            Path("/Applications/Steam.app/Contents/MacOS/steam_osx"),
            Path.home() / "Applications/Steam.app/Contents/MacOS/steam_osx",
        ]
    elif sys.platform == "linux":
        candidates = [
            Path.home() / ".steam/steam/steam.sh",
            Path("/usr/bin/steam"),
            Path("/usr/local/bin/steam"),
            Path.home() / ".steam/steam/ubuntu12_32/steam",
            Path.home() / ".local/share/Steam/ubuntu12_32/steam",
            # Flatpak Steam
            Path("/var/lib/flatpak/exports/bin/com.valvesoftware.Steam"),
            Path.home() / ".local/share/flatpak/exports/bin/com.valvesoftware.Steam",
        ]
    elif sys.platform == "win32":
        import os

        program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        candidates = [
            Path(program_files_x86) / "Steam" / "steam.exe",
            Path(program_files) / "Steam" / "steam.exe",
        ]

    for candidate in candidates:
        if candidate.exists():
            logger.debug(f"Found Steam executable at: {candidate}")
            return candidate

    logger.debug("Steam executable not found in any standard location")
    return None


def _is_steam_running() -> bool:
    """
    Check whether the Steam client process is currently running.

    Uses psutil to scan running processes. Matches by process name on
    all platforms.

    :return: True if a Steam process is detected, False otherwise.
    """
    target_names: set[str]
    if sys.platform == "win32":
        target_names = {"steam.exe", "steamservice.exe"}
    elif sys.platform == "darwin":
        target_names = {"steam_osx", "Steam Helper"}
    else:
        target_names = {"steam", "steam.sh", "steamwebhelper"}

    try:
        for proc in psutil.process_iter(["name"]):
            try:
                name = proc.info["name"]
                if name and name.lower() in {t.lower() for t in target_names}:
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
    except Exception as e:
        logger.warning(f"Error scanning processes for Steam: {e}")

    return False


class _SteamLaunchWorker(QThread):
    """
    Background worker that launches Steam and polls until it is running
    or a timeout is reached. Runs off the UI thread to avoid blocking.
    """

    launch_succeeded = Signal()
    launch_failed = Signal(str)  # reason

    def __init__(self, steam_path: Path) -> None:
        super().__init__()
        self._steam_path = steam_path

    def run(self) -> None:
        """
        Launch Steam and poll for the process to appear.
        """
        logger.info(f"Launching Steam from: {self._steam_path}")
        try:
            if sys.platform == "win32":
                subprocess.Popen(
                    [str(self._steam_path)],
                    creationflags=subprocess.DETACHED_PROCESS,
                )
            else:
                subprocess.Popen(
                    [str(self._steam_path)],
                    start_new_session=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
        except Exception as e:
            reason = f"Failed to start Steam process: {e}"
            logger.error(reason)
            self.launch_failed.emit(reason)
            return

        deadline = time.monotonic() + _STEAM_LAUNCH_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if _is_steam_running():
                logger.info("Steam process detected after launch")
                self.launch_succeeded.emit()
                return
            time.sleep(_STEAM_POLL_INTERVAL_SECONDS)

        reason = f"Steam did not start within {_STEAM_LAUNCH_TIMEOUT_SECONDS} seconds"
        logger.warning(reason)
        self.launch_failed.emit(reason)


class SteamStatusHandler(QObject):
    """
    Coordinates Steam status checks and auto-launch behavior.

    Connects to ``EventBus`` signals:
    - ``do_check_steam_connection`` -- checks if Steam is running
    - ``do_launch_steam`` -- attempts to launch Steam
    - ``steam_not_running`` -- emitted when a Steam operation discovers
      Steam is not running; triggers auto-launch or a warning dialog
      depending on the ``auto_launch_steam`` setting.

    This class does **not** create any Steamworks instances or call
    ``SteamAPI_Init()``.
    """

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self._settings = settings
        self._launch_worker: _SteamLaunchWorker | None = None

        event_bus = EventBus()
        event_bus.do_check_steam_connection.connect(self._on_check_steam_connection)
        event_bus.do_launch_steam.connect(self._on_launch_steam)
        event_bus.steam_not_running.connect(self._on_steam_not_running)
        event_bus.steam_operation_failed.connect(self._on_steam_operation_failed)

    def _on_steam_operation_failed(self, pfid: str, reason: str) -> None:
        """
        Handle the ``steam_operation_failed`` signal.

        :param pfid: The publishedfileid of the mod whose operation failed.
        :param reason: Human-readable failure reason.
        """
        logger.warning(f"Steam operation failed for pfid={pfid}: {reason}")
        show_warning(
            title=QCoreApplication.translate("SteamStatusHandler", "Steam Operation Failed"),
            text=QCoreApplication.translate(
                "SteamStatusHandler",
                "A Steam operation has failed.",
            ),
            information=reason,
        )

    def _on_check_steam_connection(self) -> None:
        """
        Handle explicit Steam connection check request (e.g. from the Help menu).
        """
        if _is_steam_running():
            show_information(
                title=QCoreApplication.translate("SteamStatusHandler", "Steam Status"),
                text=QCoreApplication.translate(
                    "SteamStatusHandler",
                    "Steam is running.",
                ),
            )
        else:
            show_warning(
                title=QCoreApplication.translate("SteamStatusHandler", "Steam Status"),
                text=QCoreApplication.translate(
                    "SteamStatusHandler",
                    "Steam is not running.",
                ),
                information=QCoreApplication.translate(
                    "SteamStatusHandler",
                    "Some features require Steam to be running. You can launch Steam from Help > Launch Steam.",
                ),
            )

    def _on_launch_steam(self) -> None:
        """
        Handle explicit Steam launch request (e.g. from the Help menu).
        """
        if _is_steam_running():
            show_information(
                title=QCoreApplication.translate("SteamStatusHandler", "Steam Status"),
                text=QCoreApplication.translate(
                    "SteamStatusHandler",
                    "Steam is already running.",
                ),
            )
            return

        self._do_launch_steam()

    def _on_steam_not_running(self) -> None:
        """
        Handle the ``steam_not_running`` signal emitted when a Steam operation
        fails because Steam is not detected.

        If ``auto_launch_steam`` is enabled, attempts to launch Steam
        automatically. Otherwise, shows a warning dialog asking the user
        whether to launch Steam.
        """
        if self._settings.auto_launch_steam:
            logger.info("Auto-launch Steam is enabled; attempting to launch Steam")
            self._do_launch_steam()
        else:
            self._show_steam_not_running_dialog()

    def _show_steam_not_running_dialog(self) -> None:
        """
        Show a dialog informing the user that Steam is not running and
        offering to launch it.
        """
        dialog = BinaryChoiceDialog(
            title=QCoreApplication.translate("SteamStatusHandler", "Steam Not Running"),
            text=QCoreApplication.translate(
                "SteamStatusHandler",
                "Steam does not appear to be running. Would you like to launch it now?",
            ),
            information=QCoreApplication.translate(
                "SteamStatusHandler",
                "Steam is required for this operation. You can enable automatic launching in Settings > Advanced.",
            ),
            positive_text=QCoreApplication.translate("SteamStatusHandler", "Launch Steam"),
            negative_text=QCoreApplication.translate("SteamStatusHandler", "Cancel"),
        )
        if dialog.exec_is_positive():
            self._do_launch_steam()

    def _do_launch_steam(self) -> None:
        """
        Find the Steam executable and launch it in a background thread.
        """
        if self._launch_worker is not None and self._launch_worker.isRunning():
            logger.debug("Steam launch already in progress, ignoring duplicate request")
            return

        steam_path = _find_steam_executable()
        if steam_path is None:
            show_warning(
                title=QCoreApplication.translate("SteamStatusHandler", "Steam Not Found"),
                text=QCoreApplication.translate(
                    "SteamStatusHandler",
                    "Could not find the Steam executable.",
                ),
                information=QCoreApplication.translate(
                    "SteamStatusHandler",
                    "Please ensure Steam is installed in a standard location, or launch it manually.",
                ),
            )
            return

        self._launch_worker = _SteamLaunchWorker(steam_path)
        self._launch_worker.launch_succeeded.connect(self._on_launch_succeeded)
        self._launch_worker.launch_failed.connect(self._on_launch_failed)
        self._launch_worker.start()

    def _on_launch_succeeded(self) -> None:
        """
        Called when the background worker detects that Steam has started.
        """
        logger.info("Steam launched successfully")
        show_information(
            title=QCoreApplication.translate("SteamStatusHandler", "Steam Launched"),
            text=QCoreApplication.translate(
                "SteamStatusHandler",
                "Steam has been launched successfully. You may now retry the operation.",
            ),
        )

    def _on_launch_failed(self, reason: str) -> None:
        """
        Called when the background worker fails to detect Steam after launching.

        :param reason: Human-readable failure reason.
        """
        logger.warning(f"Steam launch failed: {reason}")
        show_warning(
            title=QCoreApplication.translate("SteamStatusHandler", "Steam Launch Failed"),
            text=QCoreApplication.translate(
                "SteamStatusHandler",
                "Failed to launch Steam.",
            ),
            information=reason,
        )

import os
import shutil
import subprocess
import sys
from collections.abc import MutableMapping
from pathlib import Path
from time import sleep
from typing import TYPE_CHECKING

from loguru import logger
from PySide6.QtCore import QCoreApplication, QThread, Signal
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout

from app.utils.generic import show_no_steam_warning, show_snap_steam_warning

if TYPE_CHECKING:
    from app.models.settings import Settings

# If we're running from a Python interpreter, Ensure SteamworksPy module is in Python path, sys.path ($PYTHONPATH)
# Ensure that this is available by running via: git submodule update --init --recursive
# You can automatically ensure this is done by utilizing distribute.py
try:
    if "__compiled__" not in globals():
        sys.path.append(str((Path.cwd() / "submodules" / "SteamworksPy")))
except Exception:
    pass

SLEEP_TIME = 15
MAX_ATTEMPTS = 10
SNAP_STEAM_PATH = (
    Path.home() / "snap" / "steam" / "common" / ".local" / "share" / "Steam"
)

_STEAM_LAUNCH_BEHAVIOR_PROMPT = "prompt"
_STEAM_LAUNCH_BEHAVIOR_ALWAYS = "always"
_STEAM_LAUNCH_BEHAVIOR_NEVER = "never"


def _find_steam_executable() -> Path | None:
    """
    Find the Steam executable path based on the current platform.

    Returns:
        Path | None: Path to Steam executable, or None if not found
    """
    if sys.platform == "win32":
        from app.utils.win_find_steam import find_steam_folder

        steam_path, found = find_steam_folder()
        if not found:
            return None
        return Path(steam_path) / "steam.exe"
    elif sys.platform == "darwin":
        return Path("/Applications/Steam.app/Contents/MacOS/steam_osx")
    elif sys.platform.startswith("linux"):
        # For Linux, we are directly launching using the 'steam' command
        return None
    else:
        return None


def is_steam_running() -> bool:
    """
    Check if Steam is currently running by looking for Steam processes.
    Single-pass check with no retries — suitable for synchronous UI calls.

    Returns:
        bool: True if Steam is running, False otherwise
    """
    try:
        import psutil
    except ImportError:
        logger.warning("psutil not available, cannot check if Steam is running")
        return False
    try:
        if sys.platform == "win32":
            steam_indicators = {
                "steam.exe",
                "steamwebhelper.exe",
                "steamservice.exe",
                "steamerrorreporter.exe",
                "steamerrorreporter64.exe",
            }
        elif sys.platform == "darwin":
            steam_indicators = {
                "steam_osx",
                "steamwebhelper",
            }
        else:
            steam_indicators = {
                "steam",
                "steamwebhelper",
            }

        for process in psutil.process_iter(attrs=["name"]):
            try:
                name = process.info["name"]
                if name and name.lower() in steam_indicators:
                    logger.debug(f"Found Steam process: {name}")
                    return True
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                continue

        return False
    except Exception as e:
        logger.warning(f"Error checking if Steam is running: {e}")
        return False


def _setup_snap_steam_env(env: MutableMapping[str, str]) -> None:
    """
    Configure environment variables for snap Steam compatibility.

    Args:
        env: Environment dictionary to update
    """
    if SNAP_STEAM_PATH.exists():
        logger.debug("Configuring environment for snap Steam...")
        env["STEAM_COMPAT_TOOL_PATHS"] = str(SNAP_STEAM_PATH)
        env["STEAMRUNTIME_PATH"] = str(SNAP_STEAM_PATH / "ubuntu12_32")


class SteamLaunchWorker(QThread):
    """Background worker that launches Steam and waits for it to be ready."""

    launch_finished = Signal(bool)
    progress = Signal(str)

    def __init__(self, libs: str) -> None:
        super().__init__()
        self._libs = libs
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        try:
            steam_exe = _find_steam_executable()
            if steam_exe is None and not sys.platform.startswith("linux"):
                logger.warning("Steam executable not found")
                self.progress.emit("Steam executable not found")
                self.launch_finished.emit(False)
                return

            self.progress.emit("Launching Steam...")
            if not self._start_steam_process(steam_exe):
                self.launch_finished.emit(False)
                return

            sleep(SLEEP_TIME)
            if self._cancelled:
                self.launch_finished.emit(False)
                return

            if is_steam_running():
                self.progress.emit(
                    "Steam processes detected, waiting for initialization..."
                )
                sleep(SLEEP_TIME)
                self.launch_finished.emit(True)
                return

            for attempt in range(MAX_ATTEMPTS):
                if self._cancelled:
                    self.launch_finished.emit(False)
                    return
                self.progress.emit(
                    f"Waiting for Steam to start ({attempt + 1}/{MAX_ATTEMPTS})..."
                )
                sleep(SLEEP_TIME)
                if is_steam_running():
                    self.progress.emit("Steam detected, finalizing...")
                    sleep(SLEEP_TIME)
                    self.launch_finished.emit(True)
                    return

            self.progress.emit("Steam failed to start within timeout")
            logger.warning("Steam failed to start within timeout")
            self.launch_finished.emit(False)

        except Exception as e:
            logger.warning(f"Error launching Steam: {e}")
            self.progress.emit(f"Error: {e}")
            self.launch_finished.emit(False)

    def _start_steam_process(self, steam_exe: Path | None) -> bool:
        try:
            env = os.environ.copy()
            if sys.platform.startswith("linux"):
                env["LD_LIBRARY_PATH"] = (
                    self._libs + os.pathsep + env.get("LD_LIBRARY_PATH", "")
                )
                _setup_snap_steam_env(env)

            if steam_exe is None:
                return self._launch_linux_steam(env)
            if not steam_exe.exists():
                logger.warning("Steam executable not found")
                self.progress.emit("Steam executable not found")
                return False
            if sys.platform.startswith("linux"):
                _setup_snap_steam_env(env)
            subprocess.Popen([str(steam_exe)], env=env)
            return True
        except FileNotFoundError:
            logger.warning("Steam executable not found")
            self.progress.emit("Steam executable not found")
            return False

    def _launch_linux_steam(self, env: dict[str, str]) -> bool:
        terminal_candidates = [
            "gnome-terminal",
            "konsole",
            "xfce4-terminal",
            "mate-terminal",
            "xterm",
            "x-terminal-emulator",
        ]
        terminal = next((t for t in terminal_candidates if shutil.which(t)), None)
        try:
            if terminal:
                logger.debug(f"Using terminal emulator: {terminal}")
                if terminal == "gnome-terminal":
                    subprocess.Popen([terminal, "--", "steam"], env=env)
                else:
                    subprocess.Popen([terminal, "-e", "steam"], env=env)
            else:
                logger.warning(
                    "No terminal emulator found, falling back to direct launch"
                )
                subprocess.Popen(["steam"], env=env)
            return True
        except FileNotFoundError:
            logger.warning("Steam executable or terminal emulator not found")
            self.progress.emit("Steam executable not found")
            return False


def run_steam_launch_with_progress(libs: str) -> bool:
    """
    Launch Steam on a background thread and show a modal progress dialog.

    :param libs: Path to the Steamworks library directory
    :return: True if Steam launched successfully
    """
    worker = SteamLaunchWorker(libs)
    result = [False]

    _tr = QCoreApplication.translate

    dialog = QDialog()
    dialog.setWindowTitle(_tr("SteamAvailability", "Launching Steam"))
    dialog.setModal(True)
    dialog.setMinimumWidth(350)

    layout = QVBoxLayout(dialog)
    status_label = QLabel(_tr("SteamAvailability", "Starting Steam..."))
    layout.addWidget(status_label)

    cancel_button = QPushButton(_tr("SteamAvailability", "Cancel"))
    layout.addWidget(cancel_button)

    def on_progress(message: str) -> None:
        status_label.setText(message)

    def on_finished(success: bool) -> None:
        result[0] = success
        dialog.accept()

    def on_cancel() -> None:
        worker.cancel()
        status_label.setText("Cancelling...")
        cancel_button.setEnabled(False)

    worker.progress.connect(on_progress)
    worker.launch_finished.connect(on_finished)
    cancel_button.clicked.connect(on_cancel)
    dialog.rejected.connect(on_cancel)

    worker.start()
    dialog.exec()
    worker.wait()

    return result[0]


_BUTTON_YES = "Yes"
_BUTTON_YES_ALWAYS = "Yes, always"
_BUTTON_NO = "No"
_BUTTON_NO_NEVER = "No, never ask"

_BUTTON_LABELS = [_BUTTON_YES, _BUTTON_YES_ALWAYS, _BUTTON_NO, _BUTTON_NO_NEVER]

_BUTTON_TO_CHOICE = {
    _BUTTON_YES: "yes",
    _BUTTON_YES_ALWAYS: "yes_always",
    _BUTTON_NO: "no",
    _BUTTON_NO_NEVER: "no_never",
}


def _show_steam_launch_prompt() -> str:
    """
    Show a dialog asking the user what to do when Steam isn't running.
    Returns one of: "yes", "yes_always", "no", "no_never", "cancel".
    """
    import app.views.dialogue as dialogue

    translated_to_key = {
        QCoreApplication.translate("show_dialogue_conditional", label): label
        for label in _BUTTON_LABELS
    }

    response = dialogue.show_dialogue_conditional(
        title=QCoreApplication.translate("SteamAvailability", "Steam Not Running"),
        text=QCoreApplication.translate(
            "SteamAvailability",
            "Steam is required for this operation but is not running.",
        ),
        information=QCoreApplication.translate(
            "SteamAvailability",
            "Would you like to launch Steam?\n\n(You can also change this in Settings)",
        ),
        button_text_override=_BUTTON_LABELS,
    )
    if isinstance(response, str):
        original_label = translated_to_key.get(response)
        if original_label is not None:
            return _BUTTON_TO_CHOICE[original_label]
    return "cancel"


def check_steam_available(_libs: str, settings: "Settings") -> bool:
    """
    Check if Steam is available and running. Respects user's launch behavior preference.

    :param _libs: Path to the Steamworks library directory
    :param settings: Application settings (for steam_launch_behavior and instance config)
    :return: True if Steam is available, False otherwise
    """
    current = settings.instances.get(settings.current_instance)
    if current is None or not current.steam_client_integration:
        return True

    if SNAP_STEAM_PATH.exists() and sys.platform.startswith("linux"):
        logger.warning(
            "Snap Steam detected. Snap Steam is incompatible with Steamworks due to sandboxing."
        )
        show_snap_steam_warning()
        return False

    if is_steam_running():
        return True

    logger.info("Steam is not running")
    behavior = settings.steam_launch_behavior

    if behavior == _STEAM_LAUNCH_BEHAVIOR_NEVER:
        show_no_steam_warning()
        return False

    if behavior == _STEAM_LAUNCH_BEHAVIOR_ALWAYS:
        return run_steam_launch_with_progress(_libs)

    choice = _show_steam_launch_prompt()

    if choice == "yes_always":
        settings.steam_launch_behavior = _STEAM_LAUNCH_BEHAVIOR_ALWAYS
        settings.save()
        return run_steam_launch_with_progress(_libs)
    elif choice == "yes":
        return run_steam_launch_with_progress(_libs)
    elif choice == "no_never":
        settings.steam_launch_behavior = _STEAM_LAUNCH_BEHAVIOR_NEVER
        settings.save()
        show_no_steam_warning()
        return False
    elif choice == "no":
        show_no_steam_warning()
        return False
    else:
        return False

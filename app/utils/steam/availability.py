import os
import shutil
import subprocess
import sys
from collections.abc import Callable, MutableMapping
from pathlib import Path
from time import sleep
from typing import Optional

from loguru import logger

from app.utils.generic import show_no_steam_warning, show_snap_steam_warning

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


def _find_steam_executable() -> Optional[Path]:
    """
    Find the Steam executable path based on the current platform.

    Returns:
        Optional[Path]: Path to Steam executable, or None if not found
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


def _is_steam_running() -> bool:
    """
    Check if Steam is currently running by looking for Steam processes.

    Returns:
        bool: True if Steam is running, False otherwise
    """
    try:
        import psutil
    except ImportError:
        logger.warning("psutil not available, cannot check if Steam is running")
        return False
    try:
        # Define platform-specific Steam process indicators once
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

        # Retry up to 5 times with 2 second delay to account for process startup time
        for attempt in range(5):
            for process in psutil.process_iter(attrs=["name"]):
                try:
                    name = process.info["name"]
                    if name and name.lower() in steam_indicators:
                        logger.debug(f"Found Steam process: {name}")
                        return True
                except (psutil.AccessDenied, psutil.NoSuchProcess):
                    continue

            if attempt < 4:
                sleep(2)

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


def _launch_steam(
    _libs: str,
    status_callback: Callable[[str], None] | None = None,
) -> bool:
    """
    Launch Steam if it's not running and wait for it to start.

    Args:
        _libs: Path to the Steamworks library directory
        status_callback: Optional callback to emit progress messages to UI

    Returns:
        bool: True if Steam was launched successfully, False otherwise
    """
    try:
        steam_exe = _find_steam_executable()
        if steam_exe is None:
            if not sys.platform.startswith("linux"):
                logger.warning("Steam executable not found")
                return False

            # For Linux, try to launch steam in a terminal emulator
            msg = "Launching Steam via 'steam' command in a terminal..."
            logger.info(msg)
            if status_callback:
                status_callback(msg)
            env = os.environ.copy()
            env["LD_LIBRARY_PATH"] = _libs + os.pathsep + env.get("LD_LIBRARY_PATH", "")

            _setup_snap_steam_env(env)

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
            except FileNotFoundError:
                logger.warning("Steam executable or terminal emulator not found")
                return False
        else:
            if not steam_exe.exists():
                logger.warning("Steam executable not found")
                return False
            msg = "Launching Steam..."
            logger.info(msg)
            if status_callback:
                status_callback(msg)
            env = os.environ.copy()
            if sys.platform.startswith("linux"):
                _setup_snap_steam_env(env)
            subprocess.Popen([str(steam_exe)], env=env)
        # Give Steam some initial time to start up before checking
        sleep(SLEEP_TIME)

        # First check if Steam processes are running after initial launch
        if _is_steam_running():
            logger.info("Steam processes detected after launch")
            # Give Steam a bit more time to fully initialize
            sleep(SLEEP_TIME)
            return True

        # Wait for Steam to start checks every SLEEP_TIME (15 seconds), MAX_ATTEMPTS (10 attempts).
        for attempt in range(MAX_ATTEMPTS):
            msg = f"Waiting for Steam to initialize ({attempt + 1}/{MAX_ATTEMPTS})..."
            logger.info(msg)
            if status_callback:
                status_callback(msg)
            sleep(SLEEP_TIME)
            # Check both process detection and API initialization
            if _is_steam_running():
                logger.info("Steam processes detected during API wait")
                # Give Steam a bit more time to fully initialize
                sleep(SLEEP_TIME)
                return True
            try:
                # Try to create a temporary Steamworks instance to test if Steam is ready
                from steamworks import STEAMWORKS  # type: ignore

                test_steamworks = STEAMWORKS()
                test_steamworks.initialize()
                test_steamworks.unload()
                msg = "Steam launched and API initialized successfully"
                logger.info(msg)
                if status_callback:
                    status_callback(msg)
                # Give Steam a bit more time to fully initialize
                sleep(SLEEP_TIME)
                return True
            except Exception as e:
                error_msg = f"{e.__class__.__name__}: {e}"
                logger.debug(
                    f"Steam API not ready yet (attempt {attempt + 1}/{MAX_ATTEMPTS}): {error_msg}"
                )
                # Log more details on the last attempt
                if attempt == MAX_ATTEMPTS - 1:
                    total_time = SLEEP_TIME + (MAX_ATTEMPTS * SLEEP_TIME)
                    logger.warning(
                        f"Steamworks initialization failed after {total_time} seconds: {error_msg}"
                    )
                    if "snap" in str(Path.home()):
                        logger.warning(
                            "Snap Steam detected - ensure you have a native Steam installation for Steamworks support"
                        )
                continue

        msg = "Steam failed to start within timeout"
        logger.warning(msg)
        if status_callback:
            status_callback(msg)
        return False

    except Exception as e:
        logger.warning(f"Error launching Steam: {e}")
        return False


def check_steam_available(
    _libs: str,
    status_callback: Callable[[str], None] | None = None,
) -> bool:
    """
    Check if Steam is available and running.

    Checks if Steam is running, and if not, attempts to launch it.
    Also checks for snap Steam incompatibility.

    Args:
        _libs: Path to the Steamworks library directory
        status_callback: Optional callback to emit progress messages to UI

    Returns:
        bool: True if Steam is available, False otherwise
    """
    # Check for snap Steam (incompatible with Steamworks)
    is_snap_steam = SNAP_STEAM_PATH.exists()

    if is_snap_steam and sys.platform.startswith("linux"):
        logger.warning(
            "Snap Steam detected. Snap Steam is incompatible with Steamworks due to sandboxing. "
            "Steam integration is unavailable."
        )
        # Show snap steam warning
        show_snap_steam_warning()
        return False

    # Check if Steam is running
    if not _is_steam_running():
        msg = "Steam is not running, attempting to launch..."
        logger.info(msg)
        if status_callback:
            status_callback(msg)
        if not _launch_steam(_libs, status_callback=status_callback):
            logger.error("Failed to launch Steam")
            # Show no steam warning
            show_no_steam_warning()
            return False

    return True

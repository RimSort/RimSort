import subprocess
import sys
from multiprocessing import Process
from os import getcwd
from pathlib import Path
from threading import Thread
from time import sleep, time
from typing import Any, Optional, Union

import psutil
from loguru import logger
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from app.utils.generic import launch_game_process
from app.views.dialogue import show_warning

# If we're running from a Python interpreter, makesure steamworks module is in our sys.path ($PYTHONPATH)
# Ensure that this is available by running `git submodule update --init --recursive`
# You can automatically ensure this is done by utilizing distribute.py
if "__compiled__" not in globals():
    sys.path.append(str((Path(getcwd()) / "submodules" / "SteamworksPy")))

from steamworks import STEAMWORKS  # type: ignore

TRANSLATE = QCoreApplication.translate


def steam_translate(text: str) -> str:
    """
    Translate text using the SteamworksInterface context.
    """
    return TRANSLATE("SteamworksInterface", text)


def _show_warning_if_app(
    title: str, text: str, information: str | None = None, details: str | None = None
) -> None:
    """
    Show a warning dialog if a QApplication instance exists.
    """
    if QApplication.instance():
        show_warning(title=title, text=text, information=information, details=details)


def _find_steam_executable() -> Optional[Path]:
    if sys.platform == "win32":
        from app.utils.win_find_steam import find_steam_folder

        if find_steam_folder is None:
            return None
        steam_path, found = find_steam_folder()
        if not found:
            return None
        return Path(steam_path) / "steam.exe"
    elif sys.platform == "darwin":
        return Path("/Applications/Steam.app/Contents/MacOS/steam_osx")
    elif sys.platform.startswith("linux"):
        possible_paths = [
            Path.home() / ".steam" / "steam" / "steam.sh",
            Path("/usr/bin/steam"),
            Path("/usr/local/bin/steam"),
        ]
        for path in possible_paths:
            if path.exists():
                return path
        return None
    else:
        return None


def _is_steam_running() -> bool:
    """
    Check if Steam is currently running by looking for Steam processes.

    Returns:
        bool: True if Steam is running, False otherwise
    """
    if psutil is None:
        return False
    try:
        steam_processes = []
        for process in psutil.process_iter(attrs=["name", "exe"]):
            try:
                name = process.info["name"]
                exe = process.info["exe"]
                if name and "steam" in name.lower():
                    steam_processes.append(name)
                # Also check executable path for steam
                if exe and "steam" in exe.lower():
                    steam_processes.append(f"{name} ({exe})")
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                continue

        # Check for main Steam processes based on platform
        if sys.platform == "win32":
            steam_indicators = [
                "steam.exe",
                "steamservice.exe",
                "steamwebhelper.exe",
            ]
        elif sys.platform == "darwin":
            steam_indicators = [
                "steam_osx",
                "steamwebhelper",
            ]
        elif sys.platform.startswith("linux"):
            steam_indicators = [
                "steam",
                "steamwebhelper",
            ]
        else:
            steam_indicators = []

        for process in psutil.process_iter(attrs=["name"]):
            try:
                name = process.info["name"]
                if name in steam_indicators:
                    logger.debug(f"Found Steam process: {name}")
                    return True
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                continue

        logger.debug(f"Steam processes found: {steam_processes}")
        return False
    except Exception as e:
        logger.warning(f"Error checking if Steam is running: {e}")
        _show_warning_if_app(
            title=steam_translate("Steam Check Error"),
            text=steam_translate("Failed to check if Steam is running."),
            information=steam_translate("This may affect Steam integration features."),
            details=str(e),
        )
        return False


def _launch_steam(_libs: str | None = None) -> bool:
    """
    Launch Steam if it's not running and wait for it to start.

    Args:
        _libs: Path to the Steamworks library directory

    Returns:
        bool: True if Steam was launched successfully, False otherwise
    """
    try:
        steam_exe = _find_steam_executable()
        if steam_exe is None or not steam_exe.exists():
            logger.warning("Steam executable not found")
            return False

        logger.info("Launching Steam...")
        subprocess.Popen([str(steam_exe)], shell=True)
        # Give Steam some initial time to start up before checking
        sleep(15)

        # Wait for Steam to start (up to 60 seconds total, including initial delay)
        for attempt in range(45):
            sleep(1)
            try:
                # Try to create a temporary Steamworks instance to test if Steam is ready
                test_steamworks = STEAMWORKS(_libs=_libs)
                test_steamworks.initialize()
                test_steamworks.unload()
                logger.info("Steam launched and API initialized successfully")
                # Give Steam a bit more time to fully initialize
                sleep(5)
                return True
            except Exception as e:
                logger.debug(f"Steam API not ready yet (attempt {attempt + 1}/45): {e}")
                continue

        logger.warning("Steam failed to start within timeout")
        return False

    except Exception as e:
        logger.warning(f"Error launching Steam: {e}")
        _show_warning_if_app(
            title=steam_translate("Steam Launch Error"),
            text=steam_translate("Failed to launch Steam."),
            information=steam_translate(
                "Please ensure Steam is installed and try again."
            ),
            details=str(e),
        )
        return False


class SteamworksInterface:
    """
    A class object to handle our interactions with SteamworksPy

    https://github.com/philippj/SteamworksPy
    https://philippj.github.io/SteamworksPy/
    https://github.com/philippj/SteamworksPy/issues/62
    https://github.com/philippj/SteamworksPy/issues/75
    https://github.com/philippj/SteamworksPy/pull/76

    Thanks to Paladin for the example
    """

    def __init__(
        self,
        callbacks: bool,
        callbacks_total: int | None = None,
        _libs: str | None = None,
    ) -> None:
        logger.info("SteamworksInterface initializing...")
        self.callbacks = callbacks
        self.callbacks_count = 0
        self.callbacks_total = callbacks_total
        if self.callbacks:
            logger.debug("Callbacks enabled!")
            self.end_callbacks = False  # Signal used to end the _callbacks Thread
            if (
                self.callbacks_total
            ):  # Pass this if you want to do multiple actions with 1 initialization
                logger.debug(f"Callbacks total : {self.callbacks_total}")
                self.multiple_queries = True
            else:
                self.multiple_queries = False
        # Used for GetAppDependencies data
        self.get_app_deps_query_result: dict[int, Any] = {}
        self.steam_not_running = False  # Skip action if True. Log occurrences.
        self.steamworks = STEAMWORKS(_libs=_libs)
        try:
            self.steamworks.initialize()  # Init the Steamworks API
            self.steam_not_running = False
        except Exception as e:
            logger.warning(
                f"Unable to initialize Steamworks API due to exception: {e.__class__.__name__}"
            )
            _show_warning_if_app(
                title=steam_translate("Steamworks Initialization Error"),
                text=steam_translate("Failed to initialize Steamworks API."),
                information=steam_translate(
                    "Steam integration features may not work properly."
                ),
                details=str(e),
            )
            if not _is_steam_running():
                logger.info("Steam not running, attempting to launch...")
                if _launch_steam(_libs):
                    try:
                        self.steamworks.initialize()
                        self.steam_not_running = False
                        logger.info("Steamworks API initialized after launching Steam")
                    except Exception as e2:
                        logger.warning(
                            f"Failed to initialize Steamworks API even after launching Steam: {e2}"
                        )
                        _show_warning_if_app(
                            title=steam_translate("Steamworks Initialization Error"),
                            text=steam_translate(
                                "Failed to initialize Steamworks API after launching Steam."
                            ),
                            information=steam_translate(
                                "Please ensure Steam is properly installed and running."
                            ),
                            details=str(e2),
                        )
                        self.steam_not_running = True
                else:
                    logger.warning("Failed to launch Steam")
                    _show_warning_if_app(
                        title=steam_translate("Steam Launch Failed"),
                        text=steam_translate("Unable to launch Steam automatically."),
                        information=steam_translate(
                            "Please start Steam manually and try again."
                        ),
                        details="Steam executable not found or launch failed.",
                    )
                    self.steam_not_running = True
            else:
                logger.warning("Steam appears to be running but initialization failed")
                _show_warning_if_app(
                    title=steam_translate("Steamworks Initialization Error"),
                    text=steam_translate(
                        "Steam is running but API initialization failed."
                    ),
                    information=steam_translate(
                        "There may be an issue with Steam or the Steamworks library."
                    ),
                    details="Steam is running but initialization failed.",
                )
                self.steam_not_running = True
        if not self.steam_not_running:  # Skip if True
            if self.callbacks:
                # Start the thread
                logger.debug("Starting thread")
                self.steamworks_thread = self._daemon()
                self.steamworks_thread.start()

    def _callbacks(self) -> None:
        logger.debug("Starting _callbacks")
        while (
            not self.steamworks.loaded()
        ):  # This should not execute as long as Steamworks API init went OK
            logger.warning("Waiting for Steamworks...")
        else:
            logger.info("Steamworks loaded!")
        while not self.end_callbacks:
            self.steamworks.run_callbacks()
            sleep(0.1)
        else:
            logger.info(
                f"{self.callbacks_count} callback(s) received. Ending thread..."
            )

    # TODO: Rework this for proper static type checking
    def _cb_app_dependencies_result_callback(self, *args: Any, **kwargs: Any) -> None:
        """
        Executes upon Steamworks API callback response
        """
        # Add to callbacks count
        self.callbacks_count = self.callbacks_count + 1
        # Debug prints
        logger.debug(f"GetAppDependencies query callback: {args}, {kwargs}")
        logger.debug(f"result : {args[0].result}")
        pfid = args[0].publishedFileId
        logger.debug(f"publishedFileId : {pfid}")
        app_dependencies_list = args[0].get_app_dependencies_list()
        logger.debug(f"app_dependencies_list : {app_dependencies_list}")
        # Collect data for our query if dependencies were returned
        if len(app_dependencies_list) > 0:
            self.get_app_deps_query_result[pfid] = app_dependencies_list
        # Check for multiple actions
        if self.multiple_queries and self.callbacks_count == self.callbacks_total:
            # Set flag so that _callbacks cease
            self.end_callbacks = True
        elif not self.multiple_queries:
            # Set flag so that _callbacks cease
            self.end_callbacks = True

    def _cb_subscription_action(self, *args: Any, **kwargs: Any) -> None:
        """
        Executes upon Steamworks API callback response
        """
        # Add to callbacks count
        self.callbacks_count = self.callbacks_count + 1
        # Debug prints
        logger.debug(f"Subscription action callback: {args}, {kwargs}")
        logger.debug(f"result: {args[0].result}")
        logger.debug(f"PublishedFileId: {args[0].publishedFileId}")
        # Uncomment to see steam client install info of the mod
        # logger.info(
        #     self.steamworks.Workshop.GetItemInstallInfo(args[0].publishedFileId)
        # )
        # Check for multiple actions
        if self.multiple_queries and self.callbacks_count == self.callbacks_total:
            # Set flag so that _callbacks cease
            self.end_callbacks = True
        elif not self.multiple_queries:
            # Set flag so that _callbacks cease
            self.end_callbacks = True

    def _daemon(self) -> Thread:
        """
        Returns a Thread pointing to our _callbacks daemon
        """
        return Thread(target=self._callbacks, daemon=True)

    def _wait_for_callbacks(self, timeout: int) -> None:
        """
        Waits for the Steamworks API callbacks to complete within a specified time interval.

        Args:
            timeout (int): Maximum time to wait in seconds.

        Returns:
            None
        """
        start_time = time()
        logger.debug(f"Waiting {timeout} seconds for Steamworks API callbacks...")
        while self.steamworks_thread.is_alive():
            elapsed_time = time() - start_time
            if elapsed_time >= timeout:
                self.end_callbacks = True
                break
            sleep(1)


class SteamworksAppDependenciesQuery:
    def __init__(
        self,
        pfid_or_pfids: Union[int, list[int]],
        interval: int = 1,
        _libs: str | None = None,
    ) -> None:
        self._libs = _libs
        self.interval = interval
        self.pfid_or_pfids = pfid_or_pfids

    def run(self) -> None | dict[int, Any]:
        """
        Query PublishedFileIDs for AppID dependency data
        :param pfid_or_pfids: is an int that corresponds with a subscribed Steam mod's PublishedFileId
                            OR is a list of int that corresponds with multiple Steam mod PublishedFileIds
        :param interval: time in seconds to sleep between multiple subsequent API calls
        """
        logger.info(
            f"Creating SteamworksInterface and passing PublishedFileID(s) {self.pfid_or_pfids}"
        )
        # If the chunk passed is a single int, convert it into a list in an effort to simplify procedure
        if isinstance(self.pfid_or_pfids, int):
            self.pfid_or_pfids = [self.pfid_or_pfids]
        # Create our Steamworks interface and initialize Steamworks API
        steamworks_interface = SteamworksInterface(
            callbacks=True, callbacks_total=len(self.pfid_or_pfids), _libs=self._libs
        )
        if not steamworks_interface.steam_not_running:  # Skip if True
            while not steamworks_interface.steamworks.loaded():  # Ensure that Steamworks API is initialized before attempting any instruction
                break
            else:
                for pfid in self.pfid_or_pfids:
                    logger.debug(f"ISteamUGC/GetAppDependencies Query: {pfid}")
                    steamworks_interface.steamworks.Workshop.SetGetAppDependenciesResultCallback(
                        steamworks_interface._cb_app_dependencies_result_callback
                    )
                    steamworks_interface.steamworks.Workshop.GetAppDependencies(pfid)
                    # Sleep for the interval if we have more than one pfid to action on
                    if len(self.pfid_or_pfids) > 1:
                        sleep(self.interval)
                # Patience, but don't wait forever
                steamworks_interface._wait_for_callbacks(timeout=60)
                # This means that the callbacks thread has ended. We are done with Steamworks API now, so we dispose of everything.
                logger.info("Thread completed. Unloading Steamworks...")
                steamworks_interface.steamworks_thread.join()
                # Grab the data and return it
                logger.warning(
                    f"Returning {len(steamworks_interface.get_app_deps_query_result.keys())} results..."
                )
                return steamworks_interface.get_app_deps_query_result
        else:
            steamworks_interface.steamworks.unload()

        return None


class SteamworksGameLaunch(Process):
    def __init__(
        self, game_install_path: str, args: list[str], _libs: str | None = None
    ) -> None:
        Process.__init__(self)
        self._libs = _libs
        self.game_install_path = game_install_path
        self.args = args

    def run(self) -> None:
        """
        Handle SW game launch; instructions received from connected signals

        :param game_install_path: is a string path to the game folder
        :param args: is a string representing the args to pass to the generated executable path
        """
        logger.info("Creating SteamworksInterface and launching game executable")
        # Try to initialize the SteamWorks API, but allow game to launch if Steam not found
        steamworks_interface = SteamworksInterface(callbacks=False, _libs=self._libs)

        # Launch the game
        launch_game_process(
            game_install_path=Path(self.game_install_path), args=self.args
        )
        # If we had an API initialization, try to unload it
        if (
            not steamworks_interface.steam_not_running
            and steamworks_interface.steamworks
        ):
            # Unload Steamworks API
            steamworks_interface.steamworks.unload()


class SteamworksSubscriptionHandler:
    def __init__(
        self,
        action: str,
        pfid_or_pfids: Union[int, list[int]],
        interval: int = 1,
        _libs: str | None = None,
    ):
        # Optionally set _libs path for Steamworks
        self._libs = _libs
        self.action = action
        self.pfid_or_pfids = pfid_or_pfids
        self.interval = interval

    def run(self) -> None:
        """
        Handle Steam mod subscription actions received from connected signals

        :param action: is a string that corresponds with the following supported_actions[]
        :param pfid_or_pfids: is an int that corresponds with a subscribed Steam mod's PublishedFileId
                            OR is a list of int that corresponds with multiple Steam mod PublishedFileIds
        :param interval: time in seconds to sleep between multiple subsequent API calls
        """

        logger.info(
            f"Creating SteamworksInterface and passing instruction {self.action}"
        )
        # If the chunk passed is a single int, convert it into a list in an effort to simplify procedure
        if isinstance(self.pfid_or_pfids, int):
            self.pfid_or_pfids = [self.pfid_or_pfids]
        # Create our Steamworks interface and initialize Steamworks API
        # If we are resubscribing, it's actually 2 callbacks to expect per pfid, because it is 2 API calls
        if self.action == "resubscribe":
            callbacks_total = len(self.pfid_or_pfids) * 2  # per API call
        # Otherwise we only expect a single callback for each API call
        else:
            callbacks_total = len(self.pfid_or_pfids)
        steamworks_interface = SteamworksInterface(
            callbacks=True, callbacks_total=callbacks_total, _libs=self._libs
        )
        if not steamworks_interface.steam_not_running:  # Skip if True
            while not steamworks_interface.steamworks.loaded():  # Ensure that Steamworks API is initialized before attempting any instruction
                break
            else:
                if self.action == "resubscribe":
                    for pfid in self.pfid_or_pfids:
                        logger.debug(
                            f"ISteamUGC/UnsubscribeItem + SubscribeItem Action : {pfid}"
                        )
                        # Point Steamworks API callback response to our functions
                        steamworks_interface.steamworks.Workshop.SetItemUnsubscribedCallback(
                            steamworks_interface._cb_subscription_action
                        )
                        steamworks_interface.steamworks.Workshop.SetItemSubscribedCallback(
                            steamworks_interface._cb_subscription_action
                        )
                        # Create API calls
                        steamworks_interface.steamworks.Workshop.UnsubscribeItem(pfid)
                        sleep(self.interval)
                        steamworks_interface.steamworks.Workshop.SubscribeItem(pfid)
                        # Sleep for the interval if we have more than one pfid to action on
                        if len(self.pfid_or_pfids) > 1:
                            sleep(self.interval)
                elif self.action == "subscribe":
                    for pfid in self.pfid_or_pfids:
                        logger.debug(f"ISteamUGC/SubscribeItem Action : {pfid}")
                        # Point Steamworks API callback response to our functions
                        steamworks_interface.steamworks.Workshop.SetItemSubscribedCallback(
                            steamworks_interface._cb_subscription_action
                        )
                        # Create API calls
                        steamworks_interface.steamworks.Workshop.SubscribeItem(pfid)
                        # Sleep for the interval if we have more than one pfid to action on
                        if len(self.pfid_or_pfids) > 1:
                            sleep(self.interval)
                elif self.action == "unsubscribe":
                    for pfid in self.pfid_or_pfids:
                        logger.debug(f"ISteamUGC/UnsubscribeItem Action : {pfid}")
                        # Point Steamworks API callback response to our functions
                        steamworks_interface.steamworks.Workshop.SetItemUnsubscribedCallback(
                            steamworks_interface._cb_subscription_action
                        )
                        # Create API calls
                        steamworks_interface.steamworks.Workshop.UnsubscribeItem(pfid)
                        # Sleep for the interval if we have more than one pfid to action on
                        if len(self.pfid_or_pfids) > 1:
                            sleep(self.interval)
                # Patience, but don't wait forever
                steamworks_interface._wait_for_callbacks(timeout=10)
                # This means that the callbacks thread has ended. We are done with Steamworks API now, so we dispose of everything.
                logger.info("Thread completed. Unloading Steamworks...")
                steamworks_interface.steamworks_thread.join()
                # Unload Steamworks API
                steamworks_interface.steamworks.unload()
        else:
            steamworks_interface.steamworks.unload()


if __name__ == "__main__":
    sys.exit()

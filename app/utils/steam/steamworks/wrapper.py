import sys
from multiprocessing import Process
from os import getcwd
from pathlib import Path
from threading import Thread
from time import sleep, time
from typing import Any, Union

from loguru import logger

# If we're running from a Python interpreter, makesure steamworks module is in our sys.path ($PYTHONPATH)
# Ensure that this is available by running `git submodule update --init --recursive`
# You can automatically ensure this is done by utilizing distribute.py
if "__compiled__" not in globals():
    sys.path.append(str((Path(getcwd()) / "submodules" / "SteamworksPy")))

from app.utils.generic import launch_game_process
from steamworks import STEAMWORKS  # type: ignore


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

    _instance: Union[None, "SteamworksInterface"] = None

    def __new__(cls, *args: Any, **kwargs: Any) -> "SteamworksInterface":
        """
        Create a new instance or return the existing singleton instance.

        :return: The singleton instance of SteamworksInterface
        """
        if cls._instance is None:
            cls._instance = super(SteamworksInterface, cls).__new__(cls)
        return cls._instance

    def __init__(self, _libs: str | None = None) -> None:
        """
        Initialize the SteamworksInterface singleton.

        :param _libs: Optional path to Steamworks libraries
        """
        # Prevent re-initialization
        if hasattr(self, "initialized"):
            return

        logger.info("SteamworksInterface initializing...")

        # One-time initialization
        self._libs = _libs
        self.steam_not_running = False
        self.steamworks = STEAMWORKS(_libs=_libs)

        try:
            self.steamworks.initialize()  # Init the Steamworks API
            logger.info("Steamworks API initialized successfully")
        except Exception as e:
            logger.warning(
                f"Unable to initialize Steamworks API due to exception: {e.__class__.__name__}"
            )
            logger.warning(
                "If you are a Steam user, please check that Steam is running and that you are logged in..."
            )
            self.steam_not_running = True

        # Initialize per-operation state
        self._reset_operation_state()
        self.initialized = True

    def _reset_operation_state(self) -> None:
        """Reset per-operation state between operations."""
        self.callbacks = False
        self.callbacks_count = 0
        self.callbacks_total: int | None = None
        self.end_callbacks = False
        self.multiple_queries = False
        self.get_app_deps_query_result: dict[int, Any] = {}
        self.steamworks_thread: Thread | None = None

    @classmethod
    def instance(cls, _libs: str | None = None) -> "SteamworksInterface":
        """
        Get or create singleton instance.

        :param _libs: Optional path to Steamworks libraries
        :return: The singleton instance of SteamworksInterface
        :raises ValueError: If instance already initialized with different _libs
        """
        if cls._instance is None:
            cls._instance = cls(_libs=_libs)
        elif _libs is not None and cls._instance._libs != _libs:
            raise ValueError(
                f"SteamworksInterface already initialized with different _libs. "
                f"Existing: {cls._instance._libs}, Requested: {_libs}"
            )
        return cls._instance

    def begin_callbacks(self, callbacks_total: int | None = None) -> None:
        """
        Start callback thread for current operation.

        :param callbacks_total: Total number of callbacks expected for this operation
        :raises RuntimeError: If callbacks are already in progress
        """
        if self.steam_not_running:
            return

        # Prevent concurrent operations from interfering with each other
        if self.callbacks:
            logger.error(
                "Cannot start new callback operation - callbacks already in progress!"
            )
            raise RuntimeError(
                "SteamworksInterface callbacks already in progress. "
                "Wait for current operation to complete before starting a new one."
            )

        self._reset_operation_state()
        self.callbacks = True
        self.callbacks_total = callbacks_total
        self.multiple_queries = bool(callbacks_total)
        self.end_callbacks = False

        logger.debug("Starting callback thread")
        self.steamworks_thread = self._daemon()
        self.steamworks_thread.start()

    def finish_callbacks(self, timeout: int = 60) -> None:
        """
        Wait for callbacks to complete and join thread.

        :param timeout: Maximum time to wait for callbacks in seconds
        """
        if not self.callbacks or self.steamworks_thread is None:
            return

        self._wait_for_callbacks(timeout)

        if self.steamworks_thread.is_alive():
            logger.warning("Callback thread timeout, forcing end")
            self.end_callbacks = True

        self.steamworks_thread.join(timeout=5)
        logger.info("Callback thread completed")
        self._reset_operation_state()

    def shutdown(self) -> None:
        """Shutdown Steamworks API. Called at app shutdown."""
        if hasattr(self, "steamworks") and self.steamworks:
            try:
                if self.steamworks.loaded():
                    logger.info("Shutting down Steamworks API")
                    self.steamworks.unload()
            except Exception as e:
                logger.error(f"Error during Steamworks shutdown: {e}")

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
        if self.steamworks_thread is None:
            return

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
            f"Querying PublishedFileID(s) {self.pfid_or_pfids} for app dependencies"
        )
        # If the chunk passed is a single int, convert it into a list in an effort to simplify procedure
        if isinstance(self.pfid_or_pfids, int):
            self.pfid_or_pfids = [self.pfid_or_pfids]

        # Get singleton instance
        steamworks_interface = SteamworksInterface.instance(_libs=self._libs)

        if not steamworks_interface.steam_not_running:
            while not steamworks_interface.steamworks.loaded():
                break
            else:
                try:
                    steamworks_interface.begin_callbacks(
                        callbacks_total=len(self.pfid_or_pfids)
                    )

                    for pfid in self.pfid_or_pfids:
                        logger.debug(f"ISteamUGC/GetAppDependencies Query: {pfid}")
                        steamworks_interface.steamworks.Workshop.SetGetAppDependenciesResultCallback(
                            steamworks_interface._cb_app_dependencies_result_callback
                        )
                        steamworks_interface.steamworks.Workshop.GetAppDependencies(
                            pfid
                        )
                        if len(self.pfid_or_pfids) > 1:
                            sleep(self.interval)

                    logger.warning(
                        f"Returning {len(steamworks_interface.get_app_deps_query_result.keys())} results..."
                    )
                    return steamworks_interface.get_app_deps_query_result
                finally:
                    # Ensure callbacks are always finished and state is reset
                    steamworks_interface.finish_callbacks(timeout=60)

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
        logger.info("Launching game with Steamworks API")

        # Get singleton (in child process, this creates process-local singleton)
        # This ensures Steam API is initialized before game launch
        SteamworksInterface.instance(_libs=self._libs)

        # Launch game
        launch_game_process(
            game_install_path=Path(self.game_install_path), args=self.args
        )

        # No explicit unload - process termination handles cleanup for child processes
        # Main process cleanup happens at app shutdown


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

        logger.info(f"Handling Steam subscription action: {self.action}")

        # If the chunk passed is a single int, convert it into a list in an effort to simplify procedure
        if isinstance(self.pfid_or_pfids, int):
            self.pfid_or_pfids = [self.pfid_or_pfids]

        # Calculate callbacks total
        callbacks_total = (
            len(self.pfid_or_pfids) * 2
            if self.action == "resubscribe"
            else len(self.pfid_or_pfids)
        )

        # Get singleton instance
        steamworks_interface = SteamworksInterface.instance(_libs=self._libs)

        if not steamworks_interface.steam_not_running:
            while not steamworks_interface.steamworks.loaded():
                break
            else:
                try:
                    steamworks_interface.begin_callbacks(
                        callbacks_total=callbacks_total
                    )

                    if self.action == "resubscribe":
                        for pfid in self.pfid_or_pfids:
                            logger.debug(
                                f"ISteamUGC/UnsubscribeItem + SubscribeItem Action: {pfid}"
                            )
                            steamworks_interface.steamworks.Workshop.SetItemUnsubscribedCallback(
                                steamworks_interface._cb_subscription_action
                            )
                            steamworks_interface.steamworks.Workshop.SetItemSubscribedCallback(
                                steamworks_interface._cb_subscription_action
                            )
                            steamworks_interface.steamworks.Workshop.UnsubscribeItem(
                                pfid
                            )
                            sleep(self.interval)
                            steamworks_interface.steamworks.Workshop.SubscribeItem(pfid)
                            if len(self.pfid_or_pfids) > 1:
                                sleep(self.interval)

                    elif self.action == "subscribe":
                        for pfid in self.pfid_or_pfids:
                            logger.debug(f"ISteamUGC/SubscribeItem Action: {pfid}")
                            steamworks_interface.steamworks.Workshop.SetItemSubscribedCallback(
                                steamworks_interface._cb_subscription_action
                            )
                            steamworks_interface.steamworks.Workshop.SubscribeItem(pfid)
                            if len(self.pfid_or_pfids) > 1:
                                sleep(self.interval)

                    elif self.action == "unsubscribe":
                        for pfid in self.pfid_or_pfids:
                            logger.debug(f"ISteamUGC/UnsubscribeItem Action: {pfid}")
                            steamworks_interface.steamworks.Workshop.SetItemUnsubscribedCallback(
                                steamworks_interface._cb_subscription_action
                            )
                            steamworks_interface.steamworks.Workshop.UnsubscribeItem(
                                pfid
                            )
                            if len(self.pfid_or_pfids) > 1:
                                sleep(self.interval)
                finally:
                    steamworks_interface.finish_callbacks(timeout=10)


if __name__ == "__main__":
    sys.exit()

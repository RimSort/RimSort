import sys
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

    def query_app_dependencies(
        self, pfid_or_pfids: Union[int, list[int]], interval: int = 1
    ) -> Union[dict[int, Any], None]:
        """
        Query Steam Workshop mod(s) for DLC/AppID dependency information.

        :param pfid_or_pfids: Single PublishedFileId or list of PublishedFileIds
        :param interval: Sleep interval between API calls (seconds)
        :return: Dict mapping PublishedFileId to app dependencies, or None
        """
        logger.info(f"Querying PublishedFileID(s) {pfid_or_pfids} for app dependencies")

        # Normalize to list
        pfids = [pfid_or_pfids] if isinstance(pfid_or_pfids, int) else pfid_or_pfids

        if self.steam_not_running or not self.steamworks.loaded():
            return None

        try:
            self._begin_callbacks(callbacks_total=len(pfids))

            for pfid in pfids:
                logger.debug(f"ISteamUGC/GetAppDependencies Query: {pfid}")
                self.steamworks.Workshop.SetGetAppDependenciesResultCallback(
                    self._cb_app_dependencies_result_callback
                )
                self.steamworks.Workshop.GetAppDependencies(pfid)
                if len(pfids) > 1:
                    sleep(interval)

            logger.info(
                f"Returning {len(self.get_app_deps_query_result.keys())} results..."
            )
            return self.get_app_deps_query_result
        finally:
            self._finish_callbacks(timeout=60)

    def subscribe_to_mods(
        self, pfid_or_pfids: Union[int, list[int]], interval: int = 1
    ) -> None:
        """Subscribe to Steam Workshop mod(s)."""
        self._handle_subscription_action("subscribe", pfid_or_pfids, interval)

    def unsubscribe_from_mods(
        self, pfid_or_pfids: Union[int, list[int]], interval: int = 1
    ) -> None:
        """Unsubscribe from Steam Workshop mod(s)."""
        self._handle_subscription_action("unsubscribe", pfid_or_pfids, interval)

    def resubscribe_to_mods(
        self, pfid_or_pfids: Union[int, list[int]], interval: int = 1
    ) -> None:
        """Resubscribe to Steam Workshop mod(s) (unsub then sub)."""
        self._handle_subscription_action("resubscribe", pfid_or_pfids, interval)

    def _handle_subscription_action(
        self, action: str, pfid_or_pfids: Union[int, list[int]], interval: int
    ) -> None:
        """Internal method to handle subscription actions with callback management."""
        logger.info(f"Handling Steam subscription action: {action}")

        pfids = [pfid_or_pfids] if isinstance(pfid_or_pfids, int) else pfid_or_pfids

        if self.steam_not_running or not self.steamworks.loaded():
            return

        callbacks_total = len(pfids) * 2 if action == "resubscribe" else len(pfids)

        try:
            self._begin_callbacks(callbacks_total=callbacks_total)

            if action == "resubscribe":
                for pfid in pfids:
                    logger.debug(f"ISteamUGC/UnsubscribeItem + SubscribeItem: {pfid}")
                    self.steamworks.Workshop.SetItemUnsubscribedCallback(
                        self._cb_subscription_action
                    )
                    self.steamworks.Workshop.SetItemSubscribedCallback(
                        self._cb_subscription_action
                    )
                    self.steamworks.Workshop.UnsubscribeItem(pfid)
                    sleep(interval)
                    self.steamworks.Workshop.SubscribeItem(pfid)
                    if len(pfids) > 1:
                        sleep(interval)

            elif action == "subscribe":
                for pfid in pfids:
                    logger.debug(f"ISteamUGC/SubscribeItem: {pfid}")
                    self.steamworks.Workshop.SetItemSubscribedCallback(
                        self._cb_subscription_action
                    )
                    self.steamworks.Workshop.SubscribeItem(pfid)
                    if len(pfids) > 1:
                        sleep(interval)

            elif action == "unsubscribe":
                for pfid in pfids:
                    logger.debug(f"ISteamUGC/UnsubscribeItem: {pfid}")
                    self.steamworks.Workshop.SetItemUnsubscribedCallback(
                        self._cb_subscription_action
                    )
                    self.steamworks.Workshop.UnsubscribeItem(pfid)
                    if len(pfids) > 1:
                        sleep(interval)
        finally:
            self._finish_callbacks(timeout=10)

    def launch_game(self, game_install_path: str, args: list[str]) -> None:
        """
        Initialize Steamworks API and launch the game.

        :param game_install_path: Path to game installation folder
        :param args: Launch arguments for the game
        """
        logger.info("Launching game with Steamworks API")

        # API already initialized in __init__, just launch game
        launch_game_process(game_install_path=Path(game_install_path), args=args)

    def _begin_callbacks(self, callbacks_total: Union[int, None] = None) -> None:
        """
        Start callback thread for current operation. INTERNAL USE ONLY.

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

    def _finish_callbacks(self, timeout: int = 60) -> None:
        """
        Wait for callbacks to complete and join thread. INTERNAL USE ONLY.

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


# Worker functions for multiprocessing


def steamworks_app_dependencies_worker(
    pfid_or_pfids: Union[int, list[int]],
    interval: int = 1,
    _libs: Union[str, None] = None,
) -> Union[dict[int, Any], None]:
    """
    Worker for querying app dependencies in multiprocessing pool.

    :param pfid_or_pfids: Single PublishedFileId or list of PublishedFileIds
    :param interval: Sleep interval between API calls (seconds)
    :param _libs: Optional path to Steamworks libraries
    :return: Dict mapping PublishedFileId to app dependencies, or None
    """
    steamworks_interface = SteamworksInterface.instance(_libs=_libs)
    return steamworks_interface.query_app_dependencies(pfid_or_pfids, interval)


def steamworks_subscription_worker(
    action: str,
    pfid_or_pfids: Union[int, list[int]],
    interval: int = 1,
    _libs: Union[str, None] = None,
) -> None:
    """
    Worker for subscription actions in multiprocessing pool.

    :param action: "subscribe", "unsubscribe", or "resubscribe"
    :param pfid_or_pfids: Single PublishedFileId or list of PublishedFileIds
    :param interval: Sleep interval between API calls (seconds)
    :param _libs: Optional path to Steamworks libraries
    """
    steamworks_interface = SteamworksInterface.instance(_libs=_libs)

    if action == "subscribe":
        steamworks_interface.subscribe_to_mods(pfid_or_pfids, interval)
    elif action == "unsubscribe":
        steamworks_interface.unsubscribe_from_mods(pfid_or_pfids, interval)
    elif action == "resubscribe":
        steamworks_interface.resubscribe_to_mods(pfid_or_pfids, interval)
    else:
        logger.error(f"Unknown subscription action: {action}")


def steamworks_game_launch_worker(
    game_install_path: str,
    args: list[str],
    _libs: Union[str, None] = None,
) -> None:
    """
    Worker for launching game in separate process.

    :param game_install_path: Path to game installation folder
    :param args: Launch arguments for the game
    :param _libs: Optional path to Steamworks libraries
    """
    steamworks_interface = SteamworksInterface.instance(_libs=_libs)
    steamworks_interface.launch_game(game_install_path, args)


if __name__ == "__main__":
    sys.exit()

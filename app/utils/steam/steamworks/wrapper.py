import sys
from multiprocessing import Process
from os import getcwd
from pathlib import Path
from threading import Thread
from time import sleep
from typing import Union

from loguru import logger

# If we're running from a Python interpreter, makesure steamworks module is in our sys.path ($PYTHONPATH)
# Ensure that this is available by running `git submodule update --init --recursive`
# You can automatically ensure this is done by utilizing distribute.py
if "__compiled__" not in globals():
    sys.path.append(str((Path(getcwd()) / "submodules" / "SteamworksPy")))

from steamworks import STEAMWORKS
from app.utils.generic import launch_game_process


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

    def __init__(self, callbacks: bool, callbacks_total=None, _libs=None):
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
        self.get_app_deps_query_result = {}
        self.steam_not_running = False  # Skip action if True. Log occurrences.
        self.steamworks = STEAMWORKS(_libs=_libs)
        try:
            self.steamworks.initialize()  # Init the Steamworks API
        except Exception as e:
            logger.warning(
                f"Unable to initialize Steamworks API due to exception: {e.__class__.__name__}"
            )
            logger.warning(
                "If you are a Steam user, please check that Steam running and that you are logged in..."
            )
            self.steam_not_running = True
        if not self.steam_not_running:  # Skip if True
            if self.callbacks:
                # Start the thread
                logger.debug("Starting thread")
                self.steamworks_thread = self._daemon()
                self.steamworks_thread.start()

    def _callbacks(self):
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

    def _cb_app_dependencies_result_callback(self, *args, **kwargs) -> None:
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

    def _cb_subscription_action(self, *args, **kwargs) -> None:
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
        # While the thread is alive, we wait for it.
        tick = 0
        while self.steamworks_thread.is_alive():
            if (
                tick == timeout
            ):  # Wait the specified interval without additional responses before we quit forcefully
                self.end_callbacks = True
                break
            else:
                tick += 1
                logger.debug(
                    f"Waiting for Steamworks API callbacks to complete {tick} : [{self.callbacks_count}/{self.callbacks_total}]"
                )
                sleep(1)


class SteamworksAppDependenciesQuery:
    def __init__(self, pfid_or_pfids: Union[int, list], interval=1, _libs=None):
        self._libs = _libs
        self.interval = interval
        self.pfid_or_pfids = pfid_or_pfids

    def run(self) -> dict:
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
            while (
                not steamworks_interface.steamworks.loaded()
            ):  # Ensure that Steamworks API is initialized before attempting any instruction
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
            steamworks_interface = None


class SteamworksGameLaunch(Process):
    def __init__(self, game_install_path: str, args: list, _libs=None) -> None:
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
        logger.info(f"Creating SteamworksInterface and launching game executable")
        # Try to initialize the SteamWorks API, but allow game to launch if Steam not found
        steamworks_interface = SteamworksInterface(callbacks=False, _libs=self._libs)
        if steamworks_interface.steam_not_running:  # Delete if true
            steamworks_interface = None
        # Launch the game
        launch_game_process(
            game_install_path=Path(self.game_install_path), args=self.args
        )
        # If we had an API initialization, try to unload it
        if steamworks_interface and steamworks_interface.steamworks:
            # Unload Steamworks API
            steamworks_interface.steamworks.unload()
        else:
            steamworks_interface = None


class SteamworksSubscriptionHandler:
    def __init__(
        self, action: str, pfid_or_pfids: Union[int, list], interval=1, _libs=None
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
        # If we are resubscribing, it's actually 3 callbacks to expect per pfid
        if self.action == "resubscribe":
            callbacks_total = len(self.pfid_or_pfids) * 3  # per API call
        elif (
            self.action == "unsubscribe"
        ):  # If we are unsubscribing, it's actually 2 callbacks to expect per pfid
            callbacks_total = len(self.pfid_or_pfids) * 2  # per API call
        # Otherwise we only expect a single callback for each mod
        else:
            callbacks_total = len(self.pfid_or_pfids)
        steamworks_interface = SteamworksInterface(
            callbacks=True, callbacks_total=callbacks_total, _libs=self._libs
        )
        if not steamworks_interface.steam_not_running:  # Skip if True
            while (
                not steamworks_interface.steamworks.loaded()
            ):  # Ensure that Steamworks API is initialized before attempting any instruction
                break
            else:
                if self.action == "resubscribe":
                    for pfid in self.pfid_or_pfids:
                        logger.debug(
                            f"ISteamUGC/UnsubscribeItem x2 + SubscribeItem Action : {pfid}"
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
                        steamworks_interface.steamworks.Workshop.UnsubscribeItem(pfid)
                        sleep(
                            5
                        )  # Wait for a few seconds while Steam does its thing, then subscribe again
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
                        sleep(self.interval)
                        steamworks_interface.steamworks.Workshop.UnsubscribeItem(pfid)
                        # Sleep for the interval if we have more than one pfid to action on
                        if len(self.pfid_or_pfids) > 1:
                            sleep(self.interval)
                # Patience, but don't wait forever
                steamworks_interface._wait_for_callbacks(timeout=60)
                # This means that the callbacks thread has ended. We are done with Steamworks API now, so we dispose of everything.
                logger.info("Thread completed. Unloading Steamworks...")
                steamworks_interface.steamworks_thread.join()
                # Unload Steamworks API
                steamworks_interface.steamworks.unload()
        else:
            steamworks_interface.steamworks.unload()
            steamworks_interface = None


if __name__ == "__main__":
    sys.exit()

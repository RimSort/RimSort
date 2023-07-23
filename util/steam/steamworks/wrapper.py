from logger_tt import logger
from multiprocessing import current_process, Process, Queue
import os
import platform
import subprocess
from threading import Thread
from time import sleep
from typing import Union
import sys

from steamworks import STEAMWORKS
from steamworks.exceptions import SteamNotRunningException
import traceback
from util.generic import launch_game_process

from model.dialogue import show_warning

# print(f"steamworks.wrapper: {current_process()}")
# print(f"__name__: {__name__}\n")
# print(f"sys.argv: {sys.argv}")


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

    def __init__(self, callbacks: bool, callbacks_total=None):
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
        self.steamworks = STEAMWORKS()
        try:
            self.steamworks.initialize()  # Init the Steamworks API
        except Exception as e:
            if e.__class__ == OSError or e.__class__ == SteamNotRunningException:
                logger.warning(
                    "Unable to initiate Steamworks API. If you are a Steam user, please check that Steam running and that you are logged in..."
                )
                self.steam_not_running = True
            else:
                raise e
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
    def __init__(self, pfid_or_pfids: Union[int, list], interval=1):
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
        if isinstance(self.pfid_or_pfids, int):
            steamworks_interface = SteamworksInterface(callbacks=True)
            multiple_queries = False
        elif isinstance(self.pfid_or_pfids, list):
            steamworks_interface = SteamworksInterface(
                callbacks=True, callbacks_total=len(self.pfid_or_pfids)
            )
            multiple_queries = True
        if not steamworks_interface.steam_not_running:  # Skip if True
            while (
                not steamworks_interface.steamworks.loaded()
            ):  # Ensure that Steamworks API is initialized before attempting any instruction
                break
            else:
                if not multiple_queries:
                    logger.debug(
                        f"ISteamUGC/GetAppDependencies Query: {self.pfid_or_pfids}"
                    )
                    steamworks_interface.steamworks.Workshop.SetGetAppDependenciesResultCallback(
                        steamworks_interface._cb_app_dependencies_result_callback
                    )
                    steamworks_interface.steamworks.Workshop.GetAppDependencies(
                        self.pfid_or_pfids
                    )
                else:
                    for pfid in self.pfid_or_pfids:
                        logger.debug(f"ISteamUGC/GetAppDependencies Query: {pfid}")
                        steamworks_interface.steamworks.Workshop.SetGetAppDependenciesResultCallback(
                            steamworks_interface._cb_app_dependencies_result_callback
                        )
                        steamworks_interface.steamworks.Workshop.GetAppDependencies(
                            pfid
                        )
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
    def __init__(self, game_install_path: str, args: list) -> None:
        Process.__init__(self)
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
        steamworks_interface = SteamworksInterface(callbacks=False)
        if not steamworks_interface.steam_not_running:  # Delete if true
            steamworks_interface = None
        # Launch the game
        launch_game_process(game_install_path=self.game_install_path, args=self.args)
        # If we had an API initialization, try to unload it
        if steamworks_interface and steamworks_interface.steamworks:
            # Unload Steamworks API
            steamworks_interface.steamworks.unload()
        else:
            steamworks_interface.steamworks.unload()
            steamworks_interface = None


class SteamworksSubscriptionHandler:
    def __init__(self, action: str, pfid_or_pfids: Union[int, list], interval=1):
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
        if isinstance(self.pfid_or_pfids, int):
            steamworks_interface = SteamworksInterface(callbacks=True)
            multiple_actions = False
        elif isinstance(self.pfid_or_pfids, list):
            steamworks_interface = SteamworksInterface(
                callbacks=True, callbacks_total=len(self.pfid_or_pfids)
            )
            multiple_actions = True
        if not steamworks_interface.steam_not_running:  # Skip if True
            while (
                not steamworks_interface.steamworks.loaded()
            ):  # Ensure that Steamworks API is initialized before attempting any instruction
                break
            else:
                if self.action == "subscribe":
                    if not multiple_actions:
                        logger.debug(
                            f"ISteamUGC/SubscribeItem Action : {self.pfid_or_pfids}"
                        )
                        # Point Steamworks API callback response to our functions
                        steamworks_interface.steamworks.Workshop.SetItemSubscribedCallback(
                            steamworks_interface._cb_subscription_action
                        )
                        # Create API call
                        steamworks_interface.steamworks.Workshop.SubscribeItem(
                            self.pfid_or_pfids
                        )
                    else:
                        for pfid in self.pfid_or_pfids:
                            logger.debug(f"ISteamUGC/SubscribeItem Action : {pfid}")
                            # Point Steamworks API callback response to our functions
                            steamworks_interface.steamworks.Workshop.SetItemSubscribedCallback(
                                steamworks_interface._cb_subscription_action
                            )
                            # Create API call
                            steamworks_interface.steamworks.Workshop.SubscribeItem(pfid)
                            sleep(self.interval)
                elif self.action == "unsubscribe":
                    if not multiple_actions:
                        logger.debug(
                            f"ISteamUGC/UnsubscribeItem Action : {self.pfid_or_pfids}"
                        )
                        # Point Steamworks API callback response to our functions
                        steamworks_interface.steamworks.Workshop.SetItemUnsubscribedCallback(
                            steamworks_interface._cb_subscription_action
                        )
                        # Create API calls
                        steamworks_interface.steamworks.Workshop.UnsubscribeItem(
                            self.pfid_or_pfids
                        )
                    else:
                        for pfid in self.pfid_or_pfids:
                            logger.debug(f"ISteamUGC/UnsubscribeItem Action : {pfid}")
                            # Point Steamworks API callback response to our functions
                            steamworks_interface.steamworks.Workshop.SetItemUnsubscribedCallback(
                                steamworks_interface._cb_subscription_action
                            )
                            # Create API calls
                            steamworks_interface.steamworks.Workshop.UnsubscribeItem(
                                pfid
                            )
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

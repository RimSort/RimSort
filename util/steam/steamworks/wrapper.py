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

print(f"steamworks.wrapper: {current_process()}")
print(f"__name__: {__name__}\nsys.argv: {sys.argv}")


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
        except SteamNotRunningException:
            logger.warning(
                "Unable to initiate Steamworks API call. Steam is not responding/running!"
            )
            self.steam_not_running = True
        if not self.steam_not_running:  # Skip if True
            if self.callbacks:
                # Start the thread
                logger.info("Starting thread...")
                self.steamworks_thread = self._daemon()
                self.steamworks_thread.start()

    def _callbacks(self):
        logger.info("Starting _callbacks")
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
        # logger.debug(f"array_app_dependencies : {args[0].array_app_dependencies}")
        # logger.debug(
        #     f"array_num_app_dependencies : {args[0].array_num_app_dependencies}"
        # )
        # logger.debug(
        #     f"total_num_app_dependencies : {args[0].total_num_app_dependencies}"
        # )
        app_dependencies_list = args[0].get_app_dependencies_list()
        logger.debug(f"app_dependencies_list : {app_dependencies_list}")
        # Collect data for our query
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
        logger.info(
            self.steamworks.Workshop.GetItemInstallInfo(args[0].publishedFileId)
        )
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


class SteamworksAppDependenciesQuery(Process):
    def __init__(self, pfid_or_pfids: Union[int, list], queue: Queue) -> None:
        Process.__init__(self)
        self.pfid_or_pfids = pfid_or_pfids
        self.queue = queue

    def run(self) -> None:
        """
        Handle Steam mod get_app_dependencies instruction received from connected signals

        :param published_file_id: an int or list representing a PublishedFileID(s) to query
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
                        f"ISteamUGC/GetAppDependencies Query : {self.pfid_or_pfids}"
                    )
                    steamworks_interface.steamworks.Workshop.SetGetAppDependenciesResultCallback(
                        steamworks_interface._cb_app_dependencies_result_callback
                    )
                    steamworks_interface.steamworks.Workshop.GetAppDependencies(
                        self.pfid_or_pfids
                    )
                else:
                    for pfid in self.pfid_or_pfids:
                        logger.debug(f"ISteamUGC/GetAppDependencies Query : {pfid}")
                        steamworks_interface.steamworks.Workshop.SetGetAppDependenciesResultCallback(
                            steamworks_interface._cb_app_dependencies_result_callback
                        )
                        steamworks_interface.steamworks.Workshop.GetAppDependencies(
                            pfid
                        )
                        sleep(0.7)
                # While the thread is alive, we wait for it.
                tick = 0
                while steamworks_interface.steamworks_thread.is_alive():
                    if (
                        tick > 24
                    ):  # Wait ~2 min without additional responses before we quit forcefully
                        self.steamworks_interface.end_callbacks = True
                        break
                    else:
                        tick += 1
                        logger.debug(
                            f"Waiting for Steamworks API callbacks to complete [{steamworks_interface.callbacks_count}/{steamworks_interface.callbacks_total}]"
                        )
                        sleep(5)
                else:  # This means that the callbacks thread has ended. We are done with Steamworks API now, so we dispose of everything.
                    logger.info("Thread completed. Unloading Steamworks...")
                    steamworks_interface.steamworks_thread.join()
                    # If a non-empty query was returned, grab the data
                    if len(steamworks_interface.get_app_deps_query_result.keys()) > 0:
                        self.queue.put(steamworks_interface.get_app_deps_query_result)
                # Unload Steamworks API
                steamworks_interface.steamworks.unload()


class SteamworksGameLaunch(Process):
    def __init__(self, instruction: list) -> None:
        Process.__init__(self)
        self.instruction = instruction

    def run(self) -> None:
        """
        Handle SW game launch; instructions received from connected signals

        :param instruction: a list where:
            instruction[0] is a string path to the game folder
            instruction[1] is a string representing the args to pass to the generated executable path
        """
        logger.info(
            f"Creating SteamworksInterface and launching game instruction {self.instruction}"
        )
        steamworks_interface = SteamworksInterface(callbacks=False)
        if not steamworks_interface.steam_not_running:  # Skip if True
            while (
                not steamworks_interface.steamworks.loaded()
            ):  # Ensure that Steamworks API is initialized before attempting any instruction
                break
            else:
                # Launch the game
                launch_game_process(self.instruction)
                # Unload Steamworks API
                steamworks_interface.steamworks.unload()


class SteamworksSubscriptionHandler(Process):
    def __init__(self, instruction: list) -> None:
        Process.__init__(self)
        self.instruction = instruction

    def run(self) -> None:
        """
        Handle Steam mod subscription instructions received from connected signals

        :param instruction: a list where:
            instruction[0] is a string that corresponds with the following supported_actions[]
            instruction[1] is an int that corresponds with a subscribed Steam mod's PublishedFileId
                        OR is a list of int that corresponds with multiple subscribed Steam mod's PublishedFileId
        """
        logger.info(
            f"Creating SteamworksInterface and passing instruction {self.instruction}"
        )
        if isinstance(self.instruction[1], int):
            steamworks_interface = SteamworksInterface(callbacks=True)
            multiple_actions = False
        elif isinstance(self.instruction[1], list):
            steamworks_interface = SteamworksInterface(
                callbacks=True, callbacks_total=len(self.instruction[1])
            )
            multiple_actions = True
        if not steamworks_interface.steam_not_running:  # Skip if True
            while (
                not steamworks_interface.steamworks.loaded()
            ):  # Ensure that Steamworks API is initialized before attempting any instruction
                break
            else:
                if self.instruction[0] == "subscribe":
                    if not multiple_actions:
                        logger.debug(
                            f"ISteamUGC/SubscribeItem Action : {self.instruction[1]}"
                        )
                        # Point Steamworks API callback response to our functions
                        steamworks_interface.steamworks.Workshop.SetItemSubscribedCallback(
                            steamworks_interface._cb_subscription_action
                        )
                        # Create API call
                        steamworks_interface.steamworks.Workshop.SubscribeItem(
                            self.instruction[1]
                        )
                    else:
                        for pfid in self.instruction[1]:
                            logger.debug(f"ISteamUGC/SubscribeItem Action : {pfid}")
                            # Point Steamworks API callback response to our functions
                            steamworks_interface.steamworks.Workshop.SetItemSubscribedCallback(
                                steamworks_interface._cb_subscription_action
                            )
                            # Create API call
                            steamworks_interface.steamworks.Workshop.SubscribeItem(pfid)
                            sleep(0.7)
                elif self.instruction[0] == "unsubscribe":
                    if not multiple_actions:
                        logger.debug(
                            f"ISteamUGC/UnsubscribeItem Action : {self.instruction[1]}"
                        )
                        # Point Steamworks API callback response to our functions
                        steamworks_interface.steamworks.Workshop.SetItemUnsubscribedCallback(
                            steamworks_interface._cb_subscription_action
                        )
                        # Create API calls
                        steamworks_interface.steamworks.Workshop.UnsubscribeItem(
                            self.instruction[1]
                        )
                    else:
                        for pfid in self.instruction[1]:
                            logger.debug(f"ISteamUGC/UnsubscribeItem Action : {pfid}")
                            # Point Steamworks API callback response to our functions
                            steamworks_interface.steamworks.Workshop.SetItemUnsubscribedCallback(
                                steamworks_interface._cb_subscription_action
                            )
                            # Create API calls
                            steamworks_interface.steamworks.Workshop.UnsubscribeItem(
                                pfid
                            )
                            sleep(0.7)
                # While the thread is alive, we wait for it.
                tick = 0
                while steamworks_interface.steamworks_thread.is_alive():
                    if (
                        tick > 24
                    ):  # Wait ~2 min without additional responses before we quit forcefully
                        self.steamworks_interface.end_callbacks = True
                        break
                    else:
                        tick += 1
                        logger.debug(
                            f"Waiting for Steamworks API callbacks to complete [{steamworks_interface.callbacks_count}/{steamworks_interface.callbacks_total}]"
                        )
                        sleep(5)
                else:  # This means that the callbacks thread has ended. We are done with Steamworks API now, so we dispose of everything.
                    logger.info("Thread completed. Unloading Steamworks...")
                    steamworks_interface.steamworks_thread.join()
                # Unload Steamworks API
                steamworks_interface.steamworks.unload()


if __name__ == "__main__":
    sys.exit()

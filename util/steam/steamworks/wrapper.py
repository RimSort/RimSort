import logging
from threading import Thread
from time import sleep
import sys

from steamworks import STEAMWORKS
from steamworks.exceptions import SteamNotRunningException
import traceback

from util.error import show_warning

logger = logging.getLogger(__name__)


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

    def __init__(self):
        logger.info("SteamworksInterface initializing...")
        self.callback_received = False  # Signal used to end the _callbacks Thread
        self.steam_not_running = False  # Skip action if True. Log occurrences.
        self.steamworks = STEAMWORKS()
        try:
            self.steamworks.initialize()  # Init the Steamworks API
        except SteamNotRunningException:
            logger.warning(
                "Unable to initiate Steamworks API call. Steam is not running!"
            )
            self.steam_not_running = True
        if not self.steam_not_running:  # Skip if True
            # Point Steamworks API callback response to our functions
            self.steamworks.Workshop.SetItemSubscribedCallback(
                self._cb_subscription_action
            )
            self.steamworks.Workshop.SetItemUnsubscribedCallback(
                self._cb_subscription_action
            )
            # Start the thread
            logger.info("Starting thread...")
            self.steamworks_thread = self._daemon()
            self.steamworks_thread.start()

    def _callbacks(self):
        logger.info("Starting _callbacks")
        while (
            not self.steamworks.loaded()
        ):  # This should not execute as long as Steamworks API init went OK
            logger.info("Waiting for Steamworks...")
        else:
            logger.info("Steamworks loaded!")
        while not self.callback_received:
            self.steamworks.run_callbacks()
            sleep(0.1)
        else:
            logger.info("Callback received. Ending thread...")

    def _cb_subscription_action(self, *args, **kwargs) -> None:
        """
        Executes upon Steamworks API callback response
        """
        logger.info(f"Subscription action: {args}, {kwargs}")
        logger.info(
            f"Result: {args[0].result} PublishedFileId: {args[0].publishedFileId}"
        )
        # Set flag so that _callbacks cease
        self.callback_received = True

    def _daemon(self) -> Thread:
        """
        Returns a Thread pointing to our _callbacks daemon
        """
        return Thread(target=self._callbacks, daemon=True)


def steamworks_subscriptions_handler(instruction: list) -> None:
    """
    Handle Steam mod subscription instructions received from connected signals

    :param instruction: a list where:
        instruction[0] is a string that corresponds with the following supported_actions[]
        instruction[1] is an int that corresponds with a subscribed Steam mod's PublishedFileId
    """
    logger.info(f"Creating SteamworksInterface and passing instruction {instruction}")
    steamworks_interface = SteamworksInterface()
    if not steamworks_interface.steam_not_running:  # Skip if True
        while (
            not steamworks_interface.steamworks.loaded()
        ):  # Ensure that Steamworks API is initialized before attempting any instruction
            break
            sleep(0.1)
        else:
            if instruction[0] == "subscribe":
                steamworks_interface.steamworks.Workshop.SubscribeItem(
                    int(instruction[1])
                )
            elif instruction[0] == "unsubscribe":
                steamworks_interface.steamworks.Workshop.UnsubscribeItem(
                    int(instruction[1])
                )
            # Wait for thread to complete with 5 second timeout
            steamworks_interface.steamworks_thread.join(5)
            # While the thread is alive, we wait for it. This means that the above Thread.join() reached the timeout...
            # This is not good! Steam is not responding to your instruction!)
            if steamworks_interface.steamworks_thread.is_alive():
                logger.error("No response from Steam!")
            else:  # This means that Steam responded to our instruction. We are done with Steamworks API now, so we dispose of everything.
                logger.info("Thread completed. Unloading Steamworks...")
            steamworks_interface.steamworks.unload()


if __name__ == "__main__":
    sys.exit()

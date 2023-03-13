import logging
from threading import Thread
from time import sleep

from steamworks import STEAMWORKS

logger = logging.getLogger(__name__)


class SteamworksInterface:
    """
    https://github.com/philippj/SteamworksPy
    https://philippj.github.io/SteamworksPy/

    https://github.com/philippj/SteamworksPy/issues/62
    https://github.com/philippj/SteamworksPy/issues/75
    https://github.com/philippj/SteamworksPy/pull/76

    Thanks to Paladin for the example
    """

    def __init__(self):
        logger.info("SteamworksInterface initializing...")
        self.steamworks = STEAMWORKS()
        self.steamworks.initialize()
        self.steamworks.Workshop.SetItemSubscribedCallback(self._cb_subscription_action)
        self.steamworks.Workshop.SetItemUnsubscribedCallback(self._cb_subscription_action)
        logger.info("Starting daemon...")
        self.steamworks_thread = self._daemon()
        self.steamworks_thread.start()

    def _callbacks(self):
        while True:
            self.steamworks.run_callbacks()
            sleep(0.1)

    def _cb_subscription_action(self, *args, **kwargs) -> None:
        logger.info(f"Subscription action: {args}, {kwargs}")
        logger.info(f"Result: {args[0].result} PublishedFileId: {args[0].publishedFileId}")

    def _daemon(self) -> Thread:
        return Thread(target=self._callbacks, daemon=True)

from PySide6.QtCore import QObject, Slot


class JavaScriptBridge(QObject):
    """
    A minimal QObject to act as a bridge between QWebEngineView's JavaScript
    and the Python SteamBrowser class, exposing only specific methods.
    """
    def __init__(self, browser_instance, parent=None):
        super().__init__(parent)
        self._browser_instance = browser_instance

    @Slot(str, str)
    def add_mod_from_js(self, publishedfileid: str, mod_title: str):
        """
        Slot callable from JavaScript to add a mod to the download list.
        """
        self._browser_instance._add_mod_to_list(publishedfileid=publishedfileid, title=mod_title)

    @Slot(str)
    def remove_mod_from_js(self, mod_id: str) -> None:
        """
        Slot callable from JavaScript to remove a mod from the download list.
        """
        self._browser_instance._remove_mod_from_list(mod_id)

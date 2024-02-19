import os
import platform
from functools import partial
from typing import Any, Dict, Optional

from PySide6.QtCore import Qt, QPoint, QSize, QUrl, Signal
from PySide6.QtGui import QAction, QPixmap
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QToolBar,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
)
from loguru import logger

from app.models.dialogue import show_warning
from app.models.image_label import ImageLabel
from app.utils.app_info import AppInfo
from app.utils.steam.webapi.wrapper import (
    ISteamRemoteStorage_GetCollectionDetails,
    ISteamRemoteStorage_GetPublishedFileDetails,
)


class SteamBrowser(QWidget):
    """
    A generic panel used to browse Workshop content - downloader included
    """

    steamcmd_downloader_signal = Signal(list)
    steamworks_subscription_signal = Signal(list)

    def __init__(self, startpage: str):
        super().__init__()
        logger.debug("Initializing SteamBrowser")

        # This is used to fix issue described here on non-Windows platform:
        # https://doc.qt.io/qt-6/qtwebengine-platform-notes.html#sandboxing-support
        if platform.system() != "Windows":
            logger.info("Setting QTWEBENGINE_DISABLE_SANDBOX for non-Windows platform")
            os.environ["QTWEBENGINE_DISABLE_SANDBOX"] = "1"

        # VARIABLES
        self.current_html = ""
        self.current_title = "RimSort - Steam Browser"
        self.current_url = startpage

        self.downloader_list_mods_tracking = []
        self.downloader_list_dupe_tracking = {}
        self.startpage = QUrl(startpage)

        self.searchtext_string = "&searchtext="
        self.url_prefix_steam = "https://steamcommunity.com"
        self.url_prefix_sharedfiles = (
            "https://steamcommunity.com/sharedfiles/filedetails/?id="
        )
        self.url_prefix_workshop = (
            "https://steamcommunity.com/workshop/filedetails/?id="
        )

        # LAYOUTS
        self.window_layout = QHBoxLayout()
        self.browser_layout = QVBoxLayout()
        self.downloader_layout = QVBoxLayout()

        # DOWNLOADER WIDGETS
        self.downloader_label = QLabel("Mod Downloader")
        self.downloader_label.setObjectName("browserPaneldownloader_label")
        self.downloader_list = QListWidget()
        self.downloader_list.setFixedWidth(200)
        self.downloader_list.setItemAlignment(Qt.AlignCenter)
        self.downloader_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.downloader_list.customContextMenuRequested.connect(
            self._downloader_item_ContextMenuEvent
        )
        self.clear_list_button = QPushButton("Clear List")
        self.clear_list_button.setObjectName("browserPanelClearList")
        self.clear_list_button.clicked.connect(self._clear_downloader_list)
        self.download_steamcmd_button = QPushButton("Download mod(s) (SteamCMD)")
        self.download_steamcmd_button.clicked.connect(
            partial(
                self.steamcmd_downloader_signal.emit, self.downloader_list_mods_tracking
            )
        )
        self.download_steamworks_button = QPushButton("Download mod(s) (Steam app)")
        self.download_steamworks_button.clicked.connect(
            self._subscribe_to_mods_from_list
        )

        # BROWSER WIDGETS
        # "Loading..." placeholder
        self.web_view_loading_placeholder = ImageLabel()
        self.web_view_loading_placeholder.setAlignment(Qt.AlignCenter)
        self.web_view_loading_placeholder.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Expanding
        )
        self.web_view_loading_placeholder.setPixmap(
            QPixmap(
                str(AppInfo().theme_data_folder / "default-icons" / "AppIcon_b.png")
            )
        )
        # WebEngineView
        self.web_view = QWebEngineView()
        self.web_view.loadStarted.connect(self._web_view_load_started)
        self.web_view.loadProgress.connect(self._web_view_load_progress)
        self.web_view.loadFinished.connect(self._web_view_load_finished)
        self.web_view.setContextMenuPolicy(Qt.NoContextMenu)
        self.web_view.load(self.startpage)

        # Location box
        self.location = QLineEdit()
        self.location.setSizePolicy(
            QSizePolicy.Expanding, self.location.sizePolicy().verticalPolicy()
        )
        self.location.setText(self.startpage.url())
        self.location.returnPressed.connect(self.__browse_to_location)

        # Nav bar
        self.add_to_list_button = QAction("Add to list")
        self.add_to_list_button.triggered.connect(self._add_collection_or_mod_to_list)
        self.nav_bar = QToolBar()
        self.nav_bar.setObjectName("browserPanelnav_bar")
        self.nav_bar.addAction(self.web_view.pageAction(QWebEnginePage.Back))
        self.nav_bar.addAction(self.web_view.pageAction(QWebEnginePage.Forward))
        self.nav_bar.addAction(self.web_view.pageAction(QWebEnginePage.Stop))
        self.nav_bar.addAction(self.web_view.pageAction(QWebEnginePage.Reload))
        # self.nav_bar.addSeparator()
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)

        # Build the downloader layout
        self.downloader_layout.addWidget(self.downloader_label)
        self.downloader_layout.addWidget(self.downloader_list)
        self.downloader_layout.addWidget(self.clear_list_button)
        self.downloader_layout.addWidget(self.download_steamcmd_button)
        self.downloader_layout.addWidget(self.download_steamworks_button)

        # Build the browser layout
        self.browser_layout.addWidget(self.location)
        self.browser_layout.addWidget(self.nav_bar)
        self.browser_layout.addWidget(self.progress_bar)
        self.browser_layout.addWidget(self.web_view_loading_placeholder)
        self.browser_layout.addWidget(self.web_view)

        # Add our layouts to the main layout
        self.window_layout.addLayout(self.downloader_layout)
        self.window_layout.addLayout(self.browser_layout)

        self.setObjectName("browserPanel")
        # Put it all together
        self.setWindowTitle(self.current_title)
        self.setLayout(self.window_layout)
        self.setMinimumSize(QSize(800, 600))

    def __browse_to_location(self):
        url = QUrl(self.location.text())
        logger.debug(f"Browsing to: {url.url()}")
        self.web_view.load(url)

    def _add_collection_or_mod_to_list(self):
        # Ascertain the pfid depending on the url prefix
        if self.url_prefix_sharedfiles in self.current_url:
            publishedfileid = self.current_url.split(self.url_prefix_sharedfiles, 1)[1]
        elif self.url_prefix_workshop in self.current_url:
            publishedfileid = self.current_url.split(self.url_prefix_workshop, 1)[1]
        else:
            logger.error(f"Unable to parse pfid from url: {self.current_url}")
        # If there is extra data after the PFID, strip it
        if self.searchtext_string in publishedfileid:
            publishedfileid = publishedfileid.split(self.searchtext_string)[0]
        # Handle collection vs individual mod
        if "collectionItemDetails" not in self.current_html:
            self._add_mod_to_list(publishedfileid)
        else:
            # Use WebAPI to get titles for all the mods
            collection_mods_pfid_to_title = self.__compile_collection_datas(
                publishedfileid
            )
            if len(collection_mods_pfid_to_title) > 0:
                for pfid, title in collection_mods_pfid_to_title.items():
                    self._add_mod_to_list(publishedfileid=pfid, title=title)
            else:
                logger.warning(
                    "Empty list of mods returned, unable to add collection to list!"
                )
                show_warning(
                    title="SteamCMD downloader",
                    text="Empty list of mods returned, unable to add collection to list!",
                    information="Please reach out to us on Github Issues page or\n#rimsort-testing on the Rocketman/CAI discord",
                )
        if len(self.downloader_list_dupe_tracking.keys()) > 0:
            # Build a report from our dict
            dupe_report = ""
            for pfid, name in self.downloader_list_dupe_tracking.items():
                dupe_report = dupe_report + f"{name} | {pfid}\n"
            # Notify the user
            show_warning(
                title="SteamCMD downloader",
                text="You already have these mods in your download list!",
                information="Skipping the following mods which are already present in your download list!",
                details=dupe_report,
            )
            self.downloader_list_dupe_tracking = {}

    def __compile_collection_datas(self, publishedfileid: str) -> Dict[str, Any]:
        collection_mods_pfid_to_title = {}
        collection_webapi_result = ISteamRemoteStorage_GetCollectionDetails(
            [publishedfileid]
        )
        collection_pfids = []
        if len(collection_webapi_result) > 0:
            for mod in collection_webapi_result[0]["children"]:
                if mod.get("publishedfileid"):
                    collection_pfids.append(mod["publishedfileid"])
            if len(collection_pfids) > 0:
                collection_mods_webapi_response = (
                    ISteamRemoteStorage_GetPublishedFileDetails(collection_pfids)
                )
            else:
                return collection_mods_pfid_to_title
            for metadata in collection_mods_webapi_response:
                # Retrieve the published mod's title from the response
                pfid = metadata["publishedfileid"]
                collection_mods_pfid_to_title[pfid] = metadata["title"]
        return collection_mods_pfid_to_title

    def _add_mod_to_list(
        self,
        publishedfileid: str,
        title: Optional[str] = None,
    ):
        # Get the name from the page title
        page_title = self.current_title.split("Steam Workshop::", 1)[1]
        if publishedfileid not in self.downloader_list_mods_tracking:
            # Add pfid to tracking list
            logger.debug(f"Tracking PublishedFileId for download: {publishedfileid}")
            self.downloader_list_mods_tracking.append(publishedfileid)
            # Create our list item
            item = QListWidgetItem()
            item.setData(Qt.UserRole, publishedfileid)
            # Set list item label
            if not title:  # If title wasn't passed, get it from the web_view title
                label = QLabel(page_title)
                item.setToolTip(f"{label.text()}\n--> {self.current_url}")
            else:  # If the title passed, use it
                label = QLabel(title)
                item.setToolTip(
                    f"{label.text()}\n--> {self.url_prefix_sharedfiles}{publishedfileid}"
                )
            label.setObjectName("ListItemLabel")
            # Set the size hint of the item to be the size of the label
            item.setSizeHint(label.sizeHint())
            self.downloader_list.addItem(item)
            self.downloader_list.setItemWidget(item, label)
        else:
            logger.debug(
                f"Tried to add duplicate PFID to downloader list: {publishedfileid}"
            )
            if not publishedfileid in self.downloader_list_dupe_tracking.keys():
                if not title:
                    self.downloader_list_dupe_tracking[publishedfileid] = page_title
                else:
                    self.downloader_list_dupe_tracking[publishedfileid] = title

    def _clear_downloader_list(self) -> None:
        self.downloader_list.clear()
        self.downloader_list_mods_tracking = []
        self.downloader_list_dupe_tracking = {}

    def _downloader_item_ContextMenuEvent(self, point: QPoint) -> None:
        context_item = self.downloader_list.itemAt(point)

        if context_item:  # Check if the right-clicked point corresponds to an item
            context_menu = QMenu(self)  # Downloader item context menu event
            remove_item = context_menu.addAction("Remove mod from list")
            remove_item.triggered.connect(
                partial(self._remove_mod_from_list, context_item)
            )
            context_menu.exec_(self.downloader_list.mapToGlobal(point))

    def _remove_mod_from_list(self, context_item: QListWidgetItem) -> None:
        publishedfileid = context_item.data(Qt.UserRole)
        if publishedfileid in self.downloader_list_mods_tracking:
            self.downloader_list.takeItem(self.downloader_list.row(context_item))
            self.downloader_list_mods_tracking.remove(publishedfileid)
        else:
            logger.error("Steam Browser Error: Item not found in tracking list.")

    def _subscribe_to_mods_from_list(self) -> None:
        logger.debug(
            f"Signaling Steamworks subscription handler with {len(self.downloader_list_mods_tracking)} mods"
        )
        self.steamworks_subscription_signal.emit(
            [
                "subscribe",
                [eval(str_pfid) for str_pfid in self.downloader_list_mods_tracking],
            ]
        )

    def _web_view_load_started(self):
        # Progress bar start, placeholder start
        self.progress_bar.show()
        self.web_view.hide()
        self.web_view_loading_placeholder.show()

    def _web_view_load_progress(self, progress: int):
        # Progress bar progress
        self.progress_bar.setValue(progress)
        # Placeholder done after page begins to load
        if progress > 25:
            self.web_view_loading_placeholder.hide()
            self.web_view.show()

    def _web_view_load_finished(self):
        # Progress bar done
        self.progress_bar.hide()
        self.progress_bar.setValue(0)

        # Cache information from page
        self.current_title = self.web_view.title()
        self.web_view.page().toHtml(self.__set_current_html)
        self.current_url = self.web_view.url().toString()

        # Update UI elements
        self.setWindowTitle(self.current_title)
        self.location.setText(self.current_url)

        # Check if we are browsing a collection/mod - remove elements if found
        if self.url_prefix_steam in self.current_url:
            # Remove "Install Steam" button
            install_button_removal_script = """
            var elements = document.getElementsByClassName("header_installsteam_btn header_installsteam_btn_green");
            while (elements.length > 0) {
                elements[0].parentNode.removeChild(elements[0]);
            }
            """
            self.web_view.page().runJavaScript(
                install_button_removal_script, 0, lambda result: None
            )
            remove_top_banner = """
            var element = document.getElementById("global_header"); 
            var elements = document.getElementsByClassName("responsive_header")
            if (element) {
                element.parentNode.removeChild(element);
            }
            if (elements){
                elements[0].parentNode.removeChild(elements[0])
                document.getElementsByClassName("responsive_page_content")[0].setAttribute("style","padding-top: 0px;")
                document.getElementsByClassName("apphub_HeaderTop workshop")[0].setAttribute("style","padding-top: 0px;")
                document.getElementsByClassName("apphub_HomeHeaderContent")[0].setAttribute("style","padding-top: 0px;")
            }
            
            """
            self.web_view.page().runJavaScript(
                remove_top_banner, 0, lambda result: None
            )
            # change target <a>
            change_target_a_script = """
            var elements = document.getElementsByTagName("a");
            for (var i = 0, l = elements.length; i < l; i++) {
                elements[i].target = "_self";
            }
            """
            self.web_view.page().runJavaScript(
                change_target_a_script, 0, lambda result: None
            )
            # Remove "Login" button
            login_button_removal_script = """
            var elements = document.getElementsByClassName("global_action_link");
            while (elements.length > 0) {
                elements[0].parentNode.removeChild(elements[0]);
            }
            """
            if (
                self.url_prefix_sharedfiles in self.current_url
                or self.url_prefix_workshop in self.current_url
            ):
                # Remove area that shows "Subscribe to download" and "Subscribe"/"Unsubscribe" button for mods
                mod_subscribe_area_removal_script = """
                var elements = document.getElementsByClassName("game_area_purchase_game");
                while (elements.length > 0) {
                    elements[0].parentNode.removeChild(elements[0]);
                }
                """
                self.web_view.page().runJavaScript(
                    mod_subscribe_area_removal_script, 0, lambda result: None
                )
                # Remove area that shows "Subscribe to all" and "Unsubscribe to all" buttons for collections
                mod_unsubscribe_button_removal_script = """
                var elements = document.getElementsByClassName("subscribeCollection");
                while (elements.length > 0) {
                    elements[0].parentNode.removeChild(elements[0]);
                }
                """
                self.web_view.page().runJavaScript(
                    mod_unsubscribe_button_removal_script, 0, lambda result: None
                )
                # Remove "Subscribe" buttons from any mods shown in a collection
                subscribe_buttons_removal_script = """
                var elements = document.getElementsByClassName("general_btn subscribe");
                while (elements.length > 0) {
                    elements[0].parentNode.removeChild(elements[0]);
                }
                """
                self.web_view.page().runJavaScript(
                    subscribe_buttons_removal_script, 0, lambda result: None
                )
                # Show the add_to_list_button
                self.nav_bar.addAction(self.add_to_list_button)
            else:
                self.nav_bar.removeAction(self.add_to_list_button)

    def __set_current_html(self, html: str) -> None:
        # Update cached html with html from current page
        self.current_html = html

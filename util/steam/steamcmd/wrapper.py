from functools import partial
from io import BytesIO
from logger_tt import logger
import os
from pathlib import Path
import platform
import requests
import sys
import tarfile
from tempfile import gettempdir
from zipfile import ZipFile
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import Qt, QObject, QPoint, QSize, QUrl, Signal
from PySide6.QtGui import QAction, QPixmap
from PySide6.QtWebChannel import QWebChannel
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
import shutil

from model.dialogue import (
    show_dialogue_conditional,
    show_fatal_error,
    show_information,
    show_warning,
)
from model.image_label import ImageLabel
from util.steam.webapi.wrapper import (
    ISteamRemoteStorage_GetCollectionDetails,
    ISteamRemoteStorage_GetPublishedFileDetails,
)
from window.runner_panel import RunnerPanel


class SteamcmdDownloader(QWidget):
    """
    A generic panel used to browse web content
    """

    downloader_signal = Signal(list)

    def __init__(self, startpage: str):
        super().__init__()
        logger.info("Initializing SteamcmdDownloader")

        # This is used to fix issue described here on non-Windows platform:
        # https://doc.qt.io/qt-6/qtwebengine-platform-notes.html#sandboxing-support
        if platform.system() != "Windows":
            logger.info("Setting QTWEBENGINE_DISABLE_SANDBOX for non-Windows platform")
            os.environ["QTWEBENGINE_DISABLE_SANDBOX"] = "1"

        # VARIABLES
        self.current_html = ""
        self.current_title = "SteamCMD downloader"
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
        self.downloader_label = QLabel("SteamCMD downloader")
        self.downloader_list = QListWidget()
        self.downloader_list.setFixedWidth(140)
        self.downloader_list.setItemAlignment(Qt.AlignCenter)
        self.downloader_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.downloader_list.customContextMenuRequested.connect(
            self._downloader_item_ContextMenuEvent
        )
        self.clear_list_button = QPushButton("Clear List")
        self.clear_list_button.clicked.connect(self._clear_downloader_list)
        self.download_button = QPushButton("Download mod(s)")
        self.download_button.clicked.connect(
            partial(self.downloader_signal.emit, self.downloader_list_mods_tracking)
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
                os.path.join(
                    os.path.split(
                        os.path.split(os.path.split(os.path.dirname(__file__))[0])[0]
                    )[0],
                    "data",
                    "AppIcon_b.png",
                )
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
        self.location.setReadOnly(True)
        self.location.setSizePolicy(
            QSizePolicy.Expanding, self.location.sizePolicy().verticalPolicy()
        )
        self.location.setText(self.startpage.url())

        # Nav bar
        self.add_to_list_button = QAction("Add to list")
        self.add_to_list_button.triggered.connect(self._add_collection_or_mod_to_list)
        self.nav_bar = QToolBar()
        self.nav_bar.addAction(self.web_view.pageAction(QWebEnginePage.Back))
        self.nav_bar.addAction(self.web_view.pageAction(QWebEnginePage.Forward))
        self.nav_bar.addAction(self.web_view.pageAction(QWebEnginePage.Stop))
        self.nav_bar.addAction(self.web_view.pageAction(QWebEnginePage.Reload))
        self.nav_bar.addSeparator()
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)

        # Build the downloader layout
        self.downloader_layout.addWidget(self.downloader_label)
        self.downloader_layout.addWidget(self.downloader_list)
        self.downloader_layout.addWidget(self.clear_list_button)
        self.downloader_layout.addWidget(self.download_button)

        # Build the browser layout
        self.browser_layout.addWidget(self.location)
        self.browser_layout.addWidget(self.nav_bar)
        self.browser_layout.addWidget(self.progress_bar)
        self.browser_layout.addWidget(self.web_view_loading_placeholder)
        self.browser_layout.addWidget(self.web_view)

        # Add our layouts to the main layout
        self.window_layout.addLayout(self.downloader_layout)
        self.window_layout.addLayout(self.browser_layout)

        # Put it all together
        self.setWindowTitle(self.current_title)
        self.setLayout(self.window_layout)
        self.setMinimumSize(QSize(800, 600))

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
        if (
            collection_webapi_result["response"]["result"] == 1
            and collection_webapi_result["response"]["resultcount"] > 0
            and len(collection_webapi_result["response"]["collectiondetails"]) > 0
        ):
            for mod in collection_webapi_result["response"]["collectiondetails"][0][
                "children"
            ]:
                if mod.get("publishedfileid"):
                    collection_pfids.append(mod["publishedfileid"])
            if len(collection_pfids) > 0:
                collection_mods_webapi_response = (
                    ISteamRemoteStorage_GetPublishedFileDetails(collection_pfids)
                )
            else:
                return collection_mods_pfid_to_title
            for metadata in collection_mods_webapi_response["response"][
                "publishedfiledetails"
            ]:
                if metadata["result"] != 1:
                    logger.warning(
                        f"Invalid result returned from WebAPI: {collection_mods_webapi_response}"
                    )
                else:
                    # Retrieve the published mod's title from the response
                    pfid = metadata["publishedfileid"]
                    collection_mods_pfid_to_title[pfid] = metadata["title"]
        else:
            logger.warning(
                f"Invalid result returned from WebAPI: {collection_webapi_result}"
            )
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
            logger.debug(
                f"Downloader list tracking: {self.downloader_list_mods_tracking}"
            )
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
        context_menu = QMenu(self)  # Downloader item context menu event
        context_item = self.downloader_list.itemAt(point)
        remove_item = context_menu.addAction(
            "Remove mod from list"
        )  # Remove mod from list
        remove_item.triggered.connect(partial(self._remove_mod_from_list, context_item))
        action = context_menu.exec_(self.downloader_list.mapToGlobal(point))

    def _remove_mod_from_list(self, context_item: QListWidgetItem) -> None:
        publishedfileid = context_item.data(Qt.UserRole)
        if publishedfileid in self.downloader_list_mods_tracking:
            self.downloader_list.takeItem(self.downloader_list.row(context_item))
            self.downloader_list_mods_tracking.remove(publishedfileid)

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


class SteamcmdInterface:
    """
    Create SteamcmdInterface object to provide an interface for steamcmd functionality
    """

    def __init__(self, steamcmd_prefix: str, validate: bool) -> None:
        logger.info("SteamcmdInterface initilizing...")
        self.steamcmd_path = Path(steamcmd_prefix, "steamcmd").resolve()
        self.steamcmd_mods_path = Path(steamcmd_prefix, "steam").resolve()
        self.system = platform.system()
        self.validate_downloads = validate

        if self.system == "Darwin":
            self.steamcmd_url = (
                "https://steamcdn-a.akamaihd.net/client/installer/steamcmd_osx.tar.gz"
            )
            self.steamcmd = os.path.join(self.steamcmd_path, "steamcmd.sh")
        elif self.system == "Linux":
            self.steamcmd_url = (
                "https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz"
            )
            self.steamcmd = os.path.join(self.steamcmd_path, "steamcmd.sh")
        elif self.system == "Windows":
            self.steamcmd_url = (
                "https://steamcdn-a.akamaihd.net/client/installer/steamcmd.zip"
            )
            self.steamcmd = os.path.join(self.steamcmd_path, "steamcmd.exe")
        else:
            show_fatal_error(
                "SteamcmdInterface",
                f"Found platform {self.system}. steamcmd is not supported on this platform.",
            )
            return

        if not os.path.exists(self.steamcmd_path):
            os.makedirs(self.steamcmd_path)

        if not os.path.exists(self.steamcmd_mods_path):
            os.makedirs(self.steamcmd_mods_path)

    def download_mods(self, appid: str, publishedfileids: list, runner: RunnerPanel):
        """
        This function downloads a list of mods from a list publishedfileids

        https://developer.valvesoftware.com/wiki/SteamCMD

        :param appid: a Steam AppID to pass to steamcmd
        :param publishedfileids: list of publishedfileids
        :param runner: a RimSort RunnerPanel to interact with
        """
        runner.message("Checking for steamcmd...")
        if self.steamcmd is not None and os.path.exists(self.steamcmd):
            runner.message(
                f"Got it: {self.steamcmd}\n"
                + f"Downloading list of {str(len(publishedfileids))} "
                + f"publishedfileids to: {self.steamcmd_mods_path}"
            )
            script = [f"force_install_dir {self.steamcmd_mods_path}", "login anonymous"]
            for publishedfileid in publishedfileids:
                if self.validate_downloads:
                    script.append(
                        f"workshop_download_item {appid} {publishedfileid} validate"
                    )
                else:
                    script.append(f"workshop_download_item {appid} {publishedfileid}")
            script.extend(["quit\n"])
            tempdir = gettempdir()
            script_path = os.path.join(tempdir, "steamcmd_download_mods.txt")
            with open(script_path, "w") as script_output:
                script_output.write("\n".join(script))
            runner.message(f"Compiled & using script: {script_path}")
            runner.execute(self.steamcmd, [f"+runscript {script_path}"])
        else:
            runner.message("SteamCMD was not found. Please setup SteamCMD first!")

    def setup_steamcmd(
        self, symlink_source_path: str, reinstall: bool, runner: RunnerPanel
    ) -> None:
        installed = None
        if reinstall:
            runner.message("Existing steamcmd installation found!")
            runner.message(f"Deleting existing installation from: {self.steamcmd_path}")
            shutil.rmtree(self.steamcmd_path)
            os.makedirs(self.steamcmd_path)
            shutil.rmtree(self.steamcmd_mods_path)
            os.makedirs(self.steamcmd_mods_path)
        if not os.path.exists(self.steamcmd):
            try:
                runner.message(
                    f"Downloading & extracting steamcmd release from: {self.steamcmd_url}"
                )
                if ".zip" in self.steamcmd_url:
                    with ZipFile(
                        BytesIO(requests.get(self.steamcmd_url).content)
                    ) as zipobj:
                        zipobj.extractall(self.steamcmd_path)
                    runner.message(f"Installation completed")
                    installed = True
                elif ".tar.gz" in self.steamcmd_url:
                    with requests.get(
                        self.steamcmd_url, stream=True
                    ) as rx, tarfile.open(fileobj=rx.raw, mode="r:gz") as tarobj:
                        tarobj.extractall(self.steamcmd_path)
                    runner.message(f"Installation completed")
                    installed = True
            except:
                runner.message("Installation failed")
                show_fatal_error(
                    "SteamcmdInterface",
                    f"Failed to download steamcmd for {self.system}",
                    f"Did the file/url change?\nDoes your environment have access to the internet?",
                )
        else:
            runner.message("Steamcmd already installed...")
            show_warning(
                "SteamcmdInterface",
                f"A steamcmd runner already exists at: {self.steamcmd}",
            )
            answer = show_dialogue_conditional(
                "Reinstall?",
                "Would you like to reinstall steamcmd?",
                f"Existing install: {self.steamcmd_path}",
            )
            if answer == "&Yes":
                runner.message(f"Reinstalling steamcmd: {self.steamcmd_path}")
                self.setup_steamcmd(symlink_source_path, True, runner)
        if installed:
            workshop_content_path = os.path.join(
                self.steamcmd_mods_path, "steamapps", "workshop", "content"
            )
            if not os.path.exists(workshop_content_path):
                os.makedirs(workshop_content_path)
                runner.message(
                    f"Workshop content path does not exist. Creating for symlinking:\n\n{workshop_content_path}\n"
                )
            symlink_destination_path = os.path.join(workshop_content_path, "294100")
            runner.message(f"Symlink source : {symlink_source_path}")
            runner.message(f"Symlink destination: {symlink_destination_path}")
            if os.path.exists(symlink_destination_path):
                runner.message(
                    f"Symlink destination already exists! Please remove existing destination:\n\n{symlink_destination_path}\n"
                )
            else:
                answer = show_dialogue_conditional(
                    "Create symlink?",
                    "Would you like to create a symlink as followed?",
                    f"[{symlink_source_path}] -> " + symlink_destination_path,
                )
                if answer == "&Yes":
                    runner.message(
                        f"[{symlink_source_path}] -> " + symlink_destination_path
                    )
                    if self.system != "Windows":
                        os.symlink(
                            symlink_source_path,
                            symlink_destination_path,
                            target_is_directory=True,
                        )
                    else:
                        from _winapi import CreateJunction

                        CreateJunction(symlink_source_path, symlink_destination_path)

    def show_workshop_status(self, appid: str, runner: RunnerPanel):
        """
        This function shows steamcmd workshop mod status for the detected prefix

        https://developer.valvesoftware.com/wiki/SteamCMD

        :param appid: a Steam AppID to pass to steamcmd
        :param runner: a RimSort RunnerPanel to interact with
        """
        runner.message("Checking for steamcmd...")
        if self.steamcmd is not None and os.path.exists(self.steamcmd):
            runner.message(
                f"Got it: {self.steamcmd}\n"
                + f"Showing steamcmd workshop mod status for prefix: {self.steamcmd_mods_path}"
            )
            script = [
                f"force_install_dir {self.steamcmd_mods_path}",
                "login anonymous",
                f"workshop_status {appid}",
                "quit\n",
            ]
            tempdir = gettempdir()
            script_path = os.path.join(tempdir, "steamcmd_script.txt")
            with open(script_path, "w") as script_output:
                script_output.write("\n".join(script))
            runner.message(f"Compiled & using script: {script_path}")
            runner.execute(self.steamcmd, [f"+runscript {script_path}"])
        else:
            runner.message("SteamCMD was not found. Please setup SteamCMD first!")


if __name__ == "__main__":
    sys.exit()

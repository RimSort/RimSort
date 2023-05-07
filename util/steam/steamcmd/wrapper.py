from concurrent.futures import ThreadPoolExecutor
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

from PySide6.QtCore import Qt, QObject, QUrl, Signal
from PySide6.QtGui import QAction
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QToolBar,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
)

from model.dialogue import (
    show_dialogue_conditional,
    show_fatal_error,
    show_information,
    show_warning,
)
from window.runner_panel import RunnerPanel

import shutil


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

        # FOR CONVENIENCE
        self.current_url = startpage
        self.current_title = "steamcmd downloader"
        self.downloader_tracking_list = []

        # LAYOUTS
        self.window_layout = QHBoxLayout()
        self.browser_layout = QVBoxLayout()
        self.downloader_layout = QVBoxLayout()

        # DOWNLOADER WIDGETS
        self.downloader_label = QLabel("steamcmd downloader")
        self.downloader_list = QListWidget()
        self.downloader_list.setFixedWidth(140)
        self.downloader_list.setItemAlignment(Qt.AlignCenter)
        self.download_button = QPushButton("Download mod(s)")
        self.download_button.clicked.connect(
            partial(self.downloader_signal.emit, self.downloader_tracking_list)
        )

        # BROWSER WIDGETS
        self.web_view = QWebEngineView()
        # Location box
        self.location = QLineEdit(startpage)
        self.location.setSizePolicy(
            QSizePolicy.Expanding, self.location.sizePolicy().verticalPolicy()
        )
        self.location.returnPressed.connect(  # enter browses to url in location box
            partial(self._changeLocation, self.location.text())
        )
        # Nav bar
        self.add_to_list_button = QAction("Add to list")
        self.add_to_list_button.triggered.connect(self._add_to_list)
        self.nav_bar = QToolBar()
        self.nav_bar.addAction(self.web_view.pageAction(QWebEnginePage.Back))
        self.nav_bar.addAction(self.web_view.pageAction(QWebEnginePage.Forward))
        self.nav_bar.addAction(self.web_view.pageAction(QWebEnginePage.Stop))
        self.nav_bar.addAction(self.web_view.pageAction(QWebEnginePage.Reload))
        self.nav_bar.addSeparator()
        # WebEngine
        self.web_view.loadFinished.connect(self.view_load_finished)
        self.web_view.setContextMenuPolicy(Qt.NoContextMenu)
        self._changeLocation(startpage)  # Browse to the startpage passed to class

        # Build the downloader layout
        self.downloader_layout.addWidget(self.downloader_label)
        self.downloader_layout.addWidget(self.downloader_list)
        self.downloader_layout.addWidget(self.download_button)

        # Build the browser layout
        self.browser_layout.addWidget(self.location)
        self.browser_layout.addWidget(self.nav_bar)
        self.browser_layout.addWidget(self.web_view)

        # Add our layouts to the main layout
        self.window_layout.addLayout(self.downloader_layout)
        self.window_layout.addLayout(self.browser_layout)

        # Put it all together
        self.setWindowTitle(self.current_title)
        self.setLayout(self.window_layout)
        self.resize(800, 600)

    def _add_to_list(self):
        publishedfileid = self.current_url[self.current_url.index("=") + 1 :]
        print(publishedfileid)
        # use steam api
        Stapi = requests.post(
            "https://api.steampowered.com/ISteamRemoteStorage/GetCollectionDetails/v1/",
            data={"collectioncount": "1", "publishedfileids[0]": publishedfileid},
        )
        JRequest = Stapi.json()["response"]

        if JRequest["resultcount"] == 0:  # 0:item 1:collection
            logger.debug(f"Tried to add PFID to downloader list: {publishedfileid}")
            self._INTERNAL_add_to_list(
                publishedfileid, self.current_title.split("Steam Workshop::")[1]
            )

        elif JRequest["resultcount"] == 1:
            logger.debug(
                f"Tried to add all PFID of the collection to downloader list: {publishedfileid}"
            )
            IDcolReq = JRequest["collectiondetails"][0]["children"]
            ID = []
            for id in IDcolReq:
                ID = ID + [id["publishedfileid"]]

            with ThreadPoolExecutor() as execu:
                test = execu.map(self._INTERNALL_get_title, ID)
            for i1, i2 in test:
                self._INTERNAL_add_to_list(i1, i2)

    def _INTERNALL_get_title(self, ids):
        t = requests.get(
            "https://steamcommunity.com/sharedfiles/filedetails/?id=" + ids
        )
        t = t.text[t.text.index("<title>") + 7 : t.text.index("</title>") - 1].split(
            "Steam Workshop::"
        )[1]

        return ids, t

    def _INTERNAL_add_to_list(self, publishedfileid, name):
        if publishedfileid not in self.downloader_tracking_list:
            self.downloader_tracking_list.append(publishedfileid)
            logger.debug(f"Downloader list tracking: {self.downloader_tracking_list}")
            label = QLabel(name)
            label.setObjectName("ListItemLabel")
            item = QListWidgetItem()
            item.setSizeHint(
                label.sizeHint()
            )  # Set the size hint of the item to be the size of the label
            item.setToolTip(
                f"{label.text()}\n--> {'https://steamcommunity.com/sharedfiles/filedetails/?id='+str(publishedfileid)}"
            )
            item.setData(Qt.UserRole, publishedfileid)
            self.downloader_list.addItem(item)
            self.downloader_list.setItemWidget(item, label)
        else:
            show_warning(
                text="steamcmd downloader",
                information="You already have this mod in your download list!",
            )

    def _changeLocation(self, location: str):
        self.location.setText(location)
        self.web_view.load(QUrl(location))

    def view_load_finished(self):
        self.current_url = self.web_view.url().toString()
        self.current_title = self.web_view.title()
        self.setWindowTitle(self.current_title)
        if (
            "https://steamcommunity.com/sharedfiles/filedetails/?id="
            in self.current_url
        ):
            steamcmd_button_removal_script = """
            var to_replace = document.getElementById('SubscribeItemBtn');
            if (to_replace) {
                to_replace.parentNode.removeChild(to_replace);
            }
            """
            self.web_view.page().runJavaScript(
                steamcmd_button_removal_script, 0, lambda result: None
            )
            self.nav_bar.addAction(self.add_to_list_button)
        else:
            self.nav_bar.removeAction(self.add_to_list_button)


class SteamcmdInterface:
    """
    Create SteamcmdInterface object to provide an interface for steamcmd functionality
    """

    def __init__(self, storage_path: str) -> None:
        logger.info("SteamcmdInterface initilizing...")
        self.steamcmd_path = Path(storage_path, "steamcmd").resolve()
        self.system = platform.system()
        self.steamcmd_mods_path = Path(storage_path, "steam").resolve()

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

    def download_publishedfileids(
        self, appid: str, publishedfileids: list, runner: RunnerPanel
    ):
        """
        This function downloads a list of mods from a list publishedfileids

        https://developer.valvesoftware.com/wiki/SteamCMD

        :param appid: a Steam AppID to pass to steamcmd
        :param publishedfileids: list of publishedfileids
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
                script.append(f"workshop_download_item {appid} {publishedfileid}")
            script.extend(["quit\n"])
            tempdir = gettempdir()
            script_path = os.path.join(tempdir, "steamcmd_script.txt")
            with open(script_path, "w") as script_output:
                script_output.write("\n".join(script))
            runner.message(f"Compiled & using script: {script_path}")
            runner.execute(self.steamcmd, [f"+runscript {script_path}"])
        else:
            runner.message("steamcmd was not found. Please setup steamcmd first!")

    def setup_steamcmd(
        self, symlink_source_path: str, reinstall: bool, runner: RunnerPanel
    ) -> None:
        installed = None
        if reinstall:
            runner.message("Existing steamcmd installation found!")
            runner.message(f"Deleting existing installation from: {self.steamcmd_path}")
            shutil.rmtree(self.steamcmd_path)
            os.makedirs(self.steamcmd_path)
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


if __name__ == "__main__":
    sys.exit()

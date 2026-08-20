import json
import os
import platform
import re
from enum import Enum
from functools import partial
from pathlib import Path
from typing import Any

from loguru import logger
from PySide6.QtCore import QPoint, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QCloseEvent, QPixmap
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import (
    QWebEnginePage,
    QWebEngineProfile,
    QWebEngineScript,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtWidgets import QDialogButtonBox as ButtonBox

from app.controllers.metadata_controller import MetadataController
from app.models.image_label import ImageLabel
from app.models.settings import Settings
from app.utils.app_info import AppInfo
from app.utils.event_bus import EventBus
from app.utils.generic import extract_page_title_steam_browser
from app.utils.steam.webapi.wrapper import (
    ISteamRemoteStorage_GetCollectionDetails,
    ISteamRemoteStorage_GetPublishedFileDetails,
)
from app.utils.window_launch_state import apply_window_launch_state
from app.views.dialogue import show_dialogue_conditional, show_warning

from .js_bridge import JavaScriptBridge

URL_PREFIX_SHAREDFILES = "https://steamcommunity.com/sharedfiles/filedetails/?id="
URL_PREFIX_WORKSHOP = "https://steamcommunity.com/workshop/filedetails/?id="
SEARCHTEXT_STRING = "&searchtext="
CHROME_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def parse_publishedfileid_from_url(
    url: str,
    *,
    url_prefix_sharedfiles: str = URL_PREFIX_SHAREDFILES,
    url_prefix_workshop: str = URL_PREFIX_WORKSHOP,
    searchtext_string: str = SEARCHTEXT_STRING,
) -> str | None:
    """Extract a Steam publishedfileid from a workshop URL."""
    publishedfileid: str | None = None
    if url_prefix_sharedfiles in url:
        publishedfileid = url.split(url_prefix_sharedfiles, 1)[1]
    elif url_prefix_workshop in url:
        publishedfileid = url.split(url_prefix_workshop, 1)[1]
    else:
        return None
    if searchtext_string in publishedfileid:
        publishedfileid = publishedfileid.split(searchtext_string)[0]
    if "?" in publishedfileid:
        publishedfileid = publishedfileid.split("?")[0]
    if "/" in publishedfileid:
        publishedfileid = publishedfileid.split("/")[0]
    publishedfileid = publishedfileid.strip()
    return publishedfileid or None


class BadgeState(str, Enum):
    INSTALLED = "installed"
    ADDED = "added"
    DEFAULT = "default"


def resolve_workshop_page_mode(
    current_url: str,
    *,
    url_prefix_steam: str = "https://steamcommunity.com",
    url_prefix_sharedfiles: str = URL_PREFIX_SHAREDFILES,
    url_prefix_workshop: str = URL_PREFIX_WORKSHOP,
    section_readytouseitems: str = "section=readytouseitems",
    section_collections: str = "section=collections",
) -> str:
    """Classify the Steam workshop page for targeted JS injection."""
    if url_prefix_steam not in current_url:
        return "other"

    is_workshop_hub = (
        "/app/294100/workshop" in current_url
        and "/workshop/browse" not in current_url
        and "filedetails" not in current_url
    )
    is_collections_page = section_collections in current_url
    is_browse_grid = (
        section_readytouseitems in current_url
        or "/workshop/browse" in current_url
        or "/myworkshopfiles" in current_url
        or (not is_collections_page and "section=" in current_url)
    )
    is_item_page = url_prefix_sharedfiles in current_url
    is_collection_page = url_prefix_workshop in current_url

    if is_browse_grid:
        return "browse"
    if is_workshop_hub:
        return "hub"
    if is_item_page or is_collection_page:
        return "detail"
    return "other"


def toolbar_add_to_list_visible(
    current_url: str,
    *,
    url_prefix_steam: str = "https://steamcommunity.com",
    url_prefix_sharedfiles: str = URL_PREFIX_SHAREDFILES,
    url_prefix_workshop: str = URL_PREFIX_WORKSHOP,
    searchtext_string: str = SEARCHTEXT_STRING,
) -> bool:
    """Whether the toolbar Add to list action applies to the current page URL."""
    if url_prefix_steam not in current_url:
        return False
    is_item_page = url_prefix_sharedfiles in current_url
    is_collection_page = url_prefix_workshop in current_url
    if not (is_item_page or is_collection_page):
        return False
    return (
        parse_publishedfileid_from_url(
            current_url,
            url_prefix_sharedfiles=url_prefix_sharedfiles,
            url_prefix_workshop=url_prefix_workshop,
            searchtext_string=searchtext_string,
        )
        is not None
    )


def build_web_channel_script(
    *,
    installed_mods: list[str],
    added_mods: list[str],
    page_mode: str,
    script_path: Path,
    inject_delay_ms: int = 300,
) -> str:
    """Inject workshop badge script using marker replacement (safe for JS `$` syntax)."""
    raw_script = script_path.read_text(encoding="utf-8")
    js_badge_state = {member.name: member.value for member in BadgeState}
    replacements = {
        "@badge_state_js@": json.dumps(js_badge_state),
        "@page_mode@": page_mode,
        "@installed_mods@": json.dumps(installed_mods),
        "@added_mods@": json.dumps(added_mods),
        "@inject_delay_ms@": str(inject_delay_ms),
    }
    script = raw_script
    for marker, value in replacements.items():
        script = script.replace(marker, value)
    return script


class SteamBrowser(QWidget):
    """
    A generic panel used to browse Workshop content - downloader included
    """

    # Cleared in closeEvent when the window is closed.
    web_view: QWebEngineView | None
    web_profile: QWebEngineProfile | None
    metadata_controller: MetadataController | None
    settings: Settings | None
    js_bridge: JavaScriptBridge | None

    def __init__(
        self,
        startpage: str,
        metadata_controller: MetadataController,
        settings: Settings,
    ):
        super().__init__()
        logger.debug("Initializing SteamBrowser")

        # store metadata controller reference so we can use it to check if mods are installed
        self.metadata_controller = metadata_controller
        self.settings = settings

        # This is used to fix issue described here on non-Windows platform:
        # https://doc.qt.io/qt-6/qtwebengine-platform-notes.html#sandboxing-support
        if platform.system() != "Windows":
            logger.info("Setting QTWEBENGINE_DISABLE_SANDBOX for non-Windows platform")
            os.environ["QTWEBENGINE_DISABLE_SANDBOX"] = "1"

        # Add Mods by Workshop ID Button (always create, not just non-Windows)
        self.add_mods_by_id_button = QPushButton(self.tr("Add Mods by Workshop ID"))
        self.add_mods_by_id_button.setObjectName("browserPanelAddModsByID")
        self.add_mods_by_id_button.clicked.connect(self._show_add_mods_by_id_dialog)

        # VARIABLES
        profile_dir = Path(AppInfo()._browser_profile_folder)
        profile_dir.mkdir(parents=True, exist_ok=True)
        self._web_profile_storage = str(profile_dir)

        # Create persistent profile (persists cookies, localStorage, indexedDB, service workers)
        self.web_profile = QWebEngineProfile("SteamBrowserProfile", self)
        self.web_profile.setPersistentStoragePath(self._web_profile_storage)
        self.web_profile.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies
        )
        self.web_profile.setHttpUserAgent(CHROME_USER_AGENT)
        self._inject_steam_recovery_script()
        self.current_html = ""
        self.current_title = "RimSort - Steam Browser"
        self.current_url = startpage

        self.downloader_list_mods_tracking: list[str] = []
        self.downloader_list_dupe_tracking: dict[str, Any] = {}
        self.startpage = QUrl(startpage)

        self.searchtext_string = "&searchtext="
        self.url_prefix_steam = "https://steamcommunity.com"
        self.url_prefix_sharedfiles = (
            "https://steamcommunity.com/sharedfiles/filedetails/?id="
        )
        self.url_prefix_workshop = (
            "https://steamcommunity.com/workshop/filedetails/?id="
        )
        self.section_readytouseitems = "section=readytouseitems"
        self.section_collections = "section=collections"
        self._load_progress_fallback_timer: QTimer | None = None
        self._load_stall_timer: QTimer | None = None
        self._load_show_fallback_timer: QTimer | None = None
        self._load_stall_reloaded: bool = False

        # LAYOUTS
        self.window_layout = QHBoxLayout()
        self.browser_layout = QVBoxLayout()
        self.downloader_layout = QVBoxLayout()

        # DOWNLOADER WIDGETS
        self.downloader_label = QLabel(self.tr("Mod Downloader"))
        self.downloader_label.setObjectName("browserPaneldownloader_label")
        self.downloader_list = QListWidget()
        self.downloader_list.setFixedWidth(200)
        self.downloader_list.setItemAlignment(Qt.AlignmentFlag.AlignCenter)
        self.downloader_list.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.downloader_list.customContextMenuRequested.connect(
            self._downloader_item_contextmenu_event
        )
        self.downloader_list.itemDoubleClicked.connect(self._open_mod_url)
        self.add_to_list2_button = QPushButton(self.tr("Add to List"))
        self.add_to_list2_button.clicked.connect(self._add_collection_or_mod_to_list)
        self.clear_list_button = QPushButton(self.tr("Clear List"))
        self.clear_list_button.setObjectName("browserPanelClearList")
        self.clear_list_button.clicked.connect(self._clear_downloader_list)
        self.download_steamcmd_button = QPushButton(
            self.tr("Download mod(s) (SteamCMD)")
        )
        self.download_steamcmd_button.clicked.connect(
            partial(
                EventBus().do_steamcmd_download.emit,
                self.downloader_list_mods_tracking,
            )
        )
        self.download_steamworks_button = QPushButton(
            self.tr("Download mod(s) (Steam app)")
        )
        self.download_steamworks_button.clicked.connect(
            self._subscribe_to_mods_from_list
        )

        # BROWSER WIDGETS
        # "Loading..." placeholder
        self.web_view_loading_placeholder = ImageLabel()
        self.web_view_loading_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.web_view_loading_placeholder.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.web_view_loading_placeholder.setPixmap(
            QPixmap(
                str(AppInfo().theme_data_folder / "default-icons" / "AppIcon_b.png")
            )
        )
        # WebEngineView
        self.web_view = QWebEngineView()

        page = QWebEnginePage(self.web_profile, self.web_view)
        self.web_view.setPage(page)

        self.web_view.hide()
        self.web_view.loadStarted.connect(self._web_view_load_started)
        self.web_view.loadProgress.connect(self._web_view_load_progress)
        self.web_view.loadFinished.connect(self._web_view_load_finished)
        self.web_view.urlChanged.connect(self._on_web_view_url_changed)
        self.web_view.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)

        # QWebChannel setup
        self.channel = QWebChannel(self)
        self.js_bridge = JavaScriptBridge(self)
        self.channel.registerObject("browserBridge", self.js_bridge)
        self.web_view.page().setWebChannel(self.channel)

        # qwebchannel.js injection
        script = QWebEngineScript()
        script.setSourceUrl(QUrl("qrc:///qtwebchannel/qwebchannel.js"))
        script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        script.setRunsOnSubFrames(True)
        self.web_view.page().profile().scripts().insert(script)

        #  QWebEngineProfile.defaultProfile().setHttpAcceptLanguages

        # Location box
        self.location = QLineEdit()
        self.location.setSizePolicy(
            QSizePolicy.Policy.Expanding, self.location.sizePolicy().verticalPolicy()
        )
        self.location.setText(self.startpage.url())
        self.location.returnPressed.connect(self.__browse_to_location)

        # Nav bar
        self.add_to_list_button = QAction(self.tr("Add to list"))
        self.add_to_list_button.triggered.connect(self._add_collection_or_mod_to_list)
        self.nav_bar = QToolBar()
        self.nav_bar.setObjectName("browserPanelnav_bar")
        self.nav_bar.addAction(self.web_view.pageAction(QWebEnginePage.WebAction.Back))
        self.nav_bar.addAction(
            self.web_view.pageAction(QWebEnginePage.WebAction.Forward)
        )
        self.nav_bar.addAction(self.web_view.pageAction(QWebEnginePage.WebAction.Stop))
        self.nav_bar.addAction(
            self.web_view.pageAction(QWebEnginePage.WebAction.Reload)
        )
        # self.nav_bar.addSeparator()
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("browser")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setVisible(True)

        # Build the downloader layout
        self.downloader_layout.addWidget(self.downloader_label)
        self.downloader_layout.addWidget(self.downloader_list)
        self.downloader_layout.addWidget(self.add_to_list2_button)
        self.downloader_layout.addWidget(self.add_mods_by_id_button)
        self.downloader_layout.addWidget(self.download_steamcmd_button)
        self.downloader_layout.addWidget(self.download_steamworks_button)
        self.downloader_layout.addWidget(self.clear_list_button)

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

        # launch the browser window
        self._launch_browser_window()
        QTimer.singleShot(0, self._start_initial_load)
        logger.debug("Finished Browser Window initialization")

    def _start_initial_load(self) -> None:
        assert self.web_view is not None
        self.web_view.load(self.startpage)

    def _show_add_mods_by_id_dialog(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle(self.tr("Add Mods by Workshop ID"))
        layout = QVBoxLayout(dialog)
        label = QLabel(
            self.tr(
                "Enter one or more Workshop IDs (one per line or separated by commas):"
            )
        )
        layout.addWidget(label)
        text_edit = QTextEdit()
        layout.addWidget(text_edit)
        buttons = ButtonBox(
            ButtonBox.StandardButton.Ok | ButtonBox.StandardButton.Cancel
        )
        layout.addWidget(buttons)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            ids_text = text_edit.toPlainText()
            ids = re.split(r"[\s,]+", ids_text.strip())
            ids = [id_.strip() for id_ in ids if id_.strip()]
            for workshop_id in ids:
                self._add_mod_to_list(publishedfileid=workshop_id)

    def _launch_browser_window(self) -> None:
        """Apply browser window launch state from settings"""
        assert self.settings is not None
        browser_window_launch_state = self.settings.browser_window_launch_state
        custom_width = self.settings.browser_window_custom_width
        custom_height = self.settings.browser_window_custom_height

        apply_window_launch_state(
            self, browser_window_launch_state, custom_width, custom_height
        )
        logger.info(
            f"Browser window started with launch state: {browser_window_launch_state}"
        )

    def _get_effective_page_url(self) -> str:
        """Return the best available URL for the current browser page."""
        location_text = self.location.text().strip()
        if location_text:
            location_url = QUrl(location_text)
            if location_url.isValid() and location_url.scheme():
                return location_url.toString()
        assert self.web_view is not None
        web_view_url = self.web_view.url().toString()
        if web_view_url and web_view_url != "about:blank":
            return web_view_url
        return self.current_url

    def _normalize_browse_url(self, raw_url: str) -> str:
        """Normalize user-entered URL text before loading."""
        text = raw_url.strip()
        if not text:
            return text
        if not text.startswith(("http://", "https://")):
            text = f"https://{text}"
        return text

    def _on_web_view_url_changed(self, url: QUrl) -> None:
        self._sync_location_from_js(url.toString())

    def _sync_location_from_js(self, url: str) -> None:
        """Update the address bar from the page URL without triggering a reload."""
        text = (url or "").strip()
        if not text or text == "about:blank":
            return
        if self.current_url == text and self.location.text() == text:
            return
        self.current_url = text
        self.location.setText(text)
        self._update_toolbar_add_to_list_button(text)

    def _is_add_to_list_in_toolbar(self) -> bool:
        return any(
            action is self.add_to_list_button for action in self.nav_bar.actions()
        )

    def _update_toolbar_add_to_list_button(self, url: str) -> None:
        should_show = toolbar_add_to_list_visible(
            url,
            url_prefix_steam=self.url_prefix_steam,
            url_prefix_sharedfiles=self.url_prefix_sharedfiles,
            url_prefix_workshop=self.url_prefix_workshop,
            searchtext_string=self.searchtext_string,
        )
        in_toolbar = self._is_add_to_list_in_toolbar()
        if should_show and not in_toolbar:
            self.nav_bar.addAction(self.add_to_list_button)
        elif not should_show and in_toolbar:
            self.nav_bar.removeAction(self.add_to_list_button)

    def __browse_to_location(self) -> None:
        assert self.web_view is not None
        normalized = self._normalize_browse_url(self.location.text())
        url = QUrl(normalized)
        if not url.isValid():
            logger.warning(f"Invalid browse URL: {normalized}")
            return
        self.current_url = url.toString()
        self.location.setText(self.current_url)
        logger.debug(f"Browsing to: {self.current_url}")
        self.web_view.load(url)

    def _add_collection_or_mod_to_list(self) -> None:
        page_url = self._get_effective_page_url()
        publishedfileid = parse_publishedfileid_from_url(
            page_url,
            url_prefix_sharedfiles=self.url_prefix_sharedfiles,
            url_prefix_workshop=self.url_prefix_workshop,
            searchtext_string=self.searchtext_string,
        )
        if not publishedfileid:
            logger.error(f"Unable to parse publishedfileid from url: {page_url}")
            show_warning(
                title=self.tr("No publishedfileid found"),
                text=self.tr(
                    "Unable to parse publishedfileid from url, Please check if url is in the correct format"
                ),
                information=f"Url: {page_url}",
            )
            return None
        self.current_url = page_url
        # Handle collection vs individual mod
        if "collectionItemDetails" not in self.current_html:
            self._add_mod_to_list(publishedfileid)
        else:
            # Use WebAPI to get titles for all the mods
            collection_mods_pfid_to_title = self.__compile_collection_datas(
                publishedfileid
            )
            if len(collection_mods_pfid_to_title) == 0:
                # Fallback to scraping HTML if WebAPI returns empty
                collection_mods_pfid_to_title = self.__scrape_collection_mods_from_html(
                    self.current_html
                )
            if len(collection_mods_pfid_to_title) > 0:
                # ask user whether to add all mods or only missing ones
                answer = show_dialogue_conditional(
                    title=self.tr("Add Collection"),
                    text=self.tr("How would you like to add the collection?"),
                    information=self.tr(
                        "You can choose to add all mods from the collection or only the ones you don't have installed."
                    ),
                    button_text_override=[
                        self.tr("Add All Mods"),
                        self.tr("Add Missing Mods"),
                    ],
                )

                if answer == self.tr("Add All Mods"):
                    # add all mods
                    for pfid, title in collection_mods_pfid_to_title.items():
                        self._add_mod_to_list(publishedfileid=pfid, title=title)
                elif answer == self.tr("Add Missing Mods"):
                    # add only mods that aren't installed
                    for pfid, title in collection_mods_pfid_to_title.items():
                        if not self._is_mod_installed(pfid):
                            self._add_mod_to_list(publishedfileid=pfid, title=title)
            else:
                logger.warning(
                    "Empty list of mods returned, unable to add collection to list!"
                )
                show_warning(
                    title=self.tr("SteamCMD downloader"),
                    text=self.tr(
                        "Empty list of mods returned, unable to add collection to list!"
                    ),
                    information=self.tr(
                        "Please reach out to us on Github Issues page or<br>#rimsort-testing on the Rocketman/CAI discord"
                    ),
                )
        if len(self.downloader_list_dupe_tracking.keys()) > 0:
            # Build a report from our dict
            dupe_report = ""
            for pfid, name in self.downloader_list_dupe_tracking.items():
                dupe_report = dupe_report + f"{name} | {pfid}<br>"
            # Notify the user
            show_warning(
                title=self.tr("SteamCMD downloader"),
                text=self.tr("You already have these mods in your download list!"),
                information=self.tr(
                    "Skipping the following mods which are already present in your download list!"
                ),
                details=dupe_report,
            )
            self.downloader_list_dupe_tracking = {}

    def __compile_collection_datas(self, publishedfileid: str) -> dict[str, Any]:
        collection_mods_pfid_to_title: dict[str, Any] = {}
        collection_webapi_result = ISteamRemoteStorage_GetCollectionDetails(
            [publishedfileid]
        )
        collection_pfids = []

        if collection_webapi_result is not None and len(collection_webapi_result) > 0:
            for mod in collection_webapi_result[0].get("children", []):
                if mod.get("publishedfileid"):
                    collection_pfids.append(mod["publishedfileid"])
            if len(collection_pfids) > 0:
                collection_mods_webapi_response, _, _ = (
                    ISteamRemoteStorage_GetPublishedFileDetails(collection_pfids)
                )
            else:
                return collection_mods_pfid_to_title

            if not collection_mods_webapi_response:
                return collection_mods_pfid_to_title

            for metadata in collection_mods_webapi_response:
                # Retrieve the published mod's title from the response
                pfid = metadata["publishedfileid"]
                if "title" in metadata:
                    collection_mods_pfid_to_title[pfid] = metadata["title"]
                else:
                    collection_mods_pfid_to_title[pfid] = metadata["publishedfileid"]
        return collection_mods_pfid_to_title

    def __scrape_collection_mods_from_html(self, html: str) -> dict[str, Any]:
        # Fallback method to scrape collection mod IDs and titles from HTML
        # This is used if the WebAPI call fails or returns empty
        collection_mods_pfid_to_title: dict[str, Any] = {}
        # Regex pattern to find mod IDs and titles in the HTML
        pattern = re.compile(
            r'<div[^>]+id="sharedfile_(\d+)"[^>]*class="[^"]*collectionItem[^"]*"[^>]*>.*?<a[^>]+href="https://steamcommunity.com/sharedfiles/filedetails/\?id=\1"[^>]*>.*?<div[^>]+class="[^"]*workshopItemTitle[^"]*"[^>]*>([^<]+)</div>',
            re.DOTALL | re.IGNORECASE,
        )
        matches = pattern.findall(html)
        logger.debug(
            f"Found {len(matches)} matches in fallback HTML scraping for collection mods"
        )
        if matches:
            for pfid, title in matches:
                logger.debug(f"Scraped mod: {pfid} - {title}")
                collection_mods_pfid_to_title[pfid] = title
        else:
            logger.warning(
                "No matches found in fallback HTML scraping for collection mods"
            )
        return collection_mods_pfid_to_title

    def _add_mod_to_list(
        self,
        publishedfileid: str,
        title: str | None = None,
    ) -> None:
        # Try to extract the mod name from the page title, fallback to current_title
        extracted_page_title = extract_page_title_steam_browser(self.current_title)
        page_title = (
            extracted_page_title if extracted_page_title else self.current_title
        )
        # Check if the mod is already in the list
        if publishedfileid not in self.downloader_list_mods_tracking:
            # Add pfid to tracking list
            logger.debug(f"Tracking PublishedFileId for download: {publishedfileid}")
            self.downloader_list_mods_tracking.append(publishedfileid)
            # Create our list item
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, publishedfileid)
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
            self._update_badge_js(publishedfileid, BadgeState.ADDED)
        else:
            logger.debug(
                f"Tried to add duplicate PFID to downloader list: {publishedfileid}"
            )
            if publishedfileid not in self.downloader_list_dupe_tracking.keys():
                if not title:
                    self.downloader_list_dupe_tracking[publishedfileid] = page_title
                else:
                    self.downloader_list_dupe_tracking[publishedfileid] = title

    def _open_mod_url(self, item: QListWidgetItem) -> None:
        publishedfileid = item.data(Qt.ItemDataRole.UserRole)
        if publishedfileid and self.web_view is not None:
            url = f"{self.url_prefix_sharedfiles}{publishedfileid}"
            self.web_view.load(QUrl(url))

    def _clear_downloader_list(self) -> None:
        mods_to_clear_badges_for = list(self.downloader_list_mods_tracking)

        self.downloader_list.clear()
        self.downloader_list_mods_tracking.clear()
        self.downloader_list_dupe_tracking.clear()
        for mod_id in mods_to_clear_badges_for:
            self._update_badge_js(mod_id, BadgeState.DEFAULT)

    def _downloader_item_contextmenu_event(self, point: QPoint) -> None:
        context_item = self.downloader_list.itemAt(point)

        if context_item:  # Check if the right-clicked point corresponds to an item
            publishedfileid = context_item.data(Qt.ItemDataRole.UserRole)

            context_menu = QMenu(self)  # Downloader item context menu event
            remove_item = context_menu.addAction(self.tr("Remove mod from list"))
            remove_item.triggered.connect(
                partial(self._remove_mod_from_list, publishedfileid)
            )
            context_menu.exec_(self.downloader_list.mapToGlobal(point))

    def _remove_mod_from_list(self, publishedfileid: str) -> None:
        """
        Removes a mod from the downloader list (both internal tracking and UI)
        and updates its badge status to DEFAULT.
        This method is called both from the UI context menu and from the JS bridge.
        """
        if publishedfileid in self.downloader_list_mods_tracking:
            self.downloader_list_mods_tracking.remove(publishedfileid)

            item_found_in_ui = False
            for i in range(self.downloader_list.count()):
                item = self.downloader_list.item(i)
                if item.data(Qt.ItemDataRole.UserRole) == publishedfileid:
                    self.downloader_list.takeItem(i)
                    item_found_in_ui = True
                    break

            if not item_found_in_ui:
                logger.warning(
                    f"Mod {publishedfileid} removed from tracking, but corresponding UI item was not found."
                )

            self._update_badge_js(publishedfileid, BadgeState.DEFAULT)
        else:
            logger.warning(
                f"Mod {publishedfileid} not found in download tracking list, cannot remove."
            )

    def _subscribe_to_mods_from_list(self) -> None:
        logger.debug(
            f"Signaling Steamworks subscription handler with {len(self.downloader_list_mods_tracking)} mods"
        )
        EventBus().do_steamworks_api_call.emit(
            [
                "subscribe",
                [int(str_pfid) for str_pfid in self.downloader_list_mods_tracking],
            ]
        )

    def _inject_steam_recovery_script(self) -> None:
        recovery_path = Path(AppInfo().setup_steam_recovery_script_file)
        script = QWebEngineScript()
        script.setSourceCode(recovery_path.read_text(encoding="utf-8"))
        script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        script.setRunsOnSubFrames(True)
        assert self.web_profile is not None
        self.web_profile.scripts().insert(script)

    def _web_view_load_started(self) -> None:
        # Progress bar start, placeholder start
        # Commented out to stop flashing on every page load
        # self.web_view.hide()
        # self.web_view_loading_placeholder.show()
        self.progress_bar.setTextVisible(True)
        self.nav_bar.removeAction(self.add_to_list_button)

        if self._load_progress_fallback_timer is not None:
            self._load_progress_fallback_timer.stop()
        self._load_progress_fallback_timer = QTimer(self)
        self._load_progress_fallback_timer.setSingleShot(True)
        self._load_progress_fallback_timer.timeout.connect(
            self._reset_stuck_progress_bar
        )
        self._load_progress_fallback_timer.start(15000)

        if self._load_stall_timer is not None:
            self._load_stall_timer.stop()
        self._load_stall_timer = QTimer(self)
        self._load_stall_timer.setSingleShot(True)
        self._load_stall_timer.timeout.connect(self._on_load_stall)
        self._load_stall_timer.start(10000)

        if self._load_show_fallback_timer is not None:
            self._load_show_fallback_timer.stop()
        self._load_show_fallback_timer = QTimer(self)
        self._load_show_fallback_timer.setSingleShot(True)
        self._load_show_fallback_timer.timeout.connect(self._on_load_show_fallback)
        self._load_show_fallback_timer.start(1200)

    def _on_load_stall(self) -> None:
        if self.progress_bar.value() > 0 or self._load_stall_reloaded:
            return
        assert self.web_view is not None
        logger.warning("Steam browser load stalled at 0%; reloading once per session")
        self._load_stall_reloaded = True
        self.web_view.reload()

    def _on_load_show_fallback(self) -> None:
        if self.progress_bar.value() > 0:
            return
        assert self.web_view is not None
        self.web_view_loading_placeholder.hide()
        self.web_view.show()

    def _reset_stuck_progress_bar(self) -> None:
        if self.progress_bar.value() > 0:
            self.progress_bar.setValue(0)
            self.progress_bar.setTextVisible(False)

    def _web_view_load_progress(self, progress: int) -> None:
        # Progress bar progress
        self.progress_bar.setValue(progress)
        # Placeholder done after page begins to load
        if progress > 0:
            if self._load_stall_timer is not None:
                self._load_stall_timer.stop()
            if self._load_show_fallback_timer is not None:
                self._load_show_fallback_timer.stop()
            assert self.web_view is not None
            self.web_view_loading_placeholder.hide()
            self.web_view.show()

    # TODO: Probably a good idea to break this huge function down into a bunch of smaller helpers
    def _web_view_load_finished(self, ok: bool) -> None:
        assert self.web_view is not None

        if self._load_progress_fallback_timer is not None:
            self._load_progress_fallback_timer.stop()
        if self._load_stall_timer is not None:
            self._load_stall_timer.stop()
        if self._load_show_fallback_timer is not None:
            self._load_show_fallback_timer.stop()

        self.web_view_loading_placeholder.hide()
        self.web_view.show()

        # Progress bar done
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)

        inject_delay_ms = 300
        if not ok:
            inject_delay_ms = 1200
            logger.warning(
                "Steam browser load reported failure; continuing with deferred workshop inject"
            )

        # Cache information from page
        self.current_title = self.web_view.title()
        self.web_view.page().toHtml(self.__set_current_html)
        self.current_url = self.web_view.url().toString()

        # Update UI elements
        self.setWindowTitle(self.current_title)
        self.location.setText(self.current_url)

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
            # change target <a> — only inside workshop/collection tiles
            change_target_a_script = """
            var linkSelectors = [
                '.workshopItem a',
                '.collectionItem a',
                'a[href*="filedetails/?id="]'
            ];
            for (var s = 0; s < linkSelectors.length; s++) {
                var links = document.querySelectorAll(linkSelectors[s]);
                for (var i = 0; i < links.length; i++) {
                    links[i].target = "_self";
                }
            }
            """
            self.web_view.page().runJavaScript(
                change_target_a_script, 0, lambda result: None
            )
            # Remove "Login" button
            # login_button_removal_script = """
            # var elements = document.getElementsByClassName("global_action_link");
            # while (elements.length > 0) {
            #     elements[0].parentNode.removeChild(elements[0]);
            # }
            # """

            installed_mods_list = self._get_installed_mods_list()
            added_mods_list = self._get_added_mods_list()
            is_item_page = self.url_prefix_sharedfiles in self.current_url
            is_collection_page = self.url_prefix_workshop in self.current_url
            page_mode = resolve_workshop_page_mode(
                self.current_url,
                url_prefix_steam=self.url_prefix_steam,
                url_prefix_sharedfiles=self.url_prefix_sharedfiles,
                url_prefix_workshop=self.url_prefix_workshop,
                section_readytouseitems=self.section_readytouseitems,
                section_collections=self.section_collections,
            )

            try:
                setup_web_channel_script = build_web_channel_script(
                    installed_mods=installed_mods_list,
                    added_mods=added_mods_list,
                    page_mode=page_mode,
                    script_path=Path(AppInfo().setup_web_channel_script_file),
                    inject_delay_ms=inject_delay_ms,
                )
                self.web_view.page().runJavaScript(
                    setup_web_channel_script, 0, lambda result: None
                )
            except Exception as exc:
                logger.error(f"Failed to inject workshop badge script: {exc}")

            if is_item_page or is_collection_page:
                publishedfileid = parse_publishedfileid_from_url(
                    self.current_url,
                    url_prefix_sharedfiles=self.url_prefix_sharedfiles,
                    url_prefix_workshop=self.url_prefix_workshop,
                    searchtext_string=self.searchtext_string,
                )
                if not publishedfileid:
                    return
                # check if mod is installed
                is_installed = self._is_mod_installed(publishedfileid)
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
                # add buttons for collection items
                add_collection_buttons_script = """
                // find all collection items
                var collectionItems = document.getElementsByClassName('collectionItem');
                
                for (var i = 0; i < collectionItems.length; i++) {
                    var item = collectionItems[i];
                    
                    // get the mod id from the item
                    var modId = item.id.replace('sharedfile_', '');
                    
                    // find the subscription controls div
                    var subscriptionControls = item.querySelector('.subscriptionControls');
                    if (!subscriptionControls) {
                        continue;
                    }
                    
                    // check if mod is installed
                    var isInstalled = window.installedMods && window.installedMods.includes(modId);
                    
                    if (isInstalled) {
                        // create installed indicator
                        var installedIndicator = document.createElement('div');
                        installedIndicator.innerHTML = '✓';
                        installedIndicator.style.backgroundColor = '#4CAF50';
                        installedIndicator.style.color = 'white';
                        installedIndicator.style.width = '24px';
                        installedIndicator.style.height = '24px';
                        installedIndicator.style.borderRadius = '4px';
                        installedIndicator.style.display = 'flex';
                        installedIndicator.style.alignItems = 'center';
                        installedIndicator.style.justifyContent = 'center';
                        installedIndicator.style.fontWeight = 'bold';
                        installedIndicator.style.fontSize = '16px';
                        
                        // Replace subscription controls with our indicator
                        subscriptionControls.innerHTML = '';
                        subscriptionControls.appendChild(installedIndicator);
                    } else {
                        // create link button
                        var linkButton = document.createElement('a');
                        linkButton.innerHTML = '→';
                        linkButton.href = 'https://steamcommunity.com/sharedfiles/filedetails/?id=' + modId;
                        linkButton.style.backgroundColor = '#2196F3';
                        linkButton.style.color = 'white';
                        linkButton.style.width = '24px';
                        linkButton.style.height = '24px';
                        linkButton.style.borderRadius = '4px';
                        linkButton.style.display = 'flex';
                        linkButton.style.alignItems = 'center';
                        linkButton.style.justifyContent = 'center';
                        linkButton.style.cursor = 'pointer';
                        linkButton.style.fontWeight = 'bold';
                        linkButton.style.fontSize = '20px';
                        linkButton.style.textDecoration = 'none';
                        
                        // Replace subscription controls with our button
                        subscriptionControls.innerHTML = '';
                        subscriptionControls.appendChild(linkButton);
                    }
                }
                """
                self.web_view.page().runJavaScript(
                    add_collection_buttons_script, 0, lambda result: None
                )
                # add installed indicator if mod is installed
                if is_installed:
                    add_installed_indicator_script = """
                    // Create a new div for the installed indicator
                    var installedDiv = document.createElement('div');
                    installedDiv.style.backgroundColor = '#4CAF50';  // Green background
                    installedDiv.style.color = 'white';
                    installedDiv.style.padding = '10px';
                    installedDiv.style.borderRadius = '5px';
                    installedDiv.style.marginBottom = '10px';
                    installedDiv.style.textAlign = 'center';
                    installedDiv.style.fontWeight = 'bold';
                    installedDiv.innerHTML = '✓ Already Installed';
                    // Insert it at the top of the page content
                    var contentDiv = document.querySelector('.workshopItemDetailsHeader');
                    if (contentDiv) {
                        contentDiv.parentNode.insertBefore(installedDiv, contentDiv);
                    }
                    """
                    self.web_view.page().runJavaScript(
                        add_installed_indicator_script, 0, lambda result: None
                    )

            self._update_toolbar_add_to_list_button(self.current_url)

    def __set_current_html(self, html: str) -> None:
        # Update cached html with html from current page
        self.current_html = html

    def _is_mod_installed(self, publishedfileid: str) -> bool:
        """Check if a mod is installed by looking through local and workshop folders"""
        assert self.metadata_controller is not None
        # check all mods in metadata
        for mod in self.metadata_controller.mods_metadata.values():
            if mod.published_file_id == publishedfileid:
                return True
        return False

    def _get_installed_mods_list(self) -> list[str]:
        """Get list of installed mod IDs"""
        assert self.metadata_controller is not None
        installed_mods = []
        for mod in self.metadata_controller.mods_metadata.values():
            pfid = mod.published_file_id
            if pfid is not None:
                installed_mods.append(pfid)

        return installed_mods

    def _get_added_mods_list(self) -> list[str]:
        """Get list of mod IDs added to the download list"""
        added_mods = []
        for modId in self.downloader_list_mods_tracking:
            added_mods.append(modId)

        return added_mods

    def _update_badge_js(self, mod_id: str, status: BadgeState) -> None:
        """Calls a JavaScript function in the web view to update a specific mod's badge"""
        assert self.web_view is not None
        script = f"""
        if (typeof PAGE_MODE !== 'undefined' && PAGE_MODE === 'hub'
            && typeof rimsortUpdateHubAddButton === 'function') {{
            rimsortUpdateHubAddButton('{mod_id}', '{status.value}');
        }} else if (typeof window.updateModBadge === 'function') {{
            window.updateModBadge('{mod_id}', '{status.value}');
        }} else {{
            console.warn('window.updateModBadge is not defined yet.');
        }}
        if (typeof PAGE_MODE !== 'undefined' && PAGE_MODE === 'browse'
            && typeof window.updateAllModBadges === 'function') {{
            window.updateAllModBadges();
        }}
        """
        self.web_view.page().runJavaScript(script, 0, lambda result: None)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Properly clean up web engine resources to prevent memory leaks and hanging processes"""
        logger.debug("Cleaning up SteamBrowser resources...")

        if self._load_progress_fallback_timer is not None:
            self._load_progress_fallback_timer.stop()
        if self._load_stall_timer is not None:
            self._load_stall_timer.stop()
        if self._load_show_fallback_timer is not None:
            self._load_show_fallback_timer.stop()

        # Delete on close flag
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        # Stop any loading
        if self.web_view is not None:
            self.web_view.stop()

            # Disconnect all web view signals
            try:
                self.web_view.loadStarted.disconnect()
                self.web_view.loadProgress.disconnect()
                self.web_view.loadFinished.disconnect()
                self.web_view.urlChanged.disconnect()
            except Exception:
                pass

            # Clean up page
            if self.web_view.page():
                # Delete web channel
                if self.js_bridge is not None and hasattr(self, "channel"):
                    self.channel.deregisterObject(self.js_bridge)
                    self.channel.deleteLater()

                # Clear scripts
                self.web_view.page().profile().scripts().clear()

                # Delete page
                self.web_view.page().deleteLater()

            # Delete web view
            self.web_view.deleteLater()
            self.web_view = None

        # Clean up web profile
        if self.web_profile is not None:
            self.web_profile.deleteLater()
            self.web_profile = None

        # Clear all references
        self.metadata_controller = None
        self.settings = None
        self.js_bridge = None
        self.downloader_list_mods_tracking.clear()
        self.downloader_list_dupe_tracking.clear()

        # Clear layouts
        self.clear_layout(self.window_layout)

        logger.debug("SteamBrowser cleanup completed")

        event.accept()

    def clear_layout(self, layout: QLayout | None) -> None:
        """Recursively clear layout and delete all widgets"""
        if layout is not None:
            while layout.count():
                item = layout.takeAt(0)
                if item is None:
                    break
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
                else:
                    self.clear_layout(item.layout())

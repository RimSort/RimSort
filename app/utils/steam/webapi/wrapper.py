from __future__ import annotations

import sys
import traceback
from collections.abc import Callable
from logging import WARNING, getLogger
from math import ceil
from multiprocessing import Lock, Pool, cpu_count
from time import sleep, time
from typing import TYPE_CHECKING, Any, Optional
from urllib.parse import urlparse

import requests
from loguru import logger
from PySide6.QtCore import QCoreApplication, QObject, Signal
from PySide6.QtWidgets import QInputDialog
from steam.webapi import WebAPI

from app.models.metadata.metadata_structure import AboutXmlMod
from app.utils import http
from app.utils.app_info import AppInfo
from app.utils.constants import RIMWORLD_DLC_METADATA
from app.utils.generic import chunks
from app.utils.json_utils import atomic_json_dump
from app.utils.steam.availability import check_steam_available
from app.utils.steam.steamworks.wrapper import (
    SteamworksAppDependenciesQuery,
    _pool_init_worker,
)
from app.views.dialogue import show_warning

STEAM_THERE_WAS_A_PROBLEM_FLAG = "There was a problem accessing the item. "

# Prevent circular dependencies for type checking
if TYPE_CHECKING:
    from app.controllers.metadata_controller import MetadataController


# This is redundant since it is also done in `logger-tt` config,
# however, it can't hurt, just in case!
# Uncomment this if you want to see the full urllib3 request
# THIS CONTAINS THE STEAM API KEY
getLogger("urllib3").setLevel(WARNING)

BASE_URL = "https://steamcommunity.com"
BASE_URL_STEAMFILES = "https://steamcommunity.com/sharedfiles/filedetails/?id="
BASE_URL_WORKSHOP = "https://steamcommunity.com/workshop/filedetails/?id="


class CollectionImport:
    """
    Class to handle importing workshop collection links and extracting package IDs.
    """

    def __init__(self, metadata_controller: "MetadataController") -> None:
        """
        Initialize the CollectionImport instance.

        :param metadata_controller: The MetadataController instance.
        """
        self.metadata_controller = metadata_controller
        self.translate = QCoreApplication.translate
        self.package_ids: list[
            str
        ] = []  # Initialize an empty list to store package IDs
        self.publishedfileids: list[str] = []  # Initialize an empty list to store pfids
        self.input_dialog()  # Call the input_dialog method to set up the UI

    def input_dialog(self) -> None:
        # Initialize the UI for entering collection links
        self.link_input = QInputDialog.getText(
            None,
            self.translate("CollectionImport", "Add Workshop collection link"),
            self.translate("CollectionImport", "Add Workshop collection link"),
        )
        logger.info("Workshop collection link Input UI initialized successfully!")
        if self.link_input[1]:
            self.import_collection_link()
        else:
            logger.info("User exited workshop collection import window.")
            return

    def is_valid_collection_link(self, link: str) -> bool:
        """
        Check if the provided link is a valid workshop collection link.

        Args:
            link: The collection link to validate.

        Returns:
            bool: True if the link is valid, False otherwise.
        """
        parsed = urlparse(link)
        if parsed.scheme != "https" or parsed.hostname != "steamcommunity.com":
            return False
        return BASE_URL_STEAMFILES in link or BASE_URL_WORKSHOP in link

    def import_collection_link(self) -> None:
        # Handle the import button click event
        logger.info("Import Workshop collection clicked")
        collection_link = self.link_input[0]

        # Check if the input link is a valid workshop collection link
        if not self.is_valid_collection_link(collection_link):
            logger.error(
                "Invalid Workshop collection link. Please enter a valid Workshop collection link."
            )
            # Show warning message box
            show_warning(
                title=self.translate("CollectionImport", "Invalid Link"),
                text=self.translate(
                    "CollectionImport",
                    "Invalid Workshop collection link. Please enter a valid Workshop collection link.",
                ),
            )
            return

        try:
            if BASE_URL_STEAMFILES in collection_link:
                collection_link = collection_link.split(BASE_URL_STEAMFILES, 1)[1]
            elif BASE_URL_WORKSHOP in collection_link:
                collection_link = collection_link.split(BASE_URL_WORKSHOP, 1)[1]
            collection_webapi_result = ISteamRemoteStorage_GetCollectionDetails(
                [collection_link]
            )
            if (
                collection_webapi_result is not None
                and len(collection_webapi_result) > 0
            ):
                self.publishedfileids = [
                    pfid
                    for mod in collection_webapi_result[0]["children"]
                    if (pfid := _find_value_in_dict(mod, "publishedfileid"))
                    if _find_value_in_dict(mod, "filetype") == 0
                ]
                failed_mods = []
                for pfid in self.publishedfileids:
                    try:
                        pkgid = self._get_package_id_from_pfid(pfid)
                    except ValueError:
                        logger.warning(
                            f"Failed to parse packageId from collection PublishedFileId {pfid}: incorrect pfid format"
                        )
                        failed_mods.append(f"{pfid} - incorrect pfid format")
                        continue
                    if pkgid is None:
                        # Try to check if the mod is inaccessible
                        steam_link = f"https://steamcommunity.com/sharedfiles/filedetails/?id={pfid}"

                        try:
                            steam_response = http.get(steam_link).text
                        except Exception as e:
                            logger.exception(e)
                            steam_response = ""
                        if STEAM_THERE_WAS_A_PROBLEM_FLAG in steam_response:
                            logger.info(f"Mod with pfid {pfid} is inaccessible")
                            continue
                        logger.error(
                            f"Failed to fetch packageId from collection PublishedFileId {pfid}: "
                            "PackageId not found. Try subscribing to collection first. "
                            f"Check {steam_link} for mod details."
                        )
                        failed_mods.append(steam_link)
                        continue
                    self.package_ids.append(pkgid)

                logger.info("Parsed packageIds from publishedfileids successfully")
                if failed_mods:
                    show_warning(
                        title=self.translate("CollectionImport", "Incomplete import"),
                        text=self.translate(
                            "CollectionImport",
                            f"{len(failed_mods)} mods could not be imported due to missing package ids. "
                            "This may happen if you don't have all the mods downloaded.<br><br>"
                            "Try subscribing to the collection first",
                        ),
                        details="\n".join(failed_mods),
                    )
        except Exception as e:
            logger.error(
                f"An error occurred while fetching collection content: {str(e)}"
            )

    def _get_package_id_from_pfid(self, pfid: str | int | None) -> str | None:
        """Map published id to package id if possible

        Order:

        * steamdb, if configured
        * internal metadata
        * internal metadata using mod folder name as pfid
        """
        if pfid is None:
            return None
        pfid_str = str(pfid).strip()
        if not pfid_str.isdigit():
            raise ValueError(
                f"PublishedFileId (pfid) is expected to be a numeric sequence, not {pfid_str}"
            )
        return (
            self._get_package_id_from_pfid_using_steamdb(pfid_str)
            or self._get_package_id_from_pfid_using_metadata(pfid_str)
            or self._get_package_id_from_pfid_using_mod_folder_name(pfid_str)
        )

    def _get_package_id_from_pfid_using_metadata(self, pfid: str) -> str | None:
        metadata_controller = self.metadata_controller
        if not metadata_controller:
            return None
        for mod in metadata_controller.mods_metadata.values():
            if mod.published_file_id == pfid and isinstance(mod, AboutXmlMod):
                return str(mod.package_id)
        return None

    def _get_package_id_from_pfid_using_steamdb(self, pfid: str) -> str | None:
        if not self.metadata_controller:
            return None
        steam_db = self.metadata_controller.steam_db
        if steam_db is None:
            return None
        entry = steam_db.database.get(pfid)
        if entry is None:
            return None
        # SteamDbEntry uses camelCase: .packageId
        return entry.packageId if entry.packageId else None

    def _get_package_id_from_pfid_using_mod_folder_name(self, pfid: str) -> str | None:
        metadata_controller = self.metadata_controller
        if not metadata_controller:
            return None
        for mod in metadata_controller.mods_metadata.values():
            if mod.mod_path is None:
                continue
            if not mod.mod_path.is_dir():
                continue
            if mod.mod_path.name != pfid:
                continue
            if isinstance(mod, AboutXmlMod):
                return str(mod.package_id)
        return None


def _find_value_in_dict(coll: dict[str, Any], key: str) -> Any:
    key = key.strip().lower()
    key_found = next((_ for _ in coll.keys() if _.strip().lower() == key), None)
    if not key_found:
        return None
    return coll.get(key_found)


class DynamicQuery(QObject):
    """
    Create DynamicQuery object to initialize the scraped data from Workshop

    :param apikey: Steam API key to be used for query
    :param appid: The AppID associated with the game you are looking up info for
    :param life: The lifespan of the Query in terms of the seconds added to the time of
    database generation. This adds an 'expiry' to the data being cached.
    :param get_appid_deps: This toggle determines whether or not to query DLC dependency data
    """

    dq_messaging_signal = Signal(str)

    def __init__(
        self,
        apikey: str,
        appid: int,
        get_appid_deps: bool = False,
        life: int = 0,
        callback: Optional[Callable[[str], None]] = None,
        output_database_path: str = "",
    ) -> None:
        QObject.__init__(self)

        logger.info("Initializing DynamicQuery")
        self.api = None
        self.apikey = apikey
        self.appid = appid
        self.expiry = self.__expires(life)
        self.get_appid_deps = get_appid_deps
        self.output_database_path = output_database_path
        self.next_cursor = "*"
        self.pagenum = 1
        self.pages = 1
        self.publishedfileids: list[str] = []
        self.total = 0
        self.database: dict[str, Any] = {}
        self.callback = callback

    def __expires(self, life: int) -> int:
        """Returns current epoch + life

        :param life: The lifespan of the Query in terms of the seconds added to life
        :type life: int
        :return: current epoch + life
        :rtype: int
        """
        return int(time() + life)

    def _emit_message(self, msg: str) -> None:
        """
        Emit a progress message via callback or Qt signal.

        If a callback was provided during initialization, use it.
        Otherwise, fall back to the Qt signal for GUI compatibility.

        :param msg: The message to emit
        """
        if self.callback:
            self.callback(msg)
        else:
            self.dq_messaging_signal.emit(msg)

    def _process_mod_details(
        self,
        all_details: list[dict[str, Any]],
        json_to_update: dict[str, Any],
    ) -> list[str]:
        """
        Process raw publishedfiledetails into the database.

        Populates steamName, url, tags, and dependency entries for each mod.
        Returns a list of missing children pfids (dependencies not yet in the DB).

        :param all_details: flat list of publishedfiledetails dicts from the API
        :param json_to_update: database dict to update in-place
        :return: list of missing children PublishedFileIds
        """
        missing_children: list[str] = []
        result = json_to_update
        for metadata in all_details:
            publishedfileid = metadata["publishedfileid"]
            if metadata["result"] != 1:
                if not result["database"].get(publishedfileid):
                    result["database"][publishedfileid] = {}
                logger.debug(
                    f"Tried to parse metadata for a mod that is deleted/private/removed/unposted: {publishedfileid}"
                )
                result["database"][publishedfileid]["unpublished"] = True
                continue
            else:
                if not result["database"].get(publishedfileid):
                    result["database"][publishedfileid] = {}
                result["database"][publishedfileid]["steamName"] = metadata["title"]
                result["database"][publishedfileid]["url"] = (
                    f"https://steamcommunity.com/sharedfiles/filedetails/?id={publishedfileid}"
                )
                if metadata.get("tags"):
                    result["database"][publishedfileid]["tags"] = sorted(
                        metadata["tags"], key=lambda t: t.get("tag", "")
                    )
                if metadata.get("children"):
                    if not result["database"][publishedfileid].get("dependencies"):
                        result["database"][publishedfileid]["dependencies"] = {}
                    for children in metadata["children"]:
                        child_pfid = children["publishedfileid"]
                        if result["database"].get(child_pfid):
                            if not result["database"][child_pfid].get("unpublished"):
                                if result["database"][child_pfid].get("name"):
                                    child_name = result["database"][child_pfid]["name"]
                                elif result["database"][child_pfid].get("steamName"):
                                    child_name = result["database"][child_pfid][
                                        "steamName"
                                    ]
                                else:
                                    child_name = "UNKNOWN"
                                child_url = result["database"][child_pfid]["url"]
                                result["database"][publishedfileid]["dependencies"][
                                    child_pfid
                                ] = [
                                    child_name,
                                    child_url,
                                ]
                        else:
                            if child_pfid not in missing_children:
                                logger.debug(
                                    f"Could not find pfid {child_pfid} in database. Adding child to missing_children"
                                )
                                missing_children.append(child_pfid)
        for missing_child in missing_children[:]:
            if result["database"].get(missing_child) and result["database"][
                missing_child
            ].get("unpublished"):
                missing_children.remove(missing_child)
        return missing_children

    def __initialize_webapi(self) -> None:
        if self.api:
            # Make a request to GetServerInfo to check if the API is active
            response = self.api.call(method_path="ISteamWebAPIUtil.GetServerInfo")
            # Check if the API request was successful and contains server info
            if response.get("servertime") is not None:
                # The API request was successful, and the WebAPI class is active
                logger.debug("WebAPI is active!")
                return
        # The API request failed, and we're still here, so initialize the API
        logger.debug("WebAPI is not active!")
        try:  # Try to initialize the API
            self.api = WebAPI(self.apikey, format="json", https=True)
        except Exception as e:
            self.api = None
            # Catch exceptions that can potentially leak Steam API key
            stacktrace = traceback.format_exc()
            pattern = "&key="
            if pattern in stacktrace:
                stacktrace = stacktrace[
                    : len(stacktrace)
                    - (len(stacktrace) - (stacktrace.find(pattern) + len(pattern)))
                ]  # If an HTTPError/SSLError from steam/urllib3 module(s) somehow is uncaught, try to remove the Steam API key from the stacktrace
            logger.warning(
                f"Dynamic Query received an uncaught exception: {e.__class__.__name__}"
            )
            self._emit_message(
                "\nDynamicQuery failed to initialize WebAPI query!"
                + "\nAre you connected to the internet?\nIs your configured key invalid or revoked?\n"
            )

    def create_steam_db(
        self, database: dict[str, Any], publishedfileids: list[str]
    ) -> None:
        """
        Builds a database using a chunked WebAPI query of all available
        PublishedFileIds supplied.

        Uses a cache-and-replay approach to avoid redundant API calls:

        1. Fetch + process all mods, caching the raw API responses
        2. Fetch + process any missing dependency children
        3. Re-process the cached round 1 responses locally (no API calls)
           so dependency entries that couldn't resolve in round 1 now resolve

        :param database: a database to update using IPublishedFileService_GetDetails queries
        :param publishedfileids: a list of PublishedFileIDs to query
        """

        self.__initialize_webapi()

        query = database
        query["version"] = self.expiry
        query["database"] = database["database"]

        # Round 1: fetch + process all mods, cache the raw responses
        result = self.IPublishedFileService_GetDetails(query, publishedfileids)
        if result is None:
            logger.warning(
                "Dynamic Query failed to initialize WebAPI query! "
                "Critical failure. Aborting steam_db creation."
            )
            return

        query, missing_children, cached_details = result

        # Round 2: fetch + process only the missing children
        if missing_children:
            self._emit_message(
                f"\nRetrieving dependency information for {len(missing_children)} missing children"
            )
            result = self.IPublishedFileService_GetDetails(query, missing_children)
            if result is None:
                logger.warning(
                    "Dynamic Query failed during missing children query! "
                    "Proceeding with partial data."
                )
            else:
                query, _, round2_details = result
                cached_details = cached_details + round2_details

            # Re-process all cached responses locally (no API calls).
            # Now that all mods are in the DB, dependency entries that
            # were unresolvable due to processing order will resolve correctly.
            self._emit_message(
                "\nRe-processing cached mod details to resolve remaining dependencies"
            )
            self._process_mod_details(cached_details, query)

        all_publishedfileids = publishedfileids + [
            c for c in missing_children if c not in publishedfileids
        ]

        if self.get_appid_deps:
            self._emit_message(
                "\nAppID dependency retrieval enabled. Starting Steamworks API call(s)"
            )
            self.ISteamUGC_GetAppDependencies(
                publishedfileids=all_publishedfileids, query=query
            )
        else:
            self._emit_message(
                "\nAppID dependency retrieval disabled. Skipping Steamworks API call(s)!"
            )

        # Notify & return
        total = len(query["database"])
        self._emit_message(f"\nReturning Steam Workshop metadata for {total} items")
        self.database.update(query)

    def pfids_by_appid(self) -> None:
        """
        Builds a total collection of PublishedFileIds representing a list of all workshop mods
        for any given Steam AppID. These PublishedFileIds can be used in a many ways!
        """

        self.__initialize_webapi()

        if self.api:
            query = True
            while query:
                if self.pagenum > self.pages:
                    query = False
                    break
                self.next_cursor = self.IPublishedFileService_QueryFiles(
                    self.next_cursor
                )
        else:
            self._emit_message("AppIDQuery: WebAPI failed to initialize!")

    def IPublishedFileService_GetDetails(
        self, json_to_update: dict[Any, Any], publishedfileids: list[str]
    ) -> tuple[dict[Any, Any], list[str], list[dict[str, Any]]] | None:
        """
        Given a list of PublishedFileIds, fetch mod metadata from Steam WebAPI
        in chunks, process it into the database, and return the raw responses
        for potential re-processing.

        https://steamapi.xpaw.me/#IPublishedFileService/GetDetails

        :param json_to_update: database dict to update in-place
        :param publishedfileids: list of PublishedFileIds to query
        :return: Tuple of (updated_db, missing_children, raw_details) where
            raw_details can be passed to _process_mod_details for re-processing.
            Returns None on critical failure.
        """
        items_processed = 0
        total = len(publishedfileids)
        self._emit_message(
            f"\nSteam WebAPI: IPublishedFileService/GetDetails initializing for {total} mods\n\n"
        )
        self._emit_message(f"IPublishedFileService/GetDetails chunk [0/{total}]")
        if not self.api:
            return None
        all_details: list[dict[str, Any]] = []
        for chunk in chunks(
            _list=publishedfileids, limit=200
        ):  # Chunk limit appears to be 213 PublishedFileIds at a time - this appears to be a WebAPI limitation
            chunk_total = len(chunk)
            items_processed += chunk_total
            # Uncomment to see the pfids from each chunk
            # logger.debug(f"{chunk_total} PublishedFileIds in chunk: {chunk}")
            try:
                response = self.api.call(
                    method_path="IPublishedFileService.GetDetails",
                    key=self.apikey,
                    publishedfileids=chunk,
                    includetags=True,
                    includeadditionalpreviews=False,
                    includechildren=True,
                    includekvtags=True,
                    includevotes=False,
                    short_description=False,
                    includeforsaledata=False,
                    includemetadata=True,
                    return_playtime_stats=0,
                    appid=self.appid,
                    strip_description_bbcode=False,
                    includereactions=False,
                    admin_query=False,
                )
                all_details.extend(response["response"]["publishedfiledetails"])
            except Exception as e:
                stacktrace = traceback.format_exc()
                if (
                    e.__class__.__name__ == "HTTPError"
                    or e.__class__.__name__ == "SSLError"
                ):  # requests.exceptions.HTTPError OR urllib3.exceptions.SSLError
                    pattern = "&key="
                    stacktrace = stacktrace[
                        : len(stacktrace)
                        - (len(stacktrace) - (stacktrace.find(pattern) + len(pattern)))
                    ]
                logger.error(
                    f"IPublishedFileService/GetDetails errored querying batch [{items_processed}/{total}]: {stacktrace}"
                )
            self._emit_message(
                f"IPublishedFileService/GetDetails chunk [{items_processed}/{total}]"
            )
        missing_children = self._process_mod_details(all_details, json_to_update)
        return json_to_update, missing_children, all_details

    def IPublishedFileService_QueryFiles(self, cursor: str) -> str:
        """
        Utility to crawl the entirety of Rimworld's Steam Workshop catalogue, compile,
        and populate a list of all PublishedFileIDs

        Given a string cursor, return a string next_cursor from Steam WebAPI, from the
        data being parsed from the loop of each page - API has 100 item limit per page

        https://steamapi.xpaw.me/#IPublishedFileService/QueryFiles
        https://partner.steamgames.com/doc/webapi/IPublishedFileService#QueryFiles
        https://steamwebapi.azurewebsites.net (Ctrl + F search: "IPublishedFileService/QueryFiles")

        :param str: IN string containing the variable that corresponds to the
        `cursor` parameter being passed to the CURRENT WebAPI.call() query

        :return: OUT string containing the variable that corresponds to the
        `cursor` parameter being returned to the FOLLOWING loop in our series of
        WebAPI.call() results that are being are parsing
        """
        if self.api is None:
            raise Exception(
                "Tried to query files while API was not properly initialized."
            )  # Exit query

        result = self.api.call(
            method_path="IPublishedFileService.QueryFiles",
            key=self.apikey,
            query_type=1,
            page=1,
            cursor=cursor,
            numperpage=50000,
            creator_appid=self.appid,
            appid=self.appid,
            requiredtags=None,
            excludedtags=None,
            match_all_tags=False,
            required_flags=None,
            omitted_flags=None,
            search_text="",
            filetype=0,
            child_publishedfileid=None,
            days=None,
            include_recent_votes_only=False,
            required_kv_tags=None,
            taggroups=None,
            date_range_created=None,
            date_range_updated=None,
            excluded_content_descriptors=None,
            special_filter=None,
            appids_required_for_use=None,
            excluded_appids_required_for_use=None,
            search_text_target=None,
            totalonly=False,
            ids_only=True,
            return_vote_data=False,
            return_tags=False,
            return_kv_tags=False,
            return_previews=False,
            return_children=True,
            return_short_description=False,
            return_for_sale_data=False,
            return_playtime_stats=False,
            return_details=False,
            strip_description_bbcode=False,
            admin_query=False,
        )
        # Print total mods found we need to iter through paginations to get info for
        if (
            self.pagenum and self.total == 0
        ):  # If True, this is initial loop; we properly set them in initial loop
            if result["response"]["total"]:
                self.pagenum = 1
                self.total = result["response"]["total"]
                self.pages = ceil(
                    self.total / len(result["response"]["publishedfiledetails"])
                )
                # Since this is only run during the initial loop, we print out the 0
                # needed for RunnerPanel progress bar calculations
                self._emit_message(
                    "IPublishedFileService/QueryFiles page [0" + f"/{str(self.pages)}]"
                )
        self._emit_message(
            f"IPublishedFileService/QueryFiles page [{str(self.pagenum)}"
            + f"/{str(self.pages)}]"
        )
        ids_from_page = []
        for item in result["response"]["publishedfiledetails"]:
            self.publishedfileids.append(item["publishedfileid"])
            ids_from_page.append(item["publishedfileid"])
        self.pagenum += 1
        return result["response"]["next_cursor"]

    def _merge_app_deps(
        self, query: dict[str, Any], pfids_appid_deps: dict[int, list[int]]
    ) -> None:
        """Merge app dependency results into the database in-place."""
        for pfid in query.get("database", {}):
            if int(pfid) not in pfids_appid_deps:
                continue
            for appid in pfids_appid_deps[int(pfid)]:
                appid_str = str(appid)
                if appid_str not in RIMWORLD_DLC_METADATA:
                    continue
                deps = query["database"][pfid].setdefault("dependencies", {})
                if appid_str not in deps:
                    deps[appid_str] = [
                        RIMWORLD_DLC_METADATA[appid_str]["name"],
                        RIMWORLD_DLC_METADATA[appid_str]["steam_url"],
                    ]

    def ISteamUGC_GetAppDependencies(
        self, publishedfileids: list[str], query: dict[str, Any]
    ) -> None:
        """
        Given a list of PublishedFileIds and a query, return the query after looking up
        and appending DLC dependency data from the Steamworks API.

        Uses multiprocessing.Pool with cpu_count() workers. SteamInit() calls
        are serialized via a shared Lock to prevent pipe-registration storms.

        https://partner.steamgames.com/doc/api/ISteamUGC#GetAppDependencies

        :param publishedfileids: a list of PublishedFileIds to query metadata for
        :param query: a Dict of json data, containing a query to update in
        RimPy db_data["database"] format, or the skeleton of one from local_metadata
        """
        # Filter pfids that already have DLC deps populated in the database
        pfids_needing_deps = []
        for pfid in publishedfileids:
            deps = query.get("database", {}).get(pfid, {}).get("dependencies", {})
            needs = any(str(a) not in deps for a in RIMWORLD_DLC_METADATA)
            if needs:
                pfids_needing_deps.append(pfid)

        skipped = len(publishedfileids) - len(pfids_needing_deps)
        total_to_query = len(pfids_needing_deps)

        if total_to_query == 0:
            self._emit_message(
                "\nAll mods already have DLC dependency data. Skipping Steamworks call."
            )
            return

        self._emit_message(
            f"\nSteamworks API: ISteamUGC/GetAppDependencies initializing for "
            f"{total_to_query} mods ({cpu_count()} workers)"
            + (f", {skipped} already resolved" if skipped else "")
        )

        # Save the database before Steamworks phase — even if Steam fails,
        # the user has the WebAPI data
        if self.output_database_path:
            try:
                atomic_json_dump(query, self.output_database_path, indent=4)
            except Exception as e:
                logger.warning(f"Failed to save database before Steamworks: {e}")

        # Check Steam availability
        if not check_steam_available(
            str(AppInfo().libs_folder),
            status_callback=self._emit_message,
        ):
            self._emit_message(
                "\nSteam is not available. Skipping AppID dependency retrieval."
            )
            return

        # Run the Steamworks query using multiprocessing Pool.
        # Each worker has its own SteamworksInterface (separate IPC pipe),
        # but SteamInit() in _pool_init_worker is serialized via init_lock
        # so the Steam client is not overwhelmed by concurrent pipe registration.
        # Leave 2 cores free for the system/Steam client; add a 30s cooldown
        # every 6000 pfids to prevent the Steam client IPC pipe from
        # overflowing (pipes.cpp:BWrite failed) under sustained load.
        num_processes = max(1, cpu_count() - 2)
        interval = 0.2
        est_seconds = int(total_to_query * interval / num_processes)
        if est_seconds < 60:
            est_str = f"{est_seconds}s"
        else:
            est_str = f"{est_seconds // 60}m {est_seconds % 60}s"
        self._emit_message(f"Estimated time: ~{est_str}.\nPlease wait...")

        # Split pfids into fixed-size chunks so results trickle back via imap_unordered
        CHUNK_SIZE = 100
        pfid_chunks = list(chunks(pfids_needing_deps, limit=CHUNK_SIZE))

        queries = [
            SteamworksAppDependenciesQuery(
                pfid_or_pfids=[int(pfid) for pfid in chunk],
                interval=interval,
                _libs=str(AppInfo().libs_folder),
            )
            for chunk in pfid_chunks
        ]

        pfids_appid_deps: dict[int, list[int]] = {}
        total_chunks = len(queries)
        self._emit_message(f"Progress: 0/{total_chunks}")
        libs_path = str(AppInfo().libs_folder)
        project_root = str(AppInfo().application_folder)
        init_lock = Lock()
        COOLDOWN_INTERVAL = 6000  # pfids — give Steam client a 30s breather
        pfids_processed = 0
        with Pool(
            processes=num_processes,
            initializer=_pool_init_worker,
            initargs=(project_root, libs_path, init_lock),
        ) as pool:
            for i, result in enumerate(
                pool.imap_unordered(SteamworksAppDependenciesQuery.run, queries)
            ):
                if result is not None:
                    pfids_appid_deps.update(result)
                pfids_processed += CHUNK_SIZE
                if pfids_processed % COOLDOWN_INTERVAL == 0:
                    remaining = total_to_query - pfids_processed
                    remaining_est = int(remaining * interval / num_processes) + 30
                    if remaining_est < 60:
                        est_str = f"{remaining_est}s"
                    else:
                        est_str = f"{remaining_est // 60}m {remaining_est % 60}s"
                    self._emit_message(
                        f"Cooldown: 30s pause after ~{pfids_processed} pfids "
                        f"to let Steam client recover. "
                        f"~{remaining} pfids remaining (est. {est_str})"
                    )
                    sleep(30)
                self._emit_message(f"Progress: {i + 1}/{total_chunks}")

        self._merge_app_deps(query, pfids_appid_deps)
        self._emit_message(f"\nTotal: {len(pfids_appid_deps.keys())}")
        # Save final database
        if self.output_database_path:
            try:
                atomic_json_dump(query, self.output_database_path, indent=4)
            except Exception as e:
                logger.warning(f"Failed to save database after Steamworks: {e}")


def ISteamRemoteStorage_GetCollectionDetails(
    publishedfileids: list[str],
) -> list[Any] | None:
    """
    Given a list of Steam Workshopmod collection PublishedFileIds, return a dict of
    json data queried from Steam WebAPI, containing data to be parsed.

    https://steamapi.xpaw.me/#ISteamRemoteStorage/GetCollectionDetails

    :param publishedfileids: a list of 1 or more publishedfileids to lookup metadata for
    :return: a JSON object that is the response from your WebAPI query
    """
    # Construct the URL to retrieve information about the collection
    url = "https://api.steampowered.com/ISteamRemoteStorage/GetCollectionDetails/v1/"
    # Construct arguments to pass to the API call
    metadata = []
    for chunk in list(chunks(_list=publishedfileids, limit=5000)):
        logger.debug(
            f"Querying details for {len(chunk)} collection(s) via Steam WebAPI"
        )
        # Construct arguments to pass to the API call
        data = {"collectioncount": f"{str(len(chunk))}"}
        for publishedfileid in chunk:
            count = chunk.index(publishedfileid)
            data[f"publishedfileids[{count}]"] = publishedfileid
        try:  # Make a request to the Steam Web API
            request = http.post(url, data=data, timeout=(5, 60))
        except Exception as e:
            logger.warning(
                f"Unable to complete request! Are you connected to the internet? Received exception: {e.__class__.__name__}"
            )
            return None
        try:  # Parse the JSON response
            json_response = request.json()
            logger.debug(json_response)
            if json_response.get("response", {}).get("resultcount", 0) > 0:
                for mod_metadata in json_response["response"]["collectiondetails"]:
                    metadata.append(mod_metadata)
        except requests.exceptions.JSONDecodeError as e:
            logger.error(f"Invalid JSON response: {e}")
        finally:
            logger.debug(f"Received WebAPI response {request.status_code} from query")

    return metadata


_RETRYABLE_HTTP_CODES = {429, 500, 502, 503, 504}
_MAX_CHUNK_ATTEMPTS = 3


def ISteamRemoteStorage_GetPublishedFileDetails(
    publishedfileids: list[str],
) -> tuple[list[Any], list[str], list[str]]:
    """
    Query Steam WebAPI for published file details with per-chunk retry.

    https://steamapi.xpaw.me/#ISteamRemoteStorage/GetPublishedFileDetails

    :param publishedfileids: PublishedFileIds to look up
    :return: Tuple of (metadata_list, failed_pfids, error_descriptions)
    """
    url = "https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/"
    metadata: list[Any] = []
    failed_pfids: list[str] = []
    errors: list[str] = []
    total = len(publishedfileids)
    items_processed = 0

    for chunk in list(chunks(_list=publishedfileids, limit=5000)):
        chunk_size = len(chunk)
        items_processed += chunk_size

        data: dict[str, str] = {"itemcount": str(chunk_size)}
        for i, publishedfileid in enumerate(chunk):
            data[f"publishedfileids[{i}]"] = publishedfileid

        last_error_desc = ""

        for attempt in range(_MAX_CHUNK_ATTEMPTS):
            try:
                request = http.post(url, data=data, timeout=(5, 60))

                if request.status_code in _RETRYABLE_HTTP_CODES:
                    last_error_desc = f"Steam API returned HTTP {request.status_code}"
                    raise requests.exceptions.HTTPError(
                        last_error_desc, response=request
                    )

                if request.status_code >= 400:
                    last_error_desc = f"Steam API returned HTTP {request.status_code}"
                    logger.error(
                        f"GetPublishedFileDetails chunk [{items_processed}/{total}]: "
                        f"{last_error_desc} (non-retryable)"
                    )
                    failed_pfids.extend(chunk)
                    errors.append(f"{last_error_desc} for {chunk_size} mods")
                    break

                try:
                    json_response = request.json()
                except requests.exceptions.JSONDecodeError as e:
                    last_error_desc = (
                        f"Invalid JSON response (HTTP {request.status_code})"
                    )
                    logger.error(
                        f"GetPublishedFileDetails chunk [{items_processed}/{total}]: "
                        f"{last_error_desc}: {e}"
                    )
                    failed_pfids.extend(chunk)
                    errors.append(f"{last_error_desc} for {chunk_size} mods")
                    break

                if json_response.get("response", {}).get("resultcount", 0) > 0:
                    for mod_metadata in json_response["response"][
                        "publishedfiledetails"
                    ]:
                        metadata.append(mod_metadata)
                logger.debug(
                    f"GetPublishedFileDetails chunk [{items_processed}/{total}]: "
                    f"HTTP {request.status_code}, "
                    f"{json_response.get('response', {}).get('resultcount', 0)} results"
                )
                break

            except (
                requests.exceptions.Timeout,
                requests.exceptions.ConnectionError,
                requests.exceptions.HTTPError,
            ) as e:
                if not last_error_desc:
                    last_error_desc = f"{e.__class__.__name__}: {e}"

                if attempt < _MAX_CHUNK_ATTEMPTS - 1:
                    delay = 2**attempt  # 1s, 2s
                    logger.warning(
                        f"GetPublishedFileDetails chunk [{items_processed}/{total}] "
                        f"failed (attempt {attempt + 1}/{_MAX_CHUNK_ATTEMPTS}): "
                        f"{last_error_desc}. Retrying in {delay}s..."
                    )
                    sleep(delay)
                    last_error_desc = ""
                else:
                    logger.error(
                        f"GetPublishedFileDetails chunk [{items_processed}/{total}] "
                        f"failed after {_MAX_CHUNK_ATTEMPTS} attempts: {last_error_desc}"
                    )
                    failed_pfids.extend(chunk)
                    errors.append(
                        f"{last_error_desc} for {chunk_size} mods "
                        f"after {_MAX_CHUNK_ATTEMPTS} attempts"
                    )

    succeeded = total - len(failed_pfids)
    if total > 0:
        logger.info(
            f"GetPublishedFileDetails complete: queried {total} mods, "
            f"{succeeded} succeeded, {len(failed_pfids)} failed"
        )

    return metadata, failed_pfids, errors


if __name__ == "__main__":
    sys.exit()

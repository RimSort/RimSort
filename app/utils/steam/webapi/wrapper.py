import sys
import traceback
from logging import WARNING, getLogger
from math import ceil
from pathlib import Path
from time import time
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

import requests
from loguru import logger
from PySide6.QtCore import QCoreApplication, QObject, QRunnable, QThreadPool, Signal
from PySide6.QtWidgets import QInputDialog
from steam.webapi import WebAPI

from app.utils.app_info import AppInfo
from app.utils.constants import RIMWORLD_DLC_METADATA
from app.utils.generic import chunks
from app.utils.steam.steamworks.wrapper import steamworks_app_dependencies_worker
from app.views.dialogue import show_warning

STEAM_THERE_WAS_A_PROBLEM_FLAG = "There was a problem accessing the item. "

# Prevent circular dependencies for type checking
if TYPE_CHECKING:
    from app.utils.metadata import MetadataManager


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

    def __init__(self, metadata_manager: "MetadataManager") -> None:
        """
        Initialize the CollectionImport instance.

        Args:
            metadata_manager: The metadata manager instance.
        """
        self.metadata_manager = metadata_manager
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
        return link.startswith(BASE_URL) and (
            BASE_URL_STEAMFILES in link or BASE_URL_WORKSHOP in link
        )

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
                            f"Failed to parse packageId from collection PublishedFileId {pfid}: "
                            "incorrect pfid format"
                        )
                        failed_mods.append(f"{pfid} - incorrect pfid format")
                        continue
                    if pkgid is None:
                        # Try to check if the mod is inaccessible
                        steam_link = f"https://steamcommunity.com/sharedfiles/filedetails/?id={pfid}"

                        try:
                            steam_response = requests.get(steam_link).text
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
                            "This may happen if you don't have all the mods downloaded.\n\n"
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
        metadata_manager = self.metadata_manager
        if not metadata_manager:
            return None
        return next(
            (
                package_id
                for mod in metadata_manager.internal_local_metadata.values()
                if str(_find_value_in_dict(mod, "publishedfileid")) == pfid
                if (package_id := _find_value_in_dict(mod, "packageid"))
            ),
            None,
        )

    def _get_package_id_from_pfid_using_steamdb(self, pfid: str) -> str | None:
        steamdb = (
            self.metadata_manager.external_steam_metadata
            if self.metadata_manager
            else None
        )
        if not steamdb:
            return None
        mod = steamdb.get(pfid)
        if not mod:
            return None
        return _find_value_in_dict(mod, "packageid")

    def _get_package_id_from_pfid_using_mod_folder_name(self, pfid: str) -> str | None:
        metadata_manager = self.metadata_manager
        if not metadata_manager:
            return None
        return next(
            (
                package_id
                for mod in metadata_manager.internal_local_metadata.values()
                if (str_path := _find_value_in_dict(mod, "path"))
                if ((path := Path(str_path)).is_dir())
                if (path.name == pfid)
                if (package_id := _find_value_in_dict(mod, "packageid"))
            ),
            None,
        )


def _find_value_in_dict(coll: dict[str, Any], key: str) -> Any:
    key = key.strip().lower()
    key_found = next((_ for _ in coll.keys() if _.strip().lower() == key), None)
    if not key_found:
        return None
    return coll.get(key_found)


class AppDependenciesWorker(QRunnable):
    """
    QRunnable worker for querying app dependencies sequentially.

    Since SteamworksInterface enforces operation serialization (only one
    operation at a time via lock), we process chunks sequentially rather
    than in parallel.
    """

    class Signals(QObject):
        """Signal container for AppDependenciesWorker."""

        progress = Signal(str)  # Progress message
        chunk_complete = Signal(int, int)  # (current_chunk, total_chunks)
        finished = Signal(dict)  # Final results: dict[int, list[int]]
        error = Signal(str)  # Error message

    def __init__(
        self,
        publishedfileids: list[str],
        libs_path: str,
        chunk_size: int,
    ):
        """
        Initialize the AppDependenciesWorker.

        :param publishedfileids: List of PublishedFileIds to query
        :param libs_path: Path to Steamworks libraries
        :param chunk_size: Number of mods to process per chunk
        """
        super().__init__()
        self.publishedfileids = publishedfileids
        self.libs_path = libs_path
        self.chunk_size = chunk_size
        self.signals = self.Signals()
        self.setAutoDelete(True)

    def run(self) -> None:
        """Process all chunks sequentially and collect results."""
        try:
            pfids_appid_deps: dict[int, list[int]] = {}

            # Create chunks
            chunks_list = list(
                chunks(
                    _list=self.publishedfileids,
                    limit=self.chunk_size,
                )
            )
            total_chunks = len(chunks_list)

            # Emit initial progress
            self.signals.progress.emit(
                f"Processing {len(self.publishedfileids)} mods in {total_chunks} chunks"
            )

            # Process each chunk sequentially
            for idx, chunk in enumerate(chunks_list, start=1):
                # Convert string pfids to integers
                int_pfids = [eval(str_pfid) for str_pfid in chunk]

                # Emit progress
                self.signals.progress.emit(
                    f"Processing chunk {idx}/{total_chunks} ({len(int_pfids)} mods)"
                )

                # Query this chunk - SteamworksInterface handles locking
                result = steamworks_app_dependencies_worker(
                    pfid_or_pfids=int_pfids,
                    interval=1,
                    _libs=self.libs_path,
                )

                # Merge results
                if result is not None:
                    pfids_appid_deps.update(result)

                # Emit chunk completion
                self.signals.chunk_complete.emit(idx, total_chunks)

            # Emit final results
            self.signals.progress.emit(
                f"Completed! Collected {len(pfids_appid_deps)} results"
            )
            self.signals.finished.emit(pfids_appid_deps)

        except Exception as e:
            logger.error(f"Error in AppDependenciesWorker: {e}")
            self.signals.error.emit(str(e))


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
    ) -> None:
        QObject.__init__(self)

        logger.info("Initializing DynamicQuery")
        self.api = None
        self.apikey = apikey
        self.appid = appid
        self.expiry = self.__expires(life)
        self.get_appid_deps = get_appid_deps
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
        self, database: Dict[str, Any], publishedfileids: list[str]
    ) -> None:
        """
        Builds a database using a chunked WebAPI query of all available
        PublishedFileIds supplied.

        :param database: a database to update using IPublishedFileService_GetDetails queries
        :param publishedfileids: a list of PublishedFileIDs to query
        """

        self.__initialize_webapi()

        query = database
        query["version"] = self.expiry
        query["database"] = database["database"]
        querying = True
        while querying:  # Begin initial query
            result = self.IPublishedFileService_GetDetails(query, publishedfileids)

            if result is None:
                logger.warning(
                    f"Dynamic Query failed to initialize WebAPI query! Critical failure. Aborting steam_db creation. query: {query} publishedfileids: {publishedfileids}"
                )
                return

            # Returns WHAT we can get remotely, FROM what we have locally
            query, missing_children = result

            if (
                missing_children and len(missing_children) > 0
            ):  # If we have missing data for any dependency...
                # Uncomment to see the contents of missing_children
                # logger.debug(missing_children)
                self._emit_message(
                    f"\nRetrieving dependency information for {len(missing_children)} missing children"
                )
                # Extend publishedfileids with the missing_children PublishedFileIds for final query
                publishedfileids.extend(missing_children)
                # Launch a separate query from the initial, to recursively append
                # any of the missing_children's metadata to the query["database"].
                #
                # This will ensure that we get ALL dependency data that is possible,
                # even if we do not have the dependenc{y, ies}. It's not perfect,
                # because it will always cause one additional full query to ensure that
                # the query["database"] is complete with missing_children metadata.
                #
                # It is the only way to paint the full picture without already
                # possessing the mod's metadata for the initial query.
                result = self.IPublishedFileService_GetDetails(query, missing_children)

                if result is None:
                    logger.warning(
                        f"Dynamic Query failed to initialize WebAPI query! Critical failure. Aborting steam_db creation. Query: {query} Missing Children: {missing_children}"
                    )
                    return

                query, missing_children = result
                self._emit_message(
                    "\nLaunching addiitonal full query to complete dependency information for the missing children"
                )
            else:  # Stop querying once we have 0 missing_children
                missing_children = []
                querying = False

        if self.get_appid_deps:
            self._emit_message(
                "\nAppID dependency retrieval enabled. Starting Steamworks API call(s)"
            )
            # ISteamUGC/GetAppDependencies
            self.ISteamUGC_GetAppDependencies(
                publishedfileids=publishedfileids, query=query
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
    ) -> tuple[dict[Any, Any], list[str]] | None:
        """

        Given a list of PublishedFileIds, return a dict of json data queried
        from Steam WebAPI, containing data to be parsed during db update.

        https://steamapi.xpaw.me/#IPublishedFileService/GetDetails
        https://steamwebapi.azurewebsites.net (Ctrl + F search: "IPublishedFileService/GetDetails")

        :param json_to_update: a Dict of json data, containing a query to update in
        RimPy db_data["database"] format, or the skeleton of one from local_metadata
        :param publishedfileids: a list of PublishedFileIds to query Steam Workshop mod metadata for
        :return: Tuple containing the updated json data from PublishedFileIds query, as well as
        a list of any missing children's PublishedFileIds to consider for additional queries
            OR None, None -  which indicates a critical failure in an ongoing Dynamic Query
        """
        chunks_processed = 0
        total = len(publishedfileids)
        self._emit_message(
            f"\nSteam WebAPI: IPublishedFileService/GetDetails initializing for {total} mods\n\n"
        )
        self._emit_message(f"IPublishedFileService/GetDetails chunk [0/{total}]")
        if not self.api:  # If we don't have API initialized
            return None  # Exit query
        missing_children = []
        result = json_to_update
        # Uncomment to see the all pfids to be queried
        # logger.debug(f"PublishedFileIds being queried: {publishedfileids}")
        for chunk in chunks(
            _list=publishedfileids, limit=213
        ):  # Chunk limit appears to be 213 PublishedFileIds at a time - this appears to be a WebAPI limitation
            chunk_total = len(chunk)
            chunks_processed += chunk_total
            # Uncomment to see the pfids from each chunk
            # logger.debug(f"{chunk_total} PublishedFileIds in chunk: {chunk}")
            try:
                response = self.api.call(
                    method_path="IPublishedFileService.GetDetails",
                    key=self.apikey,
                    publishedfileids=chunk,
                    includetags=False,
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
                for metadata in response["response"]["publishedfiledetails"]:
                    publishedfileid = metadata[
                        "publishedfileid"
                    ]  # Set the PublishedFileId to that of the metadata we are parsing

                    # Uncomment this to view the metadata being parsed in real time
                    # logger.debug(f"{publishedfileid}: {metadata}")
                    # If the mod is no longer published
                    if metadata["result"] != 1:
                        if not result[
                            "database"
                        ].get(
                            publishedfileid
                        ):  # If we don't already have a ["database"] entry for this pfid
                            result["database"][publishedfileid] = {}
                        logger.debug(
                            f"Tried to parse metadata for a mod that is deleted/private/removed/unposted: {publishedfileid}"
                        )
                        result["database"][publishedfileid]["unpublished"] = True
                        # If mod is unpublished, it has no metadata.
                        continue  # We are done with this publishedfileid
                    else:
                        # This case is mostly intended for any missing_children passed back thru
                        # If this is part of an AppIDQuery, then it is useful for population of
                        # child_name and/or child_url below as part of the dependency data being collected
                        if not result[
                            "database"
                        ].get(
                            publishedfileid
                        ):  # If we don't already have a ["database"] entry for this pfid
                            result["database"][
                                publishedfileid
                            ] = {}  # Add in skeleton data
                        # We populate the data
                        result["database"][publishedfileid]["steamName"] = metadata[
                            "title"
                        ]
                        result["database"][publishedfileid]["url"] = (
                            f"https://steamcommunity.com/sharedfiles/filedetails/?id={publishedfileid}"
                        )
                        # Track time publishing created
                        # result["database"][publishedfileid][
                        #     "external_time_created"
                        # ] = metadata["time_created"]
                        # # Track time publishing last updated
                        # result["database"][publishedfileid][
                        #     "external_time_updated"
                        # ] = metadata["time_updated"]
                        result["database"][publishedfileid]["dependencies"] = {}
                        # If the publishing has listed mod dependencies
                        if metadata.get("children"):
                            for children in metadata[
                                "children"
                            ]:  # Check if children present in database
                                child_pfid = children["publishedfileid"]
                                if result["database"].get(
                                    child_pfid
                                ):  # If we have data for this child already cached
                                    if not result["database"][child_pfid].get(
                                        "unpublished"
                                    ):  # ... and the mod is published, populate it
                                        if result["database"][child_pfid].get(
                                            "name"
                                        ):  # Use local name over Steam name if possible
                                            child_name = result["database"][child_pfid][
                                                "name"
                                            ]
                                        elif result["database"][child_pfid].get(
                                            "steamName"
                                        ):
                                            child_name = result["database"][child_pfid][
                                                "steamName"
                                            ]
                                        else:  # This is a stub value used in-memory only (hopefully)
                                            # and is intended for AppIdQuery first pass
                                            child_name = "UNKNOWN"
                                        child_url = result["database"][child_pfid][
                                            "url"
                                        ]
                                        result["database"][publishedfileid][
                                            "dependencies"
                                        ][child_pfid] = [child_name, child_url]
                                else:  # Child was not found in database, track it's pfid for later
                                    if child_pfid not in missing_children:
                                        logger.debug(
                                            f"Could not find pfid {child_pfid} in database. Adding child to missing_children"
                                        )
                                        missing_children.append(child_pfid)
            except Exception as e:
                stacktrace = traceback.format_exc()
                if (
                    e.__class__.__name__ == "HTTPError"
                    or e.__class__.__name__ == "SSLError"
                ):  # requests.exceptions.HTTPError OR urllib3.exceptions.SSLError
                    # If an HTTPError from steam/urllib3 module(s) somehow is uncaught,
                    # try to remove the Steam API key from the stacktrace
                    pattern = "&key="
                    stacktrace = stacktrace[
                        : len(stacktrace)
                        - (len(stacktrace) - (stacktrace.find(pattern) + len(pattern)))
                    ]
                logger.error(
                    f"IPublishedFileService/GetDetails errored querying batch [{chunks_processed}/{total}]: {stacktrace}"
                )
            self._emit_message(
                f"IPublishedFileService/GetDetails chunk [{chunks_processed}/{total}]"
            )
        for missing_child in missing_children:
            if result["database"].get(missing_child) and result["database"][
                missing_child
            ].get(
                "unpublished"
            ):  # If there is somehow an unpublished mod in missing_children, remove it
                missing_children.remove(missing_child)
        return result, missing_children

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

    def ISteamUGC_GetAppDependencies(
        self, publishedfileids: list[str], query: Dict[str, Any]
    ) -> None:
        """
        Given a list of PublishedFileIds and a query, return the query after looking up
        and appending DLC dependency data from the Steamworks API.

        https://partner.steamgames.com/doc/api/ISteamUGC#GetAppDependencies

        :param publishedfileids: a list of PublishedFileIds to query metadata for
        :param json_to_update: a Dict of json data, containing a query to update in
        RimPy db_data["database"] format, or the skeleton of one from local_metadata
        :return: Dict containing the updated json data from PublishedFileIds query
        """
        self._emit_message(
            f"\nSteamworks API: ISteamUGC/GetAppDependencies initializing for {len(publishedfileids)} mods\n\nThis may take a while. Please wait..."
        )

        # Determine chunk size - balance between progress granularity and overhead
        # Process ~50-100 mods per chunk for reasonable progress updates
        chunk_size = min(100, max(50, len(publishedfileids) // 10))

        # Storage for results (accessed only after worker completes)
        pfids_appid_deps: dict[int, list[int]] = {}
        worker_error: list[str] = []  # Mutable container for error capture

        # Create worker
        worker = AppDependenciesWorker(
            publishedfileids=publishedfileids,
            libs_path=str(AppInfo().application_folder / "libs"),
            chunk_size=chunk_size,
        )

        # Connect signals
        worker.signals.progress.connect(lambda msg: self._emit_message(f"\n{msg}"))
        worker.signals.chunk_complete.connect(
            lambda current, total: self._emit_message(
                f"Chunk {current}/{total} complete"
            )
        )
        worker.signals.finished.connect(
            lambda results: pfids_appid_deps.update(results)
        )
        worker.signals.error.connect(lambda error: worker_error.append(error))

        # Use global thread pool (consistent with rest of codebase)
        thread_pool = QThreadPool.globalInstance()

        # Start worker
        thread_pool.start(worker)

        # Wait for completion - QThreadPool.waitForDone() waits for all tasks
        self._emit_message("\nWaiting for Steamworks queries to complete...")
        thread_pool.waitForDone()

        # Check for errors
        if worker_error:
            self._emit_message(f"\nError during processing: {worker_error[0]}")
            logger.error(f"AppDependencies worker failed: {worker_error[0]}")
            return

        self._emit_message("\nThreads completed!\nCollecting results...")
        self._emit_message(f"\nTotal: {len(pfids_appid_deps.keys())}")
        # Uncomment to see the total metadata returned from all Processes
        # logger.debug(pfids_appid_deps)
        # Add our metadata to the query...
        logger.debug("Populating AppID dependency information into database from query")
        for pfid in query["database"].keys():
            if int(pfid) in pfids_appid_deps:
                for appid in pfids_appid_deps[int(pfid)]:
                    if str(appid) in RIMWORLD_DLC_METADATA.keys():
                        if not query["database"][pfid].get("dependencies"):
                            query["database"][pfid]["dependencies"] = {}
                        query["database"][pfid]["dependencies"].update(
                            {
                                str(appid): [
                                    RIMWORLD_DLC_METADATA[str(appid)]["name"],
                                    RIMWORLD_DLC_METADATA[str(appid)]["steam_url"],
                                ]
                            }
                        )


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
            request = requests.post(url, data=data)
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


def ISteamRemoteStorage_GetPublishedFileDetails(
    publishedfileids: list[str],
) -> list[Any] | None:
    """
    Given a list of PublishedFileIds, return a dict of json data queried
    from Steam WebAPI, containing data to be parsed.

    https://steamapi.xpaw.me/#ISteamRemoteStorage/GetPublishedFileDetails

    :param publishedfileids: a list of 1 or more publishedfileids to lookup metadata for
    :return: a JSON object that is the response from your WebAPI query
    """
    # Construct the URL to retrieve information about the mod
    url = "https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/"
    metadata = []
    # Construct arguments to pass to the API call
    for chunk in list(chunks(_list=publishedfileids, limit=5000)):
        logger.debug(f"Querying details for {len(chunk)} mod(s) via Steam WebAPI")
        # Construct arguments to pass to the API call
        data = {"itemcount": f"{str(len(chunk))}"}
        for publishedfileid in chunk:
            count = chunk.index(publishedfileid)
            data[f"publishedfileids[{count}]"] = publishedfileid
        try:  # Make a request to the Steam Web API
            request = requests.post(url, data=data)
        except Exception as e:
            logger.debug(
                f"Unable to complete request! Are you connected to the internet? Received exception: {e.__class__.__name__}"
            )
            return None
        try:  # Parse the JSON response
            json_response = request.json()
            if json_response.get("response", {}).get("resultcount", 0) > 0:
                for mod_metadata in json_response["response"]["publishedfiledetails"]:
                    metadata.append(mod_metadata)
        except requests.exceptions.JSONDecodeError as e:
            logger.error(f"Invalid JSON response: {e}")
        finally:
            logger.debug(f"Received WebAPI response {request.status_code} from query")

    return metadata


if __name__ == "__main__":
    sys.exit()

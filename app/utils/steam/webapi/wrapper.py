import sys
import traceback
from logging import getLogger, WARNING
from math import ceil
from multiprocessing import cpu_count, Pool
from time import time
from typing import Any, Dict, Optional, Tuple

from PySide6.QtCore import QObject, Signal
from loguru import logger
from requests import post as requests_post
from requests.exceptions import JSONDecodeError
from steam.webapi import WebAPI

from app.models.dialogue import show_dialogue_input, show_warning
from app.utils.app_info import AppInfo
from app.utils.constants import RIMWORLD_DLC_METADATA
from app.utils.generic import chunks
from app.utils.steam.steamworks.wrapper import SteamworksAppDependenciesQuery

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

    def __init__(self, metadata_manager):
        """
        Initialize the CollectionImport instance.

        Args:
            metadata_manager: The metadata manager instance.
        """
        self.metadata_manager = metadata_manager
        self.package_ids: list[str] = (
            []
        )  # Initialize an empty list to store package IDs
        self.publishedfileids: list[str] = []  # Initialize an empty list to store pfids
        self.input_dialog()  # Call the input_dialog method to set up the UI

    def input_dialog(self):
        # Initialize the UI for entering collection links
        self.link_input = show_dialogue_input(
            title="Add Workshop collection link",
            text="Add Workshop collection link",
        )
        self.import_collection_link()
        logger.info("Workshop collection link Input UI initialized successfully!")

    def is_valid_collection_link(self, link):
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

    def import_collection_link(self):
        # Handle the import button click event
        logger.info("Import Workshop collection clicked")
        collection_link = self.link_input[0]
        steamdb = (
            self.metadata_manager.external_steam_metadata
            if self.metadata_manager
            else None
        )

        # Check if the input link is a valid workshop collection link
        if not self.is_valid_collection_link(collection_link):
            logger.error(
                "Invalid Workshop collection link. Please enter a valid Workshop collection link."
            )
            # Show warning message box
            show_warning(
                title="Invalid Link",
                text="Invalid Workshop collection link. Please enter a valid Workshop collection link.",
            )
            return

        # Check if there is a steamdb supplied
        if not steamdb:
            logger.error(
                "Cannot import collection without SteamDB supplied! Please configure Steam Workshop Database in settings."
            )
            # Show warning message box
            show_warning(
                title="Invalid Database",
                text="Cannot import collection without SteamDB supplied! Please configure Steam Workshop Database in settings.",
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
            if len(collection_webapi_result) > 0:
                for mod in collection_webapi_result[0]["children"]:
                    if mod.get("publishedfileid"):
                        self.publishedfileids.append(mod["publishedfileid"])
                for pfid in self.publishedfileids:
                    if steamdb.get(pfid, {}).get("packageId"):
                        self.package_ids.append(steamdb[pfid]["packageId"])
                    else:
                        logger.warning(
                            f"Failed to parse packageId from collection PublishedFileId {pfid}"
                        )
                logger.info("Parsed packageIds from publishedfileids successfully")
        except Exception as e:
            logger.error(
                f"An error occurred while fetching collection content: {str(e)}"
            )


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
        get_appid_deps=None,
        life=None,
    ):
        QObject.__init__(self)

        logger.info("Initializing DynamicQuery")
        self.api = None
        self.apikey = apikey
        self.appid = appid
        if life:
            self.expiry = self.__expires(life)
        self.get_appid_deps = get_appid_deps
        self.next_cursor = "*"
        self.pagenum = 1
        self.pages = 1
        self.publishedfileids = []
        self.total = 0
        self.database = {}

    def __expires(self, life: int) -> int:
        return int(time() + life)  # current seconds since epoch + 30 minutes

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
            self.dq_messaging_signal.emit(
                "\nDynamicQuery failed to initialize WebAPI query!"
                + "\nAre you connected to the internet?\nIs your configured key invalid or revoked?\n",
            )

    def create_steam_db(self, database: Dict[str, Any], publishedfileids: list) -> None:
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
            (  # Returns WHAT we can get remotely, FROM what we have locally
                query,
                missing_children,
            ) = self.IPublishedFileService_GetDetails(query, publishedfileids)
            if (
                missing_children and len(missing_children) > 0
            ):  # If we have missing data for any dependency...
                # Uncomment to see the contents of missing_children
                # logger.debug(missing_children)
                self.dq_messaging_signal.emit(
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
                (
                    query,
                    missing_children,
                ) = self.IPublishedFileService_GetDetails(query, missing_children)
                self.dq_messaging_signal.emit(
                    f"\nLaunching addiitonal full query to complete dependency information for the missing children"
                )
            else:  # Stop querying once we have 0 missing_children
                missing_children = []
                querying = False

        if self.get_appid_deps:
            self.dq_messaging_signal.emit(
                "\nAppID dependency retrieval enabled. Starting Steamworks API call(s)"
            )
            # ISteamUGC/GetAppDependencies
            self.ISteamUGC_GetAppDependencies(
                publishedfileids=publishedfileids, query=query
            )
        else:
            self.dq_messaging_signal.emit(
                "\nAppID dependency retrieval disabled. Skipping Steamworks API call(s)!"
            )

        # Notify & return
        total = len(query["database"])
        self.dq_messaging_signal.emit(
            f"\nReturning Steam Workshop metadata for {total} items"
        )
        self.database.update(query)

    def pfids_by_appid(self) -> None:
        """
        Builds a total collection of PublishedFileIds representing a list of all workshop mods
        for any given Steam AppID. These PublishedFileIds can be used in a many ways!
        """

        self.__initialize_webapi()

        if self.api:
            self.query = True
            while self.query:
                if self.pagenum > self.pages:
                    self.query = False
                    break
                self.next_cursor = self.IPublishedFileService_QueryFiles(
                    self.next_cursor
                )
        else:
            self.query = False
            self.dq_messaging_signal.emit(f"AppIDQuery: WebAPI failed to initialize!")

    def IPublishedFileService_GetDetails(
        self, json_to_update: Dict[Any, Any], publishedfileids: list
    ) -> Optional[Tuple[Dict[Any, Any], list]]:
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
        self.dq_messaging_signal.emit(
            f"\nSteam WebAPI: IPublishedFileService/GetDetails initializing for {total} mods\n\n"
        )
        self.dq_messaging_signal.emit(
            f"IPublishedFileService/GetDetails chunk [0/{total}]"
        )
        if not self.api:  # If we don't have API initialized
            return None, None  # Exit query
        missing_children = []
        result = json_to_update
        # Uncomment to see the all pfids to be queried
        # logger.debug(f"PublishedFileIds being queried: {publishedfileids}")
        for chunk in chunks(
            _list=publishedfileids, limit=215
        ):  # Chunk limit appears to be 215 PublishedFileIds at a time - this appears to be a WebAPI limitation
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
                        if not result["database"].get(
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
                        if not result["database"].get(
                            publishedfileid
                        ):  # If we don't already have a ["database"] entry for this pfid
                            result["database"][
                                publishedfileid
                            ] = {}  # Add in skeleton data
                        # We populate the data
                        result["database"][publishedfileid]["steamName"] = metadata[
                            "title"
                        ]
                        result["database"][publishedfileid][
                            "url"
                        ] = f"https://steamcommunity.com/sharedfiles/filedetails/?id={publishedfileid}"
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
            self.dq_messaging_signal.emit(
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
                self.dq_messaging_signal.emit(
                    f"IPublishedFileService/QueryFiles page [0" + f"/{str(self.pages)}]"
                )
        self.dq_messaging_signal.emit(
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
        self, publishedfileids: list, query: Dict[str, Any]
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
        self.dq_messaging_signal.emit(
            f"\nSteamworks API: ISteamUGC/GetAppDependencies initializing for {len(publishedfileids)} mods\n"
        )
        # Maximum processes
        num_processes = cpu_count()
        # Create a pool of worker processes
        with Pool(processes=num_processes) as pool:
            # Create instances of SteamworksAppDependenciesQuery for each chunk
            queries = [
                SteamworksAppDependenciesQuery(
                    pfid_or_pfids=[eval(str_pfid) for str_pfid in chunk],
                    interval=1,
                    _libs=str((AppInfo().application_folder / "libs")),
                )
                for chunk in list(
                    chunks(
                        _list=publishedfileids,
                        limit=ceil(len(publishedfileids) / num_processes),
                    )
                )
            ]
            # Map the execution of the queries to the pool of processes
            results = pool.map(SteamworksAppDependenciesQuery.run, queries)
        # Merge the results from all processes into a single dictionary
        self.dq_messaging_signal.emit("Processes completed!\nCollecting results")
        pfids_appid_deps = {}
        for result in results:
            pfids_appid_deps.update(result)
        self.dq_messaging_signal.emit(f"\nTotal: {len(pfids_appid_deps.keys())}")
        # Uncomment to see the total metadata returned from all Processes
        # logger.debug(pfids_appid_deps)
        # Add our metadata to the query...
        logger.debug(
            f"Populating AppID dependency information into database from query"
        )
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
    publishedfileids: list,
) -> Optional[list]:
    """
    Given a list of Steam Workshopmod collection PublishedFileIds, return a dict of
    json data queried from Steam WebAPI, containing data to be parsed.

    https://steamapi.xpaw.me/#ISteamRemoteStorage/GetCollectionDetails

    :param publishedfileids: a list of 1 or more publishedfileids to lookup metadata for
    :return: a JSON object that is the response from your WebAPI query
    """
    # Construct the URL to retrieve information about the collection
    url = f"https://api.steampowered.com/ISteamRemoteStorage/GetCollectionDetails/v1/"
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
            request = requests_post(url, data=data)
        except Exception as e:
            logger.warning(
                f"Unable to complete request! Are you connected to the internet? Received exception: {e.__class__.__name__}"
            )
            return None
        try:  # Parse the JSON response
            json_response = request.json()
            logger.debug(json_response)
            if json_response.get("response", {}).get("resultcount") > 0:
                for mod_metadata in json_response["response"]["collectiondetails"]:
                    metadata.append(mod_metadata)
        except JSONDecodeError as e:
            logger.error(f"Invalid JSON response: {e}")
        finally:
            logger.debug(f"Received WebAPI response {request.status_code} from query")

    return metadata


def ISteamRemoteStorage_GetPublishedFileDetails(
    publishedfileids: list,
) -> Optional[list]:
    """
    Given a list of PublishedFileIds, return a dict of json data queried
    from Steam WebAPI, containing data to be parsed.

    https://steamapi.xpaw.me/#ISteamRemoteStorage/GetPublishedFileDetails

    :param publishedfileids: a list of 1 or more publishedfileids to lookup metadata for
    :return: a JSON object that is the response from your WebAPI query
    """
    # Construct the URL to retrieve information about the mod
    url = (
        f"https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/"
    )
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
            request = requests_post(url, data=data)
        except Exception as e:
            logger.debug(
                f"Unable to complete request! Are you connected to the internet? Received exception: {e.__class__.__name__}"
            )
            return None
        try:  # Parse the JSON response
            json_response = request.json()
            if json_response.get("response", {}).get("resultcount") > 0:
                for mod_metadata in json_response["response"]["publishedfiledetails"]:
                    metadata.append(mod_metadata)
        except JSONDecodeError as e:
            logger.error(f"Invalid JSON response: {e}")
        finally:
            logger.debug(f"Received WebAPI response {request.status_code} from query")

    return metadata


if __name__ == "__main__":
    sys.exit()

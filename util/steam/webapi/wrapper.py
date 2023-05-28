import json
from logging import getLogger, WARNING
from logger_tt import logger
from math import ceil
from multiprocessing import Queue
from requests import post as requests_post
from requests.exceptions import HTTPError, JSONDecodeError
import sys
from time import time
import traceback
from typing import Any, Dict, List, Optional, Tuple, Union

from PySide6.QtCore import QObject, Signal

from model.dialogue import show_fatal_error
from steam.webapi import WebAPI
from util.constants import RIMWORLD_DLC_METADATA
from util.steam.steamworks.wrapper import SteamworksAppDependenciesQuery
from window.runner_panel import RunnerPanel


# This is redundant since it is also done in `logger-tt` config,
# however, it can't hurt, just in case!
# Uncomment this if you want to see the full urllib3 request
# THIS CONTAINS THE STEAM API KEY
getLogger("urllib3").setLevel(WARNING)


class AppIDQuery(QObject):
    """
    Create AppIDQuery object to initialize the scraped data from Workshop
    """

    appid_messaging_signal = Signal(str)

    def __init__(
        self,
        apikey: str,
        appid: int,
    ):
        QObject.__init__(self)

        logger.info("Initializing AppIDQuery...")
        self.apikey = apikey
        self.appid = appid
        self.next_cursor = "*"
        self.pagenum = 1
        self.pages = 1
        self.publishedfileids = []
        self.total = 0

    def __initialize_webapi(self) -> None:
        try:  # Try to initialize the API
            self.api = WebAPI(self.apikey, format="json", https=True)
        except Exception as e:
            self.api = None
            # Catch exceptions that can potentially leak Steam API key
            e_name = e.__class__.__name__
            stacktrace = traceback.format_exc()
            pattern = "&key="
            if pattern in stacktrace:
                stacktrace = stacktrace[
                    : len(stacktrace)
                    - (len(stacktrace) - (stacktrace.find(pattern) + len(pattern)))
                ]  # If an HTTPError/SSLError from steam/urllib3 module(s) somehow is uncaught, try to remove the Steam API key from the stacktrace
            self.appid_messaging_signal.emit(
                f"Dynamic Query received an uncaught exception: {e_name}\nPlease reach out to us on Discord/Github!"
            )
            show_fatal_error(
                text="RimSort AppIDQuery",
                information="AppIDQuery failed to initialize WebAPI query!\n\n"
                + "Are you connected to the internet?\n\nIs your configured key invalid or revoked?\n\n",
                details=stacktrace,
            )

    def compile_pfids_by_appid(self):
        """
        Builds a total collection of PublishedFileIds representing a list of all workshop mods
        for any given Steam AppID. These PublishedFileIds can be used in a many ways!
        """
        self.appid_messaging_signal.emit(f"AppIDQuery initializing for {self.appid}")

        self.__initialize_webapi()

        if self.api:
            self.query = True
            self.appid_messaging_signal.emit(
                f"WebAPI initialized! Compiling list of all Workshop mod PublishedFileIDs for {self.appid}..."
            )
            while self.query:
                if self.pagenum > self.pages:
                    self.query = False
                    break
                self.next_cursor = self.IPublishedFileService_QueryFiles(
                    self.next_cursor
                )
        else:
            self.query = False
            self.appid_messaging_signal.emit(
                f"AppIDQuery: WebAPI failed to initialize!"
            )

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
                self.appid_messaging_signal.emit(
                    f"Total mod items to parse: {str(self.total)}"
                )
        self.appid_messaging_signal.emit(
            f"IPublishedFileService.QueryFiles page [{str(self.pagenum)}"
            + f"/{str(self.pages)}]"
        )
        ids_from_page = []
        for item in result["response"]["publishedfiledetails"]:
            self.publishedfileids.append(item["publishedfileid"])
            ids_from_page.append(item["publishedfileid"])
        self.pagenum += 1
        return result["response"]["next_cursor"]


class DynamicQuery(QObject):
    """
    Create DynamicQuery object to initialize the scraped data from Workshop

    :param apikey: Steam API key to be used for query
    :param appid: The AppID associated with the game you are looking up info for
    :param life: The lifespan of the Query in terms of the seconds added to the time of
    database generation. This adds an 'expiry' to the data being cached.
    """

    dq_messaging_signal = Signal(str)

    def __init__(
        self,
        apikey: str,
        appid: int,
        life: int,
        get_appid_deps=None,
    ):
        QObject.__init__(self)

        logger.info("Initializing DynamicQuery...")
        self.apikey = apikey
        self.appid = appid
        self.expiry = self.__expires(life)
        self.workshop_json_data = {}
        self.get_appid_deps = get_appid_deps

    def __chunks(self, _list: list, limit: int):
        """
        Split list into chunks no larger than the configured limit

        :param _list: a list to break into chunks
        :param limit: maximum size of the returned list
        """
        for i in range(0, len(_list), limit):
            yield _list[i : i + limit]

    def __expires(self, life: int) -> int:
        return int(time() + life)  # current seconds since epoch + 30 minutes

    def __initialize_webapi(self) -> None:
        try:  # Try to initialize the API
            self.api = WebAPI(self.apikey, format="json", https=True)
        except Exception as e:
            self.api = None
            # Catch exceptions that can potentially leak Steam API key
            e_name = e.__class__.__name__
            stacktrace = traceback.format_exc()
            pattern = "&key="
            if pattern in stacktrace:
                stacktrace = stacktrace[
                    : len(stacktrace)
                    - (len(stacktrace) - (stacktrace.find(pattern) + len(pattern)))
                ]  # If an HTTPError/SSLError from steam/urllib3 module(s) somehow is uncaught, try to remove the Steam API key from the stacktrace
            self.dq_messaging_signal.emit(
                f"Dynamic Query received an uncaught exception: {e_name}\nPlease reach out to us on Discord/Github!"
            )
            show_fatal_error(
                text="RimSort Dynamic Query",
                information="DynamicQuery failed to initialize WebAPI query!\n\n"
                + "Are you connected to the internet?\n\nIs your configured key invalid or revoked?\n\n",
                details=stacktrace,
            )

    def cache_parsable_db_data(
        self, database: Dict[str, Any], publishedfileids: list
    ) -> None:
        """
        Builds a database using a chunked WebAPI query of all available PublishedFileIds
        that are pulled from local mod metadata.

        :param database: a database to update using IPublishedFileService_GetDetails queries
        """

        self.dq_messaging_signal.emit(
            f"\nDynamicQuery initializing for {len(publishedfileids)} mods"
        )

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
            # None check, if None, this indicates the Query failed...
            if query is None or missing_children is None:
                return None
            if (
                len(missing_children) > 0
            ):  # If we have missing data for any dependency...
                self.dq_messaging_signal.emit(
                    f"Retrieving dependency information for the following missing children: {missing_children}"
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
            else:  # Stop querying once we have 0 missing_children
                missing_children = []
                querying = False

        if self.get_appid_deps:
            self.dq_messaging_signal.emit(
                "Parameter `get_appid_deps` is set to True. Retrieving AppID dependency information with Steamworks API..."
            )
            self.dq_messaging_signal.emit(
                "Starting ISteamUGC/GetAppDependencies... This may take awhile..."
            )
            # ISteamUGC/GetAppDependencies
            queue = Queue()
            steamworks_api_process = SteamworksAppDependenciesQuery(
                [eval(str_pfid) for str_pfid in publishedfileids], queue=queue
            )  # Convert the list of string pfid to integers - SW API requirement
            # Launch query & pass Queue for metadata return
            steamworks_api_process.start()
            steamworks_api_process.join()
            pfids_appid_deps = (
                queue.get()
            )  # Queue contains our metadata: {int publishedFileId: [int appid(s)]}
            for pfid in query["database"].keys():
                if int(pfid) in pfids_appid_deps:
                    self.dq_messaging_signal.emit(
                        f"Populating AppID dependency information for mod {pfid}..."
                    )
                    for appid in pfids_appid_deps[int(pfid)]:
                        query["database"][pfid]["dependencies"].update(
                            {
                                str(appid): [
                                    RIMWORLD_DLC_METADATA[str(appid)]["name"],
                                    RIMWORLD_DLC_METADATA[str(appid)]["steam_url"],
                                ]
                            }
                        )
        else:
            self.dq_messaging_signal.emit(
                "Parameter `get_appid_deps` is set to False or was not passed."
            )
            self.dq_messaging_signal.emit("Skipping ISteamUGC/GetAppDependencies...")

        # Notify & return
        total = len(query["database"])
        self.dq_messaging_signal.emit(
            f"Returning Steam Workshop metadata for {total} PublishedFileIds"
        )
        self.workshop_json_data = query.copy()

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
        if not self.api:  # If we don't have API initialized
            return None, None  # Exit query
        missing_children = []
        result = json_to_update
        # Uncomment to see the all pfids to be queried
        # self.dq_messaging_signal.emit(f"PublishedFileIds being queried: {publishedfileids}")
        for batch in self.__chunks(
            publishedfileids, 215
        ):  # Batch limit appears to be 215 PublishedFileIds at a time - this appears to be a WebAPI limitation
            self.dq_messaging_signal.emit(f"Retrieving metadata for {len(batch)} mods")
            # Uncomment to see the pfids from each batch
            # self.dq_messaging_signal.emit(f"PublishedFileIds in batch: {batch}")
            response = self.api.call(
                method_path="IPublishedFileService.GetDetails",
                key=self.apikey,
                publishedfileids=batch,
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
            )
            for metadata in response["response"]["publishedfiledetails"]:
                publishedfileid = metadata[
                    "publishedfileid"
                ]  # Set the PublishedFileId to that of the metadata we are parsing

                # Uncomment this to view the metadata being parsed in real time
                # self.dq_messaging_signal.emit(f"{publishedfileid}: {metadata}")

                # If the mod is no longer published
                if metadata["result"] != 1:
                    if not result["database"].get(
                        publishedfileid
                    ):  # If we don't already have a ["database"] entry for this pfid
                        result["database"][publishedfileid] = {}
                    self.dq_messaging_signal.emit(
                        f"Tried to parse metadata for a mod that is deleted/private/removed/unposted: {publishedfileid}"
                    )
                    result["database"][
                        publishedfileid
                    ][  # Reflect the mod's status in it's attributes
                        "steamName"
                    ] = "Missing mod: deleted/private/removed/unposted"
                    result["database"][publishedfileid][
                        "url"
                    ] = f"https://steamcommunity.com/sharedfiles/filedetails/?id={publishedfileid}"
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
                        result["database"][publishedfileid] = {}  # Add in skeleton data
                        result["database"][publishedfileid]["missing"] = True
                    # We populate the data
                    result["database"][publishedfileid]["steamName"] = metadata["title"]
                    result["database"][publishedfileid][
                        "url"
                    ] = f"https://steamcommunity.com/sharedfiles/filedetails/?id={publishedfileid}"
                    # Track time publishing created
                    result["database"][publishedfileid][
                        "external_time_created"
                    ] = metadata["time_created"]
                    # Track time publishing last updated
                    result["database"][publishedfileid][
                        "external_time_updated"
                    ] = metadata["time_updated"]
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
                                    child_url = result["database"][child_pfid]["url"]
                                    result["database"][publishedfileid]["dependencies"][
                                        child_pfid
                                    ] = [child_name, child_url]
                            else:  # Child was not found in database, track it's pfid for later
                                if child_pfid not in missing_children:
                                    self.dq_messaging_signal.emit(
                                        f"Could not find pfid {child_pfid} in database. Adding child to missing_children..."
                                    )
                                    missing_children.append(child_pfid)
        for missing_child in missing_children:
            if result["database"].get(missing_child) and result["database"][
                missing_child
            ].get(
                "unpublished"
            ):  # If there is somehow an unpublished mod in missing_children, remove it
                missing_children.remove(missing_child)
        return result, missing_children


def ISteamRemoteStorage_GetCollectionDetails(publishedfileids: list) -> Dict[str, Any]:
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
    data = {"collectioncount": f"{str(len(publishedfileids))}"}
    for publishedfileid in publishedfileids:
        count = publishedfileids.index(publishedfileid)
        data[f"publishedfileids[{count}]"] = publishedfileid
    # Make a request to the Steam Web API
    request = requests_post(url, data=data)

    # Check the response status code
    if request.status_code == 200:
        try:
            # Parse the JSON response
            json_response = request.json()
            logger.debug(f"Received WebAPI response from query: {json_response}")
        except JSONDecodeError as e:
            logger.warning(f"Invalid JSON response: {e}")
            return None
    else:
        logger.error(f"Error {request.status_code} retrieving data from Steam Web API")
        return None

    return json_response


def ISteamRemoteStorage_GetPublishedFileDetails(
    publishedfileids: list,
) -> Dict[str, Any]:
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
    # Construct arguments to pass to the API call
    data = {"itemcount": f"{str(len(publishedfileids))}"}
    for publishedfileid in publishedfileids:
        count = publishedfileids.index(publishedfileid)
        data[f"publishedfileids[{count}]"] = publishedfileid
    # Make a request to the Steam Web API
    request = requests_post(url, data=data)

    # Check the response status code
    if request.status_code == 200:
        try:
            # Parse the JSON response
            json_response = request.json()
            logger.debug(f"Received WebAPI response from query: {json_response}")
        except JSONDecodeError as e:
            logger.warning(f"Invalid JSON response: {e}")
            return None
    else:
        logger.error(f"Error {request.status_code} retrieving data from Steam Web API")
        return None

    return json_response


if __name__ == "__main__":
    sys.exit()

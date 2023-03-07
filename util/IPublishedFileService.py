import json
import logging
import sys
from time import time
from typing import Any, Dict, List, Optional, Tuple

from steam.webapi import WebAPI

logger = logging.getLogger(__name__)
# Uncomment this if you want to see the full urllib3 request
# THIS CONTAINS THE STEAM API KEY
logging.getLogger("urllib3").setLevel(logging.WARNING)


class SteamWorkshopQuery:
    """
    Create SteamWorkshopQuery object to initialize the scraped data from Workshop

    :param apikey: Steam API key to be used for query
    :param appid: The AppID associated with the game you are looking up info for
    :param life: The lifespan of the Query in terms of the seconds added to the time of
    database generation. This adds an 'expiry' to the data being cached.
    :param mods: A Dict equivalent to 'all_mods' or mod_list.get_list_items_by_dict() in
    which contains possible Steam mods to lookup metadata for
    """

    def __init__(self, apikey: str, appid: int, life: int, mods: Dict[str, Any]):
        self.api = WebAPI(apikey, format="json", https=True)
        self.apikey = apikey
        self.appid = appid
        self.expiry = self.__expires(life)
        self.workshop_json_data = self.cache_parsable_db_json_data(mods)

    def __chunks(self, _list: list, limit: int):
        for i in range(0, len(_list), limit):
            yield _list[i : i + limit]

    def __expires(self, life: int) -> int:
        return int(time() + life)  # current seconds since epoch + 30 minutes

    def cache_parsable_db_json_data(self, mods: Dict[str, Any]) -> Dict[Any, Any]:
        authors = ""
        gameVersions = []
        pfid = ""
        pid = ""
        name = ""
        local_metadata = {}
        local_metadata["database"] = {}
        publishedfileids = []
        for v in mods.values():
            if v.get("publishedfileid"):
                pfid = v["publishedfileid"]
                url = f"https://steamcommunity.com/sharedfiles/filedetails/?id={pfid}"
                local_metadata["database"][pfid] = {}
                local_metadata["database"][pfid]["url"] = url
                publishedfileids.append(pfid)
                if v.get("packageId"):
                    pid = v["packageId"]
                    local_metadata["database"][pfid]["packageId"] = pid
                if v.get("name"):
                    name = v["name"]
                    local_metadata["database"][pfid]["name"] = name
                if v.get("author"):
                    authors = v["author"]
                    local_metadata["database"][pfid]["authors"] = authors
                if v["supportedVersions"].get("li"):
                    gameVersions = v["supportedVersions"]["li"]
                    local_metadata["database"][pfid]["gameVersions"] = gameVersions
        logger.info(
            f"SteamWorkshopQuery initializing for {len(publishedfileids)} mods"
        )
        querying = True
        query = {}
        query["version"] = self.expiry
        query["database"] = local_metadata["database"]
        while querying:  # Begin initial query
            query, missing_children = self.IPublishedFileService_GetDetails(
                query, publishedfileids
            )
            if (
                len(missing_children) > 0
            ):  # If we have missing data for any dependency, get it
                logger.info(
                    f"Retrieving dependency information for the following missing children: {missing_children}"
                )
                query, missing_children = self.IPublishedFileService_GetDetails(
                    query, missing_children
                )
            else:
                missing_children = []
                querying = False
            if missing_children:
                publishedfileids.extend(missing_children)
        total = len(query["database"])
        logger.info(f"Returning Steam Workshop db_json_data with {total} items")
        with open("data/db_json_data.json", "w") as output:
            json.dump(query, output, indent=4)
        return query

    def IPublishedFileService_GetDetails(
        self, json_to_update: Dict[Any, Any], publishedfileids: list
    ) -> Tuple[Dict[Any, Any], list]:
        """
        Given a list of PublishedFileIds, return a dict of json data queried
        from Steam WebAPI, containing data to be parsed during db update.

        https://steamapi.xpaw.me/#IPublishedFileService/GetDetails

        :param json_to_update: a Dict of json data, containing a query to update (or the skeleton of one from local_metadata)
        :param publishedfileids: a list of PublishedFileIds to query Steam Workshop mod metadata for
        :return: Tuple containing the updated json data from pfid query, as well as a list of any missing children's pfids
        to consider for additional queries
        """
        missing_children = []
        result = json_to_update
        for batch in self.__chunks(
            publishedfileids, 215
        ):  # Batch limit appears to be 215 PublishedFileIds at a time - this appears to be a WebAPI limitation
            logger.info(f"Retrieving metadata for {len(batch)} mods")
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
                publishedfileid = metadata["publishedfileid"]
                if not result["database"].get(publishedfileid):
                    result["database"][publishedfileid] = {}
                    result["database"][publishedfileid]["missing"] = True
                    result["database"][publishedfileid][
                        "url"
                    ] = f"https://steamcommunity.com/sharedfiles/filedetails/?id={publishedfileid}"
                steam_title = metadata["title"]
                result["database"][publishedfileid]["steamName"] = steam_title
                result["database"][publishedfileid]["dependencies"] = {}
                if metadata.get("children"):
                    for children in metadata[
                        "children"
                    ]:  # Check if children present in database
                        child_pfid = children["publishedfileid"]
                        if result["database"].get(
                            child_pfid
                        ):  # If we have data for this child already cached, populate it
                            if result["database"][child_pfid].get("name"):
                                child_name = result["database"][child_pfid]["name"]
                            elif result["database"][child_pfid].get("steamName"):
                                child_name = result["database"][child_pfid]["steamName"]
                            else:
                                logger.warning(
                                    f"Unable to find name for child {child_pfid}"
                                )
                            if result["database"][child_pfid].get("url"):
                                child_url = result["database"][child_pfid]["url"]
                            else:
                                logger.warning(
                                    f"Unable to find url for child {child_pfid}"
                                )
                            result["database"][publishedfileid]["dependencies"][
                                child_pfid
                            ] = [child_name, child_url]
                        else:  # Child was not found in database, track it's pfid for later
                            if child_pfid not in missing_children:
                                logger.warning(
                                    f"Could not find pfid {child_pfid} in database. Adding child to missing_children..."
                                )
                                missing_children.append(child_pfid)
        return result, missing_children


if __name__ == "__main__":
    sys.exit()

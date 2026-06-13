"""
Core DB builder logic without Qt dependencies.

This module contains the pure Python implementation of the Steam Workshop
database builder, extracted from the Qt-dependent SteamDatabaseBuilder class.
"""

import json
import os
from pathlib import Path
from typing import Any, Callable, Optional

from app.utils.constants import (
    DB_BUILDER_PRUNE_EXCEPTIONS,
    DB_BUILDER_RECURSE_EXCEPTIONS,
    RIMWORLD_DLC_METADATA,
)
from app.utils.dict_utils import recursively_update_dict
from app.utils.steam.webapi.wrapper import DynamicQuery


def init_empty_db_from_publishedfileids(
    publishedfileids: list[str],
    appid: int,
    progress_callback: Callable[[str], None],
) -> dict[str, Any]:
    """Create a skeleton database from DLC metadata and a list of published file IDs.

    :param publishedfileids: List of Steam Workshop PublishedFileIds
    :param appid: Steam AppId (for progress message)
    :param progress_callback: Callable for progress messages
    :return: Database dict with version and skeleton entries
    """
    database: dict[str, int | dict[str, Any]] = {
        "version": 0,
        "database": {
            **{
                appid_key: {
                    "appid": True,
                    "url": f"https://store.steampowered.com/app/{appid_key}",
                    "packageid": meta.get("packageid"),
                    "name": meta.get("name"),
                }
                for appid_key, meta in RIMWORLD_DLC_METADATA.items()
            },
            **{
                pfid: {
                    "url": f"https://steamcommunity.com/sharedfiles/filedetails/?id={pfid}"
                }
                for pfid in publishedfileids
            },
        },
    }
    total = len(database["database"]) if isinstance(database["database"], dict) else 0
    progress_callback(
        f"\nPopulated {total} items queried from Steam Workshop into initial database for AppId {appid}"
    )
    return database


def output_database(
    database: dict[str, Any],
    output_database_path: str,
    update: bool,
    progress_callback: Callable[[str], None],
) -> None:
    """Write a database dict to disk, optionally merging with an existing file.

    :param database: The database dictionary to write
    :param output_database_path: Path to the output JSON file
    :param update: If True and file exists, recursively merge instead of overwrite
    :param progress_callback: Callable for progress messages
    """
    if update and os.path.exists(output_database_path):
        progress_callback(
            f"\nIn-place DB update configured. Existing DB to update:\n{output_database_path}"
        )
        if output_database_path and os.path.exists(output_database_path):
            with open(output_database_path, encoding="utf-8") as f:
                json_string = f.read()
                progress_callback("\nReading info from file...")
                db_to_update = json.loads(json_string)
                progress_callback("Retrieved cached database!\n")
            progress_callback(
                "Recursively updating previous database with new metadata...\n"
            )
            recursively_update_dict(
                db_to_update,
                database,
                prune_exceptions=DB_BUILDER_PRUNE_EXCEPTIONS,
                recurse_exceptions=DB_BUILDER_RECURSE_EXCEPTIONS,
            )
            with open(output_database_path, "w", encoding="utf-8") as output:
                json.dump(db_to_update, output, indent=4)
        else:
            progress_callback(
                "Unable to load database from specified path! Does the file exist...?"
            )
            appended_path = str(
                Path(output_database_path).parent
                / ("NEW_" + Path(output_database_path).name)
            )
            progress_callback(f"\nCaching DynamicQuery result:\n\n{appended_path}")
            with open(appended_path, "w", encoding="utf-8") as output_f:
                json.dump(database, output_f, indent=4)
    else:
        progress_callback(
            f"\nCaching DynamicQuery result:\n{output_database_path}"
        )
        with open(output_database_path, "w", encoding="utf-8") as output_f:
            json.dump(database, output_f, indent=4)


class DBBuilderCore:
    """
    Pure Python Steam Workshop database builder.

    This class contains the core logic for building Steam Workshop metadata
    databases without any Qt dependencies. Progress is reported via callbacks.

    Args:
        apikey: Steam WebAPI key (must be 32 characters)
        appid: Steam AppID (e.g., 294100 for RimWorld)
        database_expiry: Database lifespan in seconds
        output_database_path: Path to output JSON file
        get_appid_deps: Whether to query DLC dependencies
        update: Whether to update existing DB (merge) or overwrite
        progress_callback: Optional callback for progress messages
    """

    def __init__(
        self,
        apikey: str,
        appid: int,
        database_expiry: int,
        output_database_path: str,
        get_appid_deps: bool = False,
        update: bool = False,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.apikey = apikey
        self.appid = appid
        self.database_expiry = database_expiry
        self.get_appid_deps = get_appid_deps
        self.output_database_path = output_database_path
        self.publishedfileids: list[str] = []
        self.update = update
        self.progress_callback = progress_callback or (lambda msg: None)

    def run(self) -> bool:
        """
        Execute the database builder.

        Returns:
            True if successful, False otherwise
        """
        # We only support "no_local" mode in the CLI
        mode = "no_local"

        self.progress_callback(
            f"\nInitiating RimSort Steam Database Builder with mode : {mode}\n"
        )

        if len(self.apikey) == 32:  # If supplied WebAPI key is 32 characters
            self.progress_callback("Received valid Steam WebAPI key")
            # Since the key is valid, we try to launch a live query
            self.progress_callback(
                f'\nInitializing "DynamicQuery" with configured Steam API key for AppID: {self.appid}\n\n'
            )
            # Create query
            dynamic_query = DynamicQuery(
                apikey=self.apikey,
                appid=self.appid,
                life=self.database_expiry,
                get_appid_deps=self.get_appid_deps,
                callback=self.progress_callback,
            )
            # Compile PublishedFileIds
            dynamic_query.pfids_by_appid()
            # Make sure we have PublishedFileIds to work with...
            if len(dynamic_query.publishedfileids) == 0:  # If we didn't get any pfids
                self.progress_callback(
                    "Did not receive any PublishedFileIds from IPublishedFileService/QueryFiles! Cannot continue!"
                )
                return False  # Exit operation

            database = self._init_empty_db_from_publishedfileids(
                dynamic_query.publishedfileids
            )
            dynamic_query.create_steam_db(
                database=database, publishedfileids=dynamic_query.publishedfileids
            )
            self._output_database(dynamic_query.database)
            self.progress_callback("SteamDatabasebuilder: Completed!")
            return True
        else:  # Otherwise, API key is not valid
            self.progress_callback(
                "SteamDatabaseBuilder (no_local): Invalid Steam WebAPI key!"
            )
            self.progress_callback("SteamDatabaseBuilder (no_local): Exiting...")
            return False

    def _init_empty_db_from_publishedfileids(
        self, publishedfileids: list[str]
    ) -> dict[str, Any]:
        """
        Initialize an empty database from a list of PublishedFileIds.

        Args:
            publishedfileids: List of Steam Workshop PublishedFileIds

        Returns:
            Empty database structure with skeleton entries
        """
        return init_empty_db_from_publishedfileids(
            publishedfileids, self.appid, self.progress_callback
        )

    def _output_database(self, database: dict[str, Any]) -> None:
        output_database(
            database, self.output_database_path, self.update, self.progress_callback
        )

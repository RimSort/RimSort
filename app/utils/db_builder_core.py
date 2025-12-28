"""
Core DB builder logic without Qt dependencies.

This module contains the pure Python implementation of the Steam Workshop
database builder, extracted from the Qt-dependent SteamDatabaseBuilder class.
"""

import json
import os
import time
from pathlib import Path
from typing import Any, Callable, Optional

from app.utils.constants import (
    DB_BUILDER_PRUNE_EXCEPTIONS,
    DB_BUILDER_RECURSE_EXCEPTIONS,
    RIMWORLD_DLC_METADATA,
)
from app.utils.steam.webapi.wrapper import DynamicQuery


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
        incremental: Whether to use incremental updates (only query changed mods)
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
        incremental: bool = True,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.apikey = apikey
        self.appid = appid
        self.database_expiry = database_expiry
        self.get_appid_deps = get_appid_deps
        self.output_database_path = output_database_path
        self.publishedfileids: list[str] = []
        self.update = update
        self.incremental = incremental
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

            # Load existing database if update mode
            existing_db = self._load_existing_database() if self.update else None

            # Determine which mods to query
            mods_to_query = dynamic_query.publishedfileids
            deleted_mods: list[str] = []

            # Incremental mode: only query changed/new mods
            if self.incremental and existing_db:
                self.progress_callback("\nIncremental update mode enabled")

                # Get timestamps for all mods (lightweight query)
                remote_timestamps = dynamic_query.get_bulk_timestamps(
                    dynamic_query.publishedfileids
                )

                # Detect what changed
                new_mods, changed_mods, deleted_mods = self._detect_changes(
                    dynamic_query.publishedfileids, remote_timestamps, existing_db
                )

                # Only query changed/new mods
                mods_to_query = new_mods + changed_mods

                self.progress_callback(
                    f"\nIncremental analysis complete:"
                    f"\n  - New mods: {len(new_mods)}"
                    f"\n  - Changed mods: {len(changed_mods)}"
                    f"\n  - Deleted mods: {len(deleted_mods)}"
                    f"\n  - Total to query: {len(mods_to_query)}"
                    f"\n  - Skipped (unchanged): {len(dynamic_query.publishedfileids) - len(mods_to_query)}\n"
                )

                # Handle deleted mods (soft delete with tombstone)
                if deleted_mods:
                    for pfid in deleted_mods:
                        if pfid in existing_db["database"]:
                            existing_db["database"][pfid]["deleted"] = True
                            existing_db["database"][pfid]["deleted_at"] = int(
                                time.time()
                            )
            else:
                if not self.incremental:
                    self.progress_callback(
                        "\nFull rebuild mode (--full-rebuild specified)"
                    )
                else:
                    self.progress_callback(
                        "\nFull rebuild mode (no existing database or --overwrite specified)"
                    )

            # Query metadata for selected mods
            database = self._init_empty_db_from_publishedfileids(mods_to_query)
            dynamic_query.create_steam_db(
                database=database, publishedfileids=mods_to_query
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
        database: dict[str, int | dict[str, Any]] = {
            "version": 0,
            "database": {
                **{
                    appid: {
                        "appid": True,
                        "url": f"https://store.steampowered.com/app/{appid}",
                        "packageid": metadata.get("packageid"),
                        "name": metadata.get("name"),
                    }
                    for appid, metadata in RIMWORLD_DLC_METADATA.items()
                },
                **{
                    publishedfileid: {
                        "url": f"https://steamcommunity.com/sharedfiles/filedetails/?id={publishedfileid}"
                    }
                    for publishedfileid in publishedfileids
                },
            },
        }
        total = (
            len(database["database"].keys())
            if isinstance(database["database"], dict)
            else 0
        )
        self.progress_callback(
            f"\nPopulated {total} items queried from Steam Workshop into initial database for AppId {self.appid}"
        )
        return database

    def _output_database(self, database: dict[str, Any]) -> None:
        """
        Write the database to the output file.

        If update mode is enabled, recursively merges with existing database.
        Otherwise, overwrites the file.

        Args:
            database: The database dictionary to write
        """
        # Import recursively_update_dict here to avoid circular imports
        from app.utils.metadata import recursively_update_dict

        # If user-configured `update` parameter, update old db with new query data recursively
        if self.update and os.path.exists(self.output_database_path):
            self.progress_callback(
                f"\nIn-place DB update configured. Existing DB to update:\n{self.output_database_path}"
            )
            if self.output_database_path and os.path.exists(self.output_database_path):
                with open(self.output_database_path, encoding="utf-8") as f:
                    json_string = f.read()
                    self.progress_callback("\nReading info from file...")
                    db_to_update = json.loads(json_string)
                    self.progress_callback("Retrieved cached database!\n")
                self.progress_callback(
                    "Recursively updating previous database with new metadata...\n"
                )
                recursively_update_dict(
                    db_to_update,
                    database,
                    prune_exceptions=DB_BUILDER_PRUNE_EXCEPTIONS,
                    recurse_exceptions=DB_BUILDER_RECURSE_EXCEPTIONS,
                )
                with open(self.output_database_path, "w", encoding="utf-8") as output:
                    json.dump(db_to_update, output, indent=4)
            else:
                self.progress_callback(
                    "Unable to load database from specified path! Does the file exist...?"
                )
                appended_path = str(
                    Path(self.output_database_path).parent
                    / ("NEW_" + Path(self.output_database_path).name)
                )
                self.progress_callback(
                    f"\nCaching DynamicQuery result:\n\n{appended_path}"
                )
                with open(appended_path, "w", encoding="utf-8") as output:
                    json.dump(database, output, indent=4)
        else:  # Dump new db to specified path, effectively "overwriting" the db with fresh data
            self.progress_callback(
                f"\nCaching DynamicQuery result:\n{self.output_database_path}"
            )
            with open(self.output_database_path, "w", encoding="utf-8") as output:
                json.dump(database, output, indent=4)

    def _load_existing_database(self) -> dict[str, Any] | None:
        """
        Load and validate existing database.

        Returns:
            Existing database dict, or None if invalid/missing
        """
        try:
            with open(self.output_database_path, encoding="utf-8") as f:
                db = json.load(f)

            # Validate structure
            if not db.get("database") or not isinstance(db["database"], dict):
                self.progress_callback(
                    "Warning: Invalid database structure, will perform full rebuild"
                )
                return None

            return db
        except json.JSONDecodeError as e:
            self.progress_callback(
                f"Warning: Could not parse existing database ({e}), will perform full rebuild"
            )
            return None
        except FileNotFoundError:
            self.progress_callback(
                "Warning: No existing database found, will perform full rebuild"
            )
            return None

    def _detect_changes(
        self,
        all_pfids: list[str],
        remote_timestamps: dict[str, int],
        existing_db: dict[str, Any],
    ) -> tuple[list[str], list[str], list[str]]:
        """
        Compare timestamps to detect new, changed, and deleted mods.

        Args:
            all_pfids: All current workshop mod IDs from Steam
            remote_timestamps: Current timestamps from Steam API
            existing_db: Current database (loaded from file)

        Returns:
            (new_mods, changed_mods, deleted_mods)
        """
        new_mods: list[str] = []
        changed_mods: list[str] = []
        deleted_mods: list[str] = []

        existing_pfids = set(existing_db["database"].keys())
        current_pfids = set(all_pfids)

        # Detect new mods (in current but not in existing)
        for pfid in current_pfids:
            if pfid not in existing_pfids:
                new_mods.append(pfid)

        # Detect changed mods (timestamp increased)
        for pfid in current_pfids:
            if pfid in existing_pfids:
                remote_time = remote_timestamps.get(pfid, 0)
                existing_time = existing_db["database"][pfid].get("time_updated", 0)

                # If existing DB has no timestamp, treat as changed (safe default)
                if existing_time == 0 or remote_time > existing_time:
                    changed_mods.append(pfid)

        # Detect deleted mods (in existing but not in current)
        # Skip entries that are DLC (have 'appid' flag) or already marked deleted
        for pfid in existing_pfids:
            if pfid not in current_pfids:
                entry = existing_db["database"][pfid]
                if not entry.get("appid") and not entry.get("deleted"):
                    deleted_mods.append(pfid)

        return new_mods, changed_mods, deleted_mods

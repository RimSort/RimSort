from typing import Any

from PySide6.QtCore import QThread, Signal

from app.models.metadata.metadata_structure import AboutXmlMod
from app.utils.db_builder_core import (
    DBBuilderCore,
    init_empty_db_from_publishedfileids,
    output_database,
)
from app.utils.steam.webapi.wrapper import DynamicQuery


class SteamDatabaseBuilder(QThread):
    db_builder_message_output_signal = Signal(str)

    def __init__(
        self,
        apikey: str,
        appid: int,
        database_expiry: int,
        mode: str,
        output_database_path: str = "",
        get_appid_deps: bool = False,
        update: bool = False,
        mods: dict[str, Any] = {},
    ):
        QThread.__init__(self)

        # For backwards compatibility with GUI code that uses these attributes
        self.apikey = apikey
        self.appid = appid
        self.database_expiry = database_expiry
        self.get_appid_deps = get_appid_deps
        self.mode = mode
        self.mods = mods
        self.output_database_path = output_database_path
        self.publishedfileids: list[str] = []
        self.update = update
        self.core: DBBuilderCore | None

        # Note: DBBuilderCore only supports "no_local" mode currently
        # The "all_mods" and "pfids_by_appid" modes remain in the Qt wrapper
        if mode == "no_local":
            # Create core instance with callback connected to Qt signal
            self.core = DBBuilderCore(
                apikey=apikey,
                appid=appid,
                database_expiry=database_expiry,
                output_database_path=output_database_path,
                get_appid_deps=get_appid_deps,
                update=update,
                progress_callback=self.db_builder_message_output_signal.emit,
            )
        else:
            self.core = None

    def run(self) -> None:
        # Use core implementation for no_local mode
        if self.mode == "no_local" and self.core:
            self.core.run()
            return

        # Original implementation for other modes
        self.db_builder_message_output_signal.emit(
            f"\nInitiating RimSort Steam Database Builder with mode : {self.mode}\n"
        )
        if len(self.apikey) == 32:  # If supplied WebAPI key is 32 characters
            self.db_builder_message_output_signal.emit(
                "Received valid Steam WebAPI key from settings"
            )
            # Since the key is valid, we try to launch a live query
            if self.mode == "all_mods":
                if not self.mods:
                    self.db_builder_message_output_signal.emit(
                        "SteamDatabaseBuilder: Please passthrough a dict of mod metadata for this mode."
                    )
                    return
                else:
                    if len(self.mods.keys()) > 0:  # No empty queries!
                        # Since the key is valid, and we have a list of pfid, we try to launch a live query
                        self.db_builder_message_output_signal.emit(
                            f'\nInitializing "DynamicQuery" with configured Steam API key for {self.appid}\n'
                        )
                        database = self._init_db_from_local_metadata()
                        publishedfileids = []
                        for publishedfileid, metadata in database["database"].items():
                            if not metadata.get("appid"):  # If it's not an appid
                                publishedfileids.append(
                                    publishedfileid
                                )  # Add it to our list
                        dynamic_query = DynamicQuery(
                            apikey=self.apikey,
                            appid=self.appid,
                            life=self.database_expiry,
                            get_appid_deps=self.get_appid_deps,
                            output_database_path=self.output_database_path,
                        )
                        dynamic_query.dq_messaging_signal.connect(
                            self.db_builder_message_output_signal.emit
                        )
                        dynamic_query.create_steam_db(database, publishedfileids)
                        self._output_database(dynamic_query.database)
                        self.db_builder_message_output_signal.emit(
                            "SteamDatabasebuilder: Completed!"
                        )
                    else:
                        self.db_builder_message_output_signal.emit(
                            "Tried to generate DynamicQuery with 0 mods...? Unable to initialize DynamicQuery for live metadata..."
                        )  # TODO: Make this warning visible to the user
                        return
            elif self.mode == "pfids_by_appid":
                self.db_builder_message_output_signal.emit(
                    f'\nInitializing "PublishedFileIDs by AppID" Query with configured Steam API key for AppID: {self.appid}\n\n'
                )
                # Create query
                dynamic_query = DynamicQuery(self.apikey, self.appid)
                # Connect messaging signal
                dynamic_query.dq_messaging_signal.connect(
                    self.db_builder_message_output_signal.emit
                )
                # Compile PublishedFileIds
                dynamic_query.pfids_by_appid()
                self.publishedfileids = dynamic_query.publishedfileids.copy()
                self.db_builder_message_output_signal.emit(
                    "SteamDatabasebuilder: Completed!"
                )
            else:
                self.db_builder_message_output_signal.emit(
                    "SteamDatabaseBuilder: Invalid mode specified."
                )
        else:  # Otherwise, API key is not valid
            self.db_builder_message_output_signal.emit(
                f"SteamDatabaseBuilder ({self.mode}): Invalid Steam WebAPI key!"
            )
            self.db_builder_message_output_signal.emit(
                f"SteamDatabaseBuilder ({self.mode}): Exiting..."
            )

    def _init_db_from_local_metadata(self) -> dict[str, Any]:
        db_from_local_metadata: dict[str, Any] = {
            "version": 0,
            "database": {
                **{
                    str(v.steam_app_id): {
                        "appid": True,
                        "url": f"https://store.steampowered.com/app/{v.steam_app_id}",
                        "packageId": str(v.package_id),
                        "name": v.name,
                        "authors": ", ".join(v.authors)
                        if v.authors
                        else "Missing XML: <author(s)>",
                    }
                    for v in self.mods.values()
                    if isinstance(v, AboutXmlMod) and v.steam_app_id > 0
                },
                **{
                    v.published_file_id: {
                        "url": f"https://steamcommunity.com/sharedfiles/filedetails/?id={v.published_file_id}",
                        "packageId": str(v.package_id)
                        if isinstance(v, AboutXmlMod)
                        else None,
                        "name": v.name
                        if not v.db_builder_no_name
                        else "Missing XML: <name>",
                        "authors": ", ".join(v.authors)
                        if isinstance(v, AboutXmlMod) and v.authors
                        else "Missing XML: <author(s)>",
                        "gameVersions": (
                            sorted(v.supported_versions)
                            if isinstance(v, AboutXmlMod) and v.supported_versions
                            else ["Missing XML: <supportedversions> or <targetversion>"]
                        ),
                    }
                    for v in self.mods.values()
                    if v.published_file_id
                },
            },
        }
        total = len(db_from_local_metadata["database"])
        self.db_builder_message_output_signal.emit(
            f"Populated {total} items from locally found metadata into initial database for "
            + f"{self.appid}"
        )
        return db_from_local_metadata

    def _init_empty_db_from_publishedfileids(
        self, publishedfileids: list[str]
    ) -> dict[str, Any]:
        return init_empty_db_from_publishedfileids(
            publishedfileids, self.appid, self.db_builder_message_output_signal.emit
        )

    def _output_database(self, database: dict[str, Any]) -> None:
        output_database(
            database,
            self.output_database_path,
            self.update,
            self.db_builder_message_output_signal.emit,
        )

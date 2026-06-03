import json
import os
from typing import Any, Optional

from loguru import logger
from PySide6.QtCore import QEventLoop, QObject, Slot
from PySide6.QtWidgets import QMessageBox

import app.utils.constants as app_constants
import app.utils.metadata as metadata
import app.views.dialogue as dialogue
from app.utils.app_info import AppInfo
from app.utils.event_bus import EventBus
from app.windows.runner_panel import RunnerPanel


class DatabaseBuilder(QObject):
    """
    Singleton class responsible for building a Steam Workshop database by querying the Steam WebAPI for metadata on mods.
    """

    _instance: Optional["DatabaseBuilder"] = None

    def __new__(cls, *args: Any, **kwargs: Any) -> "DatabaseBuilder":
        if cls._instance is None:
            cls._instance = super(DatabaseBuilder, cls).__new__(cls)
        return cls._instance

    def __init__(self, settings_controller: metadata.SettingsController) -> None:
        """
        Initialize the Database Builder.

        :param settings_controller: the settings controller for the application
        """
        if not hasattr(self, "initialized"):
            super(DatabaseBuilder, self).__init__()
            logger.info("Initializing DatabaseBuilder")

            self.settings_controller = settings_controller

            # Initialize MetadataManager
            self.metadata_manager = metadata.MetadataManager.instance()

            # Instantiate query runner
            self.query_runner: RunnerPanel | None = None

            logger.info("Finished DatabaseBuilder initialization")
            self.initialized = True

    def _do_build_database_thread(self) -> None:
        # Prompt user file dialog to choose/create new DB
        logger.info("Opening file dialog to specify output file")
        output_path = dialogue.show_dialogue_file(
            mode="save",
            caption="Designate output path",
            _dir=str(AppInfo().app_storage_folder),
            _filter="JSON (*.json)",
        )
        # Check file path and launch DB Builder with user configured mode
        if output_path:  # If output path was returned
            logger.info(f"Selected path: {output_path}")
            if not output_path.endswith(".json"):
                output_path += ".json"  # Handle file extension if needed
            # RimWorld Workshop contains 30,000+ PublishedFileIDs (mods) as of 2023!
            # "No": Produce accurate, complete DB by QueryFiles via WebAPI
            # Queries ALL available PublishedFileIDs (mods) it can find via Steam WebAPI.
            # Does not use metadata from locally available mods. This means no packageids!
            if self.settings_controller.settings.db_builder_include == "no_local":
                self.db_builder = metadata.SteamDatabaseBuilder(
                    apikey=self.settings_controller.settings.steam_apikey,
                    appid=294100,
                    database_expiry=self.settings_controller.settings.database_expiry,
                    mode=self.settings_controller.settings.db_builder_include,
                    output_database_path=output_path,
                    get_appid_deps=self.settings_controller.settings.build_steam_database_dlc_data,
                    update=self.settings_controller.settings.build_steam_database_update_toggle,
                )
            # "Yes": Produce accurate, possibly semi-incomplete DB without QueryFiles via API
            # CAN produce a complete DB! Only includes metadata parsed from mods you have downloaded.
            # Produces DB which contains metadata from locally available mods. Includes packageids!
            elif self.settings_controller.settings.db_builder_include == "all_mods":
                self.db_builder = metadata.SteamDatabaseBuilder(
                    apikey=self.settings_controller.settings.steam_apikey,
                    appid=294100,
                    database_expiry=self.settings_controller.settings.database_expiry,
                    mode=self.settings_controller.settings.db_builder_include,
                    output_database_path=output_path,
                    get_appid_deps=self.settings_controller.settings.build_steam_database_dlc_data,
                    mods=self.metadata_manager.internal_local_metadata,
                    update=self.settings_controller.settings.build_steam_database_update_toggle,
                )
            # Create query runner
            self.query_runner = RunnerPanel()
            self.query_runner.closing_signal.connect(self.db_builder.terminate)
            self.query_runner.setWindowTitle(
                f"RimSort - DB Builder ({self.settings_controller.settings.db_builder_include})"
            )
            self.query_runner.progress_bar.show()
            self.query_runner.show()
            # Connect message signal
            self.db_builder.db_builder_message_output_signal.connect(
                self.query_runner.message
            )
            # Start DB builder
            self.db_builder.start()
        else:
            logger.debug("USER ACTION: cancelled selection...")

    def _do_download_entire_workshop(self, action: str) -> None:
        # DB Builder is used to run DQ and grab entirety of
        # any available Steam Workshop PublishedFileIDs
        self.db_builder = metadata.SteamDatabaseBuilder(
            apikey=self.settings_controller.settings.steam_apikey,
            appid=294100,
            database_expiry=self.settings_controller.settings.database_expiry,
            mode="pfids_by_appid",
        )
        # Create query runner
        self.query_runner = RunnerPanel()
        self.query_runner.closing_signal.connect(self.db_builder.terminate)
        self.query_runner.setWindowTitle("RimSort - DB Builder PublishedFileIDs query")
        self.query_runner.progress_bar.show()
        self.query_runner.show()
        # Connect message signal
        self.db_builder.db_builder_message_output_signal.connect(
            self.query_runner.message
        )
        # Start DB builder
        self.db_builder.start()
        loop = QEventLoop()
        self.db_builder.finished.connect(loop.quit)
        loop.exec_()
        if len(self.db_builder.publishedfileids) == 0:
            dialogue.show_warning(
                title=self.tr("No PublishedFileIDs"),
                text=self.tr("DB Builder query did not return any PublishedFileIDs!"),
                information=self.tr(
                    "This is typically caused by invalid/missing Steam WebAPI key, or a connectivity issue to the Steam WebAPI.\n"
                    + "PublishedFileIDs are needed to retrieve mods from Steam!"
                ),
            )
        else:
            self.query_runner.close()
            self.query_runner = None
            if "steamcmd" in action:
                # Filter out existing SteamCMD mods
                mod_pfid = None
                for (
                    metadata_values
                ) in self.metadata_manager.internal_local_metadata.values():
                    if metadata_values.get("steamcmd"):
                        mod_pfid = metadata_values.get("publishedfileid")
                    if mod_pfid and mod_pfid in self.db_builder.publishedfileids:
                        logger.debug(
                            f"Skipping download of existing SteamCMD mod: {mod_pfid}"
                        )
                        self.db_builder.publishedfileids.remove(mod_pfid)
                EventBus().do_steamcmd_download.emit(self.db_builder.publishedfileids)
            elif "steamworks" in action:
                answer = dialogue.show_dialogue_conditional(
                    title=self.tr("Are you sure?"),
                    text=self.tr("Here be dragons."),
                    information=self.tr(
                        "WARNING: It is NOT recommended to subscribe to this many mods at once via Steam. "
                        + "Steam has limitations in place seemingly intentionally and unintentionally for API subscriptions. "
                        + "It is highly recommended that you instead download these mods to a SteamCMD prefix by using SteamCMD. "
                        + "This can take longer due to rate limits, but you can also re-use the script generated by RimSort with "
                        + "a separate, authenticated instance of SteamCMD, if you do not want to anonymously download via RimSort."
                    ),
                )
                if answer == QMessageBox.StandardButton.Yes:
                    for (
                        metadata_values
                    ) in self.metadata_manager.internal_local_metadata.values():
                        mod_pfid = metadata_values.get("publishedfileid")
                        if (
                            metadata_values["data_source"] == "workshop"
                            and mod_pfid
                            and mod_pfid in self.db_builder.publishedfileids
                        ):
                            logger.warning(
                                f"Skipping download of existing Steam mod: {mod_pfid}"
                            )
                            self.db_builder.publishedfileids.remove(mod_pfid)
                    EventBus().do_steamworks_api_call.emit(
                        [
                            "subscribe",
                            [
                                str(int(str_pfid))
                                for str_pfid in self.db_builder.publishedfileids
                            ],
                        ]
                    )

    def _do_generate_metadata_comparison_report(self) -> None:
        """
        Open a user-selected JSON file. Calculate and display discrepancies
        found between database and this file.
        """
        # TODO: Refactor this...
        discrepancies: list[str] = []
        database_a_deps: dict[str, Any] = {}
        database_b_deps: dict[str, Any] = {}
        # Notify user
        dialogue.show_information(
            title=self.tr("Steam DB Builder"),
            text=self.tr(
                "This operation will compare 2 databases, A & B, by checking dependencies from A with dependencies from B."
            ),
            information=self.tr(
                "- This will produce an accurate comparison of dependency data between 2 Steam DBs.\n"
                + "A report of discrepancies is generated. You will be prompted for these paths in order:\n"
                + "\n\t1) Select input A"
                + "\n\t2) Select input B",
            ),
        )
        # Input A
        logger.info("Opening file dialog to specify input file A")
        input_path_a = dialogue.show_dialogue_file(
            mode="open",
            caption='Input "to-be-updated" database, input A',
            _dir=str(AppInfo().app_storage_folder),
            _filter="JSON (*.json)",
        )
        logger.info(f"Selected path: {input_path_a}")
        if input_path_a and os.path.exists(input_path_a):
            with open(input_path_a, encoding="utf-8") as f:
                json_string = f.read()
                logger.debug("Reading info...")
                db_input_a = json.loads(json_string)
                logger.debug("Retrieved database A...")
        else:
            logger.warning("Steam DB Builder: User cancelled selection...")
            return
        # Input B
        logger.info("Opening file dialog to specify input file B")
        input_path_b = dialogue.show_dialogue_file(
            mode="open",
            caption='Input "to-be-updated" database, input A',
            _dir=str(AppInfo().app_storage_folder),
            _filter="JSON (*.json)",
        )
        logger.info(f"Selected path: {input_path_b}")
        if input_path_b and os.path.exists(input_path_b):
            with open(input_path_b, encoding="utf-8") as f:
                json_string = f.read()
                logger.debug("Reading info...")
                db_input_b = json.loads(json_string)
                logger.debug("Retrieved database B...")
        else:
            logger.debug("Steam DB Builder: User cancelled selection...")
            return
        for k, v in db_input_a["database"].items():
            # print(k, v['dependencies'])
            database_b_deps[k] = set()
            if v.get("dependencies"):
                for dep_key in v["dependencies"]:
                    database_b_deps[k].add(dep_key)
        for k, v in db_input_b["database"].items():
            # print(k, v['dependencies'])
            if k in database_b_deps:
                database_a_deps[k] = set()
                if v.get("dependencies"):
                    for dep_key in v["dependencies"]:
                        database_a_deps[k].add(dep_key)
        no_deps_str = "*no explicit dependencies listed*"
        database_a_total_deps = len(database_a_deps)
        database_b_total_deps = len(database_b_deps)
        report = (
            "\nSteam DB comparison report:\n"
            + "\nTotal # of deps from database A:\n"
            + f"{database_a_total_deps}"
            + "\nTotal # of deps from database B:\n"
            + f"{database_b_total_deps}"
            + f"\nTotal # of discrepancies:\n{len(discrepancies)}"
        )
        comparison_skipped = []
        for k, v in database_b_deps.items():
            if db_input_a["database"][k].get("unpublished"):
                comparison_skipped.append(k)
                # logger.debug(f"Skipping comparison for unpublished mod: {k}")
            else:
                # If the deps are different...
                if v != database_a_deps.get(k):
                    pp = database_a_deps.get(k)
                    if pp:
                        # Normalize here (get rid of core/dlc deps)
                        if v != pp:
                            discrepancies.append(k)
                            pp_total = len(pp)
                            v_total = len(v)
                            if v == set():
                                v = no_deps_str
                            if pp == set():
                                pp = no_deps_str
                            mod_name = db_input_b["database"][k]["name"]
                            report += f"\n\nDISCREPANCY FOUND for {k}:"
                            report += f"\nhttps://steamcommunity.com/sharedfiles/filedetails/?id={k}"
                            report += f"\nMod name: {mod_name}"
                            report += (
                                f"\n\nDatabase A:\n{v_total} dependencies found:\n{v}"
                            )
                            report += (
                                f"\n\nDatabase B:\n{pp_total} dependencies found:\n{pp}"
                            )
        logger.debug(
            f"Comparison skipped for {len(comparison_skipped)} unpublished mods: {comparison_skipped}"
        )
        dialogue.show_information(
            title=self.tr("Steam DB Builder"),
            text=self.tr("Steam DB comparison report: {len} found").format(
                len=len(discrepancies)
            ),
            information=self.tr("Click 'Show Details' to see the full report!"),
            details=report,
        )

    def _do_merge_databases(self) -> None:
        # Notify user
        dialogue.show_information(
            title=self.tr("Steam DB Builder"),
            text=self.tr(
                "This operation will merge 2 databases, A & B, by recursively updating A with B, barring exceptions."
            ),
            information=self.tr(
                "- This will effectively recursively overwrite A's key/value with B's key/value to the resultant database.\n"
                + "- Exceptions will not be recursively updated. Instead, they will be overwritten with B's key entirely.\n"
                + "- The following exceptions will be made:\n"
                + "\n\t{DB_BUILDER_RECURSE_EXCEPTIONS}\n\n"
                + "The resultant database, C, is saved to a user-specified path. You will be prompted for these paths in order:\n"
                + "\n\t1) Select input A (db to-be-updated)"
                + "\n\t2) Select input B (update source)"
                + "\n\t3) Select output C (resultant db)"
            ).format(
                DB_BUILDER_RECURSE_EXCEPTIONS=app_constants.DB_BUILDER_RECURSE_EXCEPTIONS
            ),
        )
        # Input A
        logger.info("Opening file dialog to specify input file A")
        input_path_a = dialogue.show_dialogue_file(
            mode="open",
            caption='Input "to-be-updated" database, input A',
            _dir=str(AppInfo().app_storage_folder),
            _filter="JSON (*.json)",
        )
        logger.info(f"Selected path: {input_path_a}")
        if input_path_a and os.path.exists(input_path_a):
            with open(input_path_a, encoding="utf-8") as f:
                json_string = f.read()
                logger.debug("Reading info...")
                db_input_a = json.loads(json_string)
                logger.debug("Retrieved database A...")
        else:
            logger.warning("Steam DB Builder: User cancelled selection...")
            return
        # Input B
        logger.info("Opening file dialog to specify input file B")
        input_path_b = dialogue.show_dialogue_file(
            mode="open",
            caption='Input "update source" database, input B',
            _dir=str(AppInfo().app_storage_folder),
            _filter="JSON (*.json)",
        )
        logger.info(f"Selected path: {input_path_b}")
        if input_path_b and os.path.exists(input_path_b):
            with open(input_path_b, encoding="utf-8") as f:
                json_string = f.read()
                logger.debug("Reading info...")
                db_input_b = json.loads(json_string)
                logger.debug("Retrieved database B...")
        else:
            logger.debug("Steam DB Builder: User cancelled selection...")
            return
        # Output C
        db_output_c = db_input_a.copy()
        metadata.recursively_update_dict(
            db_output_c,
            db_input_b,
            prune_exceptions=app_constants.DB_BUILDER_PRUNE_EXCEPTIONS,
            recurse_exceptions=app_constants.DB_BUILDER_RECURSE_EXCEPTIONS,
        )
        logger.info("Updated DB A with DB B!")
        logger.debug(db_output_c)
        logger.info("Opening file dialog to specify output file")
        output_path = dialogue.show_dialogue_file(
            mode="save",
            caption="Designate output path for resultant database:",
            _dir=str(AppInfo().app_storage_folder),
            _filter="JSON (*.json)",
        )
        logger.info(f"Selected path: {output_path}")
        if output_path:
            if not output_path.endswith(".json"):
                output_path += ".json"  # Handle file extension if needed
            with open(output_path, "w", encoding="utf-8") as output:
                json.dump(db_output_c, output, indent=4)
        else:
            logger.warning("Steam DB Builder: User cancelled selection...")
            return

    @Slot()
    def _on_do_download_all_mods_via_steamcmd(self) -> None:
        self._do_download_entire_workshop("steamcmd")

    @Slot()
    def _on_do_download_all_mods_via_steam(self) -> None:
        self._do_download_entire_workshop("steamworks")

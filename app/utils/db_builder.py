import copy
import json
import os
from typing import Any, Optional

from loguru import logger
from PySide6.QtCore import QEventLoop, QObject, Slot
from PySide6.QtWidgets import QMessageBox

import app.utils.constants as app_constants
import app.utils.metadata as metadata
import app.views.dialogue as dialogue
from app.controllers.settings_controller import SettingsController
from app.utils.app_info import AppInfo
from app.utils.event_bus import EventBus
from app.windows.runner_panel import RunnerPanel


class DatabaseBuilder(QObject):
    """
    Singleton class responsible for building a Steam Workshop database by querying
    the Steam WebAPI for metadata on mods. Handles database generation, merging,
    and comparison operations.
    """

    _instance: Optional["DatabaseBuilder"] = None

    # Database builder modes
    MODE_NO_LOCAL = "no_local"
    MODE_ALL_MODS = "all_mods"
    MODE_PFIDS_BY_APPID = "pfids_by_appid"

    # RimWorld Workshop appid
    RIMWORLD_APPID = 294100

    def __new__(cls, *args: Any, **kwargs: Any) -> "DatabaseBuilder":
        if cls._instance is None:
            cls._instance = super(DatabaseBuilder, cls).__new__(cls)
        return cls._instance

    def __init__(self, settings_controller: SettingsController) -> None:
        """
        Initialize the Database Builder singleton.

        Args:
            settings_controller: The settings controller for the application.
        """
        if not hasattr(self, "initialized"):
            super(DatabaseBuilder, self).__init__()
            logger.info("Initializing DatabaseBuilder")

            self.settings_controller = settings_controller
            self.metadata_manager = metadata.MetadataManager.instance()
            self.query_runner: RunnerPanel | None = None

            logger.info("Finished DatabaseBuilder initialization")
            self.initialized = True

    def _get_output_path(self, caption: str = "Designate output path") -> Optional[str]:
        """
        Prompt user to select output file path and ensure .json extension.

        Args:
            caption: The dialog caption text.

        Returns:
            Validated file path with .json extension, or None if cancelled.
        """
        logger.info("Opening file dialog to specify output file")
        output_path = dialogue.show_dialogue_file(
            mode="save",
            caption=caption,
            _dir=str(AppInfo().app_storage_folder),
            _filter="JSON (*.json)",
        )
        if output_path:
            logger.info(f"Selected path: {output_path}")
            if not output_path.endswith(".json"):
                output_path += ".json"
            return output_path
        return None

    def _load_json_database(self, file_path: Optional[str]) -> Optional[dict[str, Any]]:
        """
        Load and parse a JSON database file.

        Args:
            file_path: Path to the JSON file.

        Returns:
            Parsed JSON data, or None if file doesn't exist or user cancelled.
        """
        if not file_path or not os.path.exists(file_path):
            logger.warning("Database file not found or selection cancelled")
            return None
        try:
            with open(file_path, encoding="utf-8") as f:
                logger.debug(f"Reading database from {file_path}")
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Failed to load database: {e}")
            return None

    def _create_database_builder(
        self, mode: str, output_path: str
    ) -> metadata.SteamDatabaseBuilder:
        """
        Factory method to create SteamDatabaseBuilder with appropriate settings.

        Args:
            mode: Database builder mode (no_local or all_mods).
            output_path: Output file path for the database.

        Returns:
            Configured SteamDatabaseBuilder instance.

        Note:
            RimWorld Workshop contains 30,000+ PublishedFileIDs (mods).
            - MODE_NO_LOCAL: Complete DB via WebAPI QueryFiles, no local metadata.
            - MODE_ALL_MODS: Includes locally available mod metadata with packageids.
        """
        base_kwargs: dict[str, Any] = {
            "apikey": self.settings_controller.settings.steam_apikey,
            "appid": self.RIMWORLD_APPID,
            "database_expiry": self.settings_controller.settings.database_expiry,
            "mode": mode,
            "output_database_path": output_path,
            "get_appid_deps": self.settings_controller.settings.build_steam_database_dlc_data,
            "update": self.settings_controller.settings.build_steam_database_update_toggle,
        }

        if mode == self.MODE_ALL_MODS:
            base_kwargs["mods"] = self.metadata_manager.internal_local_metadata

        return metadata.SteamDatabaseBuilder(**base_kwargs)

    def _setup_query_runner(self, title: str) -> RunnerPanel:
        """
        Create and configure a RunnerPanel for displaying query progress.

        Args:
            title: Window title for the runner panel.

        Returns:
            Configured RunnerPanel instance.
        """
        self.query_runner = RunnerPanel()
        self.query_runner.closing_signal.connect(self.db_builder.terminate)
        self.query_runner.setWindowTitle(title)
        self.query_runner.progress_bar.show()
        self.query_runner.show()
        self.db_builder.db_builder_message_output_signal.connect(
            self.query_runner.message
        )
        return self.query_runner

    def _do_build_database_thread(self) -> None:
        """
        Build a Steam Workshop database with user-selected output path and options.
        """
        output_path = self._get_output_path("Designate output path")
        if not output_path:
            logger.debug("USER ACTION: cancelled selection")
            return

        mode = self.settings_controller.settings.db_builder_include
        self.db_builder = self._create_database_builder(mode, output_path)
        self._setup_query_runner(f"RimSort - DB Builder ({mode})")
        self.db_builder.start()

    def _filter_existing_mods(
        self, publishedfileids: list[str], check_mode: str
    ) -> list[str]:
        """
        Filter out mods that already exist locally based on check mode.

        Args:
            publishedfileids: List of mod PublishedFileIDs to filter.
            check_mode: Type of check - "steamcmd" or "steamworks".

        Returns:
            Filtered list of PublishedFileIDs excluding existing mods.
        """
        existing_ids: set[str] = set()

        for mod_metadata in self.metadata_manager.internal_local_metadata.values():
            mod_pfid = mod_metadata.get("publishedfileid")
            if not mod_pfid:
                continue

            if check_mode == "steamcmd" and mod_metadata.get("steamcmd"):
                logger.debug(f"Skipping download of existing SteamCMD mod: {mod_pfid}")
                existing_ids.add(mod_pfid)
            elif (
                check_mode == "steamworks"
                and mod_metadata.get("data_source") == "workshop"
            ):
                logger.warning(f"Skipping download of existing Steam mod: {mod_pfid}")
                existing_ids.add(mod_pfid)

        return [pfid for pfid in publishedfileids if pfid not in existing_ids]

    def _do_download_entire_workshop(self, action: str) -> None:
        """
        Query Steam Workshop for all available PublishedFileIDs and initiate download.

        Args:
            action: Download method - "steamcmd" or "steamworks".

        Note:
            Queries the Steam WebAPI to retrieve all available mod PublishedFileIDs,
            filters out existing mods, and emits appropriate download signals.
        """
        self.db_builder = metadata.SteamDatabaseBuilder(
            apikey=self.settings_controller.settings.steam_apikey,
            appid=self.RIMWORLD_APPID,
            database_expiry=self.settings_controller.settings.database_expiry,
            mode=self.MODE_PFIDS_BY_APPID,
        )

        self._setup_query_runner("RimSort - DB Builder PublishedFileIDs query")
        self.db_builder.start()

        loop = QEventLoop()
        self.db_builder.finished.connect(loop.quit)
        loop.exec_()

        if not self.db_builder.publishedfileids:
            dialogue.show_warning(
                title=self.tr("No PublishedFileIDs"),
                text=self.tr("DB Builder query did not return any PublishedFileIDs!"),
                information=self.tr(
                    "This is typically caused by invalid/missing Steam WebAPI key, "
                    "or a connectivity issue to the Steam WebAPI.<br>"
                    "PublishedFileIDs are needed to retrieve mods from Steam!"
                ),
            )
            return

        if self.query_runner:
            self.query_runner.close()
        self.query_runner = None

        # Filter existing mods based on download method
        filtered_ids = self._filter_existing_mods(
            self.db_builder.publishedfileids,
            "steamcmd" if "steamcmd" in action else "steamworks",
        )

        if "steamcmd" in action:
            EventBus().do_steamcmd_download.emit(filtered_ids)
        elif "steamworks" in action:
            answer = dialogue.show_dialogue_conditional(
                title=self.tr("Are you sure?"),
                text=self.tr("Here be dragons."),
                information=self.tr(
                    "WARNING: It is NOT recommended to subscribe to this many mods at once via Steam. "
                    "Steam has limitations in place seemingly intentionally and unintentionally for API subscriptions. "
                    "It is highly recommended that you instead download these mods to a SteamCMD prefix by using SteamCMD. "
                    "This can take longer due to rate limits, but you can also re-use the script generated by RimSort with "
                    "a separate, authenticated instance of SteamCMD, if you do not want to anonymously download via RimSort."
                ),
            )
            if answer == QMessageBox.StandardButton.Yes:
                EventBus().do_steamworks_api_call.emit(
                    [
                        "subscribe",
                        [str(int(pfid)) for pfid in filtered_ids],
                    ]
                )

    def _select_and_load_database(self, caption: str) -> Optional[dict[str, Any]]:
        """
        Prompt user to select and load a database file.

        Args:
            caption: Dialog caption describing the database selection.

        Returns:
            Parsed JSON database, or None if cancelled or load failed.
        """
        logger.info(f"Opening file dialog: {caption}")
        input_path = dialogue.show_dialogue_file(
            mode="open",
            caption=caption,
            _dir=str(AppInfo().app_storage_folder),
            _filter="JSON (*.json)",
        )
        return self._load_json_database(input_path)

    def _extract_dependencies(self, database: dict[str, Any]) -> dict[str, set[str]]:
        """
        Extract dependencies from a database as a mapping of mod ID to dependency sets.

        Args:
            database: The database dictionary containing mod entries.

        Returns:
            Dictionary mapping mod IDs to sets of their dependencies.
        """
        dependencies: dict[str, set[str]] = {}
        for mod_id, mod_data in database.get("database", {}).items():
            dependencies[mod_id] = set(mod_data.get("dependencies", []))
        return dependencies

    def _compare_dependencies(
        self,
        db_input_a: dict[str, Any],
        db_input_b: dict[str, Any],
        deps_a: dict[str, set[str]],
        deps_b: dict[str, set[str]],
    ) -> tuple[list[str], dict[str, tuple[set[str], set[str]]]]:
        """
        Compare dependencies between two databases and identify discrepancies.

        Args:
            db_input_a: Database A (to-be-updated).
            db_input_b: Database B (comparison source).
            deps_a: Extracted dependencies from database A.
            deps_b: Extracted dependencies from database B.

        Returns:
            Tuple of (list of mod IDs with discrepancies, dict mapping mod IDs to (deps_a, deps_b) pairs).
        """
        discrepancies: list[str] = []
        discrepancy_details: dict[str, tuple[set[str], set[str]]] = {}

        for mod_id, deps_b_set in deps_b.items():
            if db_input_a.get("database", {}).get(mod_id, {}).get("unpublished"):
                continue

            deps_a_set = deps_a.get(mod_id)
            if deps_a_set and deps_b_set != deps_a_set:
                discrepancies.append(mod_id)
                discrepancy_details[mod_id] = (deps_a_set, deps_b_set)

        return discrepancies, discrepancy_details

    def _build_comparison_report(
        self,
        db_input_a: dict[str, Any],
        db_input_b: dict[str, Any],
        discrepancy_details: dict[str, tuple[set[str], set[str]]],
        total_a: int,
        total_b: int,
    ) -> str:
        """
        Build a detailed comparison report between two databases.

        Args:
            db_input_a: Database A content.
            db_input_b: Database B content.
            discrepancy_details: Mapping of mod IDs to their dependency discrepancies.
            total_a: Total number of dependencies in database A.
            total_b: Total number of dependencies in database B.

        Returns:
            Formatted comparison report string.
        """
        no_deps_str = "*no explicit dependencies listed*"
        report_lines = [
            "\nSteam DB comparison report:",
            f"\nTotal # of deps from database A:\n{total_a}",
            f"\nTotal # of deps from database B:\n{total_b}",
            f"\nTotal # of discrepancies:\n{len(discrepancy_details)}",
        ]

        for mod_id, (deps_a, deps_b) in discrepancy_details.items():
            mod_name = (
                db_input_b.get("database", {}).get(mod_id, {}).get("name", "Unknown")
            )
            deps_a_display = deps_a if deps_a else no_deps_str
            deps_b_display = deps_b if deps_b else no_deps_str

            report_lines.extend(
                [
                    f"\n\nDISCREPANCY FOUND for {mod_id}:",
                    f"\nhttps://steamcommunity.com/sharedfiles/filedetails/?id={mod_id}",
                    f"\nMod name: {mod_name}",
                    f"\n\nDatabase A:\n{len(deps_a)} dependencies found:\n{deps_a_display}",
                    f"\n\nDatabase B:\n{len(deps_b)} dependencies found:\n{deps_b_display}",
                ]
            )

        return "".join(report_lines)

    def _do_generate_metadata_comparison_report(self) -> None:
        """
        Compare two Steam databases and generate a discrepancy report.

        Prompts user to select two database files (A and B) and produces a detailed
        report of dependency differences found between them.
        """
        # Notify user
        dialogue.show_information(
            title=self.tr("Steam DB Builder"),
            text=self.tr(
                "This operation will compare 2 databases, A & B, by checking dependencies from A with dependencies from B."
            ),
            information=self.tr(
                "- This will produce an accurate comparison of dependency data between 2 Steam DBs.<br>"
                "A report of discrepancies is generated. You will be prompted for these paths in order:<br>"
                "<br>\t1) Select input A"
                "<br>\t2) Select input B"
            ),
        )

        # Load database A
        db_input_a = self._select_and_load_database(
            'Input "to-be-updated" database, input A'
        )
        if not db_input_a:
            logger.warning(
                "Steam DB Builder: User cancelled selection or file load failed"
            )
            return

        # Load database B
        db_input_b = self._select_and_load_database(
            'Input "comparison source" database, input B'
        )
        if not db_input_b:
            logger.debug(
                "Steam DB Builder: User cancelled selection or file load failed"
            )
            return

        # Extract and compare dependencies
        deps_a = self._extract_dependencies(db_input_a)
        deps_b = self._extract_dependencies(db_input_b)

        discrepancies, discrepancy_details = self._compare_dependencies(
            db_input_a, db_input_b, deps_a, deps_b
        )

        # Build report
        report = self._build_comparison_report(
            db_input_a, db_input_b, discrepancy_details, len(deps_a), len(deps_b)
        )

        dialogue.show_information(
            title=self.tr("Steam DB Builder"),
            text=self.tr("Steam DB comparison report: {count} found").format(
                count=len(discrepancies)
            ),
            information=self.tr("Click 'Show Details' to see the full report!"),
            details=report,
        )

    def _do_merge_databases(self) -> None:
        """
        Merge two Steam databases with user control over merge strategy and output.

        Prompts user to select two input databases (A and B) and an output path (C).
        Database C is created by recursively updating A with values from B, with
        specified exceptions that are completely replaced rather than recursed.
        """
        # Notify user
        dialogue.show_information(
            title=self.tr("Steam DB Builder"),
            text=self.tr(
                "This operation will merge 2 databases, A & B, by recursively updating A with B, barring exceptions."
            ),
            information=self.tr(
                "- This will effectively recursively overwrite A's key/value with B's key/value to the resultant database.<br>"
                "- Exceptions will not be recursively updated. Instead, they will be overwritten with B's key entirely.<br>"
                "- The following exceptions will be made:<br>"
                "<br>\t{DB_BUILDER_RECURSE_EXCEPTIONS}<br><br>"
                "The resultant database, C, is saved to a user-specified path. You will be prompted for these paths in order:<br>"
                "<br>\t1) Select input A (db to-be-updated)"
                "<br>\t2) Select input B (update source)"
                "<br>\t3) Select output C (resultant db)"
            ).format(
                DB_BUILDER_RECURSE_EXCEPTIONS=app_constants.DB_BUILDER_RECURSE_EXCEPTIONS
            ),
        )

        # Load database A
        db_input_a = self._select_and_load_database(
            'Input "to-be-updated" database, input A'
        )
        if not db_input_a:
            logger.warning(
                "Steam DB Builder: User cancelled selection or file load failed"
            )
            return

        # Load database B
        db_input_b = self._select_and_load_database(
            'Input "update source" database, input B'
        )
        if not db_input_b:
            logger.debug(
                "Steam DB Builder: User cancelled selection or file load failed"
            )
            return

        # Merge databases
        db_output_c = copy.deepcopy(db_input_a)
        metadata.recursively_update_dict(
            db_output_c,
            db_input_b,
            prune_exceptions=app_constants.DB_BUILDER_PRUNE_EXCEPTIONS,
            recurse_exceptions=app_constants.DB_BUILDER_RECURSE_EXCEPTIONS,
        )
        logger.info("Updated DB A with DB B!")
        logger.debug(db_output_c)

        # Save merged database
        output_path = self._get_output_path(
            "Designate output path for resultant database:"
        )
        if not output_path:
            logger.warning("Steam DB Builder: User cancelled output selection")
            return

        try:
            with open(output_path, "w", encoding="utf-8") as output_file:
                json.dump(db_output_c, output_file, indent=4)
            logger.info(f"Successfully saved merged database to {output_path}")
        except OSError as e:
            logger.error(f"Failed to save merged database: {e}")
            dialogue.show_warning(
                title=self.tr("Save Error"),
                text=self.tr("Failed to save merged database"),
                information=self.tr(f"Error: {e}"),
            )

    @Slot()
    def _on_do_download_all_mods_via_steamcmd(self) -> None:
        """Slot: Initiate download of all mods via SteamCMD."""
        self._do_download_entire_workshop("steamcmd")

    @Slot()
    def _on_do_download_all_mods_via_steam(self) -> None:
        """Slot: Initiate download of all mods via Steam Workshop."""
        self._do_download_entire_workshop("steamworks")

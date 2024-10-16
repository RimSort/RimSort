import os
from functools import partial
from pathlib import Path

from loguru import logger
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from app.models.metadata.metadata_factory import (
    create_listed_mod_from_path,
    read_rules_db,
    read_steam_db,
)
from app.models.metadata.metadata_structure import (
    ExternalRulesSchema,
    ListedMod,
    SteamDbSchema,
)


class MetadataMediator:
    "Mediator class for metadata."

    _user_rules: ExternalRulesSchema | None
    _community_rules: ExternalRulesSchema | None
    _steam_db: SteamDbSchema | None
    _mods_metadata: dict[str, ListedMod]
    _game_version: str = "Unknown"

    def __init__(
        self,
        user_rules_path: Path,
        community_rules_path: Path | None,
        steam_db_path: Path | None,
        workshop_mods_path: Path | None,
        local_mods_path: Path,
        game_path: Path,
    ):
        self.user_rules_path = user_rules_path
        self.community_rules_path = community_rules_path
        self.steam_db_path = steam_db_path
        self.workshop_mods_path = workshop_mods_path
        self.local_mods_path = local_mods_path
        self.game_path = game_path

        self.parser_threadpool = QThreadPool.globalInstance()

        self.refresh_metadata()

    @property
    def user_rules(self) -> ExternalRulesSchema | None:
        return self._user_rules

    @property
    def community_rules(self) -> ExternalRulesSchema | None:
        return self._community_rules

    @property
    def steam_db(self) -> SteamDbSchema | None:
        return self._steam_db

    @property
    def mods_metadata(self) -> dict[str, ListedMod]:
        if self._mods_metadata is not None:
            return self._mods_metadata

        raise ValueError("Mods metadata have not been initiated")

    @property
    def game_modules_path(self) -> Path:
        return self.game_path / "Data"

    @property
    def game_version(self) -> str:
        return self._game_version

    def refresh_metadata(self) -> None:
        """Force refreshes the internal metadata."""
        self._refresh_game_version()

        self._user_rules = read_rules_db(self.user_rules_path)

        self._community_rules = (
            read_rules_db(self.community_rules_path)
            if self.community_rules_path is not None
            else None
        )
        self._steam_db = (
            read_steam_db(self.steam_db_path)
            if self.steam_db_path is not None
            else None
        )

        create_listed_mod = partial(
            create_listed_mod_from_path,
            target_version=self.game_version,
            local_path=self.local_mods_path,
            workshop_path=self.workshop_mods_path,
            rimworld_path=self.game_path,
        )

        self._mods_metadata = dict()

        # Get all folders in the workshop and local mods paths
        mod_paths = list()
        if self.workshop_mods_path is not None:
            if not self.workshop_mods_path.exists():
                logger.warning(
                    f"Workshop mods path does not exist: {self.workshop_mods_path}"
                )
            else:
                mod_paths += list(self.workshop_mods_path.iterdir())

        if self.local_mods_path is not None:
            if not self.local_mods_path.exists():
                logger.warning(
                    f"Local mods path does not exist: {self.local_mods_path}"
                )
            else:
                mod_paths += list(self.local_mods_path.iterdir())

        if self.game_modules_path is not None:
            if not self.game_modules_path.exists():
                logger.warning(
                    f"Game modules path does not exist: {self.game_modules_path}"
                )
            else:
                mod_paths += list(self.game_modules_path.iterdir())

        # Create equal sized batches of mod_paths for threadpool processing
        """ threads = QThread.idealThreadCount()
        batch_size = len(mod_paths) // threads
        logger.debug(
            f"Creating {threads} threads for metadata parsing with batch size of {batch_size}"
        )
        mod_paths_batches = [
            mod_paths[i : i + batch_size] for i in range(0, len(mod_paths), batch_size)
        ] """
        parsers = [
            self._ParserWorker(
                mod_path,
                self.game_version,
                self.local_mods_path,
                self.game_path,
                self.workshop_mods_path,
            )
            for mod_path in mod_paths
        ]

        for parser in parsers:
            parser.signals.result.connect(self._process_results)
            parser.signals.error.connect(self._process_errors)
            parser.signals.finished.connect(
                lambda: logger.info("Finished processing mod")
            )
            self.parser_threadpool.start(parser)

        # log how many threads are running
        logger.info(f"Started {self.parser_threadpool.activeThreadCount()} threads")
        self.parser_threadpool.waitForDone()
        logger.info(f"Metadata refresh complete, found {len(self._mods_metadata)} mods")
        return

    def _process_results(self, result: tuple[bool, ListedMod]) -> None:
        success, mod = result
        logger.info(f"Processed mod: {mod.name}")
        if success:
            self._mods_metadata[mod.uuid] = mod

    def _process_errors(self, error: tuple[Path, Exception]) -> None:
        mod_path, e = error
        logger.error(f"Error parsing mod at path: {mod_path}")
        logger.error(e)

    def _process_finished(self) -> None:
        logger.info("Finished processing mod")

    def _refresh_game_version(self) -> bool:
        # Get & set Rimworld version string
        version_file_path = str(self.game_path / "Version.txt")
        if os.path.exists(version_file_path):
            try:
                with open(version_file_path, encoding="utf-8") as f:
                    self._game_version = f.read().strip()
                    logger.info(
                        f"Retrieved game version from Version.txt: {self.game_version}"
                    )
                    return True
            except Exception:
                logger.error(
                    f"Unable to parse Version.txt from game folder: {version_file_path}"
                )
                self._game_version = "Unknown"
                return False
        else:
            logger.error(
                f"The provided Version.txt path does not exist: {version_file_path}"
            )
            self._game_version = "Unknown"
            return False

    class _WorkerSignals(QObject):
        result = Signal(tuple)
        error = Signal(tuple)
        finished = Signal()

    class _ParserWorker(QRunnable):
        def __init__(
            self,
            mod_path: Path | str,
            target_version: str,
            local_path: Path,
            rimworld_path: Path,
            workshop_path: Path | None,
        ):
            super().__init__()
            self.mod_path = mod_path
            self.target_version = target_version
            self.local_path = local_path
            self.rimworld_path = rimworld_path
            self.workshop_path = workshop_path

            self.signals = MetadataMediator._WorkerSignals()

        def run(self) -> None:
            self.signals.finished.emit()
            try:
                if isinstance(self.mod_path, str):
                    self.mod_path = Path(self.mod_path)
                success, mod = create_listed_mod_from_path(
                    self.mod_path,
                    self.target_version,
                    self.local_path,
                    self.rimworld_path,
                    self.workshop_path,
                )
                self.signals.result.emit((success, mod))
            except Exception as e:
                self.signals.error.emit((self.mod_path, e))

            self.signals.finished.emit()

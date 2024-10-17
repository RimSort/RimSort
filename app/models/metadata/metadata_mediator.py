import os
from pathlib import Path

from loguru import logger
from PySide6.QtCore import QMutex, QRunnable, QThread, QThreadPool

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
        local_mods_path: Path | None,
        game_path: Path | None,
    ):
        self.user_rules_path = user_rules_path
        self.community_rules_path = community_rules_path
        self.steam_db_path = steam_db_path
        self.workshop_mods_path = workshop_mods_path
        self.local_mods_path = local_mods_path
        self.game_path = game_path

        self.parser_threadpool = QThreadPool.globalInstance()

    @property
    def user_rules(self) -> ExternalRulesSchema | None:
        if hasattr(self, "_user_rules") is False:
            return None
        return self._user_rules

    @property
    def community_rules(self) -> ExternalRulesSchema | None:
        if hasattr(self, "_community_rules") is False:
            return None
        return self._community_rules

    @property
    def steam_db(self) -> SteamDbSchema | None:
        if hasattr(self, "_steam_db") is False:
            return None
        return self._steam_db

    @property
    def mods_metadata(self) -> dict[str, ListedMod]:
        if hasattr(self, "_mods_metadata") is False or self._mods_metadata is None:
            raise ValueError("Mods metadata have not been initiated")

        return self._mods_metadata

    @property
    def game_modules_path(self) -> Path:
        if self.game_path is not None:
            return self.game_path / "Data"

        raise ValueError("Game path is not set")

    @property
    def game_version(self) -> str:
        return self._game_version

    def refresh_metadata(self) -> None:
        """Force refreshes the internal metadata."""

        for path in {self.local_mods_path, self.game_path}:
            if path is None or not path.exists() or not path.is_dir():
                raise ValueError(
                    "Essential paths are missing, invalid, or not directories"
                )

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
        threads = QThread.idealThreadCount()
        batch_size = max(len(mod_paths) // threads, 1)

        logger.debug(
            f"Creating {threads} threads for metadata parsing with batch size of {batch_size}"
        )
        mod_paths_batches = [
            mod_paths[i : i + batch_size] for i in range(0, len(mod_paths), batch_size)
        ]

        assert self.local_mods_path is not None
        assert self.game_path is not None

        metadata_mutex = QMutex()
        self._mods_metadata = dict()
        parsers = [
            self._ParserWorker(
                mod_path_batch,
                self.game_version,
                self.local_mods_path,
                self.game_path,
                self.workshop_mods_path,
                metadata_mutex,
                self._mods_metadata,
            )
            for mod_path_batch in mod_paths_batches
        ]

        for parser in parsers:
            self.parser_threadpool.start(parser)

        logger.debug(f"Started {self.parser_threadpool.activeThreadCount()} threads")
        self.parser_threadpool.waitForDone()
        logger.info(f"Metadata refresh complete, found {len(self._mods_metadata)} mods")
        return

    def _refresh_game_version(self) -> bool:
        # Get & set Rimworld version string
        if self.game_path is None:
            self._game_version = "Unknown"
            return False

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

    class _ParserWorker(QRunnable):
        def __init__(
            self,
            mod_path: Path | str | list[Path] | list[str],
            target_version: str,
            local_path: Path,
            rimworld_path: Path,
            workshop_path: Path | None,
            mutex: QMutex,
            mods_metadata: dict[str, ListedMod],
        ):
            super().__init__()
            self.mod_path = mod_path
            self.target_version = target_version
            self.local_path = local_path
            self.rimworld_path = rimworld_path
            self.workshop_path = workshop_path

            self.mutex = mutex
            self.mods_metadata = mods_metadata

        def run(self) -> None:
            paths = (
                self.mod_path if isinstance(self.mod_path, list) else [self.mod_path]
            )

            results: dict[str, ListedMod] = {}
            for path in paths:
                try:
                    if isinstance(path, str):
                        path = Path(path)
                    valid, mod = create_listed_mod_from_path(
                        path,
                        self.target_version,
                        self.local_path,
                        self.rimworld_path,
                        self.workshop_path,
                    )

                    if not valid:
                        logger.warning(f"Mod at path {self.mod_path} is not valid")

                    results[mod.uuid] = mod
                except Exception as e:
                    logger.error(f"Error parsing mod at path: {self.mod_path}")
                    logger.error(e)

            self.mutex.lock()
            self.mods_metadata.update(results)
            self.mutex.unlock()

from functools import partial
from pathlib import Path

from loguru import logger

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

    user_rules_path: Path
    community_rules_path: Path | None
    steam_db_path: Path | None
    workshop_mods_path: Path | None
    local_mods_path: Path
    rimworld_path: Path
    target_version: str

    _user_rules: ExternalRulesSchema | None
    _community_rules: ExternalRulesSchema | None
    _steam_db: SteamDbSchema | None
    _mods_metadata: dict[str, ListedMod]

    def __init__(
        self,
        user_rules_path: Path,
        community_rules_path: Path | None,
        steam_db_path: Path | None,
        workshop_mods_path: Path | None,
        local_mods_path: Path,
        target_version: str,
        rimworld_path: Path,
    ):
        self.user_rules_path = user_rules_path
        self.community_rules_path = community_rules_path
        self.steam_db_path = steam_db_path
        self.workshop_mods_path = workshop_mods_path
        self.local_mods_path = local_mods_path
        self.target_version = target_version
        self.rimworld_path = rimworld_path

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
    def rimworld_modules_path(self) -> Path:
        return self.rimworld_path / "Data"

    def refresh_metadata(self) -> None:
        """Force refreshes the internal metadata."""

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
            target_version=self.target_version,
            local_path=self.local_mods_path,
            workshop_path=self.workshop_mods_path,
            rimworld_path=self.rimworld_path,
        )

        self._mods_metadata = dict()

        # Get all folders in the workshop and local mods paths
        mod_paths = list()
        if self.workshop_mods_path is not None:
            mod_paths += list(self.workshop_mods_path.iterdir())
        if self.local_mods_path is not None:
            mod_paths += list(self.local_mods_path.iterdir())
        if self.rimworld_modules_path is not None:
            mod_paths += list(self.rimworld_modules_path.iterdir())

        for mod_path in mod_paths:
            success, mod = create_listed_mod(
                mod_path,
            )
            if success:
                self._mods_metadata[mod.uuid] = mod
            else:
                logger.warning(f"Failed to read mod metadata for {mod_path}")

        return

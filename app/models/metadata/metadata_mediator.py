from pathlib import Path

from app.models.metadata.metadata_structure import (
    ExternalRulesSchema,
    ListedMod,
    SteamDbSchema,
)


class MetadataMediator:
    "Mediator class for metadata."

    _user_rules: ExternalRulesSchema
    _community_rules: ExternalRulesSchema
    _steam_db: SteamDbSchema
    _mods_metadata: dict[str, ListedMod]
    _user_rules_path: Path
    _community_rules_path: Path
    _steam_db_path: Path

    def __init__(
        self, user_rules_path: Path, community_rules_path: Path, steam_db_path: Path
    ):
        self._user_rules_path = user_rules_path
        self._community_rules_path = community_rules_path
        self._steam_db_path = steam_db_path

    @property
    def user_rules(self) -> ExternalRulesSchema:
        if self._user_rules is not None:
            return self._user_rules

        raise ValueError("User rules have not been initiated and loaded.")

    @property
    def community_rules(self) -> ExternalRulesSchema:
        if self._community_rules is not None:
            return self._community_rules

        raise ValueError("Community rules have not been initiated and loaded.")

    @property
    def steam_db(self) -> SteamDbSchema:
        return self._steam_db

    @property
    def mods_metadata(self) -> dict[str, ListedMod]:
        if self._mods_metadata is not None:
            return self._mods_metadata

    def refresh_metadata(self) -> bool:
        """Force refreshes the internal metadata."""
        raise NotImplementedError

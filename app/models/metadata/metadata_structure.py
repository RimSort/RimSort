import functools
import os
from collections.abc import MutableSet
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import AbstractSet, Any, Iterable, Iterator
from uuid import uuid4


class ModType(Enum):
    LOCAL = "Local"
    STEAM_WORKSHOP = "Steam Workshop"
    STEAM_WORKSHOP_CMD = "Steam Workshop (cmd support)"
    LUDEON = "Ludeon"
    GIT = "Git"
    UNKNOWN = "Unknown"


class CaseInsensitiveStr(str):
    """
    Wraps a package Id. Forces the package ID to be case insensitive. Stores it internally as lowercase.
    """

    def __new__(cls, pid: str) -> "CaseInsensitiveStr":
        return super().__new__(cls, pid.lower())


class CaseInsensitiveSet(MutableSet[CaseInsensitiveStr]):
    """
    Set of case insensitive strings.
    Stores the package Ids internally as PackageIDs which are lowercase.
    """

    def __init__(
        self, s: Iterable[CaseInsensitiveStr | str] | CaseInsensitiveStr | str = ()
    ):
        if isinstance(s, str):
            data = {CaseInsensitiveStr(s)}
        elif isinstance(s, Iterable):
            data = {CaseInsensitiveStr(i) for i in s}
        elif not s:
            data = set()
        else:
            raise TypeError(f"Unsupported type, got {type(s)}")
        self._data: set[CaseInsensitiveStr] = data

    def __contains__(self, value: Any) -> bool:
        if not isinstance(value, CaseInsensitiveStr) and isinstance(value, str):
            value = CaseInsensitiveStr(value)
        elif not isinstance(value, CaseInsensitiveStr):
            return False
        return value in self._data

    def __iter__(self) -> Iterator[CaseInsensitiveStr]:
        return iter(self._data)

    def __and__(self, other: AbstractSet[Any]) -> AbstractSet[CaseInsensitiveStr]:
        return super().__and__(other)

    def __len__(self) -> int:
        return len(self._data)

    def discard(self, value: CaseInsensitiveStr | str) -> None:
        if not isinstance(value, CaseInsensitiveStr) and isinstance(value, str):
            value = CaseInsensitiveStr(value)
        elif not isinstance(value, CaseInsensitiveStr):
            raise TypeError(f"Expected PackageId or str, got {type(value)}")
        return self._data.discard(value)

    def add(self, value: CaseInsensitiveStr | str) -> None:
        if not isinstance(value, CaseInsensitiveStr) and isinstance(value, str):
            value = CaseInsensitiveStr(value)
        elif not isinstance(value, CaseInsensitiveStr):
            raise TypeError(f"Expected PackageId or str, got {type(value)}")
        return self._data.add(value)


@dataclass
class BaseMod:
    package_id: CaseInsensitiveStr = CaseInsensitiveStr("")
    name: str = "Unknown Mod Name"

    _uuid: str = str(uuid4())

    @property
    def uuid(self) -> str:
        return self._uuid

    def __hash__(self) -> int:
        return hash(self.uuid)


@dataclass
class DependencyMod(BaseMod):
    workshop_url: str = ""


@dataclass
class ListedMod(BaseMod):
    """A mod which can be displayed in a list."""

    description: str = (
        "This mod is considered invalid by RimSort (and the RimWorld game)."
        + "\n\nThis mod does NOT contain an ./About/About.xml and is likely leftover from previous usage."
        + "\n\nThis can happen sometimes with Steam mods if there are leftover .dds textures or unexpected data."
    )
    valid: bool = False

    _mod_path: Path = Path()

    @property
    def mod_path(self) -> Path:
        return self._mod_path

    @mod_path.setter
    def mod_path(self, path: Path) -> None:
        """Set the mod path for the mod.
        Can only be set once as this acts as the uuid when set.
        Raises an exception if the path is already set.
        """
        if self._mod_path:
            raise ValueError("Mod path already set. Cannot override.")
        self._mod_path = path

    @property
    def mod_folder(self) -> str:
        return self.mod_path.stem

    @property
    def internal_time_touched(self) -> int:
        """Return the last modified time of the mod's path. If the path does not exist, return -1."""
        if self.mod_path and os.path.exists(self.mod_path):
            return int(os.path.getmtime(self.mod_path))
        return -1

    @property
    def mod_type(self) -> ModType:
        return ModType.UNKNOWN

    @property
    def uuid(self) -> str:
        # Use path as uuid if it is set
        if self._mod_path:
            return str(self._mod_path)
        return self._uuid


@dataclass
class BaseRules:
    """
    Represents the base rules for a mod.

    Attributes:
        load_after (CaseInsensitiveSet): A set of mods that should be loaded after this mod.
        load_before (CaseInsensitiveSet): A set of mods that should be loaded before this mod.
        incompatible_with (CaseInsensitiveSet): A set of mods that are incompatible with this mod.
        dependencies (dict[CaseInsensitiveStr, DependencyMod]): A dictionary of dependencies for this mod.
    """

    load_after: CaseInsensitiveSet = field(default_factory=CaseInsensitiveSet)
    load_before: CaseInsensitiveSet = field(default_factory=CaseInsensitiveSet)
    incompatible_with: CaseInsensitiveSet = field(default_factory=CaseInsensitiveSet)
    dependencies: dict[CaseInsensitiveStr, DependencyMod] = field(default_factory=dict)


@dataclass
class Rules(BaseRules):
    load_first: bool = False
    load_last: bool = False


@dataclass
class RuledMod(ListedMod):
    valid: bool = True
    authors: list[str] = field(default_factory=list)
    description: str = ""
    supported_versions: set[str] = field(default_factory=set)

    mod_version: str = ""
    url: str = ""

    about_rules: BaseRules = field(default_factory=BaseRules)
    community_rules: Rules = field(default_factory=Rules)
    user_rules: Rules = field(default_factory=Rules)


@dataclass
class LudeonMod(RuledMod):
    mod_type = ModType.LUDEON
    steamAppId: int = -1


@dataclass
class SteamMod(RuledMod):
    @property
    def mod_type(self) -> ModType:
        if self.published_file_id == self.mod_folder:
            return ModType.STEAM_WORKSHOP_CMD
        return ModType.STEAM_WORKSHOP

    @property
    def mod_path(self) -> Path:
        return self._mod_path

    @mod_path.setter
    def mod_path(self, path: Path) -> None:
        self._mod_path = path

        # Reset the dependent cached property
        del self.published_file_id

    @functools.cached_property
    def published_file_id(
        self, expected_sub_path: Path = Path("About/PublishedFileId.txt")
    ) -> int:
        """Cached property to return the published file id from the mod's path. If the file does not exist, return -1."""
        expected_path = self.mod_path / expected_sub_path
        if expected_path.exists():
            with open(expected_path, "r") as file:
                return int(file.read())
        return -1


@dataclass
class LocalMod(RuledMod):
    @property
    def mod_type(self) -> ModType:
        return ModType.LOCAL


@dataclass
class GitMod(RuledMod):
    @property
    def mod_type(self) -> ModType:
        return ModType.GIT

    git_url: str = ""

import functools
import os
from collections.abc import MutableSet
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import AbstractSet, Any, Iterable, Iterator
from uuid import uuid4

import msgspec

from app.utils.files import subfolder_contains_candidate_path


class ModType(Enum):
    LOCAL = "Local"
    STEAM_WORKSHOP = "Steam Workshop"
    STEAM_CMD = "Steam CMD"
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
        self,
        s: Iterable[CaseInsensitiveStr | str] | CaseInsensitiveStr | str | None = (),
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

    def __or__(self, other: AbstractSet[Any]) -> "CaseInsensitiveSet":
        return CaseInsensitiveSet(self._data | {CaseInsensitiveStr(i) for i in other})

    def __ror__(self, other: AbstractSet[Any]) -> "CaseInsensitiveSet":
        return self.__or__(other)

    def __hash__(self) -> int:
        return hash(self._data)

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, AbstractSet):
            # Check empty state
            if not self._data and not other:
                return True
            return False

        if isinstance(other, CaseInsensitiveSet):
            return self._data == other._data

        return self._data == other

    def discard(self, value: CaseInsensitiveStr | str) -> None:
        if not isinstance(value, CaseInsensitiveStr) and isinstance(value, str):
            value = CaseInsensitiveStr(value)
        return self._data.discard(value)

    def add(self, value: CaseInsensitiveStr | str) -> None:
        if not isinstance(value, CaseInsensitiveStr) and isinstance(value, str):
            value = CaseInsensitiveStr(value)
        return self._data.add(value)


class ModsConfig:
    """A class to store the mods configuration.

    Note that activeMods and knownExpansions are set up such that they are NOT mutable.
    To modify them, use the provided methods which will create a new list and set it.

    This is more performance heavy but ensures that the lists are not modified outside of the class,
    preventing weird issues with the lists being modified in place, especially with threading.

    Attributes:
        version (str): The version of the mods configuration.
        activeMods (list[CaseInsensitiveStr]): A list of active mods.
        knownExpansions (list[CaseInsensitiveStr]): A list of known expansions.
    """

    version: str
    _activeMods: list[CaseInsensitiveStr]
    _knownExpansions: list[CaseInsensitiveStr]

    def __init__(
        self,
        version: str,
        activeMods: list[CaseInsensitiveStr],
        knownExpansions: list[CaseInsensitiveStr],
    ):
        self.version = version
        self.activeMods = activeMods
        self.knownExpansions = knownExpansions

    def clear_active_mods(self) -> None:
        """Clear the active mods list."""
        self.activeMods.clear()

    def clear_all(self) -> None:
        """Clear the active mods and known expansions lists."""
        self.clear_active_mods()
        self.knownExpansions.clear()

    @property
    def activeMods(self) -> list[CaseInsensitiveStr]:
        """Copy of the active mods list.

        :return: A copy of the active mods list.
        :rtype: list[CaseInsensitiveStr]
        """
        return self._activeMods[:]

    @activeMods.setter
    def activeMods(self, value: list[CaseInsensitiveStr] | list[str]) -> None:
        """Sets the active mods list by copying the input list and converting all elements to CaseInsensitiveStr.

        :param value: The list of active mods to set.
        :type value: list[CaseInsensitiveStr] | list[str]
        :raises TypeError: If the input value is not a list.
        """
        if isinstance(value, list):
            self._activeMods = [CaseInsensitiveStr(i) for i in value]
        else:
            raise TypeError(f"Expected list, got {type(value)}")

    @property
    def knownExpansions(self) -> list[CaseInsensitiveStr]:
        """Copy of the known expansions list.

        :return: A copy of the known expansions list.
        :rtype: list[CaseInsensitiveStr]
        """
        return self._knownExpansions[:]

    @knownExpansions.setter
    def knownExpansions(self, value: list[CaseInsensitiveStr] | list[str]) -> None:
        """Set the known expansions list by copying the input list and converting all elements to CaseInsensitiveStr.

        :param value: The list of known expansions to set.
        :type value: list[CaseInsensitiveStr] | list[str]
        :raises TypeError: If the input value is not a list.
        """
        if isinstance(value, list):
            self._knownExpansions = [CaseInsensitiveStr(i) for i in value]
        else:
            raise TypeError(f"Expected list, got {type(value)}")

    def check_active_duplicates(self) -> bool:
        """Check for duplicates in the active mods list."""
        return len(self.activeMods) != len(set(self.activeMods))

    def check_expansions_duplicates(self) -> bool:
        """Check for duplicates in the known expansions list."""
        return len(self.knownExpansions) != len(set(self.knownExpansions))

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "activeMods": [str(i) for i in self.activeMods],
            "knownExpansions": [str(i) for i in self.knownExpansions],
        }


@dataclass
class BaseMod:
    """Base class for a mod.

    Attributes:
        package_id (CaseInsensitiveStr): The package id of the mod.
        name (str): The name of the mod.
        uuid (str): The internal unique identifier for the mod.
    """

    name: str = "Unknown Mod Name"

    _uuid: str = str(uuid4())

    @property
    def uuid(self) -> str:
        return self._uuid

    def __hash__(self) -> int:
        return hash(self.uuid)


@dataclass
class PackageIdMod:
    package_id: CaseInsensitiveStr = CaseInsensitiveStr("invalid.mod")


@dataclass
class DependencyMod(BaseMod, PackageIdMod):
    """A mod which is a dependency of another mod."""

    workshop_url: str = ""


@dataclass
class ListedMod(BaseMod):
    """A mod which can be displayed in a list.

    Includes the minimum required fields for a mod to be displayed in a list.

    Attributes:
        valid (bool): Whether the mod is considered valid by RimSort.
        description (str): A description of the mod.
        supported_versions (set[str]): A set of supported RimWorld versions.
        description (str): A description of the mod.
        mod_path (Path | None): The path to the mod on disk.
        mod_folder (str | None): The folder name of the mod path.
        internal_time_touched (int): The last modified time of the mod's path. If the path does not exist, -1 is returned.
        mod_type (ModType): The type of the mod.
        uuid (str): The internal unique identifier for the mod.
    """

    valid: bool = True

    supported_versions: set[str] = field(default_factory=set)
    description: str = (
        "This mod is considered invalid by RimSort (and the RimWorld game)."
        + "\n\nThis mod does NOT contain an ./About/About.xml and is likely leftover from previous usage."
        + "\n\nThis can happen sometimes with Steam mods if there are leftover .dds textures or unexpected data."
    )

    _mod_path: Path | None = None
    _mod_type: ModType = ModType.UNKNOWN

    @property
    def mod_path(self) -> Path | None:
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

        if hasattr(self, "published_file_id"):
            del self.published_file_id

    @property
    def mod_folder(self) -> str | None:
        """
        Returns the folder name of the mod path.

        If the mod path exists, the folder name is returned.
        Otherwise, None is returned.

        Returns:
            str | None: The folder name of the mod path, or None if the mod path is not set.
        """
        if self.mod_path:
            return self.mod_path.stem
        return None

    @property
    def internal_time_touched(self) -> int:
        """Return the last modified time of the mod's path. If the path does not exist, return -1."""
        if self.mod_path and os.path.exists(self.mod_path):
            return int(os.path.getmtime(self.mod_path))
        return -1

    @property
    def mod_type(self) -> ModType:
        return self._mod_type

    @mod_type.setter
    def mod_type(self, value: ModType) -> None:
        if self.mod_type != ModType.UNKNOWN:
            raise ValueError("Mod type already set. Cannot override.")
        self._mod_type = value

    @property
    def uuid(self) -> str:
        # Use path as uuid if it is set
        if self._mod_path:
            return str(self._mod_path)
        return self._uuid

    @functools.cached_property
    def published_file_id(
        self, expected_sub_path: Path = Path("About/PublishedFileId.txt")
    ) -> int:
        """Cached property to return the published file id from the mod's path. If the file does not exist, returns
        the mod folder if it is a valid published file id (non-zero natural number). Otherwise return -1."""
        if self.mod_path is None:
            return -1

        expected_path = self.mod_path.joinpath(expected_sub_path)
        if expected_path.exists():
            with open(expected_path, "r") as file:
                return int(file.read())

        if self.mod_folder is not None and self.mod_folder.isnumeric():
            candidate = int(self.mod_folder)
            if candidate > 0:
                return candidate

        return -1

    @functools.cached_property
    def c_sharp_mod(self) -> bool:
        """Return whether the mod is a C# mod based on the contents of the mod path. Looks for binaries in the Assemblies folder."""
        return subfolder_contains_candidate_path(self.mod_path, "Assemblies", "*.dll")

    @functools.cached_property
    def xml_patch_mod(self) -> bool:
        """Return whether the mod is a C# mod based on the contents of the mod path. Looks for binaries in the Assemblies folder."""
        return subfolder_contains_candidate_path(self.mod_path, "Patches", "*.xml")

    @property
    def preview_img_path(self) -> Path | None:
        """Return the path to the preview image for the mod.

        Returns:
            Path | None: The path to the preview image for the mod, or None if the path does not exist.
        """
        if self.mod_path is None:
            return None

        candidate_path = self.mod_path.joinpath("About/Preview.png")
        if candidate_path.exists():
            return candidate_path
        return None


@dataclass
class ScenarioMod(ListedMod):
    """A mod which is a scenario.

    Attributes:
        summary (str): The scenario summary.
    """

    summary: str = ""


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
class AboutXmlMod(ListedMod, PackageIdMod):
    """A listed mod with rules for load order and dependencies.

    Attributes:
        authors (list[str]): A list of authors for the mod.
        mod_version (str): The version of the mod.
        mod_icon_path (Path | None): The path to the mod icon.
        steam_app_id (int): The Steam app ID for the mod.
        url (str): A URL for the mod.
        about_rules (BaseRules): The rules for the About section of the mod.
        community_rules (Rules): The rules for the Community section of the mod.
        user_rules (Rules): The rules for the User section of the mod.
    """

    authors: list[str] = field(default_factory=list)
    mod_version: str = ""
    mod_icon_path: Path | None = None
    steam_app_id: int = -1
    url: str = ""

    about_rules: BaseRules = field(default_factory=BaseRules)
    community_rules: Rules = field(default_factory=Rules)
    user_rules: Rules = field(default_factory=Rules)

    @functools.cached_property
    def overall_rules(self) -> Rules:
        """Return the overall rules for the mod which properly merges the rules from the About, Community, and User sections.

        About has lowest priority, followed by Community, and User has the highest priority.
        Conflicting order rules are not resolved and may cause issue at sort.
        Load top and bottom rules will be true of any one of the rules type has it set to true.

        Cached property

        Returns:
            BaseRules: The overall rules for the mod.
        """
        overall_rules = Rules()

        # Load before
        overall_rules.load_before = (
            self.about_rules.load_before
            | self.community_rules.load_before
            | self.user_rules.load_before
        )

        # Load after
        overall_rules.load_after = (
            self.about_rules.load_after
            | self.community_rules.load_after
            | self.user_rules.load_after
        )

        # Incompatible with
        overall_rules.incompatible_with = (
            self.about_rules.incompatible_with
            | self.community_rules.incompatible_with
            | self.user_rules.incompatible_with
        )

        # Dependencies
        overall_rules.dependencies = {
            **self.about_rules.dependencies,
            **self.community_rules.dependencies,
            **self.user_rules.dependencies,
        }

        # Load first / last
        overall_rules.load_first = (
            self.community_rules.load_first or self.user_rules.load_first
        )
        overall_rules.load_last = (
            self.community_rules.load_last or self.user_rules.load_last
        )

        return overall_rules

    @functools.cached_property
    def overall_rules_with_deps(self) -> Rules:
        """Returns the overall rules while applying the dependencies as load after rules.

        Cached property

        :return: The overall rules with dependencies applied.
        :rtype: Rules
        """
        overall_rules = self.overall_rules

        # Apply dependencies as load after
        for dep in overall_rules.dependencies.values():
            overall_rules.load_after.add(dep.package_id)

        return overall_rules

    def clear_cache(self) -> None:
        """Clear the cached properties."""
        try:
            del self.overall_rules
        except AttributeError:
            pass

        try:
            del self.overall_rules_with_deps
        except AttributeError:
            pass


class SubExternalRule(msgspec.Struct, omit_defaults=True):
    name: list[str] | str
    comment: list[str] | str = msgspec.field(default_factory=str)


class SubExternalBoolRule(msgspec.Struct, omit_defaults=True):
    value: bool = False
    comment: list[str] | str = msgspec.field(default_factory=str)


class ExternalRule(msgspec.Struct, omit_defaults=True):
    loadAfter: dict[str, SubExternalRule] = {}
    loadBefore: dict[str, SubExternalRule] = {}
    loadTop: SubExternalBoolRule = msgspec.field(default_factory=SubExternalBoolRule)
    loadBottom: SubExternalBoolRule = msgspec.field(default_factory=SubExternalBoolRule)


class ExternalRulesSchema(msgspec.Struct, omit_defaults=True):
    timestamp: int
    rules: dict[str, ExternalRule]


class SteamDbEntryDependency(msgspec.Struct, omit_defaults=True):
    name: str
    url: str


class SteamDbEntryBlacklist(msgspec.Struct, omit_defaults=True):
    value: bool = False
    comment: str = msgspec.field(default_factory=str)


class SteamDbEntry(msgspec.Struct, omit_defaults=True):
    unpublished: bool = False
    url: str = msgspec.field(default_factory=str)
    packageId: str = msgspec.field(default_factory=str)
    gameVersions: list[str] | str = msgspec.field(default_factory=list)
    steamName: str = msgspec.field(default_factory=str)
    name: str = msgspec.field(default_factory=str)
    authors: list[str] | str | None = msgspec.field(default_factory=str)
    dependencies: dict[str, list[str] | SteamDbEntryDependency] = msgspec.field(
        default_factory=dict
    )
    blacklist: SteamDbEntryBlacklist = msgspec.field(
        default_factory=SteamDbEntryBlacklist
    )


class SteamDbSchema(msgspec.Struct):
    version: int
    database: dict[str, SteamDbEntry] = msgspec.field(default_factory=dict)

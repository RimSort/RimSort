from collections.abc import MutableSet
from dataclasses import dataclass
from typing import AbstractSet, Any, Iterable, Iterator


class CaseInsensitiveStr(str):
    """
    Wraps a package Id. Forces the package ID to be case insensitive. Stores it internally as lowercase.

    Attributes:
        pid (str): The package ID.
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
class BaseRules:
    load_after: CaseInsensitiveSet
    load_before: CaseInsensitiveSet
    incompatible_with: CaseInsensitiveSet
    dependencies: dict[CaseInsensitiveStr, "DependencyMod"]

    def __init__(
        self,
        load_after: Iterable[str] = (),
        load_before: Iterable[str] = (),
        incompatible_with: Iterable[str] = (),
        dependencies: dict[CaseInsensitiveStr, "DependencyMod"] | None = None,
    ):
        self.load_after = CaseInsensitiveSet(load_after)
        self.load_before = CaseInsensitiveSet(load_before)
        self.incompatible_with = CaseInsensitiveSet(incompatible_with)

        if dependencies is None:
            self.dependencies = {}
        else:
            self.dependencies = dependencies

    @classmethod
    def from_xml(cls, xml: dict[str, Any], target_version: str) -> "BaseRules":
        raise NotImplementedError

    @classmethod
    def from_json(cls, json: dict[str, Any], target_version: str) -> "BaseRules":
        raise NotImplementedError


@dataclass
class Rules(BaseRules):
    load_first: bool = False
    load_last: bool = False

    @classmethod
    def from_xml(cls, xml: dict[str, Any], target_version: str) -> "Rules":
        raise NotImplementedError

    @classmethod
    def from_json(cls, json: dict[str, Any], target_version: str) -> "Rules":
        raise NotImplementedError


class BaseMod:
    package_id: CaseInsensitiveStr
    name: str = ""

    @classmethod
    def from_xml(cls, xml: dict[str, Any]) -> "BaseMod":
        raise NotImplementedError


class DependencyMod(BaseMod):
    workshop_url: str = ""

    @classmethod
    def from_xml(cls, xml: dict[str, Any]) -> "DependencyMod":
        raise NotImplementedError


class RuledMod(BaseMod):
    authors: list[str] = []
    description: str = ""
    supported_versions: set[str] = set()

    mod_version: str = ""
    url: str = ""

    about_rules: BaseRules
    community_rules: Rules
    user_rules: Rules

    @classmethod
    def from_xml(cls, xml: dict[str, Any]) -> "RuledMod":
        raise NotImplementedError


class SteamMod(BaseMod):
    workshop_id: int

    @classmethod
    def from_xml(cls, xml: dict[str, Any]) -> "SteamMod":
        raise NotImplementedError


class LocalMod(BaseMod):
    @classmethod
    def from_xml(cls, xml: dict[str, Any]) -> "LocalMod":
        raise NotImplementedError


class GitMod(LocalMod):
    git_url: str

    @classmethod
    def from_xml(cls, xml: dict[str, Any]) -> "GitMod":
        raise NotImplementedError

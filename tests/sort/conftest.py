from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.models.metadata.metadata_structure import (
    AboutXmlMod,
    BaseRules,
    CaseInsensitiveStr,
    ListedMod,
    Rules,
)


def make_listed_mod(
    path: str,
    name: str = "Unknown Mod",
    package_id: str = "unknown.mod",
    load_after: set[str] | None = None,
    load_before: set[str] | None = None,
    load_first: bool = False,
    load_last: bool = False,
) -> AboutXmlMod:
    """Build a typed AboutXmlMod for sorting tests."""
    about_rules = BaseRules()
    if load_after:
        for pid in load_after:
            about_rules.load_after.add(CaseInsensitiveStr(pid))
    if load_before:
        for pid in load_before:
            about_rules.load_before.add(CaseInsensitiveStr(pid))

    mod = AboutXmlMod(
        name=name,
        package_id=CaseInsensitiveStr(package_id),
        about_rules=about_rules,
        community_rules=Rules(load_first=load_first, load_last=load_last),
    )
    mod.mod_path = Path(path)
    return mod


def three_mod_alpha_mods() -> tuple[
    dict[str, ListedMod], dict[str, set[str]], set[str]
]:
    """Metadata, graph, and active_mod_paths for a 3-mod alphabetical test."""
    mods: dict[str, ListedMod] = {
        "/mods/z": make_listed_mod("/mods/z", name="Zebra", package_id="mod.z"),
        "/mods/a": make_listed_mod("/mods/a", name="Alpha", package_id="mod.a"),
        "/mods/m": make_listed_mod("/mods/m", name="Middle", package_id="mod.m"),
    }
    graph: dict[str, set[str]] = {"mod.z": set(), "mod.a": set(), "mod.m": set()}
    return mods, graph, {"/mods/z", "/mods/a", "/mods/m"}


def diamond_mods() -> tuple[dict[str, ListedMod], dict[str, set[str]], set[str]]:
    """Metadata, graph, and active_mod_paths for a diamond dependency test."""
    mods: dict[str, ListedMod] = {
        "/mods/a": make_listed_mod("/mods/a", name="Alpha", package_id="mod.a"),
        "/mods/b": make_listed_mod("/mods/b", name="Beta", package_id="mod.b"),
        "/mods/c": make_listed_mod("/mods/c", name="Charlie", package_id="mod.c"),
        "/mods/d": make_listed_mod("/mods/d", name="Delta", package_id="mod.d"),
    }
    graph: dict[str, set[str]] = {
        "mod.a": set(),
        "mod.b": {"mod.a"},
        "mod.c": {"mod.a"},
        "mod.d": {"mod.b", "mod.c"},
    }
    return mods, graph, {"/mods/a", "/mods/b", "/mods/c", "/mods/d"}


def assert_diamond_ordering(result: list[str]) -> None:
    """Verify diamond dependency ordering: A before B,C before D."""
    assert len(result) == 4
    assert result.index("/mods/a") < result.index("/mods/b")
    assert result.index("/mods/a") < result.index("/mods/c")
    assert result.index("/mods/b") < result.index("/mods/d")
    assert result.index("/mods/c") < result.index("/mods/d")


@pytest.fixture
def metadata_controller_mock() -> Generator[MagicMock, None, None]:
    """Mock MetadataController.instance() for mod_sorting tests (PR 3 scope).

    Sets up an empty mods_metadata dict. Tests should populate
    it via the returned mock: mock.mods_metadata = {...}
    """
    with patch(
        "app.controllers.metadata_controller.MetadataController.instance"
    ) as mock_instance:
        mock = MagicMock()
        mock.mods_metadata = {}
        mock_instance.return_value = mock
        yield mock

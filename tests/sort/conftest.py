from typing import Any, Generator
from unittest.mock import MagicMock, patch

import pytest


def make_mod(
    packageid: str,
    name: str | None = None,
    load_these_before: list[tuple[str, bool]] | None = None,
    load_these_after: list[tuple[str, bool]] | None = None,
    load_top: bool = False,
    load_bottom: bool = False,
    dependencies: list[str | tuple[str, dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Build a mod metadata dict for sorting tests."""
    mod: dict[str, Any] = {
        "packageid": packageid,
        "name": name or packageid,
    }
    if load_these_before is not None:
        mod["loadTheseBefore"] = set(load_these_before)
    if load_these_after is not None:
        mod["loadTheseAfter"] = set(load_these_after)
    if load_top:
        mod["loadTop"] = True
    if load_bottom:
        mod["loadBottom"] = True
    if dependencies is not None:
        mod["dependencies"] = dependencies
    return mod


def three_mod_alpha_fixture() -> tuple[dict[str, Any], dict[str, set[str]], set[str]]:
    """Metadata, graph, and active_mods for a 3-mod alphabetical test."""
    metadata = {
        "uuid_z": make_mod("mod.z", name="Zebra"),
        "uuid_a": make_mod("mod.a", name="Alpha"),
        "uuid_m": make_mod("mod.m", name="Middle"),
    }
    graph: dict[str, set[str]] = {"mod.z": set(), "mod.a": set(), "mod.m": set()}
    return metadata, graph, {"uuid_z", "uuid_a", "uuid_m"}


def diamond_fixture() -> tuple[dict[str, Any], dict[str, set[str]], set[str]]:
    """Metadata, graph, and active_mods for a diamond dependency test."""
    metadata = {
        "uuid_a": make_mod("mod.a", name="Alpha"),
        "uuid_b": make_mod("mod.b", name="Beta"),
        "uuid_c": make_mod("mod.c", name="Charlie"),
        "uuid_d": make_mod("mod.d", name="Delta"),
    }
    graph: dict[str, set[str]] = {
        "mod.a": set(),
        "mod.b": {"mod.a"},
        "mod.c": {"mod.a"},
        "mod.d": {"mod.b", "mod.c"},
    }
    return metadata, graph, {"uuid_a", "uuid_b", "uuid_c", "uuid_d"}


def assert_diamond_ordering(result: list[str]) -> None:
    """Verify diamond dependency ordering: A before B,C before D."""
    assert len(result) == 4
    assert result.index("uuid_a") < result.index("uuid_b")
    assert result.index("uuid_a") < result.index("uuid_c")
    assert result.index("uuid_b") < result.index("uuid_d")
    assert result.index("uuid_c") < result.index("uuid_d")


@pytest.fixture
def metadata_manager_mock() -> Generator[MagicMock, None, None]:
    """Mock MetadataManager.instance() for sorting tests.

    Sets up an empty internal_local_metadata dict. Tests should populate
    it via the returned mock: mock.internal_local_metadata = {...}
    """
    with patch("app.utils.metadata.MetadataManager.instance") as mock_instance:
        mock = MagicMock()
        mock.internal_local_metadata = {}
        mock_instance.return_value = mock
        yield mock

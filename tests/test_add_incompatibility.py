"""Tests for add_incompatibility_to_mod() in the old metadata system."""

import sys
from typing import Any
from unittest.mock import MagicMock

if "steamworks" not in sys.modules:
    sys.modules["steamworks"] = MagicMock()

from app.utils.metadata import add_incompatibility_to_mod


def _make_all_mods(
    *package_ids: str,
) -> tuple[dict[str, dict[str, Any]], dict[str, list[str]]]:
    """Create a minimal all_mods dict and packageid_to_uuids lookup.

    Returns (all_mods, packageid_to_uuids).
    """
    all_mods = {f"uuid-{pid}": {"packageid": pid} for pid in package_ids}
    packageid_to_uuids: dict[str, list[str]] = {}
    for uuid, data in all_mods.items():
        packageid_to_uuids.setdefault(data["packageid"], []).append(uuid)
    return all_mods, packageid_to_uuids


def test_adds_incompatibility_to_declaring_mod() -> None:
    """Basic: declaring mod gets the incompatibility."""
    all_mods, p2u = _make_all_mods("mod.a", "mod.b")
    mod_data = all_mods["uuid-mod.a"]

    add_incompatibility_to_mod(mod_data, "mod.b", all_mods, p2u)

    assert "mod.b" in mod_data["incompatibilities"]


def test_adds_reverse_incompatibility() -> None:
    """Reverse: target mod also gets flagged as incompatible with declaring mod."""
    all_mods, p2u = _make_all_mods("mod.a", "mod.b")
    mod_a = all_mods["uuid-mod.a"]
    mod_b = all_mods["uuid-mod.b"]

    add_incompatibility_to_mod(mod_a, "mod.b", all_mods, p2u)

    assert "mod.a" in mod_b.get("incompatibilities", set())


def test_declared_incompatibilities_tracked() -> None:
    """declared_incompatibilities tracks what the declaring mod declared."""
    all_mods, p2u = _make_all_mods("mod.a", "mod.b")
    mod_a = all_mods["uuid-mod.a"]
    mod_b = all_mods["uuid-mod.b"]

    add_incompatibility_to_mod(mod_a, "mod.b", all_mods, p2u)

    # mod.a declared it
    assert "mod.b" in mod_a.get("declared_incompatibilities", set())
    # mod.b did NOT declare it
    assert "mod.a" not in mod_b.get("declared_incompatibilities", set())


def test_reverse_with_list_of_ids() -> None:
    """Reverse works when given a list of incompatible package IDs."""
    all_mods, p2u = _make_all_mods("mod.a", "mod.b", "mod.c")
    mod_a = all_mods["uuid-mod.a"]
    mod_b = all_mods["uuid-mod.b"]
    mod_c = all_mods["uuid-mod.c"]

    add_incompatibility_to_mod(mod_a, ["mod.b", "mod.c"], all_mods, p2u)

    assert "mod.a" in mod_b.get("incompatibilities", set())
    assert "mod.a" in mod_c.get("incompatibilities", set())
    assert mod_a.get("declared_incompatibilities", set()) == {"mod.b", "mod.c"}


def test_reverse_skips_nonexistent_mods() -> None:
    """Reverse is not added for mods not present in all_mods."""
    all_mods, p2u = _make_all_mods("mod.a")
    mod_a = all_mods["uuid-mod.a"]

    add_incompatibility_to_mod(mod_a, "mod.nonexistent", all_mods, p2u)

    assert mod_a.get("incompatibilities", set()) == set()


def test_no_duplicate_on_mutual_declaration() -> None:
    """When both mods declare each other, no duplicate entries (sets)."""
    all_mods, p2u = _make_all_mods("mod.a", "mod.b")
    mod_a = all_mods["uuid-mod.a"]
    mod_b = all_mods["uuid-mod.b"]

    add_incompatibility_to_mod(mod_a, "mod.b", all_mods, p2u)
    add_incompatibility_to_mod(mod_b, "mod.a", all_mods, p2u)

    assert mod_a["incompatibilities"] == {"mod.b"}
    assert mod_b["incompatibilities"] == {"mod.a"}
    # Both declared — both tracked
    assert "mod.b" in mod_a.get("declared_incompatibilities", set())
    assert "mod.a" in mod_b.get("declared_incompatibilities", set())

"""Integration tests: compile() → Sorter → sorted paths pipeline."""

import sys
from collections.abc import Mapping
from unittest.mock import MagicMock

if "steamworks" not in sys.modules:
    sys.modules["steamworks"] = MagicMock()

from app.controllers.metadata_controller import MetadataController
from app.controllers.sort_controller import Sorter
from app.models.metadata.metadata_structure import (
    CaseInsensitiveStr,
    DependencyMod,
    ListedMod,
)
from app.utils.constants import SortMethod
from tests.sort.conftest import make_listed_mod


def _pipeline(
    mods: Mapping[str, ListedMod],
    active_paths: set[str] | None = None,
    sort_method: SortMethod = SortMethod.TOPOLOGICAL,
    use_moddependencies_as_loadTheseBefore: bool = False,
) -> tuple[bool, list[str]]:
    """Full pipeline helper: compile → Sorter → sort."""
    if active_paths is None:
        active_paths = set(mods.keys())
    compiled = MetadataController._build_compiled_data(
        mods, use_moddependencies_as_loadTheseBefore
    )
    sorter = Sorter(sort_method, compiled, mods, active_paths)
    return sorter.sort()


class TestBasicPipeline:
    def test_two_mods_load_after(self) -> None:
        """A loads after B → B appears before A in output."""
        mods = {
            "/mods/a": make_listed_mod(
                "/mods/a", name="Alpha", package_id="mod.a", load_after={"mod.b"}
            ),
            "/mods/b": make_listed_mod("/mods/b", name="Beta", package_id="mod.b"),
        }
        success, result = _pipeline(mods)
        assert success
        assert result.index("/mods/b") < result.index("/mods/a")

    def test_two_mods_load_before(self) -> None:
        """A loads before B → A appears before B in output."""
        mods = {
            "/mods/a": make_listed_mod(
                "/mods/a", name="Alpha", package_id="mod.a", load_before={"mod.b"}
            ),
            "/mods/b": make_listed_mod("/mods/b", name="Beta", package_id="mod.b"),
        }
        success, result = _pipeline(mods)
        assert success
        assert result.index("/mods/a") < result.index("/mods/b")

    def test_chain_of_three(self) -> None:
        """A→B→C produces C, B, A ordering."""
        mods = {
            "/mods/a": make_listed_mod(
                "/mods/a", name="A", package_id="mod.a", load_after={"mod.b"}
            ),
            "/mods/b": make_listed_mod(
                "/mods/b", name="B", package_id="mod.b", load_after={"mod.c"}
            ),
            "/mods/c": make_listed_mod("/mods/c", name="C", package_id="mod.c"),
        }
        success, result = _pipeline(mods)
        assert success
        assert result.index("/mods/c") < result.index("/mods/b")
        assert result.index("/mods/b") < result.index("/mods/a")

    def test_no_rules_alphabetical_fallback(self) -> None:
        """Mods with no ordering rules sort alphabetically by name."""
        mods = {
            "/mods/z": make_listed_mod("/mods/z", name="Zebra", package_id="mod.z"),
            "/mods/a": make_listed_mod("/mods/a", name="Alpha", package_id="mod.a"),
            "/mods/m": make_listed_mod("/mods/m", name="Middle", package_id="mod.m"),
        }
        success, result = _pipeline(mods)
        assert success
        assert result == ["/mods/a", "/mods/m", "/mods/z"]


class TestConflictResolutionPipeline:
    def test_explicit_wins_over_inferred_produces_valid_sort(self) -> None:
        """Explicit A→B + inferred B→A: inferred dropped, sort succeeds without cycle."""
        mod_a = make_listed_mod(
            "/mods/a", name="A", package_id="mod.a", load_after={"mod.b"}
        )
        mod_b = make_listed_mod("/mods/b", name="B", package_id="mod.b")
        mod_b.about_rules.dependencies[CaseInsensitiveStr("mod.a")] = DependencyMod(
            package_id=CaseInsensitiveStr("mod.a")
        )

        mods: dict[str, ListedMod] = {"/mods/a": mod_a, "/mods/b": mod_b}
        success, result = _pipeline(mods, use_moddependencies_as_loadTheseBefore=True)

        assert success
        assert result.index("/mods/b") < result.index("/mods/a")

    def test_non_conflicting_inferred_respected_in_sort(self) -> None:
        """Inferred edges that don't conflict are reflected in sort order."""
        mod_a = make_listed_mod("/mods/a", name="A", package_id="mod.a")
        mod_a.about_rules.dependencies[CaseInsensitiveStr("mod.b")] = DependencyMod(
            package_id=CaseInsensitiveStr("mod.b")
        )
        mod_b = make_listed_mod("/mods/b", name="B", package_id="mod.b")

        mods: dict[str, ListedMod] = {"/mods/a": mod_a, "/mods/b": mod_b}
        success, result = _pipeline(mods, use_moddependencies_as_loadTheseBefore=True)

        assert success
        assert result.index("/mods/b") < result.index("/mods/a")

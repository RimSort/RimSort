"""Integration tests: compile() → Sorter → sorted paths pipeline."""

import sys
from collections.abc import Mapping
from unittest.mock import MagicMock, patch

if "steamworks" not in sys.modules:
    sys.modules["steamworks"] = MagicMock()

from app.controllers.sort_controller import Sorter
from app.models.metadata.metadata_structure import (
    CaseInsensitiveSet,
    CaseInsensitiveStr,
    CompiledDependencyData,
    DependencyMod,
    ListedMod,
    Rules,
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
    compiled = CompiledDependencyData.build(
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


class TestUserRulesOverride:
    def test_user_load_after_overrides_about_load_before(self) -> None:
        """User says A loads after B, even though about.xml says A loads before B.
        Creates contradiction → cycle → sort fails."""
        mod_a = make_listed_mod(
            "/mods/a", name="A", package_id="mod.a", load_before={"mod.b"}
        )
        mod_a.user_rules = Rules(
            load_after=CaseInsensitiveSet([CaseInsensitiveStr("mod.b")])
        )
        mod_b = make_listed_mod("/mods/b", name="B", package_id="mod.b")

        mods: dict[str, ListedMod] = {"/mods/a": mod_a, "/mods/b": mod_b}

        with patch("app.sort.topo_sort.show_warning"):
            success, _ = _pipeline(mods)
        assert not success

    def test_user_load_first_promotes_to_tier_one(self) -> None:
        """User marking a mod as load_first should place it in tier one."""
        mod_a = make_listed_mod("/mods/a", name="A", package_id="mod.a")
        mod_a.user_rules = Rules(load_first=True)
        mod_b = make_listed_mod("/mods/b", name="B", package_id="mod.b")
        mod_c = make_listed_mod("/mods/c", name="C", package_id="mod.c")

        mods: dict[str, ListedMod] = {
            "/mods/a": mod_a,
            "/mods/b": mod_b,
            "/mods/c": mod_c,
        }
        success, result = _pipeline(mods)
        assert success
        # load_first mod should appear before all others
        assert result.index("/mods/a") < result.index("/mods/b")
        assert result.index("/mods/a") < result.index("/mods/c")

    def test_user_load_last_demotes_to_tier_three(self) -> None:
        """User marking a mod as load_last should place it in tier three."""
        mod_a = make_listed_mod("/mods/a", name="A", package_id="mod.a")
        mod_a.user_rules = Rules(load_last=True)
        mod_b = make_listed_mod("/mods/b", name="B", package_id="mod.b")

        mods: dict[str, ListedMod] = {"/mods/a": mod_a, "/mods/b": mod_b}
        success, result = _pipeline(mods)
        assert success
        assert result == ["/mods/b", "/mods/a"]


class TestEdgeCases:
    def test_case_insensitive_package_ids_in_rules(self) -> None:
        """load_after with different casing still creates correct edge."""
        mods = {
            "/mods/a": make_listed_mod(
                "/mods/a",
                name="Alpha",
                package_id="Mod.Alpha",
                load_after={"MOD.BETA"},
            ),
            "/mods/b": make_listed_mod("/mods/b", name="Beta", package_id="mod.beta"),
        }
        success, result = _pipeline(mods)
        assert success
        assert result.index("/mods/b") < result.index("/mods/a")

    def test_empty_active_set(self) -> None:
        """No active mods → empty result, no crash."""
        mods = {
            "/mods/a": make_listed_mod("/mods/a", name="A", package_id="mod.a"),
        }
        success, result = _pipeline(mods, active_paths=set())
        assert success
        assert result == []

    def test_active_mod_not_in_metadata(self) -> None:
        """Active path with no matching metadata entry is silently skipped."""
        mods = {
            "/mods/a": make_listed_mod("/mods/a", name="A", package_id="mod.a"),
        }
        success, result = _pipeline(mods, active_paths={"/mods/a", "/mods/nonexistent"})
        assert success
        assert "/mods/a" in result
        assert "/mods/nonexistent" not in result

    def test_duplicate_package_ids_last_path_wins(self) -> None:
        """Two paths with the same package_id: one mod silently disappears.
        Documents current behavior — may be a bug worth fixing."""
        mods = {
            "/mods/copy1": make_listed_mod(
                "/mods/copy1", name="ModCopy1", package_id="author.shared"
            ),
            "/mods/copy2": make_listed_mod(
                "/mods/copy2", name="ModCopy2", package_id="author.shared"
            ),
        }
        success, result = _pipeline(mods)
        assert success
        assert len(result) == 1
        assert result[0] in {"/mods/copy1", "/mods/copy2"}


class TestSadPaths:
    def test_two_mod_cycle_returns_false(self) -> None:
        """A↔B cycle through full pipeline → sort returns (False, [])."""
        mods = {
            "/mods/a": make_listed_mod(
                "/mods/a", name="A", package_id="mod.a", load_after={"mod.b"}
            ),
            "/mods/b": make_listed_mod(
                "/mods/b", name="B", package_id="mod.b", load_after={"mod.a"}
            ),
        }
        with patch("app.sort.topo_sort.show_warning"):
            success, result = _pipeline(mods)
        assert not success
        assert result == []

    def test_three_mod_cycle_returns_false(self) -> None:
        """A→B→C→A cycle — exercises toposort with 3+ node cycle."""
        # Build circular chain: each mod loads after the next, C closes the loop
        names = ["X", "Y", "Z"]
        ids = ["mod.x", "mod.y", "mod.z"]
        deps = [{"mod.y"}, {"mod.z"}, {"mod.x"}]
        mods = {
            f"/mods/{n.lower()}": make_listed_mod(
                f"/mods/{n.lower()}", name=n, package_id=pid, load_after=dep
            )
            for n, pid, dep in zip(names, ids, deps)
        }
        with patch("app.sort.topo_sort.show_warning"):
            success, result = _pipeline(mods)
        assert not success
        assert result == []

    def test_listed_mod_without_package_id_skipped(self) -> None:
        """Non-AboutXmlMod entries in metadata are silently skipped."""
        from pathlib import Path

        from app.models.metadata.metadata_structure import ListedMod as BaseListed

        invalid_mod = BaseListed()
        invalid_mod.mod_path = Path("/mods/invalid")
        mods: dict[str, ListedMod] = {
            "/mods/a": make_listed_mod("/mods/a", name="A", package_id="mod.a"),
            "/mods/invalid": invalid_mod,
        }
        success, result = _pipeline(mods, active_paths={"/mods/a", "/mods/invalid"})
        assert success
        assert "/mods/a" in result
        assert "/mods/invalid" not in result

    def test_self_dependency_is_ignored(self) -> None:
        """A mod depending on itself is silently ignored (not a cycle)."""
        mods = {
            "/mods/a": make_listed_mod(
                "/mods/a", name="A", package_id="mod.a", load_after={"mod.a"}
            ),
        }
        success, result = _pipeline(mods)
        assert success
        assert result == ["/mods/a"]


class TestRealisticScale:
    def _generate_mod_set(
        self, count: int, chain_depth: int = 0
    ) -> tuple[dict[str, ListedMod], set[str]]:
        """Generate a set of mods with optional dependency chain."""
        mods: dict[str, ListedMod] = {}
        for i in range(count):
            load_after: set[str] | None = None
            if 0 < i < chain_depth:
                load_after = {f"mod.{i - 1:04d}"}
            mods[f"/mods/{i:04d}"] = make_listed_mod(
                f"/mods/{i:04d}",
                name=f"Mod {i:04d}",
                package_id=f"mod.{i:04d}",
                load_after=load_after,
            )
        return mods, set(mods.keys())

    def test_200_mods_no_deps(self) -> None:
        """200 independent mods sort without error."""
        mods, _ = self._generate_mod_set(200)
        success, result = _pipeline(mods)
        assert success
        assert len(result) == 200

    def test_300_mods_with_chain(self) -> None:
        """300 mods with a 50-deep dependency chain sort correctly."""
        mods, _ = self._generate_mod_set(300, chain_depth=50)
        success, result = _pipeline(mods)
        assert success
        assert len(result) == 300
        for i in range(1, 50):
            assert result.index(f"/mods/{i - 1:04d}") < result.index(f"/mods/{i:04d}")

    def test_200_mods_with_tiers(self) -> None:
        """200 mods across all four tiers sort in tier order."""
        mods, active = self._generate_mod_set(200)
        compiled = CompiledDependencyData.build(mods)
        compiled.tier_zero_mods = {f"mod.{i:04d}" for i in range(5)}
        compiled.tier_one_mods = {f"mod.{i:04d}" for i in range(5, 15)}
        compiled.tier_three_mods = {f"mod.{i:04d}" for i in range(195, 200)}

        sorter = Sorter(SortMethod.TOPOLOGICAL, compiled, mods, active)
        success, result = sorter.sort()
        assert success
        assert len(result) == 200

        max_t0_idx = max(result.index(f"/mods/{i:04d}") for i in range(5))
        min_t1_idx = min(result.index(f"/mods/{i:04d}") for i in range(5, 15))
        assert max_t0_idx < min_t1_idx

        min_t3_idx = min(result.index(f"/mods/{i:04d}") for i in range(195, 200))
        max_t1_idx = max(result.index(f"/mods/{i:04d}") for i in range(5, 15))
        assert max_t1_idx < min_t3_idx

    def test_half_active_half_inactive(self) -> None:
        """200 mods in metadata, only 100 active → 100 in result."""
        mods, _ = self._generate_mod_set(200)
        active = {f"/mods/{i:04d}" for i in range(100)}
        success, result = _pipeline(mods, active_paths=active)
        assert success
        assert len(result) == 100
        for i in range(100, 200):
            assert f"/mods/{i:04d}" not in result

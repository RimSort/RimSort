from collections.abc import Mapping

import pytest

from app.controllers.sort_controller import Sorter
from app.models.metadata.metadata_structure import (
    AboutXmlMod,
    CompiledDependencyData,
    ListedMod,
)
from app.utils.constants import SortMethod
from tests.sort.conftest import make_listed_mod


def _build_compiled(
    deps: dict[str, set[str]] | None = None,
    rev_deps: dict[str, set[str]] | None = None,
    tier_zero: set[str] | None = None,
    tier_one: set[str] | None = None,
    tier_three: set[str] | None = None,
) -> CompiledDependencyData:
    return CompiledDependencyData(
        deps_graph=deps or {},
        rev_deps_graph=rev_deps or {},
        tier_zero_mods=tier_zero or set(),
        tier_one_mods=tier_one or set(),
        tier_three_mods=tier_three or set(),
    )


def _build_four_tier_scenario() -> tuple[
    dict[str, ListedMod], CompiledDependencyData, set[str]
]:
    """Build a standard 4-tier mod scenario (core/fw/regular/bottom)."""
    mods: dict[str, ListedMod] = {
        "/mods/core": make_listed_mod(
            "/mods/core", name="Core", package_id="ludeon.rimworld"
        ),
        "/mods/fw": make_listed_mod(
            "/mods/fw", name="Framework", package_id="author.framework"
        ),
        "/mods/reg": make_listed_mod(
            "/mods/reg", name="Regular", package_id="author.regular"
        ),
        "/mods/bottom": make_listed_mod(
            "/mods/bottom", name="Bottom", package_id="author.bottom"
        ),
    }
    compiled = _build_compiled(
        deps={
            "ludeon.rimworld": set(),
            "author.framework": set(),
            "author.regular": set(),
            "author.bottom": set(),
        },
        tier_zero={"ludeon.rimworld"},
        tier_one={"author.framework"},
        tier_three={"author.bottom"},
    )
    active = {"/mods/core", "/mods/fw", "/mods/reg", "/mods/bottom"}
    return mods, compiled, active


class TestSorterBasic:
    def test_topological_sort_simple(self) -> None:
        mods = {
            "/mods/a": make_listed_mod("/mods/a", name="A", package_id="mod.a"),
            "/mods/b": make_listed_mod("/mods/b", name="B", package_id="mod.b"),
        }
        compiled = _build_compiled(deps={"mod.a": {"mod.b"}, "mod.b": set()})
        sorter = Sorter(
            sort_method=SortMethod.TOPOLOGICAL,
            compiled_data=compiled,
            mods_metadata=mods,
            active_mod_paths={"/mods/a", "/mods/b"},
        )
        success, result = sorter.sort()
        assert success
        assert result.index("/mods/b") < result.index("/mods/a")

    def test_alphabetical_sort(self) -> None:
        mods = {
            "/mods/z": make_listed_mod("/mods/z", name="Zebra", package_id="mod.z"),
            "/mods/a": make_listed_mod("/mods/a", name="Alpha", package_id="mod.a"),
        }
        compiled = _build_compiled(deps={"mod.z": set(), "mod.a": set()})
        sorter = Sorter(
            sort_method=SortMethod.ALPHABETICAL,
            compiled_data=compiled,
            mods_metadata=mods,
            active_mod_paths={"/mods/z", "/mods/a"},
        )
        success, result = sorter.sort()
        assert success
        assert result == ["/mods/a", "/mods/z"]

    def test_invalid_sort_method_raises(self) -> None:
        compiled = _build_compiled()
        with pytest.raises((NotImplementedError, ValueError)):
            Sorter(
                sort_method="nonexistent",  # type: ignore[arg-type]
                compiled_data=compiled,
                mods_metadata={},
                active_mod_paths=set(),
            )


class TestSorterTierOrdering:
    def test_tier_zero_sorted_first(self) -> None:
        mods = {
            "/mods/core": make_listed_mod(
                "/mods/core", name="Core", package_id="ludeon.rimworld"
            ),
            "/mods/regular": make_listed_mod(
                "/mods/regular", name="Regular", package_id="author.regular"
            ),
        }
        compiled = _build_compiled(
            deps={"ludeon.rimworld": set(), "author.regular": set()},
            tier_zero={"ludeon.rimworld"},
        )
        sorter = Sorter(
            SortMethod.TOPOLOGICAL, compiled, mods, {"/mods/core", "/mods/regular"}
        )
        success, result = sorter.sort()
        assert success
        assert result.index("/mods/core") < result.index("/mods/regular")

    def test_tier_one_after_zero_before_two(self) -> None:
        mods = {
            "/mods/core": make_listed_mod(
                "/mods/core", name="Core", package_id="ludeon.rimworld"
            ),
            "/mods/fw": make_listed_mod(
                "/mods/fw", name="Framework", package_id="author.framework"
            ),
            "/mods/regular": make_listed_mod(
                "/mods/regular", name="Regular", package_id="author.regular"
            ),
        }
        compiled = _build_compiled(
            deps={
                "ludeon.rimworld": set(),
                "author.framework": set(),
                "author.regular": set(),
            },
            tier_zero={"ludeon.rimworld"},
            tier_one={"author.framework"},
        )
        sorter = Sorter(
            SortMethod.TOPOLOGICAL,
            compiled,
            mods,
            {"/mods/core", "/mods/fw", "/mods/regular"},
        )
        success, result = sorter.sort()
        assert success
        assert result.index("/mods/core") < result.index("/mods/fw")
        assert result.index("/mods/fw") < result.index("/mods/regular")

    def test_tier_three_sorted_last(self) -> None:
        mods = {
            "/mods/regular": make_listed_mod(
                "/mods/regular", name="Regular", package_id="author.regular"
            ),
            "/mods/bottom": make_listed_mod(
                "/mods/bottom", name="Bottom", package_id="author.bottom"
            ),
        }
        compiled = _build_compiled(
            deps={"author.regular": set(), "author.bottom": set()},
            tier_three={"author.bottom"},
        )
        sorter = Sorter(
            SortMethod.TOPOLOGICAL,
            compiled,
            mods,
            {"/mods/regular", "/mods/bottom"},
        )
        success, result = sorter.sort()
        assert success
        assert result.index("/mods/regular") < result.index("/mods/bottom")

    def test_tier_one_transitive_deps_included(self) -> None:
        """Dependencies of tier one mods are pulled into tier one."""
        mods = {
            "/mods/fw": make_listed_mod(
                "/mods/fw", name="Framework", package_id="unlimitedhugs.hugslib"
            ),
            "/mods/dep": make_listed_mod(
                "/mods/dep", name="HugsDep", package_id="some.hugslib.dep"
            ),
            "/mods/regular": make_listed_mod(
                "/mods/regular", name="Regular", package_id="author.regular"
            ),
        }
        compiled = _build_compiled(
            deps={
                "unlimitedhugs.hugslib": {"some.hugslib.dep"},
                "some.hugslib.dep": set(),
                "author.regular": set(),
            },
            tier_one={"unlimitedhugs.hugslib"},
        )
        sorter = Sorter(
            SortMethod.TOPOLOGICAL,
            compiled,
            mods,
            {"/mods/fw", "/mods/dep", "/mods/regular"},
        )
        success, result = sorter.sort()
        assert success
        assert result.index("/mods/dep") < result.index("/mods/regular")
        assert result.index("/mods/fw") < result.index("/mods/regular")

    def test_reverse_deps_pulled_into_tier_three(self) -> None:
        """Mods that depend on tier three mods (via reverse graph) are also tier three."""
        mods = {
            "/mods/rocket": make_listed_mod(
                "/mods/rocket", name="RocketMan", package_id="krkr.rocketman"
            ),
            "/mods/addon": make_listed_mod(
                "/mods/addon", name="RocketAddon", package_id="rocket.addon"
            ),
            "/mods/regular": make_listed_mod(
                "/mods/regular", name="Regular", package_id="author.regular"
            ),
        }
        compiled = _build_compiled(
            deps={
                "krkr.rocketman": set(),
                "rocket.addon": {"krkr.rocketman"},
                "author.regular": set(),
            },
            rev_deps={"krkr.rocketman": {"rocket.addon"}, "rocket.addon": set()},
            tier_three={"krkr.rocketman"},
        )
        sorter = Sorter(
            SortMethod.TOPOLOGICAL,
            compiled,
            mods,
            {"/mods/rocket", "/mods/addon", "/mods/regular"},
        )
        success, result = sorter.sort()
        assert success
        assert result.index("/mods/regular") < result.index("/mods/rocket")
        assert result.index("/mods/regular") < result.index("/mods/addon")


class TestSorterActiveOnlyFiltering:
    def test_inactive_mods_excluded_from_sort(self) -> None:
        """Mods in compiled graph but not in active_mod_paths are excluded."""
        mods = {
            "/mods/a": make_listed_mod("/mods/a", name="A", package_id="mod.a"),
            "/mods/b": make_listed_mod("/mods/b", name="B", package_id="mod.b"),
            "/mods/inactive": make_listed_mod(
                "/mods/inactive", name="Inactive", package_id="mod.inactive"
            ),
        }
        compiled = _build_compiled(
            deps={"mod.a": {"mod.b"}, "mod.b": set(), "mod.inactive": {"mod.a"}},
        )
        sorter = Sorter(SortMethod.TOPOLOGICAL, compiled, mods, {"/mods/a", "/mods/b"})
        success, result = sorter.sort()
        assert success
        assert "/mods/inactive" not in result
        assert len(result) == 2

    def test_inactive_cycle_does_not_cause_error(self) -> None:
        """A cycle among inactive mods must not raise CircularDependencyError."""
        mods = {
            "/mods/a": make_listed_mod("/mods/a", name="A", package_id="mod.a"),
            "/mods/x": make_listed_mod("/mods/x", name="X", package_id="mod.x"),
            "/mods/y": make_listed_mod("/mods/y", name="Y", package_id="mod.y"),
        }
        compiled = _build_compiled(
            deps={
                "mod.a": set(),
                "mod.x": {"mod.y"},
                "mod.y": {"mod.x"},
            },
        )
        sorter = Sorter(SortMethod.TOPOLOGICAL, compiled, mods, {"/mods/a"})
        success, result = sorter.sort()
        assert success
        assert result == ["/mods/a"]

    def test_inactive_tier_mods_excluded(self) -> None:
        """Tier mods that aren't active should not appear in the sort output."""
        mods = {
            "/mods/core": make_listed_mod(
                "/mods/core", name="Core", package_id="ludeon.rimworld"
            ),
            "/mods/regular": make_listed_mod(
                "/mods/regular", name="Regular", package_id="author.regular"
            ),
            "/mods/inactive_fw": make_listed_mod(
                "/mods/inactive_fw",
                name="InactiveFW",
                package_id="inactive.framework",
            ),
        }
        compiled = _build_compiled(
            deps={
                "ludeon.rimworld": set(),
                "author.regular": set(),
                "inactive.framework": set(),
            },
            tier_zero={"ludeon.rimworld"},
            tier_one={"inactive.framework"},
        )
        sorter = Sorter(
            SortMethod.TOPOLOGICAL,
            compiled,
            mods,
            {"/mods/core", "/mods/regular"},
        )
        success, result = sorter.sort()
        assert success
        assert "/mods/inactive_fw" not in result


class TestCrossTierInteractions:
    def test_tier_two_depending_on_tier_one_mod(self) -> None:
        """A regular mod (tier two) depending on a framework (tier one)."""
        mods = {
            "/mods/fw": make_listed_mod(
                "/mods/fw", name="Framework", package_id="author.framework"
            ),
            "/mods/reg": make_listed_mod(
                "/mods/reg", name="Regular", package_id="author.regular"
            ),
        }
        compiled = _build_compiled(
            deps={
                "author.framework": set(),
                "author.regular": {"author.framework"},
            },
            rev_deps={"author.framework": {"author.regular"}},
            tier_one={"author.framework"},
        )
        sorter = Sorter(
            SortMethod.TOPOLOGICAL, compiled, mods, {"/mods/fw", "/mods/reg"}
        )
        success, result = sorter.sort()
        assert success
        assert result.index("/mods/fw") < result.index("/mods/reg")

    def test_tier_one_dep_pulled_from_tier_two(self) -> None:
        """A mod that is a dependency of a tier-one mod gets pulled into tier one."""
        mods = {
            "/mods/fw": make_listed_mod(
                "/mods/fw", name="Framework", package_id="author.framework"
            ),
            "/mods/lib": make_listed_mod(
                "/mods/lib", name="Library", package_id="author.lib"
            ),
            "/mods/reg": make_listed_mod(
                "/mods/reg", name="Regular", package_id="author.regular"
            ),
        }
        compiled = _build_compiled(
            deps={
                "author.framework": {"author.lib"},
                "author.lib": set(),
                "author.regular": set(),
            },
            tier_one={"author.framework"},
        )
        sorter = Sorter(
            SortMethod.TOPOLOGICAL,
            compiled,
            mods,
            {"/mods/fw", "/mods/lib", "/mods/reg"},
        )
        success, result = sorter.sort()
        assert success
        assert result.index("/mods/lib") < result.index("/mods/reg")
        assert result.index("/mods/fw") < result.index("/mods/reg")

    def test_mod_in_both_tier_one_and_tier_three(self) -> None:
        """A mod in both tier_one and tier_three appears exactly once."""
        mods = {
            "/mods/weird": make_listed_mod(
                "/mods/weird", name="Weird", package_id="author.weird"
            ),
            "/mods/reg": make_listed_mod(
                "/mods/reg", name="Regular", package_id="author.regular"
            ),
        }
        compiled = _build_compiled(
            deps={"author.weird": set(), "author.regular": set()},
            tier_one={"author.weird"},
            tier_three={"author.weird"},
        )
        sorter = Sorter(
            SortMethod.TOPOLOGICAL,
            compiled,
            mods,
            {"/mods/weird", "/mods/reg"},
        )
        success, result = sorter.sort()
        assert success
        assert len(result) == 2
        assert result.count("/mods/weird") == 1

    def test_all_four_tiers_present(self) -> None:
        """Full 4-tier sort: zero < one < two < three."""
        mods, compiled, active = _build_four_tier_scenario()
        sorter = Sorter(SortMethod.TOPOLOGICAL, compiled, mods, active)
        success, result = sorter.sort()
        assert success
        assert result.index("/mods/core") < result.index("/mods/fw")
        assert result.index("/mods/fw") < result.index("/mods/reg")
        assert result.index("/mods/reg") < result.index("/mods/bottom")


class TestSorterCustomCallable:
    def test_custom_sort_method_used(self) -> None:
        """Passing a raw callable as sort_method — Sorter uses it directly."""

        def reverse_sort(
            graph: dict[str, set[str]],
            active: set[str],
            metadata: Mapping[str, ListedMod],
        ) -> list[str]:
            packageid_to_path = {}
            for path in active:
                mod = metadata.get(path)
                if isinstance(mod, AboutXmlMod):
                    packageid_to_path[str(mod.package_id)] = path
            return sorted(
                [packageid_to_path[pid] for pid in graph if pid in packageid_to_path],
                reverse=True,
            )

        mods = {
            "/mods/a": make_listed_mod("/mods/a", name="A", package_id="mod.a"),
            "/mods/b": make_listed_mod("/mods/b", name="B", package_id="mod.b"),
            "/mods/c": make_listed_mod("/mods/c", name="C", package_id="mod.c"),
        }
        compiled = _build_compiled(
            deps={"mod.a": set(), "mod.b": set(), "mod.c": set()}
        )
        sorter = Sorter(
            sort_method=reverse_sort,
            compiled_data=compiled,
            mods_metadata=mods,
            active_mod_paths={"/mods/a", "/mods/b", "/mods/c"},
        )
        success, result = sorter.sort()
        assert success
        assert result == ["/mods/c", "/mods/b", "/mods/a"]


class TestGenerateDependencyGraphsPartition:
    def test_four_tier_partition_correctness(self) -> None:
        """generate_dependency_graphs() returns 4 graphs with correct mod sets."""
        mods, compiled, active = _build_four_tier_scenario()
        sorter = Sorter(SortMethod.TOPOLOGICAL, compiled, mods, active)
        graphs = sorter.generate_dependency_graphs()
        assert len(graphs) == 4

        t0_keys, t1_keys, t2_keys, t3_keys = (set(g.keys()) for g in graphs)
        assert t0_keys == {"ludeon.rimworld"}
        assert t1_keys == {"author.framework"}
        assert t2_keys == {"author.regular"}
        assert t3_keys == {"author.bottom"}

    def test_partition_is_exhaustive_and_disjoint(self) -> None:
        """Every active mod appears in exactly one tier graph."""
        mods = {
            f"/mods/{i}": make_listed_mod(
                f"/mods/{i}", name=f"Mod{i}", package_id=f"mod.{i}"
            )
            for i in range(10)
        }
        compiled = _build_compiled(
            deps={f"mod.{i}": set() for i in range(10)},
            tier_zero={"mod.0"},
            tier_one={"mod.1", "mod.2"},
            tier_three={"mod.9"},
        )
        active = set(mods.keys())
        sorter = Sorter(SortMethod.TOPOLOGICAL, compiled, mods, active)
        graphs = sorter.generate_dependency_graphs()

        all_keys = [set(g.keys()) for g in graphs]
        union = set().union(*all_keys)
        assert union == {f"mod.{i}" for i in range(10)}
        for i in range(4):
            for j in range(i + 1, 4):
                assert all_keys[i] & all_keys[j] == set()


class TestSorterRegressions:
    def test_constants_not_mutated(self) -> None:
        """Regression test for #2041: KNOWN_TIER_ONE_MODS must not be mutated."""
        from app.utils.constants import KNOWN_TIER_ONE_MODS

        original = KNOWN_TIER_ONE_MODS.copy()

        mods = {
            "/mods/a": make_listed_mod(
                "/mods/a",
                name="Framework",
                package_id="author.framework",
                load_first=True,
            ),
            "/mods/b": make_listed_mod(
                "/mods/b", name="Regular", package_id="author.regular"
            ),
        }
        compiled = CompiledDependencyData.build(mods)

        assert KNOWN_TIER_ONE_MODS == original
        assert "author.framework" in compiled.tier_one_mods

    def test_output_has_no_duplicates(self) -> None:
        """Even if a mod appears in multiple tier graphs, output has no duplicates."""
        mods = {
            "/mods/a": make_listed_mod("/mods/a", name="A", package_id="mod.a"),
            "/mods/b": make_listed_mod("/mods/b", name="B", package_id="mod.b"),
        }
        compiled = _build_compiled(
            deps={"mod.a": set(), "mod.b": set()},
            tier_one={"mod.a"},
            tier_three={"mod.a"},
        )
        sorter = Sorter(SortMethod.TOPOLOGICAL, compiled, mods, {"/mods/a", "/mods/b"})
        success, result = sorter.sort()
        assert success
        assert len(result) == len(set(result))

    def test_reverse_deps_cycle_does_not_crash_tier_three(self) -> None:
        """Regression test for #2042: circular reverse deps in tier three expansion."""
        paths_and_ids = [
            ("alpha", "mod.alpha"),
            ("beta", "mod.beta"),
            ("gamma", "mod.gamma"),
        ]
        mods = {
            f"/mods/{name}": make_listed_mod(
                f"/mods/{name}", name=name.title(), package_id=pid
            )
            for name, pid in paths_and_ids
        }
        compiled = _build_compiled(
            deps={pid: set() for _, pid in paths_and_ids},
            rev_deps={
                "mod.alpha": {"mod.beta"},
                "mod.beta": {"mod.alpha"},
                "mod.gamma": set(),
            },
            tier_three={"mod.alpha"},
        )
        sorter = Sorter(
            SortMethod.TOPOLOGICAL,
            compiled,
            mods,
            {"/mods/alpha", "/mods/beta", "/mods/gamma"},
        )
        success, result = sorter.sort()
        assert success
        assert len(result) == 3


class TestTierModsWithNoEdges:
    def test_tier_zero_mod_without_graph_entry(self) -> None:
        """Tier-zero mod with no dependency edges must still sort in tier zero.

        Uses name "Zzz Core" so alphabetical ordering would place it AFTER "Alpha" —
        only tier-based ordering makes it appear first, proving the fix works.
        """
        mods = {
            "/mods/core": make_listed_mod(
                "/mods/core", name="Zzz Core", package_id="ludeon.rimworld"
            ),
            "/mods/regular": make_listed_mod(
                "/mods/regular", name="Alpha Regular", package_id="author.regular"
            ),
        }
        compiled = _build_compiled(
            deps={"author.regular": set()}, tier_zero={"ludeon.rimworld"}
        )
        sorter = Sorter(
            SortMethod.TOPOLOGICAL, compiled, mods, {"/mods/core", "/mods/regular"}
        )
        success, result = sorter.sort()
        assert success
        assert result.index("/mods/core") < result.index("/mods/regular")
        graphs = sorter.generate_dependency_graphs()
        assert "ludeon.rimworld" in graphs[0]
        assert "ludeon.rimworld" not in graphs[2]

    def test_tier_one_mod_without_graph_entry(self) -> None:
        """Tier-one mod with no edges must still sort in tier one.

        Uses name "Zzz Framework" so alphabetical ordering would place it AFTER "Alpha".
        """
        mods = {
            "/mods/fw": make_listed_mod(
                "/mods/fw", name="Zzz Framework", package_id="author.framework"
            ),
            "/mods/regular": make_listed_mod(
                "/mods/regular", name="Alpha Regular", package_id="author.regular"
            ),
        }
        compiled = _build_compiled(
            deps={"author.regular": set()}, tier_one={"author.framework"}
        )
        sorter = Sorter(
            SortMethod.TOPOLOGICAL, compiled, mods, {"/mods/fw", "/mods/regular"}
        )
        success, result = sorter.sort()
        assert success
        assert result.index("/mods/fw") < result.index("/mods/regular")
        graphs = sorter.generate_dependency_graphs()
        assert "author.framework" in graphs[1]
        assert "author.framework" not in graphs[2]

import pytest

from app.controllers.sort_controller import Sorter
from app.models.metadata.metadata_structure import CompiledDependencyData
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


class TestSorterRegressions:
    def test_constants_not_mutated(self) -> None:
        """Regression test for #2041: KNOWN_TIER_ONE_MODS must not be mutated."""
        from app.controllers.metadata_controller import MetadataController
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
        compiled = MetadataController._build_compiled_data(mods)

        assert KNOWN_TIER_ONE_MODS == original
        assert "author.framework" in compiled.tier_one_mods

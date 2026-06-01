from collections.abc import Generator
from unittest.mock import MagicMock

import pytest

from app.sort.dependencies import (
    gen_deps_graph,
    gen_rev_deps_graph,
    gen_tier_one_deps_graph,
    gen_tier_three_deps_graph,
    gen_tier_two_deps_graph,
    gen_tier_zero_deps_graph,
    get_dependencies_recursive,
    get_reverse_dependencies_recursive,
)
from tests.sort.conftest import make_mod

# ---------------------------------------------------------------------------
# get_dependencies_recursive — pure graph traversal, no MetadataManager
# ---------------------------------------------------------------------------


class TestGetDependenciesRecursive:
    def test_no_dependencies(self) -> None:
        graph: dict[str, set[str]] = {"mod_a": set()}
        result = get_dependencies_recursive("mod_a", graph, set())
        assert result == set()

    def test_direct_dependencies(self) -> None:
        graph: dict[str, set[str]] = {
            "mod_a": {"mod_b", "mod_c"},
            "mod_b": set(),
            "mod_c": set(),
        }
        result = get_dependencies_recursive("mod_a", graph, set())
        assert result == {"mod_b", "mod_c"}

    def test_transitive_dependencies(self) -> None:
        graph: dict[str, set[str]] = {
            "mod_a": {"mod_b"},
            "mod_b": {"mod_c"},
            "mod_c": {"mod_d"},
            "mod_d": set(),
        }
        result = get_dependencies_recursive("mod_a", graph, set())
        assert result == {"mod_b", "mod_c", "mod_d"}

    def test_diamond_dependency(self) -> None:
        """A depends on B and C, both depend on D."""
        graph: dict[str, set[str]] = {
            "mod_a": {"mod_b", "mod_c"},
            "mod_b": {"mod_d"},
            "mod_c": {"mod_d"},
            "mod_d": set(),
        }
        result = get_dependencies_recursive("mod_a", graph, set())
        assert result == {"mod_b", "mod_c", "mod_d"}

    def test_circular_dependency_terminates(self) -> None:
        """Circular deps don't infinite-loop thanks to processed_ids tracking."""
        graph: dict[str, set[str]] = {
            "mod_a": {"mod_b"},
            "mod_b": {"mod_a"},
        }
        result = get_dependencies_recursive("mod_a", graph, set())
        assert result == {"mod_b", "mod_a"}

    def test_unknown_package_returns_empty(self) -> None:
        graph: dict[str, set[str]] = {"mod_a": set()}
        result = get_dependencies_recursive("nonexistent", graph, set())
        assert result == set()

    def test_processed_ids_prevents_revisit(self) -> None:
        """If mod_b is already processed, it and its deps are skipped."""
        graph: dict[str, set[str]] = {
            "mod_a": {"mod_b"},
            "mod_b": {"mod_c"},
            "mod_c": set(),
        }
        already_processed = {"mod_b"}
        result = get_dependencies_recursive("mod_a", graph, already_processed)
        assert result == set()


# ---------------------------------------------------------------------------
# get_reverse_dependencies_recursive — reverse graph traversal
# ---------------------------------------------------------------------------


class TestGetReverseDependenciesRecursive:
    def test_no_reverse_deps(self) -> None:
        graph: dict[str, set[str]] = {"mod_a": set()}
        result = get_reverse_dependencies_recursive("mod_a", graph)
        assert result == set()

    def test_direct_reverse_deps(self) -> None:
        graph: dict[str, set[str]] = {
            "mod_a": {"mod_b", "mod_c"},
            "mod_b": set(),
            "mod_c": set(),
        }
        result = get_reverse_dependencies_recursive("mod_a", graph)
        assert result == {"mod_b", "mod_c"}

    def test_transitive_reverse_deps(self) -> None:
        graph: dict[str, set[str]] = {
            "mod_a": {"mod_b"},
            "mod_b": {"mod_c"},
            "mod_c": set(),
        }
        result = get_reverse_dependencies_recursive("mod_a", graph)
        assert result == {"mod_b", "mod_c"}

    def test_unknown_package_returns_empty(self) -> None:
        graph: dict[str, set[str]] = {"mod_a": set()}
        result = get_reverse_dependencies_recursive("nonexistent", graph)
        assert result == set()

    def test_circular_reverse_deps_causes_recursion_error(self) -> None:
        """Circular reverse deps cause infinite recursion — no processed_ids guard.

        Unlike get_dependencies_recursive, this function has no cycle protection.
        This test documents the production bug: if reverse dependency data ever
        contains a cycle, the app will crash with RecursionError.
        """
        graph: dict[str, set[str]] = {
            "mod_a": {"mod_b"},
            "mod_b": {"mod_a"},
        }
        with pytest.raises(RecursionError):
            get_reverse_dependencies_recursive("mod_a", graph)


# ---------------------------------------------------------------------------
# gen_deps_graph — builds forward dependency graph from loadTheseBefore
# ---------------------------------------------------------------------------


class TestGenDepsGraph:
    def test_no_dependencies(self, metadata_manager_mock: MagicMock) -> None:
        metadata_manager_mock.internal_local_metadata = {
            "uuid_a": make_mod("mod.a"),
            "uuid_b": make_mod("mod.b"),
        }
        graph = gen_deps_graph({"uuid_a", "uuid_b"}, ["mod.a", "mod.b"])
        assert graph == {"mod.a": set(), "mod.b": set()}

    def test_single_dependency(self, metadata_manager_mock: MagicMock) -> None:
        metadata_manager_mock.internal_local_metadata = {
            "uuid_a": make_mod("mod.a", load_these_before=[("mod.b", True)]),
            "uuid_b": make_mod("mod.b"),
        }
        graph = gen_deps_graph({"uuid_a", "uuid_b"}, ["mod.a", "mod.b"])
        assert graph["mod.a"] == {"mod.b"}
        assert graph["mod.b"] == set()

    def test_dependency_not_in_active_mods_excluded(
        self, metadata_manager_mock: MagicMock
    ) -> None:
        metadata_manager_mock.internal_local_metadata = {
            "uuid_a": make_mod("mod.a", load_these_before=[("mod.inactive", True)]),
        }
        graph = gen_deps_graph({"uuid_a"}, ["mod.a"])
        assert graph["mod.a"] == set()

    def test_multiple_dependencies(self, metadata_manager_mock: MagicMock) -> None:
        metadata_manager_mock.internal_local_metadata = {
            "uuid_a": make_mod(
                "mod.a", load_these_before=[("mod.b", True), ("mod.c", False)]
            ),
            "uuid_b": make_mod("mod.b"),
            "uuid_c": make_mod("mod.c"),
        }
        graph = gen_deps_graph(
            {"uuid_a", "uuid_b", "uuid_c"}, ["mod.a", "mod.b", "mod.c"]
        )
        assert graph["mod.a"] == {"mod.b", "mod.c"}


# ---------------------------------------------------------------------------
# gen_rev_deps_graph — builds reverse dependency graph from loadTheseAfter
# ---------------------------------------------------------------------------


class TestGenRevDepsGraph:
    def test_no_reverse_dependencies(self, metadata_manager_mock: MagicMock) -> None:
        metadata_manager_mock.internal_local_metadata = {
            "uuid_a": make_mod("mod.a"),
        }
        graph = gen_rev_deps_graph({"uuid_a"}, ["mod.a"])
        assert graph == {"mod.a": set()}

    def test_single_reverse_dependency(self, metadata_manager_mock: MagicMock) -> None:
        metadata_manager_mock.internal_local_metadata = {
            "uuid_a": make_mod("mod.a", load_these_after=[("mod.b", True)]),
            "uuid_b": make_mod("mod.b"),
        }
        graph = gen_rev_deps_graph({"uuid_a", "uuid_b"}, ["mod.a", "mod.b"])
        assert graph["mod.a"] == {"mod.b"}

    def test_inactive_reverse_dep_excluded(
        self, metadata_manager_mock: MagicMock
    ) -> None:
        metadata_manager_mock.internal_local_metadata = {
            "uuid_a": make_mod("mod.a", load_these_after=[("mod.inactive", True)]),
        }
        graph = gen_rev_deps_graph({"uuid_a"}, ["mod.a"])
        assert graph["mod.a"] == set()


# ---------------------------------------------------------------------------
# gen_tier_zero_deps_graph — filters to essential mods (Core, DLCs, Harmony)
# ---------------------------------------------------------------------------


class TestGenTierZeroDepsGraph:
    def test_known_tier_zero_mod_included(self) -> None:
        graph: dict[str, set[str]] = {
            "ludeon.rimworld": set(),
            "some.regular.mod": set(),
        }
        tier_zero_graph, tier_zero_mods = gen_tier_zero_deps_graph(graph)
        assert "ludeon.rimworld" in tier_zero_mods
        assert "some.regular.mod" not in tier_zero_mods
        assert "ludeon.rimworld" in tier_zero_graph

    def test_tier_zero_deps_included_transitively(self) -> None:
        graph: dict[str, set[str]] = {
            "brrainz.harmony": {"some.dep"},
            "some.dep": set(),
            "regular.mod": set(),
        }
        _, tier_zero_mods = gen_tier_zero_deps_graph(graph)
        assert "brrainz.harmony" in tier_zero_mods
        assert "some.dep" in tier_zero_mods
        assert "regular.mod" not in tier_zero_mods

    def test_inactive_known_tier_zero_mod_excluded(self) -> None:
        graph: dict[str, set[str]] = {"some.regular.mod": set()}
        _, tier_zero_mods = gen_tier_zero_deps_graph(graph)
        assert len(tier_zero_mods) == 0

    def test_empty_graph(self) -> None:
        tier_zero_graph, tier_zero_mods = gen_tier_zero_deps_graph({})
        assert tier_zero_graph == {}
        assert tier_zero_mods == set()

    def test_circular_deps_in_tier_zero_handled(self) -> None:
        graph: dict[str, set[str]] = {
            "brrainz.harmony": {"zetrith.prepatcher"},
            "zetrith.prepatcher": {"brrainz.harmony"},
        }
        _, tier_zero_mods = gen_tier_zero_deps_graph(graph)
        assert "brrainz.harmony" in tier_zero_mods
        assert "zetrith.prepatcher" in tier_zero_mods


# ---------------------------------------------------------------------------
# gen_tier_one_deps_graph — framework mods (KNOWN_TIER_ONE_MODS + loadTop)
# ---------------------------------------------------------------------------


class TestGenTierOneDepsGraph:
    @pytest.fixture(autouse=True)
    def _protect_known_tier_one_mods(self) -> Generator[None]:
        """Snapshot and restore KNOWN_TIER_ONE_MODS.

        gen_tier_one_deps_graph mutates the module-level constant via alias
        (production bug). This fixture prevents cross-test pollution.
        """
        from app.utils.constants import KNOWN_TIER_ONE_MODS

        original = KNOWN_TIER_ONE_MODS.copy()
        yield
        KNOWN_TIER_ONE_MODS.clear()
        KNOWN_TIER_ONE_MODS.update(original)

    def test_known_tier_one_mod_included(
        self, metadata_manager_mock: MagicMock
    ) -> None:
        metadata_manager_mock.internal_local_metadata = {}
        graph: dict[str, set[str]] = {
            "unlimitedhugs.hugslib": set(),
            "some.regular.mod": set(),
        }
        _, tier_one_mods = gen_tier_one_deps_graph(graph)
        assert "unlimitedhugs.hugslib" in tier_one_mods
        assert "some.regular.mod" not in tier_one_mods

    def test_load_top_mod_included(self, metadata_manager_mock: MagicMock) -> None:
        metadata_manager_mock.internal_local_metadata = {
            "uuid_custom": make_mod("custom.framework", load_top=True),
        }
        graph: dict[str, set[str]] = {
            "custom.framework": set(),
            "some.regular.mod": set(),
        }
        _, tier_one_mods = gen_tier_one_deps_graph(graph)
        assert "custom.framework" in tier_one_mods

    def test_transitive_deps_of_tier_one_included(
        self, metadata_manager_mock: MagicMock
    ) -> None:
        metadata_manager_mock.internal_local_metadata = {}
        graph: dict[str, set[str]] = {
            "unlimitedhugs.hugslib": {"some.hugslib.dep"},
            "some.hugslib.dep": set(),
        }
        _, tier_one_mods = gen_tier_one_deps_graph(graph)
        assert "some.hugslib.dep" in tier_one_mods

    def test_empty_graph(self, metadata_manager_mock: MagicMock) -> None:
        metadata_manager_mock.internal_local_metadata = {}
        tier_one_graph, tier_one_mods = gen_tier_one_deps_graph({})
        assert tier_one_graph == {}
        assert tier_one_mods == set()


# ---------------------------------------------------------------------------
# gen_tier_three_deps_graph — bottom-loading mods (loadBottom + rocketman)
# ---------------------------------------------------------------------------


class TestGenTierThreeDepsGraph:
    def test_hardcoded_rocketman_included(
        self, metadata_manager_mock: MagicMock
    ) -> None:
        metadata_manager_mock.internal_local_metadata = {
            "uuid_rocket": make_mod("krkr.rocketman"),
        }
        deps_graph: dict[str, set[str]] = {
            "krkr.rocketman": set(),
            "some.mod": set(),
        }
        rev_graph: dict[str, set[str]] = {
            "krkr.rocketman": set(),
            "some.mod": set(),
        }
        _, tier_three_mods = gen_tier_three_deps_graph(
            deps_graph, rev_graph, {"uuid_rocket"}
        )
        assert "krkr.rocketman" in tier_three_mods
        assert "some.mod" not in tier_three_mods

    def test_load_bottom_mod_included(self, metadata_manager_mock: MagicMock) -> None:
        metadata_manager_mock.internal_local_metadata = {
            "uuid_bottom": make_mod("custom.bottom", load_bottom=True),
        }
        deps_graph: dict[str, set[str]] = {"custom.bottom": set()}
        rev_graph: dict[str, set[str]] = {"custom.bottom": set()}
        _, tier_three_mods = gen_tier_three_deps_graph(
            deps_graph, rev_graph, {"uuid_bottom"}
        )
        assert "custom.bottom" in tier_three_mods

    def test_reverse_deps_pulled_into_tier_three(
        self, metadata_manager_mock: MagicMock
    ) -> None:
        """Mods that depend on tier three mods (via reverse graph) are also tier three."""
        metadata_manager_mock.internal_local_metadata = {
            "uuid_rocket": make_mod("krkr.rocketman"),
            "uuid_addon": make_mod("rocket.addon"),
        }
        deps_graph: dict[str, set[str]] = {
            "krkr.rocketman": set(),
            "rocket.addon": {"krkr.rocketman"},
        }
        rev_graph: dict[str, set[str]] = {
            "krkr.rocketman": {"rocket.addon"},
            "rocket.addon": set(),
        }
        tier_three_graph, tier_three_mods = gen_tier_three_deps_graph(
            deps_graph, rev_graph, {"uuid_rocket", "uuid_addon"}
        )
        assert "rocket.addon" in tier_three_mods
        assert tier_three_graph["rocket.addon"] == {"krkr.rocketman"}

    def test_non_tier_three_deps_trimmed(
        self, metadata_manager_mock: MagicMock
    ) -> None:
        """Dependencies on non-tier-three mods are removed from the tier three graph."""
        metadata_manager_mock.internal_local_metadata = {
            "uuid_rocket": make_mod("krkr.rocketman"),
            "uuid_regular": make_mod("some.regular"),
        }
        deps_graph: dict[str, set[str]] = {
            "krkr.rocketman": {"some.regular"},
            "some.regular": set(),
        }
        rev_graph: dict[str, set[str]] = {
            "krkr.rocketman": set(),
            "some.regular": set(),
        }
        tier_three_graph, _ = gen_tier_three_deps_graph(
            deps_graph, rev_graph, {"uuid_rocket", "uuid_regular"}
        )
        assert tier_three_graph["krkr.rocketman"] == set()


# ---------------------------------------------------------------------------
# gen_tier_two_deps_graph — everything else, with conflict resolution
# ---------------------------------------------------------------------------


class TestGenTierTwoDepsGraph:
    def test_basic_from_load_these_before(
        self, metadata_manager_mock: MagicMock
    ) -> None:
        metadata_manager_mock.internal_local_metadata = {
            "uuid_a": make_mod("mod.a", load_these_before=[("mod.b", True)]),
            "uuid_b": make_mod("mod.b"),
        }
        graph = gen_tier_two_deps_graph(
            {"uuid_a", "uuid_b"}, ["mod.a", "mod.b"], set(), set()
        )
        assert graph["mod.a"] == {"mod.b"}
        assert graph["mod.b"] == set()

    def test_tier_one_mods_excluded(self, metadata_manager_mock: MagicMock) -> None:
        metadata_manager_mock.internal_local_metadata = {
            "uuid_a": make_mod("mod.a"),
            "uuid_fw": make_mod("framework.mod"),
        }
        graph = gen_tier_two_deps_graph(
            {"uuid_a", "uuid_fw"},
            ["mod.a", "framework.mod"],
            {"framework.mod"},
            set(),
        )
        assert "framework.mod" not in graph
        assert "mod.a" in graph

    def test_tier_three_mods_excluded(self, metadata_manager_mock: MagicMock) -> None:
        metadata_manager_mock.internal_local_metadata = {
            "uuid_a": make_mod("mod.a"),
            "uuid_bottom": make_mod("bottom.mod"),
        }
        graph = gen_tier_two_deps_graph(
            {"uuid_a", "uuid_bottom"},
            ["mod.a", "bottom.mod"],
            set(),
            {"bottom.mod"},
        )
        assert "bottom.mod" not in graph

    def test_deps_referencing_tier_one_stripped(
        self, metadata_manager_mock: MagicMock
    ) -> None:
        metadata_manager_mock.internal_local_metadata = {
            "uuid_a": make_mod(
                "mod.a", load_these_before=[("framework.mod", True), ("mod.b", True)]
            ),
            "uuid_b": make_mod("mod.b"),
        }
        graph = gen_tier_two_deps_graph(
            {"uuid_a", "uuid_b"},
            ["mod.a", "mod.b", "framework.mod"],
            {"framework.mod"},
            set(),
        )
        assert graph["mod.a"] == {"mod.b"}

    def test_inferred_deps_from_about_xml(
        self, metadata_manager_mock: MagicMock
    ) -> None:
        """About.xml dependencies become load order rules when enabled."""
        metadata_manager_mock.internal_local_metadata = {
            "uuid_a": make_mod("mod.a", dependencies=["mod.b"]),
            "uuid_b": make_mod("mod.b"),
        }
        metadata_manager_mock.settings_controller.settings.use_alternative_package_ids_as_satisfying_dependencies = False
        graph = gen_tier_two_deps_graph(
            {"uuid_a", "uuid_b"},
            ["mod.a", "mod.b"],
            set(),
            set(),
            use_moddependencies_as_loadTheseBefore=True,
        )
        assert "mod.b" in graph["mod.a"]

    def test_explicit_rules_override_inferred(
        self, metadata_manager_mock: MagicMock
    ) -> None:
        """Explicit loadTheseBefore takes precedence over conflicting inferred deps."""
        # mod.a has inferred dep on mod.b (from About.xml dependencies)
        # mod.b explicitly says mod.a loads before it (mod.b -> mod.a)
        # The inferred mod.a -> mod.b would create a cycle, so it's dropped
        metadata_manager_mock.internal_local_metadata = {
            "uuid_a": make_mod("mod.a", dependencies=["mod.b"]),
            "uuid_b": make_mod("mod.b", load_these_before=[("mod.a", True)]),
        }
        metadata_manager_mock.settings_controller.settings.use_alternative_package_ids_as_satisfying_dependencies = False
        graph = gen_tier_two_deps_graph(
            {"uuid_a", "uuid_b"},
            ["mod.a", "mod.b"],
            set(),
            set(),
            use_moddependencies_as_loadTheseBefore=True,
        )
        assert "mod.b" not in graph["mod.a"]
        assert "mod.a" in graph["mod.b"]

    def test_empty_active_mods(self, metadata_manager_mock: MagicMock) -> None:
        metadata_manager_mock.internal_local_metadata = {}
        graph = gen_tier_two_deps_graph(set(), [], set(), set())
        assert graph == {}

    def test_inferred_deps_disabled_by_default(
        self, metadata_manager_mock: MagicMock
    ) -> None:
        """Without use_moddependencies_as_loadTheseBefore, About.xml deps are ignored."""
        metadata_manager_mock.internal_local_metadata = {
            "uuid_a": make_mod("mod.a", dependencies=["mod.b"]),
            "uuid_b": make_mod("mod.b"),
        }
        graph = gen_tier_two_deps_graph(
            {"uuid_a", "uuid_b"}, ["mod.a", "mod.b"], set(), set()
        )
        assert graph["mod.a"] == set()

    def test_tuple_dependency_with_alternatives(
        self, metadata_manager_mock: MagicMock
    ) -> None:
        """Tuple-format About.xml deps with alternatives are handled."""
        metadata_manager_mock.internal_local_metadata = {
            "uuid_a": make_mod(
                "mod.a",
                dependencies=[("mod.primary", {"alternatives": {"mod.alt"}})],
            ),
            "uuid_alt": make_mod("mod.alt"),
        }
        metadata_manager_mock.settings_controller.settings.use_alternative_package_ids_as_satisfying_dependencies = True
        graph = gen_tier_two_deps_graph(
            {"uuid_a", "uuid_alt"},
            ["mod.a", "mod.alt"],
            set(),
            set(),
            use_moddependencies_as_loadTheseBefore=True,
        )
        # mod.primary is not active, but mod.alt is an active alternative
        assert "mod.alt" in graph["mod.a"]

    def test_alternative_deps_disabled_by_setting(
        self, metadata_manager_mock: MagicMock
    ) -> None:
        """Alternative package IDs are ignored when the setting is disabled."""
        metadata_manager_mock.internal_local_metadata = {
            "uuid_a": make_mod(
                "mod.a",
                dependencies=[("mod.primary", {"alternatives": {"mod.alt"}})],
            ),
            "uuid_alt": make_mod("mod.alt"),
        }
        metadata_manager_mock.settings_controller.settings.use_alternative_package_ids_as_satisfying_dependencies = False
        graph = gen_tier_two_deps_graph(
            {"uuid_a", "uuid_alt"},
            ["mod.a", "mod.alt"],
            set(),
            set(),
            use_moddependencies_as_loadTheseBefore=True,
        )
        # Alternative resolution disabled — mod.alt should not appear
        assert graph["mod.a"] == set()

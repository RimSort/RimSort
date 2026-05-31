from unittest.mock import MagicMock

from app.sort.alphabetical_sort import do_alphabetical_sort
from tests.sort.conftest import (
    assert_diamond_ordering,
    diamond_fixture,
    make_mod,
    three_mod_alpha_fixture,
)


class TestDoAlphabeticalSort:
    def test_single_mod(self, metadata_manager_mock: MagicMock) -> None:
        metadata_manager_mock.internal_local_metadata = {
            "uuid_a": make_mod("mod.a", name="Alpha"),
        }
        result = do_alphabetical_sort({"mod.a": set()}, {"uuid_a"})
        assert result == ["uuid_a"]

    def test_alphabetical_no_dependencies(
        self, metadata_manager_mock: MagicMock
    ) -> None:
        """Without dependencies, mods are sorted alphabetically by name."""
        metadata, graph, active = three_mod_alpha_fixture()
        metadata_manager_mock.internal_local_metadata = metadata
        result = do_alphabetical_sort(graph, active)
        names = [
            metadata_manager_mock.internal_local_metadata[u]["name"] for u in result
        ]
        assert names == ["Alpha", "Middle", "Zebra"]

    def test_dependency_placed_before_dependent(
        self, metadata_manager_mock: MagicMock
    ) -> None:
        """A mod's dependency appears before it even if alphabetically later."""
        metadata_manager_mock.internal_local_metadata = {
            "uuid_a": make_mod("mod.a", name="Alpha"),
            "uuid_z": make_mod("mod.z", name="Zebra"),
        }
        # Alpha depends on Zebra
        graph: dict[str, set[str]] = {
            "mod.a": {"mod.z"},
            "mod.z": set(),
        }
        result = do_alphabetical_sort(graph, {"uuid_a", "uuid_z"})
        assert result.index("uuid_z") < result.index("uuid_a")

    def test_transitive_deps_placed_before(
        self, metadata_manager_mock: MagicMock
    ) -> None:
        metadata_manager_mock.internal_local_metadata = {
            "uuid_a": make_mod("mod.a", name="Alpha"),
            "uuid_b": make_mod("mod.b", name="Beta"),
            "uuid_c": make_mod("mod.c", name="Charlie"),
        }
        # Alpha -> Beta -> Charlie
        graph: dict[str, set[str]] = {
            "mod.a": {"mod.b"},
            "mod.b": {"mod.c"},
            "mod.c": set(),
        }
        result = do_alphabetical_sort(graph, {"uuid_a", "uuid_b", "uuid_c"})
        assert result.index("uuid_c") < result.index("uuid_b")
        assert result.index("uuid_b") < result.index("uuid_a")

    def test_graph_entries_not_in_active_mods_excluded(
        self, metadata_manager_mock: MagicMock
    ) -> None:
        metadata_manager_mock.internal_local_metadata = {
            "uuid_a": make_mod("mod.a", name="Alpha"),
        }
        graph: dict[str, set[str]] = {
            "mod.a": set(),
            "mod.ghost": set(),
        }
        result = do_alphabetical_sort(graph, {"uuid_a"})
        assert result == ["uuid_a"]

    def test_empty_graph(self, metadata_manager_mock: MagicMock) -> None:
        metadata_manager_mock.internal_local_metadata = {}
        result = do_alphabetical_sort({}, set())
        assert result == []

    def test_diamond_dependency(self, metadata_manager_mock: MagicMock) -> None:
        """Diamond: D depends on B and C, both depend on A. A appears once and first."""
        metadata, graph, active = diamond_fixture()
        metadata_manager_mock.internal_local_metadata = metadata
        result = do_alphabetical_sort(graph, active)
        assert_diamond_ordering(result)

    def test_case_insensitive_sort(self, metadata_manager_mock: MagicMock) -> None:
        """Alphabetical sorting is case-insensitive."""
        metadata_manager_mock.internal_local_metadata = {
            "uuid_upper": make_mod("mod.upper", name="ZEBRA"),
            "uuid_lower": make_mod("mod.lower", name="alpha"),
        }
        graph: dict[str, set[str]] = {
            "mod.upper": set(),
            "mod.lower": set(),
        }
        result = do_alphabetical_sort(graph, {"uuid_upper", "uuid_lower"})
        assert result == ["uuid_lower", "uuid_upper"]

    def test_non_string_name_handled(self, metadata_manager_mock: MagicMock) -> None:
        """Mods with non-string name values don't crash and sort after valid names."""
        metadata_manager_mock.internal_local_metadata = {
            "uuid_a": {"packageid": "mod.a", "name": None},
            "uuid_b": make_mod("mod.b", name="Beta"),
        }
        graph: dict[str, set[str]] = {
            "mod.a": set(),
            "mod.b": set(),
        }
        result = do_alphabetical_sort(graph, {"uuid_a", "uuid_b"})
        assert len(result) == 2
        # "Beta" sorts before the fallback "name error in mod about.xml"
        assert result[0] == "uuid_b"
        assert result[1] == "uuid_a"

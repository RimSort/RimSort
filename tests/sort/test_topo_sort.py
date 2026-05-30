from unittest.mock import MagicMock, patch

import pytest
from toposort import CircularDependencyError

from app.sort.topo_sort import do_topo_sort
from tests.sort.conftest import (
    assert_diamond_ordering,
    diamond_fixture,
    make_mod,
    three_mod_alpha_fixture,
)


class TestDoTopoSort:
    def test_single_mod(self, metadata_manager_mock: MagicMock) -> None:
        metadata_manager_mock.internal_local_metadata = {
            "uuid_a": make_mod("mod.a", name="Alpha"),
        }
        result = do_topo_sort({"mod.a": set()}, {"uuid_a"})
        assert result == ["uuid_a"]

    def test_linear_chain(self, metadata_manager_mock: MagicMock) -> None:
        """A -> B -> C produces dependencies-first ordering."""
        metadata_manager_mock.internal_local_metadata = {
            "uuid_a": make_mod("mod.a", name="A"),
            "uuid_b": make_mod("mod.b", name="B"),
            "uuid_c": make_mod("mod.c", name="C"),
        }
        graph: dict[str, set[str]] = {
            "mod.a": {"mod.b"},
            "mod.b": {"mod.c"},
            "mod.c": set(),
        }
        result = do_topo_sort(graph, {"uuid_a", "uuid_b", "uuid_c"})
        assert result.index("uuid_c") < result.index("uuid_b")
        assert result.index("uuid_b") < result.index("uuid_a")

    def test_alphabetical_within_same_level(
        self, metadata_manager_mock: MagicMock
    ) -> None:
        """Mods at the same topological level are sorted alphabetically by name."""
        metadata, graph, active = three_mod_alpha_fixture()
        metadata_manager_mock.internal_local_metadata = metadata
        result = do_topo_sort(graph, active)
        assert result == ["uuid_a", "uuid_m", "uuid_z"]

    def test_graph_entry_not_in_active_mods_skipped(
        self, metadata_manager_mock: MagicMock
    ) -> None:
        metadata_manager_mock.internal_local_metadata = {
            "uuid_a": make_mod("mod.a", name="A"),
        }
        graph: dict[str, set[str]] = {
            "mod.a": set(),
            "mod.inactive": set(),
        }
        result = do_topo_sort(graph, {"uuid_a"})
        assert result == ["uuid_a"]

    def test_missing_packageid_skipped(self, metadata_manager_mock: MagicMock) -> None:
        metadata_manager_mock.internal_local_metadata = {
            "uuid_a": make_mod("mod.a", name="A"),
            "uuid_bad": {"name": "Bad Mod"},  # missing packageid
        }
        result = do_topo_sort({"mod.a": set()}, {"uuid_a", "uuid_bad"})
        assert "uuid_a" in result
        assert "uuid_bad" not in result

    @patch("app.sort.topo_sort.show_warning")
    def test_circular_dependency_raises(
        self, mock_warning: MagicMock, metadata_manager_mock: MagicMock
    ) -> None:
        metadata_manager_mock.internal_local_metadata = {
            "uuid_a": make_mod("mod.a", name="A"),
            "uuid_b": make_mod("mod.b", name="B"),
        }
        graph: dict[str, set[str]] = {
            "mod.a": {"mod.b"},
            "mod.b": {"mod.a"},
        }
        with pytest.raises(CircularDependencyError):
            do_topo_sort(graph, {"uuid_a", "uuid_b"})
        mock_warning.assert_called_once()

    def test_complex_dag(self, metadata_manager_mock: MagicMock) -> None:
        """Diamond: D depends on B and C, both depend on A."""
        metadata, graph, active = diamond_fixture()
        metadata_manager_mock.internal_local_metadata = metadata
        result = do_topo_sort(graph, active)
        assert_diamond_ordering(result)

    def test_empty_graph(self, metadata_manager_mock: MagicMock) -> None:
        metadata_manager_mock.internal_local_metadata = {}
        result = do_topo_sort({}, set())
        assert result == []

    def test_non_string_name_handled(self, metadata_manager_mock: MagicMock) -> None:
        """Mods with non-string name values don't crash the sort."""
        metadata_manager_mock.internal_local_metadata = {
            "uuid_a": {"packageid": "mod.a", "name": None},
            "uuid_b": make_mod("mod.b", name="Beta"),
        }
        result = do_topo_sort({"mod.a": set(), "mod.b": set()}, {"uuid_a", "uuid_b"})
        assert len(result) == 2

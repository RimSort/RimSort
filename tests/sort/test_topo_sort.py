from unittest.mock import MagicMock, patch

import pytest
from toposort import CircularDependencyError

from app.sort.topo_sort import do_topo_sort
from tests.sort.conftest import (
    assert_diamond_ordering,
    diamond_mods,
    make_listed_mod,
    three_mod_alpha_mods,
)


class TestDoTopoSort:
    def test_single_mod(self) -> None:
        mods = {"/mods/a": make_listed_mod("/mods/a", name="Alpha", package_id="mod.a")}
        result = do_topo_sort({"mod.a": set()}, {"/mods/a"}, mods)
        assert result == ["/mods/a"]

    def test_linear_chain(self) -> None:
        """A -> B -> C produces dependencies-first ordering."""
        mods = {
            "/mods/a": make_listed_mod("/mods/a", name="A", package_id="mod.a"),
            "/mods/b": make_listed_mod("/mods/b", name="B", package_id="mod.b"),
            "/mods/c": make_listed_mod("/mods/c", name="C", package_id="mod.c"),
        }
        graph: dict[str, set[str]] = {
            "mod.a": {"mod.b"},
            "mod.b": {"mod.c"},
            "mod.c": set(),
        }
        result = do_topo_sort(graph, {"/mods/a", "/mods/b", "/mods/c"}, mods)
        assert result.index("/mods/c") < result.index("/mods/b")
        assert result.index("/mods/b") < result.index("/mods/a")

    def test_alphabetical_within_same_level(self) -> None:
        mods, graph, active = three_mod_alpha_mods()
        result = do_topo_sort(graph, active, mods)
        assert result == ["/mods/a", "/mods/m", "/mods/z"]

    def test_graph_entry_not_in_active_mods_skipped(self) -> None:
        mods = {"/mods/a": make_listed_mod("/mods/a", name="A", package_id="mod.a")}
        graph: dict[str, set[str]] = {"mod.a": set(), "mod.inactive": set()}
        result = do_topo_sort(graph, {"/mods/a"}, mods)
        assert result == ["/mods/a"]

    def test_missing_mod_in_metadata_skipped(self) -> None:
        mods = {"/mods/a": make_listed_mod("/mods/a", name="A", package_id="mod.a")}
        result = do_topo_sort({"mod.a": set()}, {"/mods/a", "/mods/bad"}, mods)
        assert "/mods/a" in result
        assert "/mods/bad" not in result

    @patch("app.sort.topo_sort.show_warning")
    def test_circular_dependency_raises(self, mock_warning: MagicMock) -> None:
        mods = {
            "/mods/a": make_listed_mod("/mods/a", name="A", package_id="mod.a"),
            "/mods/b": make_listed_mod("/mods/b", name="B", package_id="mod.b"),
        }
        graph: dict[str, set[str]] = {"mod.a": {"mod.b"}, "mod.b": {"mod.a"}}
        with pytest.raises(CircularDependencyError):
            do_topo_sort(graph, {"/mods/a", "/mods/b"}, mods)
        mock_warning.assert_called_once()

    def test_diamond_dag(self) -> None:
        mods, graph, active = diamond_mods()
        result = do_topo_sort(graph, active, mods)
        assert_diamond_ordering(result)

    def test_empty_graph(self) -> None:
        result = do_topo_sort({}, set(), {})
        assert result == []

    def test_non_string_name_handled(self) -> None:
        mod = make_listed_mod("/mods/a", name="Alpha", package_id="mod.a")
        object.__setattr__(mod, "name", None)
        mods_b = make_listed_mod("/mods/b", name="Beta", package_id="mod.b")
        mods = {"/mods/a": mod, "/mods/b": mods_b}
        result = do_topo_sort(
            {"mod.a": set(), "mod.b": set()}, {"/mods/a", "/mods/b"}, mods
        )
        assert len(result) == 2


class TestTopoSortEdgeCases:
    def test_wide_graph_alphabetical_tiebreak(self) -> None:
        """10 independent mods at the same level sort alphabetically."""
        names = [
            "Jester",
            "Apple",
            "Banana",
            "Fox",
            "Eagle",
            "Cherry",
            "Dog",
            "Grape",
            "Hippo",
            "Ice",
        ]
        mods = {}
        graph: dict[str, set[str]] = {}
        active = set()
        for i, name in enumerate(names):
            path = f"/mods/{i}"
            pid = f"mod.{i}"
            mods[path] = make_listed_mod(path, name=name, package_id=pid)
            graph[pid] = set()
            active.add(path)

        result = do_topo_sort(graph, active, mods)
        result_names = [mods[p].name for p in result]
        assert result_names == sorted(names, key=str.lower)

    def test_multiple_roots_with_shared_dep(self) -> None:
        """Two root mods depending on the same leaf."""
        mods = {
            "/mods/r1": make_listed_mod("/mods/r1", name="Root1", package_id="mod.r1"),
            "/mods/r2": make_listed_mod("/mods/r2", name="Root2", package_id="mod.r2"),
            "/mods/leaf": make_listed_mod(
                "/mods/leaf", name="Leaf", package_id="mod.leaf"
            ),
        }
        graph: dict[str, set[str]] = {
            "mod.r1": {"mod.leaf"},
            "mod.r2": {"mod.leaf"},
            "mod.leaf": set(),
        }
        result = do_topo_sort(graph, {"/mods/r1", "/mods/r2", "/mods/leaf"}, mods)
        assert result.index("/mods/leaf") < result.index("/mods/r1")
        assert result.index("/mods/leaf") < result.index("/mods/r2")

    def test_disconnected_subgraphs(self) -> None:
        """Two independent groups sort alphabetically within each level."""
        mods = {
            "/mods/a1": make_listed_mod("/mods/a1", name="A1", package_id="g1.a1"),
            "/mods/a2": make_listed_mod("/mods/a2", name="A2", package_id="g1.a2"),
            "/mods/b1": make_listed_mod("/mods/b1", name="B1", package_id="g2.b1"),
            "/mods/b2": make_listed_mod("/mods/b2", name="B2", package_id="g2.b2"),
        }
        graph: dict[str, set[str]] = {
            "g1.a1": {"g1.a2"},
            "g1.a2": set(),
            "g2.b1": {"g2.b2"},
            "g2.b2": set(),
        }
        active = set(mods.keys())
        result = do_topo_sort(graph, active, mods)
        assert result.index("/mods/a2") < result.index("/mods/a1")
        assert result.index("/mods/b2") < result.index("/mods/b1")

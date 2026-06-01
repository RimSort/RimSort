from app.sort.alphabetical_sort import do_alphabetical_sort
from tests.sort.conftest import (
    assert_diamond_ordering,
    diamond_mods,
    make_listed_mod,
    three_mod_alpha_mods,
)


class TestDoAlphabeticalSort:
    def test_single_mod(self) -> None:
        mods = {"/mods/a": make_listed_mod("/mods/a", name="Alpha", package_id="mod.a")}
        result = do_alphabetical_sort({"mod.a": set()}, {"/mods/a"}, mods)
        assert result == ["/mods/a"]

    def test_alphabetical_no_dependencies(self) -> None:
        mods, graph, active = three_mod_alpha_mods()
        result = do_alphabetical_sort(graph, active, mods)
        names = [mods[p].name for p in result]
        assert names == ["Alpha", "Middle", "Zebra"]

    def test_dependency_placed_before_dependent(self) -> None:
        mods = {
            "/mods/a": make_listed_mod("/mods/a", name="Alpha", package_id="mod.a"),
            "/mods/z": make_listed_mod("/mods/z", name="Zebra", package_id="mod.z"),
        }
        graph: dict[str, set[str]] = {"mod.a": {"mod.z"}, "mod.z": set()}
        result = do_alphabetical_sort(graph, {"/mods/a", "/mods/z"}, mods)
        assert result.index("/mods/z") < result.index("/mods/a")

    def test_transitive_deps_placed_before(self) -> None:
        mods = {
            "/mods/a": make_listed_mod("/mods/a", name="Alpha", package_id="mod.a"),
            "/mods/b": make_listed_mod("/mods/b", name="Beta", package_id="mod.b"),
            "/mods/c": make_listed_mod("/mods/c", name="Charlie", package_id="mod.c"),
        }
        graph: dict[str, set[str]] = {
            "mod.a": {"mod.b"},
            "mod.b": {"mod.c"},
            "mod.c": set(),
        }
        result = do_alphabetical_sort(graph, {"/mods/a", "/mods/b", "/mods/c"}, mods)
        assert result.index("/mods/c") < result.index("/mods/b")
        assert result.index("/mods/b") < result.index("/mods/a")

    def test_graph_entries_not_in_active_excluded(self) -> None:
        mods = {"/mods/a": make_listed_mod("/mods/a", name="Alpha", package_id="mod.a")}
        graph: dict[str, set[str]] = {"mod.a": set(), "mod.ghost": set()}
        result = do_alphabetical_sort(graph, {"/mods/a"}, mods)
        assert result == ["/mods/a"]

    def test_empty_graph(self) -> None:
        result = do_alphabetical_sort({}, set(), {})
        assert result == []

    def test_diamond_dependency(self) -> None:
        mods, graph, active = diamond_mods()
        result = do_alphabetical_sort(graph, active, mods)
        assert_diamond_ordering(result)

    def test_case_insensitive_sort(self) -> None:
        mods = {
            "/mods/upper": make_listed_mod(
                "/mods/upper", name="ZEBRA", package_id="mod.upper"
            ),
            "/mods/lower": make_listed_mod(
                "/mods/lower", name="alpha", package_id="mod.lower"
            ),
        }
        graph: dict[str, set[str]] = {"mod.upper": set(), "mod.lower": set()}
        result = do_alphabetical_sort(graph, {"/mods/upper", "/mods/lower"}, mods)
        assert result == ["/mods/lower", "/mods/upper"]

    def test_non_string_name_handled(self) -> None:
        mod_a = make_listed_mod("/mods/a", name="Alpha", package_id="mod.a")
        object.__setattr__(mod_a, "name", None)
        mod_b = make_listed_mod("/mods/b", name="Beta", package_id="mod.b")
        mods = {"/mods/a": mod_a, "/mods/b": mod_b}
        graph: dict[str, set[str]] = {"mod.a": set(), "mod.b": set()}
        result = do_alphabetical_sort(graph, {"/mods/a", "/mods/b"}, mods)
        assert len(result) == 2
        assert result[0] == "/mods/b"
        assert result[1] == "/mods/a"

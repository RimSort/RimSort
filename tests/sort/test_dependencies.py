from app.sort.dependencies import (
    extract_tier_subgraph,
    get_dependencies_recursive,
    get_reverse_dependencies_recursive,
)


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
        graph: dict[str, set[str]] = {
            "mod_a": {"mod_b", "mod_c"},
            "mod_b": {"mod_d"},
            "mod_c": {"mod_d"},
            "mod_d": set(),
        }
        result = get_dependencies_recursive("mod_a", graph, set())
        assert result == {"mod_b", "mod_c", "mod_d"}

    def test_circular_dependency_terminates(self) -> None:
        graph: dict[str, set[str]] = {"mod_a": {"mod_b"}, "mod_b": {"mod_a"}}
        result = get_dependencies_recursive("mod_a", graph, set())
        assert result == {"mod_b", "mod_a"}

    def test_unknown_package_returns_empty(self) -> None:
        graph: dict[str, set[str]] = {"mod_a": set()}
        result = get_dependencies_recursive("nonexistent", graph, set())
        assert result == set()

    def test_processed_ids_prevents_revisit(self) -> None:
        graph: dict[str, set[str]] = {
            "mod_a": {"mod_b"},
            "mod_b": {"mod_c"},
            "mod_c": set(),
        }
        result = get_dependencies_recursive("mod_a", graph, {"mod_b"})
        assert result == set()


class TestGetReverseDependenciesRecursive:
    def test_no_reverse_deps(self) -> None:
        graph: dict[str, set[str]] = {"mod_a": set()}
        result = get_reverse_dependencies_recursive("mod_a", graph, set())
        assert result == set()

    def test_direct_reverse_deps(self) -> None:
        graph: dict[str, set[str]] = {
            "mod_a": {"mod_b", "mod_c"},
            "mod_b": set(),
            "mod_c": set(),
        }
        result = get_reverse_dependencies_recursive("mod_a", graph, set())
        assert result == {"mod_b", "mod_c"}

    def test_transitive_reverse_deps(self) -> None:
        graph: dict[str, set[str]] = {
            "mod_a": {"mod_b"},
            "mod_b": {"mod_c"},
            "mod_c": set(),
        }
        result = get_reverse_dependencies_recursive("mod_a", graph, set())
        assert result == {"mod_b", "mod_c"}

    def test_unknown_package_returns_empty(self) -> None:
        graph: dict[str, set[str]] = {"mod_a": set()}
        result = get_reverse_dependencies_recursive("nonexistent", graph, set())
        assert result == set()

    def test_circular_reverse_deps_terminates(self) -> None:
        """Regression test for #2042: circular reverse deps must not crash."""
        graph: dict[str, set[str]] = {"mod_a": {"mod_b"}, "mod_b": {"mod_a"}}
        result = get_reverse_dependencies_recursive("mod_a", graph, set())
        assert result == {"mod_b", "mod_a"}

    def test_self_referencing(self) -> None:
        graph: dict[str, set[str]] = {"mod_a": {"mod_a"}}
        result = get_reverse_dependencies_recursive("mod_a", graph, set())
        assert result == {"mod_a"}


class TestExtractTierSubgraph:
    def test_filters_to_tier_mods_only(self) -> None:
        full_graph = {
            "mod.a": {"mod.b", "mod.c"},
            "mod.b": {"mod.c"},
            "mod.c": set(),
            "mod.d": {"mod.a"},
        }
        tier_mods = {"mod.a", "mod.b"}
        result = extract_tier_subgraph(full_graph, tier_mods)
        assert result == {"mod.a": {"mod.b"}, "mod.b": set()}

    def test_mod_not_in_graph_gets_empty_deps(self) -> None:
        full_graph: dict[str, set[str]] = {"mod.a": set()}
        tier_mods = {"mod.a", "mod.missing"}
        result = extract_tier_subgraph(full_graph, tier_mods)
        assert result == {"mod.a": set(), "mod.missing": set()}

    def test_empty_tier_set(self) -> None:
        full_graph = {"mod.a": {"mod.b"}}
        result = extract_tier_subgraph(full_graph, set())
        assert result == {}

    def test_empty_graph(self) -> None:
        result = extract_tier_subgraph({}, {"mod.a"})
        assert result == {"mod.a": set()}

from collections.abc import Callable, Mapping

from loguru import logger

from app.models.metadata.metadata_structure import (
    AboutXmlMod,
    CompiledDependencyData,
    ListedMod,
)
from app.sort.alphabetical_sort import do_alphabetical_sort
from app.sort.dependencies import (
    extract_tier_subgraph,
    get_dependencies_recursive,
    get_reverse_dependencies_recursive,
)
from app.sort.topo_sort import CircularDependencyError, do_topo_sort
from app.utils.constants import SortMethod


class Sorter:
    sort_method: Callable[
        [dict[str, set[str]], set[str], Mapping[str, ListedMod]], list[str]
    ]

    def __init__(
        self,
        sort_method: SortMethod
        | Callable[[dict[str, set[str]], set[str], Mapping[str, ListedMod]], list[str]],
        compiled_data: CompiledDependencyData,
        mods_metadata: Mapping[str, ListedMod],
        active_mod_paths: set[str],
    ):
        self.compiled_data = compiled_data
        self.mods_metadata = mods_metadata
        self.active_mod_paths = active_mod_paths.copy()

        self._active_package_ids: set[str] = set()
        for path in self.active_mod_paths:
            mod = self.mods_metadata.get(path)
            if isinstance(mod, AboutXmlMod):
                self._active_package_ids.add(str(mod.package_id))

        # TODO(debt): Both do_topo_sort and do_alphabetical_sort re-derive
        # packageid_to_path and name lookup dicts from these same inputs.
        # Precompute them here and pass down when sort function signatures
        # are finalized in PR 3.

        if isinstance(sort_method, SortMethod) or isinstance(sort_method, str):
            logger.info(f"Created sorter instance with {sort_method} sort method")

            if sort_method == SortMethod.ALPHABETICAL:
                logger.warning(
                    "Alphabetical sort is deprecated and may produce incorrect results "
                    "with complex mod lists. Consider switching to Topological sort."
                )
                self.sort_method = do_alphabetical_sort
            elif sort_method == SortMethod.TOPOLOGICAL:
                self.sort_method = do_topo_sort
            else:
                raise NotImplementedError(f"Sort method {sort_method} not implemented")
        elif callable(sort_method):
            self.sort_method = sort_method
        else:
            raise ValueError(
                f"Invalid sort method {sort_method}, type: {type(sort_method)}"
            )

    def _filter_graph_to_active(
        self, graph: dict[str, set[str]]
    ) -> dict[str, set[str]]:
        """Filter a dependency graph to only include active mods and edges between them."""
        return {
            pid: deps & self._active_package_ids
            for pid, deps in graph.items()
            if pid in self._active_package_ids
        }

    def _collect_tier_mods(
        self,
        known_tier_mods: set[str],
        deps_graph: dict[str, set[str]],
    ) -> set[str]:
        """Expand a set of known tier mods with their recursive dependencies.

        Only includes mods that are in the active set.
        """
        tier_mods: set[str] = set()
        for mod_id in known_tier_mods:
            if mod_id in self._active_package_ids:
                tier_mods.add(mod_id)
                if mod_id in deps_graph:
                    tier_mods.update(
                        get_dependencies_recursive(mod_id, deps_graph, set())
                    )
        return tier_mods & self._active_package_ids

    def _collect_tier_three_mods(
        self, active_rev_graph: dict[str, set[str]]
    ) -> set[str]:
        """Expand tier three mods with their recursive reverse dependencies.

        Only includes mods that are in the active set.
        """
        tier_three_mods: set[str] = set()
        for mod_id in self.compiled_data.tier_three_mods:
            if mod_id in self._active_package_ids:
                tier_three_mods.add(mod_id)
                tier_three_mods.update(
                    get_reverse_dependencies_recursive(mod_id, active_rev_graph, set())
                )
        return tier_three_mods & self._active_package_ids

    def generate_dependency_graphs(self) -> list[dict[str, set[str]]]:
        """Build tier-specific dependency subgraphs from compiled data.

        Filters the full compiled graph to active-only mods first, then
        partitions into tier-specific subgraphs.
        """
        logger.info("Generating dependency graphs from compiled data")

        active_deps = self._filter_graph_to_active(self.compiled_data.deps_graph)
        active_rev_deps = self._filter_graph_to_active(
            self.compiled_data.rev_deps_graph
        )

        tier_zero_mods = self._collect_tier_mods(
            self.compiled_data.tier_zero_mods, active_deps
        )
        tier_one_mods = self._collect_tier_mods(
            self.compiled_data.tier_one_mods, active_deps
        )
        tier_three_mods = self._collect_tier_three_mods(active_rev_deps)

        tier_zero_graph = extract_tier_subgraph(active_deps, tier_zero_mods)
        tier_one_graph = extract_tier_subgraph(active_deps, tier_one_mods)
        tier_three_graph = extract_tier_subgraph(active_deps, tier_three_mods)

        # Tier two: active mods not in any other tier
        all_tiered = tier_zero_mods | tier_one_mods | tier_three_mods
        tier_two_mods = self._active_package_ids - all_tiered
        tier_two_graph = extract_tier_subgraph(active_deps, tier_two_mods)

        return [tier_zero_graph, tier_one_graph, tier_two_graph, tier_three_graph]

    def sort(self) -> tuple[bool, list[str]]:
        """Sort mods using the configured sort method.

        :return: (success, sorted_mod_paths)
        """
        dependency_graphs = self.generate_dependency_graphs()

        sorted_paths: list[str] = []
        try:
            for i, graph in enumerate(dependency_graphs):
                logger.info(f"Sorting tier {i}")
                sorted_mods = self.sort_method(
                    graph, self.active_mod_paths, self.mods_metadata
                )
                logger.info(f"Tier {i} sorted: {len(sorted_mods)}")
                sorted_paths += sorted_mods
        except CircularDependencyError:
            logger.info("Circular dependency detected, abandoning sort")
            return False, []

        return True, list(dict.fromkeys(sorted_paths))

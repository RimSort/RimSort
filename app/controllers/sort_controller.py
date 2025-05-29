from typing import Callable

from loguru import logger

import app.sort.dependencies as sort_deps
from app.sort.alphabetical_sort import do_alphabetical_sort
from app.sort.topo_sort import CircularDependencyError, do_topo_sort
from app.utils.constants import SortMethod


class Sorter:
    """
    Controller class to handle sorting of mods using different sorting methods
    and dependency graph generation.
    """

    sort_method: Callable[[dict[str, set[str]], set[str]], list[str]]

    def __init__(
        self,
        sort_method: SortMethod | Callable[[dict[str, set[str]], set[str]], list[str]],
        active_package_ids: set[str],
        active_uuids: set[str],
        use_moddependencies_as_loadTheseBefore: bool = False,
    ):
        """
        Initialize the Sorter instance.

        :param sort_method: Sorting method to use (alphabetical, topological, or custom callable)
        :param active_package_ids: Set of active package IDs
        :param active_uuids: Set of active UUIDs
        """
        self.active_package_ids = active_package_ids.copy()
        self.active_uuids = active_uuids.copy()
        self.use_moddependencies_as_loadTheseBefore = (
            use_moddependencies_as_loadTheseBefore
        )

        if isinstance(sort_method, SortMethod) or isinstance(sort_method, str):
            logger.info(f"Created sorter instance with {sort_method} sort method")

            if sort_method == SortMethod.ALPHABETICAL:
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

    def generate_dependency_graphs(
        self,
    ) -> list[dict[str, set[str]]]:
        """
        Generate dependency graphs for the active mods, divided into tiers.

        :return: List of dependency graphs for tier one, two, and three mods
        """
        logger.info("Generating dependency graphs")
        active_package_ids_list = list(self.active_package_ids)
        dependencies_graph = sort_deps.gen_deps_graph(
            self.active_uuids, active_package_ids_list
        )
        reverse_dependencies_graph = sort_deps.gen_rev_deps_graph(
            self.active_uuids, active_package_ids_list
        )

        tier_one_graph, tier_one_mods = sort_deps.gen_tier_one_deps_graph(
            dependencies_graph
        )

        tier_three_graph, tier_three_mods = sort_deps.gen_tier_three_deps_graph(
            dependencies_graph,
            reverse_dependencies_graph,
            self.active_uuids,
        )

        tier_two_graph = sort_deps.gen_tier_two_deps_graph(
            self.active_uuids,
            active_package_ids_list,
            tier_one_mods,
            tier_three_mods,
            use_moddependencies_as_loadTheseBefore=self.use_moddependencies_as_loadTheseBefore,
        )

        return [tier_one_graph, tier_two_graph, tier_three_graph]

    def sort(
        self, dependency_graphs: list[dict[str, set[str]]] | None = None
    ) -> tuple[bool, list[str]]:
        """
        Sorts the given dependency graph using the controller's sort method.


        :param dependency_graphs: The dependency graph to be sorted, defaults to None
        :type dependency_graphs: list[dict[str, set[str]]] | None, optional
        :return: True and the sorted list of UUIDs if the sort was successful, False and an empty list otherwise
        :rtype: tuple[bool, list[str]]
        """
        if dependency_graphs is None:
            dependency_graphs = self.generate_dependency_graphs()

        sorted_uuids = []
        try:
            for i, graph in enumerate(dependency_graphs):
                logger.info(f"Sorting tier {i + 1}")
                sorted_mods = self.sort_method(graph, self.active_uuids)
                logger.info(f"Tier {i + 1} sorted: {len(sorted_mods)}")
                sorted_uuids += sorted_mods
        except CircularDependencyError:
            logger.info("Circular dependency detected, abandoning sort")
            return False, []

        return True, list(dict.fromkeys(sorted_uuids))

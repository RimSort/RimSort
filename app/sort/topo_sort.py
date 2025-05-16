import networkx as nx
from loguru import logger
from PySide6.QtCore import QCoreApplication
from toposort import CircularDependencyError, toposort

from app.utils.metadata import MetadataManager
from app.views.dialogue import show_warning


def do_topo_sort(
    dependency_graph: dict[str, set[str]], active_mods_uuids: set[str]
) -> list[str]:
    """
    Sort mods using the topological sort algorithm. For each
    topological level, sort the mods alphabetically.

    :param dependency_graph: Dependency graph mapping package IDs to dependencies
    :param active_mods_uuids: Set of active mod UUIDs
    :return: List of sorted mod UUIDs
    """
    logger.info(f"Initializing topological sort for {len(dependency_graph)} mods")
    # Cache MetadataManager instance
    metadata_manager = MetadataManager.instance()
    try:
        sorted_dependencies = list(toposort(dependency_graph))
    except CircularDependencyError as e:
        find_circular_dependencies(dependency_graph)
        # Propagate the exception after handling
        raise e

    reordered = list()
    # Build a map of dependency package_id to name for active mods
    active_mods_packageid_to_uuid = dict(
        (
            metadata_manager.internal_local_metadata[uuid]["packageid"],
            uuid,
        )
        for uuid in active_mods_uuids
    )
    # Iterate through the sorted dependencies
    for level in sorted_dependencies:
        temp_mod_set = set(
            active_mods_packageid_to_uuid[package_id]
            for package_id in level
            if package_id in active_mods_packageid_to_uuid
        )
        # Sort packages in this topological level by name
        sorted_temp_mod_set = sorted(
            temp_mod_set,
            key=lambda uuid: metadata_manager.internal_local_metadata[uuid]["name"],
            reverse=False,
        )
        # Add into reordered set
        reordered.extend(sorted_temp_mod_set)
    logger.info(f"Finished topological sort with {len(reordered)} mods")
    return reordered


def find_circular_dependencies(dependency_graph: dict[str, set[str]]) -> None:
    """
    Detect and log circular dependencies in the given dependency graph.
    Show a warning dialog with details if any cycles are found.

    :param dependency_graph: Dependency graph mapping package IDs to dependencies
    """
    graph = nx.DiGraph(dependency_graph)  # type: ignore # Stubs seem to be broken for args
    cycles = list(nx.simple_cycles(graph))

    cycle_strings = list()
    if cycles:
        logger.info("Circular dependencies detected:")
        for cycle in cycles:
            loop = " -> ".join(cycle)
            logger.info(loop)
            cycle_strings.append(loop)
    else:
        logger.info("No circular dependencies found.")

    show_warning(
        title=QCoreApplication.translate(
            "find_circular_dependencies", "Unable to Sort"
        ),
        text=QCoreApplication.translate("find_circular_dependencies", "Unable to Sort"),
        information=QCoreApplication.translate(
            "find_circular_dependencies",
            "RimSort found circular dependencies in your mods list. Please see the details for dependency loops.",
        ),
        details="\n\n".join(cycle_strings),
    )

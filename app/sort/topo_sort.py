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
    Sort mods using the topological sort algorithm in pure toposort order.
    """
    logger.info(f"Initializing toposort for {len(dependency_graph)} mods")
    # Cache MetadataManager instance
    metadata_manager = MetadataManager.instance()

    try:
        sorted_dependencies = list(toposort(dependency_graph))
    except CircularDependencyError as e:
        find_circular_dependencies(dependency_graph)
        # Propagate the exception after handling
        raise e

    reordered = list()
    active_mods_packageid_to_uuid = dict(
        (metadata_manager.internal_local_metadata[uuid]["packageid"], uuid)
        for uuid in active_mods_uuids
    )
    for level in sorted_dependencies:
        # Preserve order from toposort - use list instead of set
        temp_mod_list = []
        for package_id in level:
            if package_id in active_mods_packageid_to_uuid:
                mod_uuid = active_mods_packageid_to_uuid[package_id]
                temp_mod_list.append(mod_uuid)

        # Add into reordered list (pure toposort order)
        reordered.extend(temp_mod_list)
    logger.info(f"Finished Toposort sort with {len(reordered)} mods")
    return reordered


def find_circular_dependencies(dependency_graph: dict[str, set[str]]) -> None:
    graph = nx.DiGraph(dependency_graph)  # type: ignore # A set is fine, but linters warn about it
    cycles = list(nx.simple_cycles(graph))  # find all cycles in the graph

    cycle_strings = []
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

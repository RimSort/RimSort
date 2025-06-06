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
        temp_mod_set = set()
        for package_id in level:
            if package_id in active_mods_packageid_to_uuid:
                mod_uuid = active_mods_packageid_to_uuid[package_id]
                temp_mod_set.add(mod_uuid)
        # Sort packages in this topological level by name
        sorted_temp_mod_set = sorted(
            temp_mod_set,
            key=lambda uuid: metadata_manager.internal_local_metadata[uuid]["name"],
            reverse=False,
        )
        # Add into reordered set
        for sorted_mod_uuid in sorted_temp_mod_set:
            reordered.append(sorted_mod_uuid)
    logger.info(f"Finished Toposort sort with {len(reordered)} mods")
    return reordered


def find_circular_dependencies(dependency_graph: dict[str, set[str]]) -> None:
    graph = nx.DiGraph(dependency_graph)  # use the networkx library
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

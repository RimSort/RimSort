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
    topological level, sort the mods alphabetically by name for consistency.
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
    active_mods_uuid_to_packageid = {}
    active_mods_packageid_to_uuid = {}
    active_mods_uuid_to_name = {}
    for uuid in active_mods_uuids:
        try:
            packageid = metadata_manager.internal_local_metadata[uuid]["packageid"]
            active_mods_uuid_to_packageid[uuid] = packageid
            active_mods_packageid_to_uuid[packageid] = uuid
            name_value = metadata_manager.internal_local_metadata[uuid].get("name")
            if not isinstance(name_value, str):
                name_value = "name error in mod about.xml"
            active_mods_uuid_to_name[uuid] = name_value
        except KeyError:
            logger.warning(f"Missing packageid for mod UUID {uuid}, skipping")
            continue

    def safe_name(name: object) -> str:
        if isinstance(name, str):
            return name.lower()
        else:
            return "name error in mod about.xml"

    for level in sorted_dependencies:
        temp_mod_list = [
            active_mods_packageid_to_uuid[package_id]
            for package_id in level
            if package_id in active_mods_packageid_to_uuid
        ]

        # Sort packages in this topological level alphabetically by name for consistency
        sorted_temp_mod_list = sorted(
            temp_mod_list,
            key=lambda u: safe_name(active_mods_uuid_to_name[u]),
            reverse=False,
        )
        # Add into reordered list
        reordered.extend(sorted_temp_mod_list)
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

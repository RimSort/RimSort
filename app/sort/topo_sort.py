import networkx as nx
from loguru import logger
from toposort import CircularDependencyError, toposort

from app.utils.metadata import MetadataManager
from app.views.dialogue import show_warning


def do_topo_sort(
    dependency_graph: dict[str, set[str]], active_mods_uuids: set[str]
) -> list[str]:
    """
    Perform a topological sort on the given dependency graph and filter
    the results to only include the active mods.

    Args:
        dependency_graph (dict[str, set[str]]): A mapping from PackageID
            to the set of PackageIDs it depends on. For example:
            {"PackageA": {"PackageB", "PackageC"}, ...}.
        active_mods_uuids (set[str]): A set of mod UUIDs that are currently active.

    Returns:
        list[str]: A list of active mod UUIDs, sorted by topological level.
    """
    logger.info(f"Initializing topological sort for {len(dependency_graph)} mods.")

    # Cache MetadataManager instance for retrieving mod info.
    metadata_manager = MetadataManager.instance()

    try:
        # Attempt to topologically sort the dependency graph.
        topological_levels = list(toposort(dependency_graph))
    except CircularDependencyError as e:
        # If there's a circular dependency, handle and then re-raise.
        find_circular_dependencies(dependency_graph)
        raise e

    # Create a quick lookup of packageID -> UUID for the active mods.
    active_pid_to_uuid = dict(
        (metadata_manager.internal_local_metadata[uuid]["packageid"], uuid)
        for uuid in active_mods_uuids
    )

    # Build the final sorted list of active mods.
    sorted_mod_uuids: list[str] = []
    for level in topological_levels:
        # Gather only those mods in the current 'level' that are also active.
        active_mods_in_level = [
            active_pid_to_uuid[package_id]
            for package_id in level
            if package_id in active_pid_to_uuid
        ]
        # Extend our master list in the order they appear in the topological sort.
        sorted_mod_uuids.extend(active_mods_in_level)

    logger.info(f"Finished topological sort, returning {len(sorted_mod_uuids)} mods.")
    return sorted_mod_uuids


def find_circular_dependencies(dependency_graph: dict[str, set[str]]) -> None:
    """
    Detect circular dependencies within the provided dependency graph.
    Display a warning dialog if any cycles are found.

    Args:
        dependency_graph (dict[str, set[str]]): The same graph passed to `do_topo_sort`.
            Its keys are package IDs, and values are sets of package IDs it depends on.

    Side Effects:
        - Logs a list of all detected cycles (each cycle is reported once).
        - Shows a warning dialog with the cycle details.
    """
    # Create a directed graph from the dictionary for cycle detection.
    # (Ignore type stubs: they sometimes incorrectly flag dict-based init.)
    graph = nx.DiGraph(dependency_graph)  # type: ignore

    # Attempt to find all simple cycles.
    cycles = list(nx.simple_cycles(graph))

    cycle_strings: list[str] = []
    if cycles:
        logger.warning("Circular dependencies detected:")
        for cycle in cycles:
            loop_str = " -> ".join(cycle)
            logger.warning(loop_str)
            cycle_strings.append(loop_str)
    else:
        logger.info("No circular dependencies found.")

    # Show a warning, with details of each cycle if any exist.
    show_warning(
        title="Unable to Sort Mods",
        text="Circular Dependency Detected",
        information="RimSort found circular dependencies in your mod list. "
        "Please review the loops below and adjust your load order.",
        details="\n\n".join(cycle_strings),
    )

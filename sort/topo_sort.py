from logger_tt import logger
from typing import Any

from toposort import toposort

from util.metadata import MetadataManager


def do_topo_sort(
    dependency_graph: dict[str, set[str]], active_mods_uuids: set[str]
) -> set[str]:
    """
    Sort mods using the topological sort algorithm. For each
    topological level, sort the mods alphabetically.
    """
    logger.info(f"Initializing toposort for {len(dependency_graph)} mods")
    sorted_dependencies = toposort(dependency_graph)
    reordered = set()
    active_mods_packageid_to_uuid = dict(
        (MetadataManager.instance().all_mods_compiled[uuid]["packageid"], uuid)
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
            key=lambda uuid: MetadataManager.instance().all_mods_compiled[uuid]["name"],
            reverse=False,
        )
        # Add into reordered set
        for sorted_mod_uuid in sorted_temp_mod_set:
            reordered.add(sorted_mod_uuid)
    logger.info(f"Finished Toposort sort with {len(reordered)} mods")
    return reordered

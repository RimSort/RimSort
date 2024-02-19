from typing import List

from loguru import logger
from toposort import toposort

from app.utils.metadata import MetadataManager


def do_topo_sort(
    dependency_graph: dict[str, set[str]], active_mods_uuids: set[str]
) -> List[str]:
    """
    Sort mods using the topological sort algorithm. For each
    topological level, sort the mods alphabetically.
    """
    logger.info(f"Initializing toposort for {len(dependency_graph)} mods")
    # Cache MetadataManager instance
    metadata_manager = MetadataManager.instance()
    sorted_dependencies = toposort(dependency_graph)
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

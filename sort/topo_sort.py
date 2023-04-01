from logger_tt import logger
from typing import Any

from toposort import toposort




def do_topo_sort(
    dependency_graph: dict[str, set[str]], active_mods_json: dict[str, Any]
) -> dict[str, Any]:
    """
    Sort mods using the topological sort algorithm. For each
    topological level, sort the mods alphabetically.
    """
    logger.info(f"Starting Toposort for {len(dependency_graph)} mods")
    sorted_dependencies = toposort(dependency_graph)
    alphabetized_dependencies_w_data = {}
    active_mods_packageid_to_uuid = dict(
        (v["packageId"], v["uuid"]) for v in active_mods_json.values()
    )
    for level in sorted_dependencies:
        temp_mod_dict = {}
        for package_id in level:
            if package_id in active_mods_packageid_to_uuid:
                mod_uuid = active_mods_packageid_to_uuid[package_id]
                temp_mod_dict[mod_uuid] = active_mods_json[mod_uuid]
        # Sort packages in this topological level by name
        sorted_temp_mod_dict = sorted(
            temp_mod_dict.items(), key=lambda x: x[1]["name"], reverse=False
        )
        # sorted_mod is tuple of (uuid, json_data)
        # Add into reordered_active_mods_data (dicts are ordered now)
        for sorted_mod in sorted_temp_mod_dict:
            alphabetized_dependencies_w_data[sorted_mod[0]] = active_mods_json[
                sorted_mod[0]
            ]
    logger.info(
        f"Finished Toposort sort with {len(alphabetized_dependencies_w_data)} mods"
    )
    return alphabetized_dependencies_w_data

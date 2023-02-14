from typing import Any, Dict
from toposort import toposort


def do_topo_sort(
    dependency_graph: Dict[str, set], active_mods_json: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Sort mods using the topological sort algorithm. For each
    topological level, sort the mods alphabetically.
    """
    sorted_dependencies = toposort(dependency_graph)
    alphabetized_dependencies_w_data = {}
    for level in sorted_dependencies:
        temp_mod_dict = {}
        for package_id in level:
            temp_mod_dict[package_id] = active_mods_json[package_id]
        # Sort packages in this topological level by name
        sorted_temp_mod_dict = sorted(
            temp_mod_dict.items(), key=lambda x: x[1]["name"], reverse=False
        )
        # sorted_mod is tuple of (packageId, json_data)
        # Add into reordered_active_mods_data (dicts are ordered now)
        for sorted_mod in sorted_temp_mod_dict:
            alphabetized_dependencies_w_data[sorted_mod[0]] = active_mods_json[
                sorted_mod[0]
            ]
    return alphabetized_dependencies_w_data

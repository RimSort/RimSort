from collections.abc import Mapping

from loguru import logger

from app.models.metadata.metadata_structure import AboutXmlMod, ListedMod


def do_alphabetical_sort(
    dependency_graph: dict[str, set[str]],
    active_mod_paths: set[str],
    mods_metadata: Mapping[str, ListedMod],
) -> list[str]:
    """Sort mods alphabetically, inserting dependencies before dependents.

    :param dependency_graph: package_id -> set of dependency package_ids
    :param active_mod_paths: Set of mod paths (identifiers) to sort
    :param mods_metadata: path -> ListedMod mapping for name lookups
    :return: Sorted list of mod paths
    """
    logger.info(f"Starting Alphabetical sort for {len(dependency_graph)} mods")

    packageid_to_name: dict[str, str] = {}
    packageid_to_path: dict[str, str] = {}

    for path in active_mod_paths:
        mod = mods_metadata.get(path)
        if not isinstance(mod, AboutXmlMod):
            continue
        pid = str(mod.package_id)
        packageid_to_name[pid] = (
            mod.name if isinstance(mod.name, str) else "name error in mod about.xml"
        )
        packageid_to_path[pid] = path

    def safe_name(name: object) -> str:
        if isinstance(name, str):
            return name.lower()
        return "name error in mod about.xml"

    active_mods_alphabetized = sorted(
        packageid_to_name.items(), key=lambda x: safe_name(x[1]), reverse=False
    )

    dependencies_alphabetized: dict[str, set[str]] = {}
    for pid, _name in active_mods_alphabetized:
        if pid in dependency_graph:
            dependencies_alphabetized[pid] = dependency_graph[pid]

    mods_load_order: list[str] = []
    for package_id in dependencies_alphabetized:
        if package_id not in mods_load_order:
            mods_load_order.append(package_id)
            index_just_appended = mods_load_order.index(package_id)
            _recursively_force_insert(
                mods_load_order,
                dependency_graph,
                package_id,
                packageid_to_name,
                index_just_appended,
            )

    reordered: list[str] = []
    for package_id in mods_load_order:
        if package_id in packageid_to_path:
            reordered.append(packageid_to_path[package_id])

    logger.info(f"Finished Alphabetical sort with {len(reordered)} mods")
    return reordered


def _recursively_force_insert(
    mods_load_order: list[str],
    dependency_graph: dict[str, set[str]],
    package_id: str,
    packageid_to_name: dict[str, str],
    index_just_appended: int,
) -> None:
    deps_of_package = dependency_graph.get(package_id, set())
    deps_id_to_name: dict[str, str] = {}
    for dep_id in deps_of_package:
        if dep_id in packageid_to_name:
            deps_id_to_name[dep_id] = packageid_to_name[dep_id]

    deps_alphabetized = sorted(
        deps_id_to_name.items(), key=lambda x: x[1], reverse=False
    )

    for dep_id, _dep_name in deps_alphabetized:
        if dep_id not in mods_load_order:
            index_to_insert_at = index_just_appended
            for e in reversed(
                mods_load_order[index_just_appended : mods_load_order.index(package_id)]
            ):
                if dep_id in dependency_graph and e in dependency_graph[dep_id]:
                    index_to_insert_at = mods_load_order.index(e) + 1
                    break

            mods_load_order.insert(index_to_insert_at, dep_id)
            new_idx = mods_load_order.index(dep_id)
            _recursively_force_insert(
                mods_load_order,
                dependency_graph,
                dep_id,
                packageid_to_name,
                new_idx,
            )

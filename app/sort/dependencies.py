def extract_tier_subgraph(
    full_graph: dict[str, set[str]],
    tier_mods: set[str],
) -> dict[str, set[str]]:
    """Extract a subgraph containing only edges between mods in ``tier_mods``.

    Every mod in ``tier_mods`` gets an entry in the result, even if it has
    no edges in ``full_graph``.
    """
    return {mod_id: full_graph.get(mod_id, set()) & tier_mods for mod_id in tier_mods}


def get_dependencies_recursive(
    package_id: str,
    active_mods_dependencies: dict[str, set[str]],
    processed_ids: set[str],
) -> set[str]:
    dependencies_set: set[str] = set()
    if package_id in active_mods_dependencies:
        for dependency_id in active_mods_dependencies[package_id]:
            if dependency_id not in processed_ids:
                processed_ids.add(dependency_id)
                dependencies_set.add(dependency_id)
                dependencies_set.update(
                    get_dependencies_recursive(
                        dependency_id, active_mods_dependencies, processed_ids
                    )
                )
    return dependencies_set


def get_reverse_dependencies_recursive(
    package_id: str,
    active_mods_rev_dependencies: dict[str, set[str]],
    processed_ids: set[str],
) -> set[str]:
    reverse_dependencies_set: set[str] = set()
    if package_id in active_mods_rev_dependencies:
        for dependent_id in active_mods_rev_dependencies[package_id]:
            if dependent_id not in processed_ids:
                processed_ids.add(dependent_id)
                reverse_dependencies_set.add(dependent_id)
                reverse_dependencies_set.update(
                    get_reverse_dependencies_recursive(
                        dependent_id, active_mods_rev_dependencies, processed_ids
                    )
                )
    return reverse_dependencies_set

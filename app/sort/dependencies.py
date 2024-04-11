from loguru import logger

from app.utils.metadata import MetadataManager


def gen_deps_graph(
    active_mods_uuids: set[str], active_mod_ids: list[str]
) -> dict[str, set[str]]:
    """
    Get dependencies
    """
    # Cache MetadataManager instance
    metadata_manager = MetadataManager.instance()
    # Schema: {item: {dependency1, dependency2, ...}}
    logger.info("Generating dependencies graph")
    dependencies_graph: dict[str, set[str]] = {}
    for uuid in active_mods_uuids:
        package_id = metadata_manager.internal_local_metadata[uuid]["packageid"]
        dependencies_graph[package_id] = set()
        if metadata_manager.internal_local_metadata[uuid].get(
            "loadTheseBefore"
        ):  # Will either be None, or a set
            for dependency in metadata_manager.internal_local_metadata[uuid][
                "loadTheseBefore"
            ]:
                # Only add a dependency if dependency exists in active_mods. Recall
                # that dependencies exist for all_mods, but not all of these will be
                # in active mods. Also note that dependencies here refers to load order
                # rules. Also note that dependency[0] is required as dependency is a tuple
                # of package_id, explicit_bool
                if not isinstance(dependency, tuple):
                    logger.error(
                        f"Expected load order rule to be a tuple: [{dependency}]"
                    )
                if dependency[0] in active_mod_ids:
                    dependencies_graph[package_id].add(dependency[0])
    logger.info(
        f"Finished generating dependencies graph of {len(dependencies_graph)} items"
    )
    return dependencies_graph


def gen_rev_deps_graph(
    active_mods_uuids: set[str], active_mod_ids: list[str]
) -> dict[str, set[str]]:
    # Cache MetadataManager instance
    metadata_manager = MetadataManager.instance()
    # Schema: {item: {isDependentOn1, isDependentOn2, ...}}
    logger.debug("Generating reverse dependencies graph")
    reverse_dependencies_graph: dict[str, set[str]] = {}
    for uuid in active_mods_uuids:
        package_id = metadata_manager.internal_local_metadata[uuid]["packageid"]
        reverse_dependencies_graph[package_id] = set()
        if metadata_manager.internal_local_metadata[uuid].get(
            "loadTheseAfter"
        ):  # Will either be None, or a set
            for dependent in metadata_manager.internal_local_metadata[uuid][
                "loadTheseAfter"
            ]:
                # Dependent[0] is required here as as dependency is a tuple of package_id, explicit_bool
                if not isinstance(dependent, tuple):
                    logger.error(
                        f"Expected load order rule to be a tuple: [{dependent}]"
                    )
                if dependent[0] in active_mod_ids:
                    reverse_dependencies_graph[package_id].add(dependent[0])
    logger.debug(
        f"Finished generating reverse dependencies graph of {len(reverse_dependencies_graph)}"
    )
    return reverse_dependencies_graph


def gen_tier_one_deps_graph(
    dependencies_graph: dict[str, set[str]]
) -> tuple[dict[str, set[str]], set[str]]:
    # Below is a list of mods determined to be "tier one", in the sense that they
    # should be loaded first before any other regular mod. Tier one mods will have specific
    # load order needs within themselves, e.g. Harmony before core. There is no guarantee that
    # this list of mods is exhaustive, so we need to add any other mod that these mods depend on
    # into this list as well.
    # TODO: pull from a config

    logger.info("Generating dependencies graph for tier one mods")
    known_tier_one_mods = {
        "zetrith.prepatcher",
        "brrainz.harmony",
        "ludeon.rimworld",
        "ludeon.rimworld.royalty",
        "ludeon.rimworld.ideology",
        "ludeon.rimworld.biotech",
        "ludeon.rimworld.anomaly",
        "unlimitedhugs.hugslib",
    }
    tier_one_mods = set()
    for known_tier_one_mod in known_tier_one_mods:
        if known_tier_one_mod in dependencies_graph:
            # Some known tier one mods might not actually be active
            tier_one_mods.add(known_tier_one_mod)
            dependencies_set = get_dependencies_recursive(
                known_tier_one_mod, dependencies_graph
            )
            tier_one_mods.update(dependencies_set)
    logger.info(
        f"Recursively generated the following set of tier one mods: {tier_one_mods}"
    )
    tier_one_dependency_graph = {}
    for tier_one_mod in tier_one_mods:
        # Tier one mods will only ever reference other tier one mods in their dependencies graph
        tier_one_dependency_graph[tier_one_mod] = dependencies_graph[tier_one_mod]
    logger.info("Attached corresponding dependencies to every tier one mod, returning")
    return tier_one_dependency_graph, tier_one_mods


def get_dependencies_recursive(
    package_id: str, active_mods_dependencies: dict[str, set[str]]
) -> set[str]:
    dependencies_set = set()
    # Should always be true since all active ids get initialized with a set()
    if package_id in active_mods_dependencies:
        for dependency_id in active_mods_dependencies[package_id]:
            dependencies_set.add(dependency_id)  # Safe, as should refer to active id
            dependencies_set.update(  # Safe, as should refer to active ids
                get_dependencies_recursive(dependency_id, active_mods_dependencies)
            )
    return dependencies_set


def gen_tier_three_deps_graph(
    dependencies_graph: dict[str, set[str]],
    reverse_dependencies_graph: dict[str, set[str]],
    active_mods_uuids: set[str],
) -> tuple[dict[str, set[str]], set[str]]:
    # Below is a list of mods determined to be "tier three", in the sense that they
    # should be loaded after any other regular mod, potentially at the very end of the load order.
    # Tier three mods will have specific load order needs within themselves. There is no guarantee that
    # this list of mods is exhaustive, so we need to add any other mod that these mods depend on
    # into this list as well.
    # TODO: pull from a config
    # Cache MetadataManager instance
    metadata_manager = MetadataManager.instance()
    logger.info("Generating dependencies graph for tier three mods")
    known_tier_three_mods = {
        metadata_manager.internal_local_metadata[uuid].get("packageid")
        for uuid in active_mods_uuids
        if metadata_manager.internal_local_metadata[uuid].get("loadBottom")
    }
    known_tier_three_mods.update({"krkr.rocketman"})
    tier_three_mods = set()
    for known_tier_three_mod in known_tier_three_mods:
        if known_tier_three_mod in dependencies_graph:
            # Some known tier three mods might not actually be active
            tier_three_mods.add(known_tier_three_mod)
            rev_dependencies_set = get_reverse_dependencies_recursive(
                known_tier_three_mod, reverse_dependencies_graph
            )
            tier_three_mods.update(rev_dependencies_set)
    logger.info(
        f"Recursively generated the following set of tier three mods: {tier_three_mods}"
    )
    tier_three_dependency_graph: dict[str, set[str]] = {}
    for tier_three_mod in tier_three_mods:
        # Tier three mods may reference non-tier-three mods in their dependencies graph,
        # so it is necessary to trim here
        tier_three_dependency_graph[tier_three_mod] = set()
        for possible_add in dependencies_graph[tier_three_mod]:
            if possible_add in tier_three_mods:
                tier_three_dependency_graph[tier_three_mod].add(possible_add)
    logger.info(
        "Attached corresponding dependencies to every tier three mod, returning"
    )
    return tier_three_dependency_graph, tier_three_mods


def get_reverse_dependencies_recursive(
    package_id: str, active_mods_rev_dependencies: dict[str, set[str]]
) -> set[str]:
    reverse_dependencies_set = set()
    # Should always be true since all active ids get initialized with a set()
    if package_id in active_mods_rev_dependencies:
        for dependent_id in active_mods_rev_dependencies[package_id]:
            reverse_dependencies_set.add(
                dependent_id
            )  # Safe, as should refer to active id
            reverse_dependencies_set.update(  # Safe, as should refer to active ids
                get_reverse_dependencies_recursive(
                    dependent_id, active_mods_rev_dependencies
                )
            )
    return reverse_dependencies_set


def gen_tier_two_deps_graph(
    active_mods_uuids: set[str],
    active_mod_ids: list[str],
    tier_one_mods: set[str],
    tier_three_mods: set[str],
) -> dict[str, set[str]]:
    # Now, sort the rest of the mods while removing references to mods in tier one and tier three
    # First, get the dependency graph for tier two mods, minus all references to tier one
    # and tier three mods
    # Cache MetadataManager instance
    metadata_manager = MetadataManager.instance()
    logger.info("Generating dependencies graph for tier two mods")
    logger.info(
        "Stripping all references to tier one and tier three mods and their dependencies"
    )
    tier_two_dependency_graph = {}
    for uuid in active_mods_uuids:
        package_id = metadata_manager.internal_local_metadata[uuid]["packageid"]
        if package_id not in tier_one_mods and package_id not in tier_three_mods:
            dependencies = metadata_manager.internal_local_metadata[uuid].get(
                "loadTheseBefore"
            )
            stripped_dependencies = set()
            if dependencies:
                for dependency_id in dependencies:
                    # Remember, dependencies from all_mods can reference non-active mods
                    # Dependent[0] is required here as as dependency is a tuple of package_id, explicit_bool
                    if not isinstance(dependency_id, tuple):
                        logger.error(
                            f"Expected load order rule to be a tuple: [{dependency_id}]"
                        )
                    if (
                        dependency_id[0] not in tier_one_mods
                        and dependency_id[0] not in tier_three_mods
                        and dependency_id[0] in active_mod_ids
                    ):
                        stripped_dependencies.add(dependency_id[0])
            tier_two_dependency_graph[package_id] = stripped_dependencies
    logger.info("Generated tier two dependency graph, returning")
    return tier_two_dependency_graph

from loguru import logger

from app.utils.constants import KNOWN_TIER_ONE_MODS, KNOWN_TIER_ZERO_MODS
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


def gen_tier_zero_deps_graph(
    dependencies_graph: dict[str, set[str]],
) -> tuple[dict[str, set[str]], set[str]]:
    """
    Generate the dependency graph for tier zero mods, which are mods that should be loaded before any other mod.
    This includes mods that are required for the game to function properly,
    These are Core abd DLC's, which are essential.
    Mods in this list is limited, so we do not need to add any other mods to this list unless DLC's.
    Mods in list are only added to the list of known tier zero mods, using the loadBefore Core flag in the database,
    Or have the loadBefore Core flag set in their About.xml.
    This will only happens when the mod author specifically states that it is a tier zero mod.
    eg : Harmony, PrePatcher, Fishery, FasterGameLoading, LoadingProgress, VisualExceptions, etc.
    These mods are mostly well known and this only happens when the mod author specifically states that it is a tier zero mod.
    """
    logger.info("Generating dependencies graph for tier zero mods")
    known_tier_zero_mods = KNOWN_TIER_ZERO_MODS
    # Bug fix: if there are circular dependencies in tier zero mods
    # then an infinite loop happens here unless we keep track of what has
    # already been processed.
    processed_ids: set[str] = set()
    tier_zero_mods: set[str] = set()
    for known_tier_zero_mod in known_tier_zero_mods:
        if known_tier_zero_mod in dependencies_graph:
            # Some known tier zero mods might not actually be active
            tier_zero_mods.add(known_tier_zero_mod)
            dependencies_set = get_dependencies_recursive(
                known_tier_zero_mod, dependencies_graph, processed_ids
            )
            tier_zero_mods.update(dependencies_set)
    logger.info(
        f"Recursively generated the following set of tier one mods: {tier_zero_mods}"
    )
    tier_zero_dependency_graph = {}
    for tier_zero_mod in tier_zero_mods:
        # Tier zero mods will only ever reference other tier zero mods in their dependencies graph
        if tier_zero_mod in dependencies_graph:
            tier_zero_dependency_graph[tier_zero_mod] = dependencies_graph[
                tier_zero_mod
            ]
    logger.info("Attached corresponding dependencies to every tier zero mod, returning")
    return tier_zero_dependency_graph, tier_zero_mods


def gen_tier_one_deps_graph(
    dependencies_graph: dict[str, set[str]],
) -> tuple[dict[str, set[str]], set[str]]:
    """
    Generate the dependency graph for "tier one" mods, which are mods that are required by other mods to function properly,
    These are mods such as Framework mods.
    Tier one mods will have specific load order needs within themselves,
    This list of mods is exhaustive, so we need to add any other mod that these mods
    e.g. "Vanilla Backgrounds Expanded" before "Vaniila Expanded Framework".
    These can also be added to the list of known tier one mods, using the "loadTop" flag, in the database.
    """
    logger.info("Generating dependencies graph for tier one mods")
    metadata_manager = MetadataManager.instance()
    known_tier_one_mods = KNOWN_TIER_ONE_MODS
    # Add mods with loadTop set to True to known_tier_one_mods
    for uuid in metadata_manager.internal_local_metadata:
        if metadata_manager.internal_local_metadata[uuid].get("loadTop"):
            known_tier_one_mods.add(
                metadata_manager.internal_local_metadata[uuid]["packageid"]
            )
    # Bug fix: if there are circular dependencies in tier one mods
    # then an infinite loop happens here unless we keep track of what has
    # already been processed.
    processed_ids: set[str] = set()
    tier_one_mods: set[str] = set()
    for known_tier_one_mod in known_tier_one_mods:
        if known_tier_one_mod in dependencies_graph:
            # Some known tier one mods might not actually be active
            tier_one_mods.add(known_tier_one_mod)
            dependencies_set = get_dependencies_recursive(
                known_tier_one_mod, dependencies_graph, processed_ids
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
    package_id: str,
    active_mods_dependencies: dict[str, set[str]],
    processed_ids: set[str],
) -> set[str]:
    dependencies_set = set()
    # Should always be true since all active ids get initialized with a set()
    if package_id in active_mods_dependencies:
        for dependency_id in active_mods_dependencies[package_id]:
            if dependency_id not in processed_ids:
                processed_ids.add(dependency_id)
                dependencies_set.add(
                    dependency_id
                )  # Safe, as should refer to active id
                dependencies_set.update(  # Safe, as should refer to active ids
                    get_dependencies_recursive(
                        dependency_id, active_mods_dependencies, processed_ids
                    )
                )
    return dependencies_set


def gen_tier_three_deps_graph(
    dependencies_graph: dict[str, set[str]],
    reverse_dependencies_graph: dict[str, set[str]],
    active_mods_uuids: set[str],
) -> tuple[dict[str, set[str]], set[str]]:
    """
    Below is a list of mods determined to be "tier three",
    These should be loaded after any other regular mod, potentially at the very end of the load order.
    Tier three mods will have specific load order needs within themselves. There is no guarantee that his list of mods is exhaustive,
    So we need to add any other mod that these mods depend on into this list as well.
    eg. "RocketMan".
    These can also be added to the list of known tier one mods, using the "loadBottom" flag, in the database.
    """
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
    use_moddependencies_as_loadTheseBefore: bool = False,
) -> dict[str, set[str]]:
    """
    Generate the dependency graph for tier two mods, optionally treating About.xml dependencies as loadTheseBefore rules.
    When conflicts exist, explicit loadTheseBefore rules take precedence over inferred dependencies.

    Args:
        active_mods_uuids: Set of UUIDs for active mods.
        active_mod_ids: List of package IDs for active mods.
        tier_one_mods: Set of package IDs for tier one mods.
        tier_three_mods: Set of package IDs for tier three mods.
        use_moddependencies_as_loadTheseBefore: If True, treat About.xml dependencies as loadTheseBefore rules.

    Returns:
        Dependency graph for tier two mods.
    """
    # Cache MetadataManager instance
    metadata_manager = MetadataManager.instance()
    logger.info("Generating dependencies graph for tier two mods")
    logger.info(
        "Stripping all references to tier one and tier three mods and their dependencies"
    )

    # First pass: collect explicit loadTheseBefore rules (highest priority)
    explicit_rules = {}  # mod_id -> set of dependencies from loadTheseBefore

    # Second pass: collect inferred rules from dependencies (lower priority)
    inferred_rules = {}  # mod_id -> set of dependencies from About.xml dependencies

    for uuid in active_mods_uuids:
        package_id = metadata_manager.internal_local_metadata[uuid]["packageid"]
        if package_id not in tier_one_mods and package_id not in tier_three_mods:
            # Always collect explicit loadTheseBefore rules
            explicit_dependencies = set()
            loadTheseBefore = metadata_manager.internal_local_metadata[uuid].get(
                "loadTheseBefore"
            )
            if loadTheseBefore and isinstance(loadTheseBefore, (set, list)):
                for dep in loadTheseBefore:
                    if isinstance(dep, tuple):
                        if (
                            dep[0] not in tier_one_mods
                            and dep[0] not in tier_three_mods
                            and dep[0] in active_mod_ids
                        ):
                            explicit_dependencies.add(dep[0])
                    else:
                        logger.error(f"loadTheseBefore entry is not a tuple: [{dep}]")

            explicit_rules[package_id] = explicit_dependencies

            # Collect inferred rules from dependencies if enabled
            inferred_dependencies = set()
            if use_moddependencies_as_loadTheseBefore:
                about_dependencies = metadata_manager.internal_local_metadata[uuid].get(
                    "dependencies"
                )
                if about_dependencies and isinstance(about_dependencies, (set, list)):
                    for dep in about_dependencies:
                        # Accept both str and tuple for about_dependencies
                        dep_id = None
                        alt_ids: set[str] = set()
                        if isinstance(dep, str):
                            dep_id = dep
                        elif isinstance(dep, tuple):
                            dep_id = dep[0]
                            if (
                                len(dep) > 1
                                and isinstance(dep[1], dict)
                                and isinstance(dep[1].get("alternatives"), set)
                            ):
                                alt_ids = dep[1]["alternatives"]
                        else:
                            logger.error(
                                f"About.xml dependency is not a string or tuple: [{dep}]"
                            )
                            continue

                        # Prefer primary dep when present; optionally use alternatives
                        if (
                            dep_id in active_mod_ids
                            and dep_id not in tier_one_mods
                            and dep_id not in tier_three_mods
                        ):
                            inferred_dependencies.add(dep_id)
                        else:
                            # Only use alternatives if allowed by settings
                            if metadata_manager.settings_controller.settings.use_alternative_package_ids_as_satisfying_dependencies:
                                for alt in alt_ids:
                                    if (
                                        alt in active_mod_ids
                                        and alt not in tier_one_mods
                                        and alt not in tier_three_mods
                                    ):
                                        inferred_dependencies.add(alt)
                                        break

            inferred_rules[package_id] = inferred_dependencies

    # Resolve conflicts: explicit rules take precedence over inferred rules
    tier_two_dependency_graph = {}
    conflicts_ignored = 0

    for package_id in explicit_rules:
        final_dependencies = set()

        # Start with explicit dependencies (always included)
        final_dependencies.update(explicit_rules[package_id])

        # Add inferred dependencies only if they don't conflict with explicit rules
        for inferred_dep in inferred_rules.get(package_id, set()):
            # Check for conflict: does any explicit rule say inferred_dep should load before package_id?
            has_conflict = False

            # Check if inferred_dep has an explicit rule that conflicts
            if inferred_dep in explicit_rules:
                if package_id in explicit_rules[inferred_dep]:
                    # Conflict: explicit rule says inferred_dep -> package_id,
                    # but we're trying to add package_id -> inferred_dep
                    logger.warning(
                        f"Ignoring inferred dependency {package_id} -> {inferred_dep} "
                        f"due to explicit rule {inferred_dep} -> {package_id}"
                    )
                    has_conflict = True
                    conflicts_ignored += 1

            if not has_conflict:
                final_dependencies.add(inferred_dep)

        tier_two_dependency_graph[package_id] = final_dependencies

    if conflicts_ignored > 0:
        logger.info(
            f"Resolved {conflicts_ignored} conflicts by prioritizing explicit loadTheseBefore rules"
        )

    logger.info(
        "Generated tier two dependency graph with conflict resolution, returning"
    )
    return tier_two_dependency_graph

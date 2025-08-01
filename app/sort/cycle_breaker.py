from loguru import logger


def break_known_cycles(dependency_graph: dict[str, set[str]]) -> dict[str, set[str]]:
    """
    Break known cycles in the dependency graph by removing one edge in the cycle.
    Currently targets the cycle between 'vanillaexpanded.vtexe.facialanims' and 'reel.facialanims'.
    """
    mod_a = "vanillaexpanded.vtexe.facialanims"
    mod_b = "reel.facialanims"

    # Make a copy to avoid mutating the original graph
    new_graph = {k: set(v) for k, v in dependency_graph.items()}

    """if mod_a in new_graph and mod_b in new_graph[mod_a]:
        logger.info(
            f"Breaking cycle by removing dependency edge from {mod_a} to {mod_b}"
        )
        new_graph[mod_a].remove(mod_b)"""

    # Also check the reverse edge in case the cycle is bidirectional
    if mod_b in new_graph and mod_a in new_graph[mod_b]:
        logger.info(
            f"Breaking cycle by removing dependency edge from {mod_b} to {mod_a}"
        )
        new_graph[mod_b].remove(mod_a)

    return new_graph

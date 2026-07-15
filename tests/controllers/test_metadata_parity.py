import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Ensure steamworks can be imported even without the native binary
if "steamworks" not in sys.modules:
    sys.modules["steamworks"] = MagicMock()

from app.models.metadata.metadata_mediator import MetadataMediator
from app.models.metadata.metadata_structure import (
    AboutXmlMod,
    CompiledDependencyData,
    ListedMod,
)
from app.utils.constants import DEFAULT_USER_RULES

MOD_EXAMPLES = Path(__file__).parent.parent / "data" / "mod_examples"


@pytest.fixture
def parity_mediator(tmp_path: Path) -> MetadataMediator:
    """Create a MetadataMediator with test fixtures loaded."""
    user_rules_path = tmp_path / "userRules.json"
    user_rules_path.write_text(json.dumps(DEFAULT_USER_RULES))

    mediator = MetadataMediator(
        user_rules_path=user_rules_path,
        community_rules_path=None,
        steam_db_path=None,
        workshop_mods_path=MOD_EXAMPLES / "Steam",
        local_mods_path=MOD_EXAMPLES / "Local",
        game_path=MOD_EXAMPLES / "RimWorld",
    )
    mediator.refresh_metadata()
    return mediator


@pytest.fixture
def parity_mods(parity_mediator: MetadataMediator) -> dict[str, ListedMod]:
    """Load mods from existing test fixtures using the new system."""
    return parity_mediator.mods_metadata


def test_mods_are_parsed(parity_mods: dict[str, ListedMod]) -> None:
    """All expected mods are parsed from fixtures."""
    assert len(parity_mods) > 0

    # Extract package IDs from all parsed mods
    package_ids = {
        str(mod.package_id)
        for mod in parity_mods.values()
        if isinstance(mod, AboutXmlMod)
    }

    # Known mods that should be present
    assert "ludeon.rimworld" in package_ids  # Core
    assert "ludeon.rimworld.royalty" in package_ids  # Royalty DLC
    assert "ludeon.rimworld.biotech" in package_ids  # Biotech DLC
    assert "bs.fishery" in package_ids  # Fishery mod


def test_compile_produces_valid_graph(parity_mods: dict[str, ListedMod]) -> None:
    """compile() produces valid CompiledDependencyData."""
    compiled = CompiledDependencyData.build(parity_mods)

    assert isinstance(compiled, CompiledDependencyData)
    assert isinstance(compiled.deps_graph, dict)
    assert isinstance(compiled.rev_deps_graph, dict)
    assert isinstance(compiled.tier_zero_mods, set)
    assert isinstance(compiled.tier_one_mods, set)
    assert isinstance(compiled.tier_three_mods, set)
    assert isinstance(compiled.incompatibilities, dict)


def test_compile_reverse_graph_is_inverse_of_forward_graph(
    parity_mods: dict[str, ListedMod],
) -> None:
    """rev_deps_graph is the exact inverse of deps_graph."""
    compiled = CompiledDependencyData.build(parity_mods)

    # For every edge A -> B in deps_graph, there must be B -> A in rev_deps_graph
    for pkg_id, deps in compiled.deps_graph.items():
        for dep in deps:
            assert pkg_id in compiled.rev_deps_graph.get(dep, set()), (
                f"deps_graph has {pkg_id} -> {dep}, "
                f"but rev_deps_graph missing {dep} -> {pkg_id}"
            )

    # And vice versa
    for pkg_id, rev_deps in compiled.rev_deps_graph.items():
        for rev_dep in rev_deps:
            assert pkg_id in compiled.deps_graph.get(rev_dep, set()), (
                f"rev_deps_graph has {pkg_id} -> {rev_dep}, "
                f"but deps_graph missing {rev_dep} -> {pkg_id}"
            )


def test_compile_tier_zero_contains_core(
    parity_mods: dict[str, ListedMod],
) -> None:
    """tier_zero_mods contains ludeon.rimworld (Core)."""
    compiled = CompiledDependencyData.build(parity_mods)
    assert "ludeon.rimworld" in compiled.tier_zero_mods


def test_compile_cores_force_load_before_creates_dependency_edges(
    parity_mods: dict[str, ListedMod],
) -> None:
    """Core's forceLoadBefore creates dependency edges for DLCs."""
    # Core has forceLoadBefore: Ludeon.RimWorld.Ideology, Ludeon.RimWorld.Royalty
    # This means those DLCs should depend on Core (Core must load before them)
    compiled = CompiledDependencyData.build(parity_mods)

    # Royalty should depend on Core (because Core has forceLoadBefore Royalty)
    royalty_deps = compiled.deps_graph.get("ludeon.rimworld.royalty", set())
    assert "ludeon.rimworld" in royalty_deps, (
        "Royalty should depend on Core due to Core's forceLoadBefore"
    )

    # Core should be in the reverse dependency graph for Royalty
    core_rev_deps = compiled.rev_deps_graph.get("ludeon.rimworld", set())
    assert "ludeon.rimworld.royalty" in core_rev_deps, (
        "Core should show Royalty in reverse deps"
    )


def test_game_version_is_parsed(parity_mediator: MetadataMediator) -> None:
    """Game version is parsed from Version.txt."""
    # Check that Version.txt exists in fixtures
    version_file = MOD_EXAMPLES / "RimWorld" / "Version.txt"
    assert version_file.exists(), "Version.txt must exist in fixtures"

    # Game version should not be "Unknown"
    assert parity_mediator.game_version != "Unknown", (
        f"Game version should be parsed from {version_file}, "
        f"got: {parity_mediator.game_version}"
    )

    # Should match the expected version from the fixture
    assert "1.5" in parity_mediator.game_version, (
        f"Expected version to contain '1.5', got: {parity_mediator.game_version}"
    )


def test_compile_incompatibilities_are_bidirectional(
    parity_mods: dict[str, ListedMod],
) -> None:
    """Every incompatibility edge has a reverse edge."""
    compiled = CompiledDependencyData.build(parity_mods)

    for pkg_id, incompatibles in compiled.incompatibilities.items():
        for incompat in incompatibles:
            assert pkg_id in compiled.incompatibilities.get(incompat, set()), (
                f"incompatibilities has {pkg_id} -> {incompat}, "
                f"but missing reverse {incompat} -> {pkg_id}"
            )


def test_compile_declared_is_subset_of_incompatibilities(
    parity_mods: dict[str, ListedMod],
) -> None:
    """declared_incompatibilities is always a subset of incompatibilities."""
    compiled = CompiledDependencyData.build(parity_mods)

    for pkg_id, declared in compiled.declared_incompatibilities.items():
        full = compiled.incompatibilities.get(pkg_id, set())
        assert declared <= full, (
            f"declared_incompatibilities[{pkg_id}] has entries not in "
            f"incompatibilities: {declared - full}"
        )

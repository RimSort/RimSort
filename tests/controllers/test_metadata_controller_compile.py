import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Ensure steamworks can be imported even without the native binary
if "steamworks" not in sys.modules:
    sys.modules["steamworks"] = MagicMock()

from app.models.metadata.metadata_structure import (
    AboutXmlMod,
    BaseRules,
    CaseInsensitiveSet,
    CaseInsensitiveStr,
    CompiledDependencyData,
    DependencyMod,
    ListedMod,
    Rules,
)


def _make_mod(
    package_id: str,
    path: str,
    load_after: list[str] | None = None,
    load_before: list[str] | None = None,
    load_first: bool = False,
    load_last: bool = False,
    incompatible_with: list[str] | None = None,
) -> AboutXmlMod:
    """Helper to create a test mod with specified rules."""
    mod = AboutXmlMod()
    mod.package_id = CaseInsensitiveStr(package_id)
    mod.mod_path = Path(path)
    mod.about_rules = BaseRules(
        load_after=CaseInsensitiveSet(load_after or []),
        load_before=CaseInsensitiveSet(load_before or []),
        incompatible_with=CaseInsensitiveSet(incompatible_with or []),
    )
    mod.community_rules = Rules(load_first=load_first, load_last=load_last)
    mod.user_rules = Rules()
    return mod


def _compile(mods: dict[str, ListedMod], **kwargs: bool) -> CompiledDependencyData:
    """Shorthand for CompiledDependencyData.build."""
    return CompiledDependencyData.build(mods, **kwargs)


@pytest.fixture
def two_mods_load_after() -> dict[str, ListedMod]:
    """mod.a loads after mod.b."""
    return {
        "/mods/a": _make_mod("mod.a", "/mods/a", load_after=["mod.b"]),
        "/mods/b": _make_mod("mod.b", "/mods/b"),
    }


@pytest.fixture
def two_mods_load_before() -> dict[str, ListedMod]:
    """mod.a loads before mod.b."""
    return {
        "/mods/a": _make_mod("mod.a", "/mods/a", load_before=["mod.b"]),
        "/mods/b": _make_mod("mod.b", "/mods/b"),
    }


def test_compile_forward_and_reverse_deps_from_load_after(
    two_mods_load_after: dict[str, ListedMod],
) -> None:
    """load_after creates forward dep and reverse dep entries."""
    compiled = _compile(two_mods_load_after)
    assert "mod.b" in compiled.deps_graph.get("mod.a", set())
    assert "mod.a" in compiled.rev_deps_graph.get("mod.b", set())


def test_compile_forward_and_reverse_deps_from_load_before(
    two_mods_load_before: dict[str, ListedMod],
) -> None:
    """load_before: A loads before B → B depends on A."""
    compiled = _compile(two_mods_load_before)
    assert "mod.a" in compiled.deps_graph.get("mod.b", set())
    assert "mod.b" in compiled.rev_deps_graph.get("mod.a", set())


def test_compile_tier_classification() -> None:
    mods: dict[str, ListedMod] = {
        "/mods/fw": _make_mod("my.framework", "/mods/fw", load_first=True),
        "/mods/bot": _make_mod("my.bottom", "/mods/bot", load_last=True),
        "/mods/reg": _make_mod("my.regular", "/mods/reg"),
    }
    compiled = _compile(mods)

    assert "my.framework" in compiled.tier_one_mods
    assert "my.bottom" in compiled.tier_three_mods
    assert "my.regular" not in compiled.tier_one_mods
    assert "my.regular" not in compiled.tier_three_mods


def test_compile_does_not_mutate_known_tier_constants() -> None:
    from app.utils.constants import KNOWN_TIER_ONE_MODS

    original_size = len(KNOWN_TIER_ONE_MODS)
    mods: dict[str, ListedMod] = {
        "/mods/dyn": _make_mod("dynamic.framework", "/mods/dyn", load_first=True)
    }
    compiled = _compile(mods)

    assert "dynamic.framework" in compiled.tier_one_mods
    assert len(KNOWN_TIER_ONE_MODS) == original_size


def test_compile_incompatibility_only_includes_existing_mods() -> None:
    mods: dict[str, ListedMod] = {
        "/mods/a": _make_mod(
            "mod.a", "/mods/a", incompatible_with=["mod.b", "mod.nonexistent"]
        ),
        "/mods/b": _make_mod("mod.b", "/mods/b"),
    }
    compiled = _compile(mods)

    assert "mod.b" in compiled.incompatibilities.get("mod.a", set())
    assert "mod.nonexistent" not in compiled.incompatibilities.get("mod.a", set())


def test_compile_empty_mods() -> None:
    compiled = _compile({})
    assert compiled.deps_graph == {}
    assert compiled.rev_deps_graph == {}
    assert compiled.tier_three_mods == set()
    assert compiled.incompatibilities == {}
    assert compiled.declared_incompatibilities == {}


def test_compile_incompatibility_is_bidirectional() -> None:
    """When mod.a declares incompatibility with mod.b, mod.b also gets mod.a."""
    mods: dict[str, ListedMod] = {
        "/mods/a": _make_mod("mod.a", "/mods/a", incompatible_with=["mod.b"]),
        "/mods/b": _make_mod("mod.b", "/mods/b"),
    }
    compiled = _compile(mods)

    assert "mod.b" in compiled.incompatibilities.get("mod.a", set())
    assert "mod.a" in compiled.incompatibilities.get("mod.b", set())


def test_compile_declared_incompatibilities_tracked() -> None:
    """declared_incompatibilities tracks what each mod explicitly declared.

    mod.a declares incompat with mod.b -> mod.a has mod.b in
    declared_incompatibilities, but mod.b does NOT have mod.a.
    """
    mods: dict[str, ListedMod] = {
        "/mods/a": _make_mod("mod.a", "/mods/a", incompatible_with=["mod.b"]),
        "/mods/b": _make_mod("mod.b", "/mods/b"),
    }
    compiled = _compile(mods)

    assert "mod.b" in compiled.declared_incompatibilities.get("mod.a", set())
    assert "mod.a" not in compiled.declared_incompatibilities.get("mod.b", set())


def test_compile_mutual_incompatibility_both_declared() -> None:
    """When both mods declare each other incompatible, both appear everywhere."""
    mods: dict[str, ListedMod] = {
        "/mods/a": _make_mod("mod.a", "/mods/a", incompatible_with=["mod.b"]),
        "/mods/b": _make_mod("mod.b", "/mods/b", incompatible_with=["mod.a"]),
    }
    compiled = _compile(mods)

    # Both in incompatibilities (bidirectional)
    assert "mod.b" in compiled.incompatibilities.get("mod.a", set())
    assert "mod.a" in compiled.incompatibilities.get("mod.b", set())
    # Both in declared_incompatibilities (each declared it)
    assert "mod.b" in compiled.declared_incompatibilities.get("mod.a", set())
    assert "mod.a" in compiled.declared_incompatibilities.get("mod.b", set())


def test_compile_incompatibility_reverse_skips_nonexistent() -> None:
    """Reverse not added for mods not in the mod set."""
    mods: dict[str, ListedMod] = {
        "/mods/a": _make_mod("mod.a", "/mods/a", incompatible_with=["mod.nonexistent"]),
    }
    compiled = _compile(mods)

    assert compiled.incompatibilities == {}
    assert compiled.declared_incompatibilities == {}


def test_compile_nonexistent_deps_not_in_graph() -> None:
    mods: dict[str, ListedMod] = {
        "/mods/a": _make_mod("mod.a", "/mods/a", load_after=["nonexistent.mod"])
    }
    compiled = _compile(mods)
    assert "nonexistent.mod" not in compiled.deps_graph.get("mod.a", set())


def test_compile_skips_non_aboutxmlmod() -> None:
    listed_mod = ListedMod()
    listed_mod.mod_path = Path("/mods/invalid")
    compiled = _compile({"/mods/invalid": listed_mod})
    assert compiled.deps_graph == {}
    assert compiled.rev_deps_graph == {}


def test_compile_tier_zero_contains_known_mods() -> None:
    from app.utils.constants import KNOWN_TIER_ZERO_MODS

    compiled = _compile({})
    assert compiled.tier_zero_mods == KNOWN_TIER_ZERO_MODS


def test_compile_tier_zero_not_in_tier_one() -> None:
    """A mod in KNOWN_TIER_ZERO_MODS with load_first=True stays in tier_zero only."""
    mods: dict[str, ListedMod] = {
        "/mods/harmony": _make_mod("brrainz.harmony", "/mods/harmony", load_first=True)
    }
    compiled = _compile(mods)
    assert "brrainz.harmony" in compiled.tier_zero_mods
    assert "brrainz.harmony" not in compiled.tier_one_mods


def test_compile_bidirectional_chain() -> None:
    """Multi-hop chain: a→b→c produces correct forward and reverse graphs."""
    mods: dict[str, ListedMod] = {
        "/mods/a": _make_mod("mod.a", "/mods/a", load_after=["mod.b"]),
        "/mods/b": _make_mod("mod.b", "/mods/b", load_after=["mod.c"]),
        "/mods/c": _make_mod("mod.c", "/mods/c"),
    }
    compiled = _compile(mods)

    assert "mod.b" in compiled.deps_graph["mod.a"]
    assert "mod.c" in compiled.deps_graph["mod.b"]
    assert "mod.a" in compiled.rev_deps_graph["mod.b"]
    assert "mod.b" in compiled.rev_deps_graph["mod.c"]


def _make_dep_mods() -> dict[str, ListedMod]:
    """Create a fresh pair of mods where mod.a depends on mod.b."""
    mod_a = _make_mod("mod.a", "/mods/a")
    mod_a.about_rules.dependencies[CaseInsensitiveStr("mod.b")] = DependencyMod(
        package_id=CaseInsensitiveStr("mod.b")
    )
    return {"/mods/a": mod_a, "/mods/b": _make_mod("mod.b", "/mods/b")}


def test_compile_deps_as_load_order_on() -> None:
    """use_moddependencies_as_loadTheseBefore=True creates load edges from dependencies."""
    compiled = _compile(_make_dep_mods(), use_moddependencies_as_loadTheseBefore=True)
    assert "mod.b" in compiled.deps_graph.get("mod.a", set())


def test_compile_deps_as_load_order_off() -> None:
    """use_moddependencies_as_loadTheseBefore=False (default) does not create load edges."""
    compiled = _compile(_make_dep_mods(), use_moddependencies_as_loadTheseBefore=False)
    assert "mod.b" not in compiled.deps_graph.get("mod.a", set())


# --- Conflict resolution tests ---


def test_compile_explicit_wins_over_conflicting_inferred() -> None:
    """Explicit rule A->B blocks inferred B->A from creating a cycle.

    mod.a has explicit load_after mod.b (A loads after B, so A -> B edge).
    mod.b has dependency on mod.a (inferred: B loads after A, so B -> A edge).
    The inferred edge conflicts — it would create a cycle. It gets dropped.
    """
    mod_a = _make_mod("mod.a", "/mods/a", load_after=["mod.b"])
    mod_b = _make_mod("mod.b", "/mods/b")
    mod_b.about_rules.dependencies[CaseInsensitiveStr("mod.a")] = DependencyMod(
        package_id=CaseInsensitiveStr("mod.a")
    )
    mods: dict[str, ListedMod] = {"/mods/a": mod_a, "/mods/b": mod_b}
    compiled = _compile(mods, use_moddependencies_as_loadTheseBefore=True)

    # Explicit: mod.a depends on mod.b (mod.a -> mod.b edge)
    assert "mod.b" in compiled.deps_graph.get("mod.a", set())
    # Inferred: mod.b depends on mod.a would conflict — should be dropped
    assert "mod.a" not in compiled.deps_graph.get("mod.b", set())


def test_compile_non_conflicting_inferred_kept() -> None:
    """Inferred edges that don't conflict with explicit edges are kept."""
    mod_a = _make_mod("mod.a", "/mods/a")
    mod_a.about_rules.dependencies[CaseInsensitiveStr("mod.b")] = DependencyMod(
        package_id=CaseInsensitiveStr("mod.b")
    )
    mod_b = _make_mod("mod.b", "/mods/b")
    mod_c = _make_mod("mod.c", "/mods/c", load_after=["mod.a"])
    mods: dict[str, ListedMod] = {"/mods/a": mod_a, "/mods/b": mod_b, "/mods/c": mod_c}
    compiled = _compile(mods, use_moddependencies_as_loadTheseBefore=True)

    # Inferred: mod.a -> mod.b (no conflict)
    assert "mod.b" in compiled.deps_graph.get("mod.a", set())
    # Explicit: mod.c -> mod.a
    assert "mod.a" in compiled.deps_graph.get("mod.c", set())


def test_compile_overall_rules_not_mutated() -> None:
    """Calling compile with deps-as-load-order must NOT mutate mod.overall_rules."""
    mods = _make_dep_mods()
    mod_a = mods["/mods/a"]
    assert isinstance(mod_a, AboutXmlMod)

    original_load_after = set(mod_a.overall_rules.load_after)
    _compile(mods, use_moddependencies_as_loadTheseBefore=True)
    assert set(mod_a.overall_rules.load_after) == original_load_after


def test_compile_load_before_and_load_after_same_pair() -> None:
    """A loads_before B AND A loads_after B → both edges exist (cycle)."""
    mods: dict[str, ListedMod] = {
        "/mods/a": _make_mod(
            "mod.a", "/mods/a", load_before=["mod.b"], load_after=["mod.b"]
        ),
        "/mods/b": _make_mod("mod.b", "/mods/b"),
    }
    compiled = _compile(mods)
    assert "mod.b" in compiled.deps_graph.get("mod.a", set())
    assert "mod.a" in compiled.deps_graph.get("mod.b", set())


def test_compile_load_first_and_load_last_same_mod() -> None:
    """A mod with both load_first and load_last ends up in both tier sets."""
    mods: dict[str, ListedMod] = {
        "/mods/a": _make_mod("mod.a", "/mods/a", load_first=True, load_last=True),
    }
    compiled = _compile(mods)
    assert "mod.a" in compiled.tier_one_mods
    assert "mod.a" in compiled.tier_three_mods


def test_compile_many_mods_all_depend_on_one() -> None:
    """Fan-in: 20 mods all depending on one shared base mod."""
    base = _make_mod("mod.base", "/mods/base")
    mods: dict[str, ListedMod] = {"/mods/base": base}
    for i in range(20):
        mods[f"/mods/{i}"] = _make_mod(
            f"mod.{i}", f"/mods/{i}", load_after=["mod.base"]
        )
    compiled = _compile(mods)
    assert len(compiled.rev_deps_graph.get("mod.base", set())) == 20
    for i in range(20):
        assert "mod.base" in compiled.deps_graph.get(f"mod.{i}", set())


def test_compile_self_referencing_load_after() -> None:
    """A mod with load_after referencing itself → self-edge in graph."""
    mods: dict[str, ListedMod] = {
        "/mods/a": _make_mod("mod.a", "/mods/a", load_after=["mod.a"]),
    }
    compiled = _compile(mods)
    assert "mod.a" in compiled.deps_graph.get("mod.a", set())


# --- Alternative package ID tests ---


def _make_alt_dep_mods() -> dict[str, ListedMod]:
    """Create mods where mod.a depends on mod.primary with mod.alt as alternative.

    mod.primary is NOT in the returned dict — only mod.a and mod.alt are present.
    """
    mod_a = _make_mod("mod.a", "/mods/a")
    dep = DependencyMod(package_id=CaseInsensitiveStr("mod.primary"))
    dep.alternative_package_ids = {CaseInsensitiveStr("mod.alt")}
    mod_a.about_rules.dependencies[CaseInsensitiveStr("mod.primary")] = dep
    mod_alt = _make_mod("mod.alt", "/mods/alt")
    return {"/mods/a": mod_a, "/mods/alt": mod_alt}


def test_compile_alternative_package_id_used_when_primary_absent() -> None:
    """When primary dep is absent but an alternative is present, create the inferred edge."""
    compiled = _compile(
        _make_alt_dep_mods(),
        use_moddependencies_as_loadTheseBefore=True,
        use_alternative_package_ids=True,
    )
    assert "mod.alt" in compiled.deps_graph.get("mod.a", set())


def test_compile_alternative_package_id_not_used_when_disabled() -> None:
    """When the alternative setting is disabled, don't fall back to alternatives."""
    compiled = _compile(
        _make_alt_dep_mods(),
        use_moddependencies_as_loadTheseBefore=True,
        use_alternative_package_ids=False,
    )
    assert "mod.alt" not in compiled.deps_graph.get("mod.a", set())


def test_compile_primary_preferred_over_alternative() -> None:
    """When both primary and alternative are present, use the primary."""
    mod_a = _make_mod("mod.a", "/mods/a")
    dep = DependencyMod(package_id=CaseInsensitiveStr("mod.primary"))
    dep.alternative_package_ids = {CaseInsensitiveStr("mod.alt")}
    mod_a.about_rules.dependencies[CaseInsensitiveStr("mod.primary")] = dep
    mod_primary = _make_mod("mod.primary", "/mods/primary")
    mod_alt = _make_mod("mod.alt", "/mods/alt")
    mods: dict[str, ListedMod] = {
        "/mods/a": mod_a,
        "/mods/primary": mod_primary,
        "/mods/alt": mod_alt,
    }
    compiled = _compile(
        mods,
        use_moddependencies_as_loadTheseBefore=True,
        use_alternative_package_ids=True,
    )
    assert "mod.primary" in compiled.deps_graph.get("mod.a", set())
    assert "mod.alt" not in compiled.deps_graph.get("mod.a", set())


# --- Tier exclusion tests ---


def test_compile_inferred_edges_skip_tier_one_source() -> None:
    """Inferred deps are not added when the source mod is tier-one."""
    mod_fw = _make_mod("mod.framework", "/mods/fw", load_first=True)
    mod_fw.about_rules.dependencies[CaseInsensitiveStr("mod.dep")] = DependencyMod(
        package_id=CaseInsensitiveStr("mod.dep")
    )
    mod_dep = _make_mod("mod.dep", "/mods/dep")
    mods: dict[str, ListedMod] = {"/mods/fw": mod_fw, "/mods/dep": mod_dep}
    compiled = _compile(mods, use_moddependencies_as_loadTheseBefore=True)
    assert "mod.dep" not in compiled.deps_graph.get("mod.framework", set())


def test_compile_inferred_edges_skip_tier_one_target() -> None:
    """Inferred deps targeting tier-one mods are not added."""
    mod_a = _make_mod("mod.a", "/mods/a")
    mod_a.about_rules.dependencies[CaseInsensitiveStr("mod.framework")] = DependencyMod(
        package_id=CaseInsensitiveStr("mod.framework")
    )
    mod_fw = _make_mod("mod.framework", "/mods/fw", load_first=True)
    mods: dict[str, ListedMod] = {"/mods/a": mod_a, "/mods/fw": mod_fw}
    compiled = _compile(mods, use_moddependencies_as_loadTheseBefore=True)
    assert "mod.framework" not in compiled.deps_graph.get("mod.a", set())


def test_compile_inferred_edges_allow_tier_zero_target() -> None:
    """Inferred deps targeting tier-zero mods ARE allowed (matches old behavior)."""
    mod_a = _make_mod("mod.a", "/mods/a")
    mod_a.about_rules.dependencies[CaseInsensitiveStr("ludeon.rimworld")] = (
        DependencyMod(package_id=CaseInsensitiveStr("ludeon.rimworld"))
    )
    mod_core = _make_mod("ludeon.rimworld", "/mods/core")
    mods: dict[str, ListedMod] = {"/mods/a": mod_a, "/mods/core": mod_core}
    compiled = _compile(mods, use_moddependencies_as_loadTheseBefore=True)
    assert "ludeon.rimworld" in compiled.deps_graph.get("mod.a", set())

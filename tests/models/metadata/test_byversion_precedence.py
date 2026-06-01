"""Tests for ByVersion non-additive override behavior in create_base_rules.

When ``prefer_versioned=True`` (the default) and a ByVersion key matches the
target RimWorld version, the versioned values REPLACE (not extend) the
corresponding base values.  ``forceLoad*`` keys are always applied on top.
"""

from typing import Any

import pytest

from app.models.metadata.metadata_factory import create_base_rules


@pytest.fixture
def mod_data_with_both_base_and_versioned() -> dict[str, Any]:
    """Mod with base loadAfter AND a matching loadAfterByVersion."""
    return {
        "loadAfter": {"li": ["base.mod.a", "base.mod.b"]},
        "loadAfterByVersion": {
            "v1.5": {"li": ["versioned.mod.c"]},
        },
        "loadBefore": {"li": ["base.before.a"]},
        "loadBeforeByVersion": {
            "v1.5": {"li": ["versioned.before.b"]},
        },
        "incompatibleWith": {"li": ["base.incompat.a"]},
        "incompatibleWithByVersion": {
            "v1.5": {"li": ["versioned.incompat.b"]},
        },
        "modDependencies": {
            "li": [{"packageId": "base.dep.a", "displayName": "Base Dep A"}]
        },
        "modDependenciesByVersion": {
            "v1.5": {
                "li": [
                    {"packageId": "versioned.dep.b", "displayName": "Versioned Dep B"}
                ]
            },
        },
    }


# ── prefer_versioned=False ────────────────────────────────────────────


def test_byversion_off_uses_only_base(
    mod_data_with_both_base_and_versioned: dict[str, Any],
) -> None:
    """When prefer_versioned is False, ByVersion tags are ignored entirely."""
    rules = create_base_rules(
        mod_data_with_both_base_and_versioned,
        target_version="1.5.1234",
        prefer_versioned=False,
    )
    assert "base.mod.a" in rules.load_after
    assert "base.mod.b" in rules.load_after
    assert "versioned.mod.c" not in rules.load_after
    assert "base.before.a" in rules.load_before
    assert "versioned.before.b" not in rules.load_before


def test_byversion_off_ignores_dependencies(
    mod_data_with_both_base_and_versioned: dict[str, Any],
) -> None:
    """When prefer_versioned is False, modDependenciesByVersion is ignored."""
    rules = create_base_rules(
        mod_data_with_both_base_and_versioned,
        target_version="1.5.1234",
        prefer_versioned=False,
    )
    assert "base.dep.a" in rules.dependencies
    assert "versioned.dep.b" not in rules.dependencies


def test_byversion_off_ignores_incompatible(
    mod_data_with_both_base_and_versioned: dict[str, Any],
) -> None:
    """When prefer_versioned is False, incompatibleWithByVersion is ignored."""
    rules = create_base_rules(
        mod_data_with_both_base_and_versioned,
        target_version="1.5.1234",
        prefer_versioned=False,
    )
    assert "base.incompat.a" in rules.incompatible_with
    assert "versioned.incompat.b" not in rules.incompatible_with


# ── prefer_versioned=True (default) — version matches ─────────────────


def test_byversion_on_suppresses_base_when_version_matches(
    mod_data_with_both_base_and_versioned: dict[str, Any],
) -> None:
    """When prefer_versioned is True and version matches, use ONLY versioned, suppress base."""
    rules = create_base_rules(
        mod_data_with_both_base_and_versioned,
        target_version="1.5.1234",
        prefer_versioned=True,
    )
    # Versioned should be present
    assert "versioned.mod.c" in rules.load_after
    # Base should be suppressed
    assert "base.mod.a" not in rules.load_after
    assert "base.mod.b" not in rules.load_after


def test_byversion_on_suppresses_base_load_before(
    mod_data_with_both_base_and_versioned: dict[str, Any],
) -> None:
    """loadBefore base is suppressed when loadBeforeByVersion matches."""
    rules = create_base_rules(
        mod_data_with_both_base_and_versioned,
        target_version="1.5.1234",
        prefer_versioned=True,
    )
    assert "versioned.before.b" in rules.load_before
    assert "base.before.a" not in rules.load_before


def test_byversion_on_suppresses_base_incompatible(
    mod_data_with_both_base_and_versioned: dict[str, Any],
) -> None:
    """incompatibleWith base is suppressed when incompatibleWithByVersion matches."""
    rules = create_base_rules(
        mod_data_with_both_base_and_versioned,
        target_version="1.5.1234",
        prefer_versioned=True,
    )
    assert "versioned.incompat.b" in rules.incompatible_with
    assert "base.incompat.a" not in rules.incompatible_with


def test_byversion_on_suppresses_base_dependencies(
    mod_data_with_both_base_and_versioned: dict[str, Any],
) -> None:
    """modDependencies base is suppressed when modDependenciesByVersion matches."""
    rules = create_base_rules(
        mod_data_with_both_base_and_versioned,
        target_version="1.5.1234",
        prefer_versioned=True,
    )
    assert "versioned.dep.b" in rules.dependencies
    assert "base.dep.a" not in rules.dependencies


# ── Empty versioned key ───────────────────────────────────────────────


def test_byversion_on_empty_version_suppresses_base() -> None:
    """When prefer_versioned is True and versioned key is empty, suppress base (no requirements)."""
    mod_data = {
        "loadAfter": {"li": ["base.mod.a"]},
        "loadAfterByVersion": {
            "v1.5": {},  # Empty — means "no loadAfter for v1.5"
        },
    }
    rules = create_base_rules(
        mod_data, target_version="1.5.1234", prefer_versioned=True
    )
    assert "base.mod.a" not in rules.load_after
    assert len(rules.load_after) == 0


def test_byversion_on_empty_dependencies_suppresses_base() -> None:
    """Empty modDependenciesByVersion version means no deps for that version."""
    mod_data = {
        "modDependencies": {
            "li": [{"packageId": "base.dep.a", "displayName": "Base Dep A"}]
        },
        "modDependenciesByVersion": {
            "v1.5": {},  # Empty
        },
    }
    rules = create_base_rules(
        mod_data, target_version="1.5.1234", prefer_versioned=True
    )
    assert len(rules.dependencies) == 0


def test_byversion_on_empty_incompatible_suppresses_base() -> None:
    """Empty incompatibleWithByVersion version means no incompatibilities for that version."""
    mod_data = {
        "incompatibleWith": {"li": ["base.incompat.a"]},
        "incompatibleWithByVersion": {
            "v1.5": {},  # Empty
        },
    }
    rules = create_base_rules(
        mod_data, target_version="1.5.1234", prefer_versioned=True
    )
    assert len(rules.incompatible_with) == 0


# ── No matching version — falls back to base ─────────────────────────


def test_byversion_on_no_matching_version_falls_back_to_base() -> None:
    """When prefer_versioned is True but no matching version key, fall back to base."""
    mod_data = {
        "loadAfter": {"li": ["base.mod.a"]},
        "loadAfterByVersion": {
            "v1.4": {"li": ["old.version.mod"]},
        },
    }
    rules = create_base_rules(
        mod_data, target_version="1.5.1234", prefer_versioned=True
    )
    assert "base.mod.a" in rules.load_after
    assert "old.version.mod" not in rules.load_after


def test_byversion_on_no_matching_dependencies_falls_back() -> None:
    """modDependencies falls back to base when no version matches."""
    mod_data = {
        "modDependencies": {
            "li": [{"packageId": "base.dep.a", "displayName": "Base Dep A"}]
        },
        "modDependenciesByVersion": {
            "v1.4": {"li": [{"packageId": "old.dep", "displayName": "Old Dep"}]},
        },
    }
    rules = create_base_rules(
        mod_data, target_version="1.5.1234", prefer_versioned=True
    )
    assert "base.dep.a" in rules.dependencies
    assert "old.dep" not in rules.dependencies


# ── forceLoad always applied ──────────────────────────────────────────


def test_byversion_force_load_always_applied() -> None:
    """forceLoadAfter/forceLoadBefore are always applied regardless of prefer_versioned."""
    mod_data = {
        "loadAfter": {"li": ["base.mod.a"]},
        "loadAfterByVersion": {
            "v1.5": {"li": ["versioned.mod.c"]},
        },
        "forceLoadAfter": {"li": ["force.mod.x"]},
    }
    rules = create_base_rules(
        mod_data, target_version="1.5.1234", prefer_versioned=True
    )
    assert "versioned.mod.c" in rules.load_after
    assert "force.mod.x" in rules.load_after
    assert "base.mod.a" not in rules.load_after


def test_byversion_force_load_before_always_applied() -> None:
    """forceLoadBefore is always applied even when loadBeforeByVersion overrides base."""
    mod_data = {
        "loadBefore": {"li": ["base.before.a"]},
        "loadBeforeByVersion": {
            "v1.5": {"li": ["versioned.before.b"]},
        },
        "forceLoadBefore": {"li": ["force.before.x"]},
    }
    rules = create_base_rules(
        mod_data, target_version="1.5.1234", prefer_versioned=True
    )
    assert "versioned.before.b" in rules.load_before
    assert "force.before.x" in rules.load_before
    assert "base.before.a" not in rules.load_before


# ── Default parameter — backward compatibility ───────────────────────


def test_default_prefer_versioned_is_true() -> None:
    """Calling create_base_rules without prefer_versioned should default to True (override)."""
    mod_data = {
        "loadAfter": {"li": ["base.mod.a"]},
        "loadAfterByVersion": {
            "v1.5": {"li": ["versioned.mod.c"]},
        },
    }
    # Call WITHOUT prefer_versioned — should behave as prefer_versioned=True
    rules = create_base_rules(mod_data, target_version="1.5.1234")
    assert "versioned.mod.c" in rules.load_after
    assert "base.mod.a" not in rules.load_after


# ── Multi-version keys ───────────────────────────────────────────────


def test_byversion_multi_version_keys_only_matching() -> None:
    """When multiple version keys exist, only the matching one is used."""
    mod_data = {
        "loadAfter": {"li": ["base.mod.a"]},
        "loadAfterByVersion": {
            "v1.4": {"li": ["old.mod"]},
            "v1.5": {"li": ["current.mod"]},
        },
    }
    rules = create_base_rules(
        mod_data, target_version="1.5.1234", prefer_versioned=True
    )
    assert "current.mod" in rules.load_after
    assert "old.mod" not in rules.load_after
    assert "base.mod.a" not in rules.load_after


# ── Missing packageId sentinel ───────────────────────────────────────


def test_missing_packageid_gets_sentinel() -> None:
    """Mods with missing packageId get the sentinel value, not marked invalid."""
    from app.models.metadata.metadata_factory import create_about_mod
    from app.utils.constants import DEFAULT_MISSING_PACKAGEID

    mod_data = {
        "name": "Test Mod Without PackageId",
    }
    valid, mod = create_about_mod(mod_data, target_version="1.5.1234")
    assert mod.package_id == DEFAULT_MISSING_PACKAGEID
    assert mod.valid is True


def test_empty_packageid_gets_sentinel() -> None:
    """Mods with empty packageId get the sentinel value, not marked invalid."""
    from app.models.metadata.metadata_factory import create_about_mod
    from app.utils.constants import DEFAULT_MISSING_PACKAGEID

    mod_data = {
        "name": "Test Mod With Empty PackageId",
        "packageId": "   ",  # Only whitespace
    }
    valid, mod = create_about_mod(mod_data, target_version="1.5.1234")
    assert mod.package_id == DEFAULT_MISSING_PACKAGEID
    assert mod.valid is True


def test_non_string_packageid_gets_sentinel() -> None:
    """Mods with non-string packageId get the sentinel value, not marked invalid."""
    from app.models.metadata.metadata_factory import create_about_mod
    from app.utils.constants import DEFAULT_MISSING_PACKAGEID

    mod_data = {
        "name": "Test Mod With Non-String PackageId",
        "packageId": 12345,  # Integer instead of string
    }
    valid, mod = create_about_mod(mod_data, target_version="1.5.1234")
    assert mod.package_id == DEFAULT_MISSING_PACKAGEID
    assert mod.valid is True

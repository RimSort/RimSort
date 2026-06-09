"""Domain model for ordered mod lists.

Provides ModEntry (frozen identity handle), ModList (indexed ordered collection),
and ModListDiff (change detection) — bridging PATH and packageId identity systems.
No Qt dependency.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.metadata.metadata_structure import (
    CaseInsensitiveStr,
    ModType,
)


@dataclass(frozen=True)
class ModEntry:
    """Identifies a mod within an ordered list.

    :param path: Canonical identifier (filesystem path as string), matches
        MetadataController.mods_metadata keys.
    :param package_id: RimWorld package ID for dependency lookups and
        CompiledDependencyData bridging.
    :param config_id: Serialization identity written to ModsConfig.xml.
        Usually equals str(package_id) but includes '_steam' suffix for
        Workshop copies when duplicates exist.
    """

    path: str
    package_id: CaseInsensitiveStr
    config_id: str


def create_mod_entry(
    path: str,
    package_id: CaseInsensitiveStr,
    mod_type: ModType,
    has_duplicate: bool,
) -> ModEntry:
    """Build a ModEntry with correct config_id resolution.

    :param path: Filesystem path to the mod.
    :param package_id: The mod's package ID.
    :param mod_type: Source type of the mod.
    :param has_duplicate: Whether another copy of this packageId exists.
    :return: A frozen ModEntry.
    """
    if has_duplicate and mod_type == ModType.STEAM_WORKSHOP:
        config_id = f"{package_id}_steam"
    else:
        config_id = str(package_id)
    return ModEntry(path=path, package_id=package_id, config_id=config_id)

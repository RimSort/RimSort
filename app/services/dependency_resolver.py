"""Resolve Steam Workshop IDs for mod dependencies."""

import os
from dataclasses import dataclass
from typing import Literal
from xml.etree import ElementTree as ET
from xml.etree.ElementTree import Element

from app.controllers.metadata_controller import MetadataController
from app.models.metadata.metadata_structure import AboutXmlMod


@dataclass
class DepResolveResult:
    package_id: str
    workshop_id: str | None
    workshop_url: str | None
    source: Literal["steam_db", "about_xml", "none"]


def parse_workshop_id_from_url(url: str) -> str | None:
    """Extract a Steam Workshop ID from a dependency URL."""
    workshop_id: str | None = None
    if "?id=" in url:
        workshop_id = url.split("?id=")[1]
    elif "CommunityFilePage/" in url:
        workshop_id = url.split("CommunityFilePage/")[1]
    else:
        return None
    if "?" in workshop_id:
        workshop_id = workshop_id.split("?")[0]
    if "&" in workshop_id:
        workshop_id = workshop_id.split("&")[0]
    if "/" in workshop_id:
        workshop_id = workshop_id.split("/")[0]
    return workshop_id or None


def _find_workshop_id_in_deps(deps_node: Element, target_pkg_id: str) -> str | None:
    target = target_pkg_id.lower()
    for dep in deps_node.findall("li"):
        package_id = dep.find("packageId")
        if (
            package_id is not None
            and package_id.text is not None
            and package_id.text.lower() == target
        ):
            workshop_url = dep.find("steamWorkshopUrl")
            if workshop_url is not None and workshop_url.text is not None:
                return parse_workshop_id_from_url(workshop_url.text)
    return None


def _resolve_from_about_xml(
    metadata_controller: MetadataController,
    package_id: str,
    active_mod_paths: set[str],
) -> str | None:
    mods_metadata = metadata_controller.mods_metadata
    prefer_versioned = metadata_controller.settings.prefer_versioned_about_tags

    for active_path in active_mod_paths:
        active_mod = mods_metadata.get(active_path)
        if not active_mod or not active_mod.mod_path:
            continue
        about_path = os.path.join(str(active_mod.mod_path), "About", "About.xml")
        if not os.path.exists(about_path):
            continue
        try:
            root = ET.parse(about_path).getroot()
            used_versioned = False
            workshop_id: str | None = None

            if prefer_versioned:
                try:
                    major, minor = metadata_controller.game_version.split(".")[:2]
                    target_keys = [f"v{major}.{minor}", f"{major}.{minor}"]
                except Exception:
                    target_keys = []

                deps_by_version = root.find("modDependenciesByVersion")
                if deps_by_version is not None and target_keys:
                    candidate = None
                    for child in list(deps_by_version):
                        if child.tag in target_keys:
                            candidate = child
                            break
                    if candidate is None:
                        for child in list(deps_by_version):
                            for key in target_keys:
                                if child.tag.startswith(key):
                                    candidate = child
                                    break
                            if candidate is not None:
                                break
                    if candidate is not None:
                        used_versioned = True
                        lis = candidate.findall("li")
                        if lis:
                            workshop_id = _find_workshop_id_in_deps(
                                candidate, package_id
                            )

            if not used_versioned:
                deps = root.find("modDependencies")
                if deps is not None:
                    workshop_id = _find_workshop_id_in_deps(deps, package_id)

            if workshop_id:
                return workshop_id
        except Exception:
            continue
    return None


def resolve_dependency_workshop_id(
    metadata_controller: MetadataController,
    package_id: str,
    active_mod_paths: set[str],
) -> DepResolveResult:
    """Resolve a dependency package ID to a Steam Workshop ID when possible."""
    steam_db = metadata_controller.steam_db
    if steam_db is not None:
        for pfid, entry in steam_db.database.items():
            if entry.packageId.lower() == package_id.lower():
                url = f"https://steamcommunity.com/sharedfiles/filedetails/?id={pfid}"
                return DepResolveResult(
                    package_id=package_id,
                    workshop_id=pfid,
                    workshop_url=url,
                    source="steam_db",
                )

    workshop_id = _resolve_from_about_xml(
        metadata_controller, package_id, active_mod_paths
    )
    if workshop_id:
        url = f"https://steamcommunity.com/sharedfiles/filedetails/?id={workshop_id}"
        return DepResolveResult(
            package_id=package_id,
            workshop_id=workshop_id,
            workshop_url=url,
            source="about_xml",
        )

    return DepResolveResult(
        package_id=package_id,
        workshop_id=None,
        workshop_url=None,
        source="none",
    )


def build_dependencies_dialog_context(
    metadata_controller: MetadataController,
    active_mod_paths: set[str],
) -> tuple[
    dict[str, dict[str, set[str]]],
    dict[str, set[str]],
    dict[str, DepResolveResult],
]:
    """Build deps summary, missing deps, and workshop ID resolve map for the dialog."""
    mods_metadata = metadata_controller.mods_metadata

    active_ids: set[str] = set()
    for path in active_mod_paths:
        mod = mods_metadata.get(path)
        if mod and isinstance(mod, AboutXmlMod):
            active_ids.add(str(mod.package_id))

    deps_summary: dict[str, dict[str, set[str]]] = {}
    missing_deps: dict[str, set[str]] = {}

    all_local_package_ids: set[str] = set()
    for mod in mods_metadata.values():
        if isinstance(mod, AboutXmlMod):
            all_local_package_ids.add(str(mod.package_id))

    consider_alternatives = metadata_controller.settings.use_alternative_package_ids_as_satisfying_dependencies

    for path in active_mod_paths:
        mod = mods_metadata.get(path)
        if not isinstance(mod, AboutXmlMod):
            continue
        mod_id = str(mod.package_id)
        if not mod_id:
            continue

        dependencies = mod.overall_rules.dependencies
        if not dependencies:
            continue

        satisfied: set[str] = set()
        local: set[str] = set()
        download: set[str] = set()

        for dep_id_key, dep_mod in dependencies.items():
            dep_id = str(dep_id_key)
            alt_ids = {str(a) for a in dep_mod.alternative_package_ids}

            is_satisfied = dep_id in active_ids
            if not is_satisfied and consider_alternatives:
                is_satisfied = any(alt in active_ids for alt in alt_ids)

            if is_satisfied:
                satisfied.add(dep_id)
            else:
                is_local = dep_id in all_local_package_ids or (
                    consider_alternatives
                    and any(alt in all_local_package_ids for alt in alt_ids)
                )
                if is_local:
                    local.add(dep_id)
                else:
                    download.add(dep_id)

        deps_summary[mod_id] = {
            "satisfied": satisfied,
            "local": local,
            "download": download,
        }

        if local or download:
            missing_deps[mod_id] = local | download

    dep_resolve: dict[str, DepResolveResult] = {}
    for deps in deps_summary.values():
        for dep_id in deps.get("download", set()):
            dep_resolve[dep_id] = resolve_dependency_workshop_id(
                metadata_controller,
                dep_id,
                active_mod_paths,
            )

    return deps_summary, missing_deps, dep_resolve

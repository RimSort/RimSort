from app.controllers.metadata_controller import MetadataController
from app.models.divider import is_divider_uuid
from app.models.metadata.metadata_structure import AboutXmlMod


def list_active_mods(
    metadata_controller: MetadataController,
    active_paths: list[str],
) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for path in active_paths:
        if is_divider_uuid(path):
            continue
        mod = metadata_controller.get_mod(path)
        if isinstance(mod, AboutXmlMod):
            result.append(
                {
                    "package_id": str(mod.package_id),
                    "name": mod.name or str(mod.package_id),
                }
            )
    return result


def format_active_mods_context(
    metadata_controller: MetadataController,
    active_paths: list[str],
    *,
    limit: int = 200,
) -> str:
    active_mods = list_active_mods(metadata_controller, active_paths)
    total = len(active_mods)
    preview = active_mods[:limit]
    lines = [
        f"Active mods preview ({len(preview)} of {total} shown, package_id — name):"
    ]
    for mod in preview:
        lines.append(f"- {mod['package_id']}: {mod['name']}")
    if total > limit:
        lines.append(
            f"... and {total - limit} more active mods. "
            "Use search_installed_mods or describe_mod for details."
        )
    return "\n".join(lines)


def describe_mod(
    metadata_controller: MetadataController, package_id: str
) -> dict[str, str] | None:
    paths = metadata_controller.packageid_to_paths.get(package_id.lower(), set())
    for path in paths:
        mod = metadata_controller.get_mod(path)
        if isinstance(mod, AboutXmlMod):
            deps = ", ".join(str(d) for d in mod.overall_rules.dependencies.keys())
            return {
                "package_id": str(mod.package_id),
                "name": mod.name or str(mod.package_id),
                "description": (mod.description or "")[:500],
                "dependencies": deps,
            }
    return None


def search_mods(
    metadata_controller: MetadataController, query: str, limit: int = 20
) -> list[dict[str, str]]:
    q = query.lower()
    matches: list[dict[str, str]] = []
    for mod in metadata_controller.mods_metadata.values():
        if not isinstance(mod, AboutXmlMod):
            continue
        name = (mod.name or "").lower()
        pid = str(mod.package_id).lower()
        if q in name or q in pid:
            matches.append({"package_id": str(mod.package_id), "name": mod.name or pid})
        if len(matches) >= limit:
            break
    return matches

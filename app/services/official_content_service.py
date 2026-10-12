"""Read-only diagnostics for missing official game content."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

from app.models.metadata.metadata_structure import AboutXmlMod, ListedMod, ModType
from app.services.game_layout_service import resolve_game_layout
from app.utils.constants import RIMWORLD_PACKAGE_IDS

_OFFICIAL_PACKAGE_IDS = frozenset(RIMWORLD_PACKAGE_IDS)


@dataclass(frozen=True)
class OfficialContentIssues:
    missing_package_ids: tuple[str, ...]
    config_unreadable: bool
    data_path: Path | None

    @property
    def has_issues(self) -> bool:
        return bool(self.missing_package_ids) or self.config_unreadable


def _read_enabled_official_ids(path: Path) -> tuple[set[str], bool]:
    try:
        if not path.exists():
            return set(), False
        root = ElementTree.parse(path).getroot()
        active = root.find("activeMods")
        if root.tag != "ModsConfigData" or active is None:
            return set(), True
        package_ids: set[str] = set()
        for item in active:
            if item.tag != "li" or not item.text or not item.text.strip() or len(item):
                return set(), True
            package_id = item.text.strip().casefold().removesuffix("_steam")
            if package_id in _OFFICIAL_PACKAGE_IDS:
                package_ids.add(package_id)
        return package_ids, False
    except (OSError, ElementTree.ParseError, ValueError):
        return set(), True


def find_official_content_issues(
    mods: Mapping[str, ListedMod], game_path: Path, mods_config_path: Path
) -> OfficialContentIssues:
    """Compare enabled official IDs with valid metadata from the selected Data root."""
    layout = resolve_game_layout(game_path)
    discovered: set[str] = set()
    if layout is not None:
        for mod in mods.values():
            if (
                not isinstance(mod, AboutXmlMod)
                or not mod.valid
                or mod.mod_type != ModType.LUDEON
            ):
                continue
            package_id = str(mod.package_id).casefold()
            if package_id not in _OFFICIAL_PACKAGE_IDS or mod.mod_path is None:
                continue
            try:
                if mod.mod_path.is_dir() and mod.mod_path.parent.samefile(
                    layout.data_path
                ):
                    discovered.add(package_id)
            except OSError:
                continue
    enabled, unreadable = _read_enabled_official_ids(mods_config_path)
    missing = ({"ludeon.rimworld"} | enabled) - discovered
    return OfficialContentIssues(
        tuple(sorted(missing)),
        unreadable,
        layout.data_path if layout is not None else None,
    )

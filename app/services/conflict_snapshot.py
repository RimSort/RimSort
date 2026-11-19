from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QCoreApplication, Qt

if TYPE_CHECKING:
    from app.controllers.metadata_controller import MetadataController
    from app.views.mods_panel import ModListWidget


@dataclass(frozen=True)
class InputIssue:
    message: str
    path: str | None


@dataclass(frozen=True)
class ScanSnapshot:
    mod_paths: tuple[str, ...]
    game_version: str | None
    instance_id: str
    issues: tuple[InputIssue, ...]


def snapshot_active_mods(
    active_list: ModListWidget,
    metadata_controller: MetadataController,
    instance_id: str,
) -> ScanSnapshot:
    """Capture the ordered live list, recording rows that cannot be scanned."""
    paths: list[str] = []
    issues: list[InputIssue] = []
    translate = QCoreApplication.translate
    for row in active_list.get_all_mod_list_items():
        data = row.data(Qt.ItemDataRole.UserRole)
        try:
            key = data["path"]
        except TypeError, KeyError, AttributeError:
            key = None
        if not isinstance(key, str) or not key:
            issues.append(
                InputIssue(translate("ConflictSnapshot", "Mod row has no path"), None)
            )
            continue
        mod = metadata_controller.get_mod(key)
        if mod is None or mod.mod_path is None:
            issues.append(
                InputIssue(
                    translate("ConflictSnapshot", "Mod metadata is unavailable"), key
                )
            )
            continue
        try:
            path = Path(mod.mod_path).resolve(strict=True)
            if not path.is_dir():
                raise NotADirectoryError(path)
            resolved = str(path)
            resolved.encode("utf-8", errors="strict")
        except OSError, RuntimeError, ValueError, UnicodeEncodeError:
            issues.append(
                InputIssue(
                    translate(
                        "ConflictSnapshot", "Mod path is not a usable UTF-8 directory"
                    ),
                    key,
                )
            )
            continue
        paths.append(resolved)

    version = metadata_controller.game_version.strip()
    return ScanSnapshot(
        mod_paths=tuple(paths),
        game_version=None
        if not version or version.casefold() == "unknown"
        else version,
        instance_id=instance_id,
        issues=tuple(issues),
    )

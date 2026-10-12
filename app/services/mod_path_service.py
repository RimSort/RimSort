"""Service for resolving mod folder paths from an Instance model."""

from pathlib import Path

from app.models.instance import Instance
from app.services.game_layout_service import resolve_game_layout


def get_mod_paths(instance: Instance) -> list[str]:
    """Return validated game Data, local and workshop search locations."""
    layout = (
        resolve_game_layout(Path(instance.game_folder))
        if instance.game_folder
        else None
    )
    paths = [str(layout.data_path)] if layout is not None else []
    paths.extend(p for p in (instance.local_folder, instance.workshop_folder) if p)
    return paths


def resolve_data_source(instance: Instance, path: str) -> str | None:
    """Identify the source of a mod from its containing directory."""
    parent = Path(path).parent
    layout = (
        resolve_game_layout(Path(instance.game_folder))
        if instance.game_folder
        else None
    )
    if layout is not None and parent == layout.data_path:
        return "expansion"
    for name, folder in (
        ("local", instance.local_folder),
        ("workshop", instance.workshop_folder),
    ):
        if folder and parent == Path(folder):
            return name
    return None

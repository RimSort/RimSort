"""Service for resolving mod folder paths from an Instance model."""

from pathlib import Path

from app.models.instance import Instance


def get_mod_paths(instance: Instance) -> list[str]:
    """Get the mod paths for the given instance.

    Returns the game Data folder, local folder, and workshop folder
    as string paths.
    """
    return [
        str(Path(instance.game_folder) / "Data"),
        str(Path(instance.local_folder)),
        str(Path(instance.workshop_folder)),
    ]


def resolve_data_source(instance: Instance, path: str) -> str | None:
    """Resolve the data source for the provided path string.

    :param instance: The active game instance
    :param path: The file path to resolve
    :return: ``"expansion"``, ``"local"``, ``"workshop"``, or ``None``
    """
    sanitized_path = Path(path)
    game_data = Path(instance.game_folder) / "Data"
    local = Path(instance.local_folder)
    workshop = Path(instance.workshop_folder)

    if sanitized_path.parent == game_data:
        return "expansion"
    elif sanitized_path.parent == local:
        return "local"
    elif sanitized_path.parent == workshop:
        return "workshop"
    return None

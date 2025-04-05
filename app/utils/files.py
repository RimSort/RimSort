import os
from pathlib import Path


def subfolder_contains_candidate_path(
    subfolder: Path | None,
    candidate_directory: Path | str | None,
    glob: str,
    case_sensitive: bool = False,
) -> bool:
    if subfolder is None:
        return False

    if candidate_directory is None:
        candidate_directory = ""

    subfolder_paths = [subfolder]
    subfolder_paths.extend(
        [
            subfolder / folder
            for folder in os.listdir(subfolder)
            if os.path.isdir(str(subfolder / folder))
        ]
    )

    for subfolder_path in subfolder_paths:
        candidate_path = subfolder_path / candidate_directory
        if candidate_path.exists():
            # Check for .dll or .DLL files in the Assemblies folder using glob
            if any(candidate_path.glob(glob, case_sensitive=case_sensitive)):
                return True

    return False

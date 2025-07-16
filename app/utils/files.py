import fnmatch
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def subfolder_contains_candidate_path(
    subfolder: Path | None,
    candidate_directory: Path | str | None,
    glob_pattern: str,
    case_sensitive: bool = False,
) -> bool:
    """
    Check if the given subfolder or its immediate subfolders contain the candidate directory
    with files matching the glob pattern.

    :param subfolder: The base subfolder to check
    :param candidate_directory: The candidate directory name or path relative to subfolder
    :param glob_pattern: The glob pattern to match files (e.g., '*.dll')
    :param case_sensitive: Whether the glob matching should be case sensitive (not supported by pathlib.glob)
    :return: True if matching files are found, False otherwise
    """
    if subfolder is None:
        return False

    if candidate_directory is None:
        candidate_directory = ""

    subfolder_paths = [subfolder]
    try:
        subfolder_paths.extend(
            [subfolder / folder for folder in subfolder.iterdir() if folder.is_dir()]
        )
    except Exception:
        # Could not list subdirectories, return False
        return False

    def check_subfolder(subfolder_path: Path) -> bool:
        candidate_path = subfolder_path / candidate_directory
        if candidate_path.exists() and candidate_path.is_dir():
            if case_sensitive:
                return any(candidate_path.glob(glob_pattern))
            else:
                for file_path in candidate_path.glob(glob_pattern):
                    if fnmatch.fnmatch(file_path.name.lower(), glob_pattern.lower()):
                        return True
        return False

    with ThreadPoolExecutor(max_workers=4) as executor:  # Limit to 4 threads
        results = executor.map(check_subfolder, subfolder_paths)
        return any(results)

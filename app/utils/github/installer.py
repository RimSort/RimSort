"""GitHub mod installer: zip extraction, unwrap heuristic, and backup/restore.

Provides file-system operations for installing GitHub-hosted RimWorld mods:

- :func:`unwrap_extracted_mod` — Detect and unwrap the single-directory wrapper
  that most GitHub release ZIPs create (``ModName/About/About.xml`` →
  ``About/About.xml``).
- :class:`GitHubInstaller` — Static methods for zip extraction (with zip-slip
  protection), HEAD cloning via ``git_utils``, and backup/restore for safe
  version switching.
"""

import os
import shutil
import tempfile
from enum import Enum
from pathlib import Path
from zipfile import ZipFile

from loguru import logger


class UnwrapResult(Enum):
    """Outcome of attempting to unwrap an extracted mod directory."""

    UNWRAPPED = "unwrapped"
    ALREADY_CORRECT = "already_correct"
    NO_ABOUT_XML = "no_about_xml"


def _has_about_xml(directory: Path) -> bool:
    """Check whether *directory* contains an ``About/About.xml`` (case-insensitive).

    :param directory: Directory to inspect.
    :return: ``True`` if an ``About.xml`` file is found inside an ``About``
        sub-directory (matching is case-insensitive for both the folder and
        the file name).
    """
    about_dir: Path | None = None

    # Try exact-case first (common), then fall back to case-insensitive scan.
    candidate = directory / "About"
    if candidate.is_dir():
        about_dir = candidate
    else:
        for item in directory.iterdir():
            if item.is_dir() and item.name.lower() == "about":
                about_dir = item
                break

    if about_dir is None:
        return False

    for item in about_dir.iterdir():
        if item.name.lower() == "about.xml":
            return True
    return False


def unwrap_extracted_mod(target_dir: Path) -> UnwrapResult:
    """Unwrap a single-directory wrapper around a mod if necessary.

    Many GitHub release ZIPs contain a single top-level directory that wraps
    the actual mod content (e.g. ``ModName-1.2.3/About/About.xml``).  This
    function detects that pattern and moves the contents up one level so that
    the ``About/`` folder sits directly inside *target_dir*.

    :param target_dir: The directory to inspect / unwrap.
    :return: An :class:`UnwrapResult` describing what happened.
    """
    # If About/About.xml is already at the root level, nothing to do.
    if _has_about_xml(target_dir):
        return UnwrapResult.ALREADY_CORRECT

    # Check for a single sub-directory that itself contains About/About.xml.
    top_level = [item for item in target_dir.iterdir() if item.is_dir()]
    if len(top_level) == 1 and _has_about_xml(top_level[0]):
        wrapper = top_level[0]
        temp_dir = target_dir.parent / f"{target_dir.name}._unwrap_temp"
        shutil.move(str(wrapper), str(temp_dir))

        for item in temp_dir.iterdir():
            dest = target_dir / item.name
            shutil.move(str(item), str(dest))

        shutil.rmtree(str(temp_dir), ignore_errors=True)
        return UnwrapResult.UNWRAPPED

    return UnwrapResult.NO_ABOUT_XML


class GitHubInstaller:
    """Static helpers for installing, updating, and rolling back GitHub mods."""

    # ------------------------------------------------------------------
    # Zip extraction
    # ------------------------------------------------------------------

    @staticmethod
    def extract_release_zip(zip_path: str, target_dir: str) -> UnwrapResult:
        """Extract a release ZIP to *target_dir* with zip-slip protection.

        After extraction the directory is passed through
        :func:`unwrap_extracted_mod` so the caller always gets a flat mod
        layout with ``About/About.xml`` at the root.

        :param zip_path: Path to the ZIP file.
        :param target_dir: Destination directory (created if absent).
        :return: The :class:`UnwrapResult` from the unwrap step.
        """
        target = Path(target_dir)
        target.mkdir(parents=True, exist_ok=True)

        real_target = os.path.realpath(str(target))
        with ZipFile(zip_path) as zf:
            for info in zf.infolist():
                dst = os.path.realpath(os.path.join(str(target), info.filename))
                if not (dst.startswith(real_target + os.sep) or dst == real_target):
                    logger.warning(f"Zip slip detected, skipping: {info.filename}")
                    continue
                if info.is_dir():
                    os.makedirs(dst, exist_ok=True)
                else:
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    with zf.open(info) as src, open(dst, "wb") as out:
                        shutil.copyfileobj(src, out)

        return unwrap_extracted_mod(target)

    @staticmethod
    def download_and_extract_release(
        asset_url: str, asset_name: str, target_dir: str
    ) -> UnwrapResult:
        """Download a release asset ZIP and extract it to *target_dir*.

        :param asset_url: Direct download URL for the release asset.
        :param asset_name: File name for the downloaded ZIP.
        :param target_dir: Destination directory for extraction.
        :return: The :class:`UnwrapResult` from the unwrap step.
        """
        from app.utils import (
            http,  # Deferred: hot-path download, avoid import at module scope
        )

        with tempfile.TemporaryDirectory() as tmp:
            zip_path = os.path.join(tmp, asset_name)
            response = http.get(asset_url, stream=True, timeout=300)
            response.raise_for_status()

            with open(zip_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            return GitHubInstaller.extract_release_zip(zip_path, target_dir)

    # ------------------------------------------------------------------
    # HEAD clone (via existing git_utils)
    # ------------------------------------------------------------------

    @staticmethod
    def install_head(repo_url: str, target_dir: str) -> tuple[bool, str | None]:
        """Shallow-clone a repository HEAD into *target_dir*.

        Uses the project's existing :mod:`app.utils.git_utils` infrastructure.
        Imports are deferred to avoid pulling in Qt/PySide6 at module load
        time.

        :param repo_url: HTTPS clone URL for the repository.
        :param target_dir: Destination path for the clone.
        :return: ``(success, short_sha)`` — the short SHA of HEAD on success,
            or ``(False, None)`` on failure.
        """
        # Deferred imports: git_utils imports PySide6 through its dependency
        # chain, and pygit2 is heavy.  Keep them out of module scope.
        from app.utils import git_utils
        from app.utils.git_utils import GitOperationConfig

        config = GitOperationConfig.create_silent()
        repo, result = git_utils.git_clone(
            repo_url=repo_url,
            repo_path=target_dir,
            depth=1,
            config=config,
        )
        if repo is not None:
            git_utils.git_cleanup(repo)

        if result.is_successful():
            from app.utils.pygit2_loader import pygit2

            commit_info = git_utils.git_get_commit_info(pygit2.Repository(target_dir))
            sha = commit_info["short_id"] if commit_info else None
            return True, sha
        return False, None

    # ------------------------------------------------------------------
    # Backup / restore for safe version switching
    # ------------------------------------------------------------------

    @staticmethod
    def backup_mod(mod_path: Path) -> Path:
        """Move a mod directory to a ``.rimsort_backup`` sibling.

        If a previous backup already exists at the same location it is
        removed first.

        :param mod_path: Path to the mod directory.
        :return: Path to the backup directory.
        """
        backup_path = mod_path.parent / f"{mod_path.name}.rimsort_backup"
        if backup_path.exists():
            shutil.rmtree(str(backup_path))
        shutil.move(str(mod_path), str(backup_path))
        return backup_path

    @staticmethod
    def restore_backup(backup_path: Path, mod_path: Path) -> None:
        """Restore a backup, replacing any current mod directory.

        :param backup_path: Path to the ``.rimsort_backup`` directory.
        :param mod_path: Destination path (the original mod location).
        """
        if mod_path.exists():
            shutil.rmtree(str(mod_path))
        shutil.move(str(backup_path), str(mod_path))

    @staticmethod
    def delete_backup(backup_path: Path) -> None:
        """Delete a backup directory if it exists.

        :param backup_path: Path to the ``.rimsort_backup`` directory.
        """
        if backup_path.exists():
            shutil.rmtree(str(backup_path))

    @staticmethod
    def check_stale_backup(mod_path: Path) -> Path | None:
        """Check whether a stale backup exists for a mod.

        A stale backup indicates a previous install/update was interrupted.

        :param mod_path: Path to the mod directory.
        :return: Path to the backup if it exists, otherwise ``None``.
        """
        backup_path = mod_path.parent / f"{mod_path.name}.rimsort_backup"
        if backup_path.exists():
            return backup_path
        return None

"""QThread workers for non-blocking GitHub mod operations.

Follows the ``BaseGitWorker(QThread)`` pattern from ``app/utils/git_worker.py``.
Each worker emits progress/finished/error signals so the UI stays responsive.
"""

from pathlib import Path

from loguru import logger
from PySide6.QtCore import QThread, Signal
from sqlalchemy.orm import sessionmaker

from app.utils.github.installer import GitHubInstaller, UnwrapResult
from app.utils.github.provider import GitHubProvider, ReleaseAsset, ReleaseInfo


class GitHubInstallWorker(QThread):
    """Download and install a mod from GitHub (release asset or HEAD clone)."""

    progress = Signal(str)
    finished = Signal(bool, str, str)  # success, message, mod_path

    def __init__(
        self,
        owner_repo: str,
        release: ReleaseInfo | None,
        asset: ReleaseAsset | None,
        repo_url: str,
        target_dir: str,
    ) -> None:
        super().__init__()
        self._owner_repo = owner_repo
        self._release = release
        self._asset = asset
        self._repo_url = repo_url
        self._target_dir = target_dir

    def run(self) -> None:
        try:
            if self._release and self._asset:
                self.progress.emit(f"Downloading {self._asset.name}...")
                result = GitHubInstaller.download_and_extract_release(
                    self._asset.download_url, self._asset.name, self._target_dir
                )
                if result == UnwrapResult.NO_ABOUT_XML:
                    logger.warning("Extracted mod has no About.xml")
                self.finished.emit(True, self._release.tag, self._target_dir)
            else:
                self.progress.emit(f"Cloning {self._owner_repo}...")
                success, sha = GitHubInstaller.install_head(
                    self._repo_url, self._target_dir
                )
                if success:
                    self.finished.emit(
                        True, f"HEAD@{sha or 'unknown'}", self._target_dir
                    )
                else:
                    self.finished.emit(False, "Clone failed", self._target_dir)
        except Exception as e:
            logger.error(f"GitHub install failed: {e}")
            self.finished.emit(False, str(e), self._target_dir)


class GitHubVersionSwitchWorker(QThread):
    """Replace an installed mod with a different release or HEAD."""

    progress = Signal(str)
    finished = Signal(bool, str, str)  # success, new_version, mod_path

    def __init__(
        self,
        mod_path: str,
        owner_repo: str,
        repo_url: str,
        target_release: ReleaseInfo | None,
        target_asset: ReleaseAsset | None,
    ) -> None:
        super().__init__()
        self._mod_path = Path(mod_path)
        self._owner_repo = owner_repo
        self._repo_url = repo_url
        self._target_release = target_release
        self._target_asset = target_asset

    def run(self) -> None:
        backup_path: Path | None = None
        try:
            self.progress.emit("Backing up current version...")
            backup_path = GitHubInstaller.backup_mod(self._mod_path)

            self.progress.emit("Installing new version...")
            if self._target_release and self._target_asset:
                GitHubInstaller.download_and_extract_release(
                    self._target_asset.download_url,
                    self._target_asset.name,
                    str(self._mod_path),
                )
                new_version = self._target_release.tag
            else:
                success, sha = GitHubInstaller.install_head(
                    self._repo_url, str(self._mod_path)
                )
                if not success:
                    raise RuntimeError("HEAD clone failed")
                new_version = f"HEAD@{sha or 'unknown'}"

            GitHubInstaller.delete_backup(backup_path)
            self.finished.emit(True, new_version, str(self._mod_path))

        except Exception as e:
            logger.error(f"Version switch failed for {self._owner_repo}: {e}")
            if backup_path and backup_path.exists():
                self.progress.emit("Restoring backup...")
                GitHubInstaller.restore_backup(backup_path, self._mod_path)
            self.finished.emit(False, str(e), str(self._mod_path))


class GitHubUpdateCheckWorker(QThread):
    """Background check for available updates across all tracked GitHub mods."""

    finished = Signal(list)  # list of UpdateAvailable
    error = Signal(str)

    def __init__(
        self,
        provider: GitHubProvider,
        instance_session_factory: sessionmaker,  # type: ignore[type-arg]
        check_interval_hours: int = 24,
    ) -> None:
        super().__init__()
        self._provider = provider
        self._session_factory = instance_session_factory
        self._check_interval = check_interval_hours

    def run(self) -> None:
        # Deferred import to avoid circular dependency:
        # updater -> models -> ... -> worker -> updater
        from app.utils.github.updater import check_for_updates

        try:
            session = self._session_factory()
            try:
                updates = check_for_updates(
                    instance_session=session,
                    provider=self._provider,
                    check_interval_hours=self._check_interval,
                )
                self.finished.emit(updates)
            finally:
                session.close()
        except Exception as e:
            logger.error(f"GitHub update check failed: {e}")
            self.error.emit(str(e))

from pathlib import Path
from typing import Dict, List, Optional, Tuple

from loguru import logger
from PySide6.QtCore import QObject, QRunnable, QThread, Signal, Slot

from app.utils import git_utils
from app.utils.git_utils import GitCloneResult


class GitCloneWorker(QThread):
    """Worker thread for git clone operations"""

    # Signals
    finished = Signal(bool, str, str)  # success, message, path
    progress = Signal(str)  # status message
    error = Signal(str)  # error message

    def __init__(
        self,
        repo_url: str,
        repo_path: str | Path,
        checkout_branch: Optional[str] = None,
        depth: int = 1,
        force: bool = False,
        notify_errors: bool = False,
    ):
        super().__init__()
        self.repo_url = repo_url
        self.repo_path = repo_path
        self.checkout_branch = checkout_branch
        self.depth = depth
        self.force = force
        self.notify_errors = notify_errors

    def run(self) -> None:
        """Execute the git clone operation in background"""
        try:
            logger.info(
                f"Starting git clone in thread: {self.repo_url} to {self.repo_path}"
            )

            # Emit progress update
            self.progress.emit(f"Cloning repository: {self.repo_url}")

            # Perform the clone operation
            repo, result = git_utils.git_clone(
                repo_url=self.repo_url,
                repo_path=self.repo_path,
                checkout_branch=self.checkout_branch,
                depth=self.depth,
                force=self.force,
                notify_errors=self.notify_errors,
            )

            # Clean up repository object if successful
            if repo is not None:
                git_utils.git_cleanup(repo)

            # Emit results based on clone result
            if result == GitCloneResult.CLONED:
                success_msg = f"Repository cloned successfully to: {self.repo_path}"
                logger.info(success_msg)
                self.finished.emit(True, success_msg, self.repo_path)
            else:
                error_msg = f"Clone failed: {result}"
                logger.error(error_msg)
                self.error.emit(False, error_msg, self.repo_path)

        except Exception as e:
            error_msg = f"Unexpected error during clone: {str(e)}"
            logger.error(error_msg)
            self.error.emit(error_msg)


class GitCheckResults:
    """Data structure to hold check-updates results."""

    def __init__(
        self,
        updates: Dict[Path, List[str]],
        invalid_paths: List[Path],
        error: Dict[Path, str],
    ):
        self.updates = updates  # {repo_path: [commit messages]}
        self.invalid_paths = invalid_paths  # paths that were not valid repos
        self.errors = error  # {repo_path: error message}


class GitCheckUpdatesWorker(QRunnable):
    """Worker to check multiple git repositories for updates in parallel."""

    def __init__(self, repos_paths: List[Path]):
        super().__init__()
        self.repos_paths = repos_paths
        # Signals via a QObject for thread-safe emit
        self.signals = GitCheckUpdatesWorker.Signals()

    class Signals(QObject):
        finished = Signal(object)  # emits GitCheckResults

        def __init__(self) -> None:
            super().__init__()

    @Slot()
    def run(self) -> None:
        """
        Iterate all repos_paths concurrently and collect update messages.
        Emits GitCheckResults when done.
        """
        updates: Dict[Path, List[str]] = {}
        invalid_paths: List[Path] = []
        errors: Dict[Path, str] = {}

        for repo_path in self.repos_paths:
            repo = git_utils.git_discover(repo_path)
            if repo is None:
                logger.warning(f"Invalid git repository: {repo_path}")
                invalid_paths.append(repo_path)
                continue
            try:
                walker = git_utils.git_check_updates(repo)
                if walker is not None:
                    commit_msgs = [commit.message for commit in walker]
                    updates[repo_path] = commit_msgs
            except Exception as e:
                logger.error(f"Error checking updates for {repo_path}: {e}")
                errors[repo_path] = str(e)
            finally:
                repo.free()

        results = GitCheckResults(
            updates=updates, invalid_paths=invalid_paths, error=errors
        )
        self.signals.finished.emit(results)


class GitBatchUpdateResults:
    """Data structure to hold batch update (pull) results."""

    def __init__(
        self,
        successful: List[Path],
        failed: List[Tuple[Path, str]],
    ):
        self.successful = successful
        self.failed = failed


class GitBatchUpdateWorker(QRunnable):
    """Worker to pull (update) multiple git repositories in parallel."""

    def __init__(self, repos_paths: List[Path]):
        super().__init__()
        self.repos_paths = repos_paths
        self.signals = GitBatchUpdateWorker.Signals()

    class Signals(QObject):
        finished = Signal(object)  # emits GitBatchUpdateResults

        def __init__(self) -> None:
            super().__init__()

    @Slot()
    def run(self) -> None:
        """
        Pull updates for each repository, collect successes and failures.
        Emits GitBatchUpdateResults when done.
        """
        successful: List[Path] = []
        failed: List[Tuple[Path, str]] = []

        for repo_path in self.repos_paths:
            repo = git_utils.git_discover(repo_path)
            if repo is None:
                logger.warning(f"Invalid git repository for pull: {repo_path}")
                failed.append((repo_path, "Invalid git repository"))
                continue
            try:
                git_utils.git_pull(repo)
                successful.append(repo_path)
            except Exception as e:
                error_msg = str(e)
                logger.error(f"Failed pulling {repo_path}: {error_msg}")
                failed.append((repo_path, error_msg))
            finally:
                repo.free()

        results = GitBatchUpdateResults(successful=successful, failed=failed)
        self.signals.finished.emit(results)

from pathlib import Path
from typing import Dict, List, Optional, Tuple

from loguru import logger
from PySide6.QtCore import QObject, QRunnable, QThread, Signal, Slot

from app.utils import git_utils
from app.utils.git_utils import GitCloneResult, GitOperationConfig


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
        config: Optional[GitOperationConfig] = None,
    ):
        super().__init__()
        self.repo_url = repo_url
        self.repo_path = repo_path
        self.checkout_branch = checkout_branch
        self.depth = depth
        self.force = force
        self.config = config or GitOperationConfig(notify_errors=False)

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
                config=self.config,
            )

            # Clean up repository object if successful
            if repo is not None:
                git_utils.git_cleanup(repo)

            # Emit results based on clone result
            if result == GitCloneResult.CLONED:
                success_msg = f"Repository cloned successfully to: {self.repo_path}"
                logger.info(success_msg)
                self.finished.emit(True, success_msg, str(self.repo_path))
            else:
                error_msg = f"Clone failed: {result}"
                logger.error(error_msg)
                self.error.emit(error_msg)

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

    def __init__(
        self, repos_paths: List[Path], config: Optional[GitOperationConfig] = None
    ):
        super().__init__()
        self.repos_paths = repos_paths
        self.config = config or GitOperationConfig(notify_errors=False)
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
            try:
                with git_utils.git_repository(repo_path, self.config) as repo:
                    if repo is None:
                        logger.warning(f"Invalid git repository: {repo_path}")
                        invalid_paths.append(repo_path)
                        continue

                    walker = git_utils.git_check_updates(repo, self.config)
                    if walker is not None:
                        commit_msgs = [commit.message for commit in walker]
                        updates[repo_path] = commit_msgs
            except Exception as e:
                logger.error(f"Error checking updates for {repo_path}: {e}")
                errors[repo_path] = str(e)

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

    def __init__(
        self, repos_paths: List[Path], config: Optional[GitOperationConfig] = None
    ):
        super().__init__()
        self.repos_paths = repos_paths
        self.config = config or GitOperationConfig(notify_errors=False)
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
            try:
                with git_utils.git_repository(repo_path, self.config) as repo:
                    if repo is None:
                        logger.warning(f"Invalid git repository for pull: {repo_path}")
                        failed.append((repo_path, "Invalid git repository"))
                        continue

                    result = git_utils.git_pull(repo, config=self.config)
                    # Check if pull was successful based on result
                    if result in [
                        git_utils.GitPullResult.UP_TO_DATE,
                        git_utils.GitPullResult.FAST_FORWARD,
                        git_utils.GitPullResult.FORCE_CHECKOUT,
                        git_utils.GitPullResult.MERGE,
                    ]:
                        successful.append(repo_path)
                    else:
                        failed.append((repo_path, str(result)))
            except Exception as e:
                error_msg = str(e)
                logger.error(f"Failed pulling {repo_path}: {error_msg}")
                failed.append((repo_path, error_msg))

        results = GitBatchUpdateResults(successful=successful, failed=failed)
        self.signals.finished.emit(results)

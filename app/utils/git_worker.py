from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger
from PySide6.QtCore import QObject, QRunnable, QThread, Signal, Slot

from app.utils import git_utils
from app.utils.git_utils import GitOperationConfig

# Base classes and common utilities


class PushConfig:
    """Configuration class for push-related operations"""

    def __init__(
        self,
        remote_name: str = "origin",
        branch: Optional[str] = None,
        force: bool = False,
        username: Optional[str] = None,
        token: Optional[str] = None,
        timeout: int = 30,  # Add timeout configuration
    ):
        self.remote_name = remote_name
        self.branch = branch
        self.force = force
        self.username = username
        self.token = token
        self.timeout = timeout


class BaseWorkerSignals(QObject):
    """Base signals for git worker threads"""

    finished = Signal(bool, str, str)  # success, message, repo_path
    progress = Signal(str)  # status message
    error = Signal(str)  # error message

    def __init__(self) -> None:
        super().__init__()


class BaseBatchSignals(QObject):
    """Base signals for batch operations"""

    finished = Signal(object)  # emits batch results

    def __init__(self) -> None:
        super().__init__()


class BatchOperationResult:
    """Base class for batch operation results"""

    def __init__(self, successful: List[Path], failed: List[Tuple[Path, str]]):
        self.successful = successful
        self.failed = failed

    @property
    def total_count(self) -> int:
        return len(self.successful) + len(self.failed)

    @property
    def success_count(self) -> int:
        return len(self.successful)

    @property
    def failure_count(self) -> int:
        return len(self.failed)


def handle_worker_error(operation_name: str, repo_path: str, error: Exception) -> str:
    """Common error handling for worker operations"""
    error_msg = f"Unexpected error during {operation_name}: {str(error)}"
    logger.error(f"{error_msg} in {repo_path}")
    return error_msg


def validate_repository(
    repo_path: Path, config: GitOperationConfig, operation_name: str
) -> Optional[str]:
    """Validate repository and return error message if invalid"""
    with git_utils.git_repository(repo_path, config) as repo:
        if repo is None:
            error_msg = f"Invalid git repository for {operation_name}: {repo_path}"
            logger.warning(error_msg)
            return error_msg
    return None


def process_batch_repository(
    repo_path: Path,
    config: GitOperationConfig,
    operation_func: Any,
    operation_name: str,
    **kwargs: Any,
) -> Tuple[bool, Optional[str]]:
    """Process a single repository in a batch operation"""
    try:
        with git_utils.git_repository(repo_path, config) as repo:
            if repo is None:
                return False, f"Invalid git repository for {operation_name}"

            result = operation_func(repo, **kwargs)
            if result.is_successful():
                return True, None
            else:
                return False, str(result)

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Failed {operation_name} {repo_path}: {error_msg}")
        return False, error_msg


class BaseBatchWorker(QRunnable):
    """Base class for batch git operations"""

    def __init__(
        self, repos_paths: List[Path], config: Optional[GitOperationConfig] = None
    ):
        super().__init__()
        self.repos_paths = repos_paths
        # Create config with reasonable timeouts for batch operations
        self.config = config or GitOperationConfig.create_with_timeout(
            fetch_timeout=30, connection_timeout=10
        )
        self.signals = BaseBatchSignals()

    def execute_batch_operation(
        self, operation_func: Any, operation_name: str, result_class: Any, **kwargs: Any
    ) -> None:
        """Execute batch operation with common logic"""
        successful: List[Path] = []
        failed: List[Tuple[Path, str]] = []

        for repo_path in self.repos_paths:
            success, error_msg = process_batch_repository(
                repo_path, self.config, operation_func, operation_name, **kwargs
            )

            if success:
                successful.append(repo_path)
            else:
                failed.append((repo_path, error_msg or "Unknown error"))

        results = result_class(successful=successful, failed=failed)
        self.signals.finished.emit(results)


class BaseGitWorker(QThread):
    """Base class for single git operations"""

    # Common signals
    finished = Signal(bool, str, str)  # success, message, repo_path
    progress = Signal(str)  # status message
    error = Signal(str)  # error message

    def __init__(
        self, repo_path: str | Path, config: Optional[GitOperationConfig] = None
    ):
        super().__init__()
        self.repo_path = repo_path
        # Create config with reasonable timeouts
        self.config = config or GitOperationConfig.create_with_timeout(
            fetch_timeout=30, connection_timeout=10
        )
        self._is_cancelled = False

    def cancel(self) -> None:
        """Cancel the operation"""
        self._is_cancelled = True
        self.requestInterruption()

    def emit_progress(self, message: str) -> None:
        """Emit progress message"""
        if not self._is_cancelled:
            self.progress.emit(message)

    def emit_success(self, message: str) -> None:
        """Emit success result"""
        if not self._is_cancelled:
            logger.info(message)
            self.finished.emit(True, message, str(self.repo_path))

    def emit_error(self, message: str) -> None:
        """Emit error result"""
        if not self._is_cancelled:
            logger.error(message)
            self.error.emit(message)
            self.finished.emit(False, message, str(self.repo_path))

    def handle_exception(self, operation_name: str, e: Exception) -> None:
        """Handle exceptions with common error handling"""
        if not self._is_cancelled:
            error_msg = handle_worker_error(operation_name, str(self.repo_path), e)
            self.error.emit(error_msg)
            self.finished.emit(False, error_msg, str(self.repo_path))


class GitCloneWorker(BaseGitWorker):
    """Worker thread for git clone operations"""

    def __init__(
        self,
        repo_url: str,
        repo_path: str | Path,
        checkout_branch: Optional[str] = None,
        depth: int = 1,
        force: bool = False,
        config: Optional[GitOperationConfig] = None,
    ):
        super().__init__(repo_path, config)
        self.repo_url = repo_url
        self.checkout_branch = checkout_branch
        self.depth = depth
        self.force = force

    def run(self) -> None:
        """Execute the git clone operation in background"""
        repo: Optional[Any] = None  # Initialize repo to None
        try:
            logger.info(
                f"Starting git clone in thread: {self.repo_url} to {self.repo_path}"
            )

            if self.isInterruptionRequested():
                return

            self.emit_progress(f"Cloning repository: {self.repo_url}")

            repo, result = git_utils.git_clone(
                repo_url=self.repo_url,
                repo_path=self.repo_path,
                checkout_branch=self.checkout_branch,
                depth=self.depth,
                force=self.force,
                config=self.config,
            )

            if self.isInterruptionRequested():
                return

            if result.is_successful():
                self.emit_success(
                    f"Repository cloned successfully to: {self.repo_path}"
                )
            else:
                self.emit_error(f"Clone failed: {result}")

        except Exception as e:
            if not self.isInterruptionRequested():
                self.handle_exception("clone", e)
        finally:
            if repo is not None:
                git_utils.git_cleanup(repo)
                try:
                    import gc

                    gc.collect()
                except Exception:
                    pass


class GitPushWorker(BaseGitWorker):
    """Worker thread for git push operations"""

    def __init__(
        self,
        repo_path: str | Path,
        push_config: Optional[PushConfig] = None,
        config: Optional[GitOperationConfig] = None,
    ):
        super().__init__(repo_path, config)
        push_config = push_config or PushConfig()
        self.remote_name = push_config.remote_name
        self.branch = push_config.branch
        self.force = push_config.force
        self.username = push_config.username
        self.token = push_config.token

    def run(self) -> None:
        """Execute the git push operation in background"""
        try:
            logger.info(f"Starting git push in thread for: {self.repo_path}")

            if self.isInterruptionRequested():
                return

            self.emit_progress(f"Pushing changes from: {self.repo_path}")

            with git_utils.git_repository(self.repo_path, self.config) as repo:
                if repo is None:
                    self.emit_error(f"Invalid git repository: {self.repo_path}")
                    return

                if self.isInterruptionRequested():
                    return

                result = git_utils.git_push(
                    repo=repo,
                    remote_name=self.remote_name,
                    branch=self.branch,
                    force=self.force,
                    config=self.config,
                    username=self.username,
                    token=self.token,
                )

                if self.isInterruptionRequested():
                    return

                if result.is_successful():
                    self.emit_success(
                        f"Changes pushed successfully from: {self.repo_path}"
                    )
                else:
                    self.emit_error(f"Push failed: {result}")

        except Exception as e:
            if not self.isInterruptionRequested():
                self.handle_exception("push", e)


class GitStageCommitWorker(BaseGitWorker):
    """Worker thread for git stage and commit operations"""

    def __init__(
        self,
        repo_path: str | Path,
        commit_message: str,
        paths: Optional[List[str]] = None,
        all: bool = False,
        config: Optional[GitOperationConfig] = None,
    ):
        super().__init__(repo_path, config)
        self.commit_message = commit_message
        self.paths = paths or []
        self.all = all

    def run(self) -> None:
        """Execute the git stage and commit operation in background"""
        try:
            logger.info(
                f"Starting git stage and commit in thread for: {self.repo_path}"
            )

            if self.isInterruptionRequested():
                return

            self.emit_progress(f"Staging and committing changes in: {self.repo_path}")

            with git_utils.git_repository(self.repo_path, self.config) as repo:
                if repo is None:
                    self.emit_error(f"Invalid git repository: {self.repo_path}")
                    return

                if self.isInterruptionRequested():
                    return

                result = git_utils.git_stage_commit(
                    repo=repo,
                    message=self.commit_message,
                    paths=self.paths,
                    all=self.all,
                    config=self.config,
                )

                if self.isInterruptionRequested():
                    return

                if result.is_successful():
                    self.emit_success(
                        f"Changes staged and committed successfully in: {self.repo_path}"
                    )
                else:
                    self.emit_error(f"Stage and commit failed: {result}")

        except Exception as e:
            if not self.isInterruptionRequested():
                self.handle_exception("stage and commit", e)


def check_repository_updates(
    repo_path: Path, config: GitOperationConfig
) -> Tuple[bool, Optional[List[str]], Optional[str]]:
    """Check updates for a single repository"""
    try:
        with git_utils.git_repository(repo_path, config) as repo:
            if repo is None:
                return False, None, "Invalid git repository"

            walker = git_utils.git_check_updates(repo, config)
            if walker is not None:
                commit_msgs = [commit.message for commit in walker]
                return True, commit_msgs, None
            else:
                return True, [], None  # No updates found

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error checking updates for {repo_path}: {error_msg}")
        return False, None, error_msg


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


class GitCheckUpdatesWorker(BaseBatchWorker):
    """Worker to check multiple git repositories for updates in parallel."""

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
            success, commit_msgs, error_msg = check_repository_updates(
                repo_path, self.config
            )

            if not success:
                if "Invalid git repository" in (error_msg or ""):
                    invalid_paths.append(repo_path)
                else:
                    errors[repo_path] = error_msg or "Unknown error"
            elif commit_msgs:  # Only add if there are actual updates
                updates[repo_path] = commit_msgs

        results = GitCheckResults(
            updates=updates, invalid_paths=invalid_paths, error=errors
        )
        self.signals.finished.emit(results)


class GitBatchUpdateResults(BatchOperationResult):
    """Data structure to hold batch update (pull) results."""

    pass


class GitBatchUpdateWorker(BaseBatchWorker):
    """Worker to pull (update) multiple git repositories in parallel."""

    @Slot()
    def run(self) -> None:
        """Pull updates for each repository, collect successes and failures."""
        self.execute_batch_operation(git_utils.git_pull, "pull", GitBatchUpdateResults)


class GitBatchPushResults(BatchOperationResult):
    """Data structure to hold batch push results."""

    pass


class GitBatchPushWorker(BaseBatchWorker):
    """Worker to push multiple git repositories in parallel."""

    def __init__(
        self,
        repos_paths: List[Path],
        push_config: Optional[PushConfig] = None,
        config: Optional[GitOperationConfig] = None,
    ):
        super().__init__(repos_paths, config)
        push_config = push_config or PushConfig()
        self.remote_name = push_config.remote_name
        self.branch = push_config.branch
        self.force = push_config.force
        self.username = push_config.username
        self.token = push_config.token

    @Slot()
    def run(self) -> None:
        """Push updates for each repository, collect successes and failures."""
        self.execute_batch_operation(
            git_utils.git_push,
            "push",
            GitBatchPushResults,
            remote_name=self.remote_name,
            branch=self.branch,
            force=self.force,
            username=self.username,
            token=self.token,
        )

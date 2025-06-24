"""This module contains a collection of utility functions for working with git repositories."""

import threading
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Generator, List, Optional, Protocol, cast
from urllib.parse import urlparse

import pygit2
from loguru import logger
from pygit2.enums import CheckoutStrategy, ResetMode, SortMode
from pygit2.repository import Repository
from PySide6.QtWidgets import QMessageBox

from app.utils.generic import check_internet_connection, delete_files_with_condition
from app.views.dialogue import InformationBox


class GitError(Exception):
    """Base exception for git operations."""

    def __init__(self, message: str, details: Optional[str] = None):
        super().__init__(message)
        self.message = message
        self.details = details

    def __str__(self) -> str:
        if self.details:
            return f"{self.message}: {self.details}"
        return self.message


class GitOperationType(Enum):
    """Types of git operations for better error categorization."""

    DISCOVER = "discover"
    CLONE = "clone"
    PULL = "pull"
    PUSH = "push"
    STAGE_COMMIT = "stage_commit"
    STASH = "stash"
    STATUS = "status"
    COMMIT_INFO = "commit_info"


class GitNotificationHandler(Protocol):
    """Protocol for handling git operation notifications."""

    def show_error(
        self, title: str, message: str, details: Optional[str] = None
    ) -> None:
        """Show error notification to user."""
        ...


class DefaultNotificationHandler:
    """Default implementation using QMessageBox for notifications."""

    def show_error(
        self, title: str, message: str, details: Optional[str] = None
    ) -> None:
        """Show error notification using InformationBox."""
        InformationBox(
            title=title,
            text=message,
            icon=QMessageBox.Icon.Critical,
            details=details,
        ).exec()


@dataclass
class GitOperationConfig:
    """Configuration for git operations."""

    notify_errors: bool = True
    notification_handler: Optional[GitNotificationHandler] = None
    fetch_timeout: int = 30  # Timeout for fetch operations in seconds
    connection_timeout: int = 10  # Timeout for connection checks in seconds

    def __post_init__(self) -> None:
        if self.notification_handler is None:
            self.notification_handler = DefaultNotificationHandler()

    def get_handler(self) -> GitNotificationHandler:
        """Get the notification handler, ensuring it's not None."""
        return self.notification_handler or DefaultNotificationHandler()

    @classmethod
    def create_silent(cls) -> "GitOperationConfig":
        """Create a config that suppresses error notifications."""
        return cls(notify_errors=False)

    @classmethod
    def create_with_handler(
        cls, handler: GitNotificationHandler
    ) -> "GitOperationConfig":
        """Create a config with a specific notification handler."""
        return cls(notify_errors=True, notification_handler=handler)

    @classmethod
    def create_with_timeout(
        cls, fetch_timeout: int = 30, connection_timeout: int = 10
    ) -> "GitOperationConfig":
        """Create a config with custom timeout values."""
        return cls(fetch_timeout=fetch_timeout, connection_timeout=connection_timeout)


def _fetch_with_timeout(remote: pygit2.Remote, timeout: int) -> bool:
    """Fetch from remote with timeout handling.

    Args:
        remote: The pygit2 remote object.
        timeout: Timeout in seconds.

    Returns:
        True if fetch was successful, False if timeout or error occurred.

    Raises:
        Exception: If the fetch operation fails with an error.
    """
    result: dict[str, Any] = {"success": False, "error": None}

    def fetch_target() -> None:
        try:
            remote.fetch()
            result["success"] = True
        except Exception as e:
            result["error"] = e

    fetch_thread = threading.Thread(target=fetch_target)
    fetch_thread.daemon = True
    fetch_thread.start()
    fetch_thread.join(timeout)

    if fetch_thread.is_alive():
        # Timeout occurred
        logger.warning(f"Fetch operation timed out after {timeout} seconds")
        return False

    if result["error"]:
        raise result["error"]

    return bool(result["success"])


def _handle_git_error(
    operation: GitOperationType,
    error: Exception,
    config: GitOperationConfig,
    context: str = "",
    **kwargs: Any,
) -> None:
    """Centralized error handling for git operations.

    Args:
        operation: The type of git operation that failed.
        error: The exception that occurred.
        config: Configuration for error handling.
        context: Additional context about the operation.
        **kwargs: Additional context for error messages.
    """
    error_msg = str(error)
    logger.error(
        f"Git {operation.value} operation failed{f' ({context})' if context else ''}: {error_msg}"
    )

    if config.notify_errors:
        title_map = {
            GitOperationType.DISCOVER: "Git Repository Discovery Error",
            GitOperationType.CLONE: "Git Clone Error",
            GitOperationType.PULL: "Git Pull Error",
            GitOperationType.PUSH: "Git Push Error",
            GitOperationType.STAGE_COMMIT: "Git Stage and Commit Error",
            GitOperationType.STASH: "Git Stash Error",
            GitOperationType.STATUS: "Git Status Error",
            GitOperationType.COMMIT_INFO: "Git Commit Info Error",
        }

        config.get_handler().show_error(
            title=title_map.get(operation, "Git Operation Error"),
            message=f"Failed to {operation.value} {context}".strip(),
            details=error_msg,
        )


@contextmanager
def git_repository(
    path: str | Path, config: Optional[GitOperationConfig] = None
) -> Generator[Optional[Repository], None, None]:
    """Context manager for automatic repository cleanup.

    Args:
        path: Path to the git repository.
        config: Configuration for the operation.

    Yields:
        Repository object if found, otherwise None.
    """
    repo = git_discover(path, config)
    try:
        yield repo
    finally:
        if repo is not None:
            git_cleanup(repo)


class GitCloneResult(Enum):
    """Enumeration of possible results of a git clone operation."""

    CLONED = "Repository cloned successfully."
    PATH_NOT_DIR = "Failed to clone repository. The path is not a directory."
    PATH_NOT_EMPTY = "Failed to clone repository. The path is not empty."
    PATH_DELETE_ERROR = "Failed to delete the local directory."
    GIT_ERROR = "Failed to clone repository."

    def __str__(self) -> str:
        return self.value

    def __repr__(self) -> str:
        return self.value

    def is_successful(self) -> bool:
        """Check if the clone result indicates a successful operation."""
        return self == GitCloneResult.CLONED

    def is_error(self) -> bool:
        """Check if the clone result indicates an error."""
        return not self.is_successful()


class GitPullResult(Enum):
    """Enumeration of possible results of a git pull operation."""

    UP_TO_DATE = "Repository is already up to date."
    FAST_FORWARD = "Repository updated successfully with fast-forward merge."
    FORCE_CHECKOUT = "Repository updated successfully with force checkout."
    MERGE = "Repository updated successfully with merge."
    CONFLICT = "Conflicts encountered during merge."
    UNKNOWN = "Unknown merge analysis result."
    UNKNOWN_REMOTE = "Remote not found in the repository."
    GIT_ERROR = "Failed to pull updates from the repository."

    def __str__(self) -> str:
        return self.value

    def __repr__(self) -> str:
        return self.value

    def is_successful(self) -> bool:
        """Check if the pull result indicates a successful operation."""
        return self in {
            GitPullResult.UP_TO_DATE,
            GitPullResult.FAST_FORWARD,
            GitPullResult.FORCE_CHECKOUT,
            GitPullResult.MERGE,
        }

    def is_error(self) -> bool:
        """Check if the pull result indicates an error."""
        return self in {
            GitPullResult.CONFLICT,
            GitPullResult.UNKNOWN,
            GitPullResult.UNKNOWN_REMOTE,
            GitPullResult.GIT_ERROR,
        }


class GitPushResult(Enum):
    """Enumeration of possible results of a git push operation."""

    PUSHED = "Changes pushed successfully."
    UP_TO_DATE = "Remote is already up to date."
    REJECTED_NON_FAST_FORWARD = "Push rejected due to non-fast-forward update."
    REJECTED_STALE = "Push rejected due to stale reference."
    AUTHENTICATION_FAILED = "Authentication failed."
    REMOTE_ERROR = "Remote server error."
    UNKNOWN_REMOTE = "Remote not found in the repository."
    NO_COMMITS = "No commits to push."
    GIT_ERROR = "Failed to push to the repository."

    def __str__(self) -> str:
        return self.value

    def __repr__(self) -> str:
        return self.value

    def is_successful(self) -> bool:
        """Check if the push result indicates a successful operation."""
        return self in {
            GitPushResult.PUSHED,
            GitPushResult.UP_TO_DATE,
        }

    def is_error(self) -> bool:
        """Check if the push result indicates an error."""
        return not self.is_successful()


class GitStageCommitResult(Enum):
    """Enumeration of possible results of a git stage and commit operation."""

    COMMITTED = "Changes staged and committed successfully."
    NO_CHANGES = "No changes to commit."
    STAGING_FAILED = "Failed to stage changes."
    COMMIT_FAILED = "Failed to create commit."
    GIT_ERROR = "Failed to stage and commit changes."

    def __str__(self) -> str:
        return self.value

    def __repr__(self) -> str:
        return self.value

    def is_successful(self) -> bool:
        """Check if the stage and commit result indicates a successful operation."""
        return self in {
            GitStageCommitResult.COMMITTED,
            GitStageCommitResult.NO_CHANGES,
        }

    def is_error(self) -> bool:
        """Check if the stage and commit result indicates an error."""
        return not self.is_successful()


class GitStashResult(Enum):
    """Enumeration of possible results of a git stash operation."""

    STASHED = "Changes stashed successfully."
    NO_CHANGES = "No changes to stash."
    STASH_APPLIED = "Stash applied successfully."
    STASH_DROPPED = "Stash dropped successfully."
    STASH_POP_SUCCESS = "Stash popped successfully."
    STASH_LIST_SUCCESS = "Stash list retrieved successfully."
    STASH_POP_CONFLICT = "Conflicts encountered during stash pop."
    GIT_ERROR = "Failed to perform stash operation."

    def __str__(self) -> str:
        return self.value

    def __repr__(self) -> str:
        return self.value

    def is_successful(self) -> bool:
        """Check if the stash result indicates a successful operation."""
        return self in {
            GitStashResult.STASHED,
            GitStashResult.NO_CHANGES,
            GitStashResult.STASH_APPLIED,
            GitStashResult.STASH_DROPPED,
            GitStashResult.STASH_POP_SUCCESS,
            GitStashResult.STASH_LIST_SUCCESS,
        }

    def is_error(self) -> bool:
        """Check if the stash result indicates an error."""
        return self == GitStashResult.GIT_ERROR


def get_config(config: Optional[GitOperationConfig]) -> GitOperationConfig:
    """Helper to get or create a default GitOperationConfig."""
    if config is None:
        return GitOperationConfig()
    return config


def git_discover(
    path: str | Path, config: Optional[GitOperationConfig] = None
) -> Optional[Repository]:
    """Discover a git repository at a given path.

    Args:
        path: The path to discover the git repository.
        config: Configuration for the operation.

    Returns:
        The repository object if found, otherwise None.
    """
    config = get_config(config)

    path_str = str(path)
    logger.info(f"Attempting to discover git repository at: {path_str}")

    try:
        repo_path = pygit2.discover_repository(path_str)
        if repo_path is None:
            logger.info(f"No git repository found at: {path_str}")
            return None

        logger.info(f"Git repository found at: {repo_path}")
        return Repository(repo_path)

    except pygit2.GitError as e:
        _handle_git_error(
            GitOperationType.DISCOVER, e, config, context=f"repository at: {path_str}"
        )
        return None


def git_get_repo_name(repo_url: str) -> str:
    """Gets the repository folder name from a git URL.

    Args:
        repo_url: The URL of the repository.

    Returns:
        The repository folder name. If the URL is not valid, returns an empty string.

    Examples:
        >>> git_get_repo_name("https://github.com/user/repo.git")
        'repo'
        >>> git_get_repo_name("git@github.com:user/repo.git")
        'repo'
        >>> git_get_repo_name("invalid-url")
        ''
    """
    if not repo_url or not isinstance(repo_url, str):
        logger.warning(f"Invalid repository URL: {repo_url}")
        return ""

    try:
        # Handle both HTTPS and SSH URLs
        if repo_url.startswith(("http://", "https://")):
            parsed = urlparse(repo_url)
            path = parsed.path.strip("/")
        elif repo_url.startswith("git@"):
            # SSH URL format: git@host:user/repo.git
            path = repo_url.split(":")[-1] if ":" in repo_url else ""
        else:
            # Assume it's a path-like format
            path = repo_url

        if not path:
            return ""

        # Extract repository name
        repo_name = Path(path).stem  # This removes .git extension automatically
        logger.debug(f"Extracted repository name '{repo_name}' from URL: {repo_url}")
        return repo_name

    except Exception as e:
        logger.warning(f"Failed to extract repository name from URL '{repo_url}': {e}")
        return ""


def git_clone(
    repo_url: str,
    repo_path: str | Path,
    checkout_branch: Optional[str] = None,
    depth: int = 1,
    force: bool = False,
    config: Optional[GitOperationConfig] = None,
) -> tuple[Optional[Repository], GitCloneResult]:
    """Clone a git repository.

    Args:
        repo_url: The URL of the repository to clone.
        repo_path: The path to clone the repository to.
        checkout_branch: The branch to checkout if any.
        depth: The clone depth.
        force: Whether to force the clone operation, even if the path is not empty.
        config: Configuration for the operation.

    Returns:
        Tuple of (repository object if successful, result enum).
    """
    config = get_config(config)

    logger.info(f"Attempting git cloning: {repo_url} to {repo_path}")
    repo_path_str = str(repo_path)
    repo_path_obj = Path(repo_path_str)

    # Validate path
    if repo_path_obj.exists() and not repo_path_obj.is_dir():
        error_msg = "The path is not a directory."
        logger.error(
            f"Failed to clone repository: {repo_url} to {repo_path} - {error_msg}"
        )
        _handle_git_error(
            GitOperationType.CLONE,
            ValueError(error_msg),
            config,
            context=f"cloning {repo_url} to {repo_path}",
        )
        return None, GitCloneResult.PATH_NOT_DIR

    # Check if directory is empty
    if repo_path_obj.exists() and any(repo_path_obj.iterdir()):
        if not force:
            error_msg = f"The path is not empty: {repo_path}"
            logger.error(
                f"Failed to clone repository: {repo_url} to {repo_path} - {error_msg}"
            )
            _handle_git_error(
                GitOperationType.CLONE,
                ValueError(error_msg),
                config,
                context=f"cloning {repo_url} to {repo_path}",
            )
            return None, GitCloneResult.PATH_NOT_EMPTY
        else:
            # Force the clone operation by deleting the directory
            logger.warning(
                f"Force cloning repository by deleting the local directory: {repo_path}"
            )
            success = delete_files_with_condition(
                repo_path_str, lambda file: not file.endswith(".dds")
            )
            if not success:
                logger.error(f"Failed to delete the local directory: {repo_path}")
                return None, GitCloneResult.PATH_DELETE_ERROR

    try:
        repo = pygit2.clone_repository(
            repo_url, repo_path_str, checkout_branch=checkout_branch, depth=depth
        )
        # Wrap the returned repo in the Python wrapper class for type consistency
        repo = Repository(repo_path_str)
        return repo, GitCloneResult.CLONED
    except pygit2.GitError as e:
        _handle_git_error(
            GitOperationType.CLONE,
            e,
            config,
            context=f"cloning {repo_url} to {repo_path}",
        )
        return None, GitCloneResult.GIT_ERROR


def git_check_updates(
    repo: Repository, config: Optional[GitOperationConfig] = None
) -> Optional[pygit2.Walker]:
    """Check for updates in a git repository in the current branch.

    Args:
        repo: The repository to check for updates in.
        config: Configuration for the operation.

    Returns:
        A walker object if updates are found, otherwise None.
    """
    config = get_config(config)

    logger.info(f"Checking for updates in git repository: {repo.path}")

    try:
        # Check if we have a valid HEAD
        if repo.head_is_unborn:
            logger.info("Repository has no commits, cannot check for updates")
            return None

        # Get the origin remote
        try:
            remote = repo.remotes["origin"]
        except KeyError:
            logger.warning("No 'origin' remote found in repository")
            return None  # Fetch updates from remote with timeout
        try:
            if not _fetch_with_timeout(remote, config.fetch_timeout):
                logger.error(
                    f"Fetch operation timed out after {config.fetch_timeout} seconds"
                )
                return None
        except Exception as e:
            logger.error(f"Fetch operation failed: {str(e)}")
            return None

        # Get current branch
        current_branch = repo.head.shorthand
        remote_ref = f"refs/remotes/origin/{current_branch}"

        # Check if remote branch exists
        try:
            remote_oid = repo.references[remote_ref].target
        except KeyError:
            logger.info(f"Remote branch 'origin/{current_branch}' not found")
            return None

        local_oid = repo.head.target

        if local_oid == remote_oid:
            logger.info("No updates found in the repository.")
            return None

        logger.info("Updates found in the repository.")
        walker = repo.walk(remote_oid, SortMode.TOPOLOGICAL)
        walker.hide(local_oid)
        return walker

    except pygit2.GitError as e:
        _handle_git_error(
            GitOperationType.PULL,
            e,
            config,
            context=f"updates check for repository: {repo.path}",
        )
        return None


def git_pull(
    repo: Repository,
    remote_name: str = "origin",
    branch: Optional[str] = None,
    reset_working_tree: bool = True,
    force: bool = False,
    config: Optional[GitOperationConfig] = None,
) -> GitPullResult:
    """Pull updates from a git repository.

    Args:
        repo: The repository to pull updates from.
        remote_name: The name of the remote to pull from.
        branch: The branch to pull from.
        reset_working_tree: Whether to discard uncommitted changes.
        force: Whether to force the pull operation via forced checkout.
        config: Configuration for the operation.

    Returns:
        Result of the pull operation.
    """
    config = get_config(config)

    logger.info(f"Pulling updates from git repository: {repo.path}")

    if branch is None:
        try:
            branch = repo.head.shorthand
        except pygit2.GitError:
            logger.error("No active branch found or repository is empty")
            return GitPullResult.GIT_ERROR  # Find the specified remote
    remote = None
    for r in repo.remotes:
        if r.name == remote_name:
            remote = r
            break

    if remote is None:
        logger.error(f"Remote '{remote_name}' not found in the repository: {repo.path}")
        return GitPullResult.UNKNOWN_REMOTE

    try:
        # Check network connectivity first
        if not check_internet_connection(timeout=config.connection_timeout):
            logger.warning("No network connectivity detected")
            return GitPullResult.GIT_ERROR

        # Fetch updates from remote with timeout
        try:
            if not _fetch_with_timeout(remote, config.fetch_timeout):
                logger.error(
                    f"Fetch operation timed out after {config.fetch_timeout} seconds"
                )
                return GitPullResult.GIT_ERROR
        except Exception as e:
            logger.error(f"Fetch operation failed: {str(e)}")
            return GitPullResult.GIT_ERROR

        # Get remote branch reference
        remote_ref = f"refs/remotes/{remote.name}/{branch}"
        try:
            remote_master_id = repo.lookup_reference(remote_ref).target
        except KeyError:
            logger.error(f"Remote branch '{remote.name}/{branch}' not found")
            return GitPullResult.GIT_ERROR

        # Analyze merge situation
        merge_result, _ = repo.merge_analysis(remote_master_id)

        if merge_result & pygit2.enums.MergeAnalysis.UP_TO_DATE:
            logger.info("Repository is already up to date.")
            return GitPullResult.UP_TO_DATE

        repo_get = repo.get(remote_master_id)
        if repo_get is None:
            raise pygit2.GitError("Failed to get remote commit object.")

        if force:
            logger.debug("Forcing merge operation.")
            repo.checkout_tree(repo_get, strategy=CheckoutStrategy.FORCE)
            repo.head.set_target(remote_master_id)
            logger.info("Repository updated successfully with force checkout.")
            return GitPullResult.FORCE_CHECKOUT

        if reset_working_tree:
            logger.debug("Resetting working tree.")
            repo.reset(repo.head.target, ResetMode.HARD)

        if merge_result & pygit2.enums.MergeAnalysis.FASTFORWARD:
            repo.checkout_tree(repo_get)
            repo.head.set_target(remote_master_id)
            logger.info("Repository updated successfully with fast-forward merge.")
            return GitPullResult.FAST_FORWARD

        elif merge_result & pygit2.enums.MergeAnalysis.NORMAL:
            repo.merge(remote_master_id)

            # Check for conflicts
            if repo.index.conflicts is not None:
                logger.warning("Conflicts encountered during merge.")

                conflict_files = []
                for conflict in repo.index.conflicts:
                    try:
                        conflict_file = conflict[0]
                        path_value = getattr(conflict_file, "path", None)
                        if path_value:
                            conflict_files.append(path_value)
                            logger.warning(f"Conflict found in: {path_value}")
                        else:
                            logger.warning("Conflict found in unknown file")
                    except Exception:
                        logger.warning("Conflict found in unknown file")

                if config.notify_errors:
                    conflict_details = (
                        f"Conflicts in files: {', '.join(conflict_files)}"
                        if conflict_files
                        else "Multiple conflicts detected"
                    )
                    config.get_handler().show_error(
                        title="Git Merge Conflict",
                        message="Conflicts encountered during merge.",
                        details=conflict_details,
                    )

                return GitPullResult.CONFLICT
            else:
                # No conflicts - complete the merge
                user = repo.default_signature
                tree = repo.index.write_tree()
                repo.create_commit(
                    "HEAD",
                    user,
                    user,
                    f"Merge branch '{branch}' from {remote.name}",
                    tree,
                    [repo.head.target, remote_master_id],
                )
                logger.info("Repository updated successfully with merge.")

            repo.state_cleanup()
            return GitPullResult.MERGE
        else:
            logger.error("Unknown merge analysis result.")
            return GitPullResult.UNKNOWN

    except pygit2.GitError as e:
        _handle_git_error(
            GitOperationType.PULL, e, config, context=f"repository: {repo.path}"
        )
        return GitPullResult.GIT_ERROR


def git_push(
    repo: Repository,
    remote_name: str = "origin",
    branch: Optional[str] = None,
    force: bool = False,
    config: Optional[GitOperationConfig] = None,
    username: Optional[str] = None,
    token: Optional[str] = None,
) -> GitPushResult:
    """Push updates to a git repository.

    Args:
        repo: The repository to push updates from.
        remote_name: The name of the remote to push to.
        branch: The branch to push. If None, uses current branch.
        force: Whether to force push (overwrites remote history).
        config: Configuration for the operation.
        username: GitHub username for authentication.
        token: GitHub personal access token for authentication.

    Returns:
        Result of the push operation.
    """
    config = get_config(config)

    logger.info(f"Pushing updates to git repository: {repo.path}")

    if branch is None:
        try:
            branch = repo.head.shorthand
        except Exception:
            logger.error("No active branch found")
            return GitPushResult.GIT_ERROR

    # Check if there are any commits to push
    try:
        local_oid = repo.head.target
        if local_oid is None:
            logger.info("No commits to push")
            return GitPushResult.NO_COMMITS
    except Exception:
        logger.error("Failed to get local commit")
        return GitPushResult.GIT_ERROR

    # Find the remote
    remote = None
    for r in repo.remotes:
        if r.name == remote_name:
            remote = r
            break

    if remote is None:
        logger.error(f"Remote '{remote_name}' not found in the repository: {repo.path}")
        return GitPushResult.UNKNOWN_REMOTE
    try:
        # Prepare refspec
        refspec = f"refs/heads/{branch}:refs/heads/{branch}"
        if force:
            refspec = f"+{refspec}"

        logger.debug(f"Pushing to remote: {remote.url} with refspec: {refspec}")

        # Setup authentication callbacks if credentials are provided
        callbacks = None
        if username and token:  # Create credentials for HTTPS authentication
            credentials = pygit2.UserPass(username, token)
            callbacks = pygit2.RemoteCallbacks(credentials=credentials)
            logger.debug(f"Using authentication for user: {username}")

        # Attempt to push with authentication
        if callbacks:
            remote.push([refspec], callbacks=callbacks)
        else:
            remote.push([refspec])

        logger.info(f"Updates pushed successfully to repository: {remote.url}")
        return GitPushResult.PUSHED

    except pygit2.GitError as e:
        _handle_git_error(
            GitOperationType.PUSH,
            e,
            config,
            context=f"repository: {repo.path}, remote: {remote.url if remote else remote_name}",
        )
        return GitPushResult.GIT_ERROR


def git_stage_commit(
    repo: Repository,
    message: str,
    paths: Optional[List[str]] = None,
    all: bool = False,
    config: Optional[GitOperationConfig] = None,
) -> GitStageCommitResult:
    """Stage and commit changes in a git repository.

    Args:
        repo: The repository to stage and commit changes in.
        message: The commit message.
        paths: The paths to stage.
        all: Whether to stage all changes.
        config: Configuration for the operation.

    Returns:
        Result of the stage and commit operation.
    """
    config = get_config(config)
    if paths is None:
        paths = []

    logger.debug(f"Staging and committing changes in git repository: {repo.path}")

    try:
        index = repo.index  # Stage changes first
        try:
            if all:
                index.add_all()
                logger.debug("Staged all changes")
            elif paths:
                for path in paths:
                    # Check if the file exists and has changes before staging
                    try:
                        # Log file status before staging
                        status = repo.status()
                        if path in status:
                            flags = status[path]
                            logger.debug(f"File {path} status flags: {flags}")
                        else:
                            logger.debug(f"File {path} not in git status")

                        # Stage the file
                        index.add(path)
                        logger.debug(f"Staged file: {path}")
                    except pygit2.GitError as e:
                        logger.warning(f"Could not stage file {path}: {e}")
                        # Continue with other files if one fails
                        continue
            else:
                # No specific paths and not staging all - check if there are already staged changes
                try:
                    tree_id = index.write_tree()
                    parent_commit = repo.head.target
                    commit_obj = cast(pygit2.Commit, repo[parent_commit])
                    parent_tree = commit_obj.tree
                    if tree_id == parent_tree.id:
                        logger.info("No changes to commit")
                        return GitStageCommitResult.NO_CHANGES
                except Exception:
                    # This might be the first commit or no staged changes
                    logger.info("No changes to commit")
                    return GitStageCommitResult.NO_CHANGES

            index.write()
        except pygit2.GitError as e:
            _handle_git_error(
                GitOperationType.STAGE_COMMIT,
                e,
                config,
                context=f"staging changes in repository: {repo.path}",
            )
            return GitStageCommitResult.STAGING_FAILED

        # Check if there are staged changes to commit after staging
        tree_id = index.write_tree()
        try:
            parent_commit = repo.head.target
            commit_obj = cast(pygit2.Commit, repo[parent_commit])
            parent_tree = commit_obj.tree
            if tree_id == parent_tree.id:
                logger.info("No changes to commit after staging")
                return GitStageCommitResult.NO_CHANGES
        except Exception:
            # This might be the first commit
            logger.debug("First commit or no parent - proceeding with commit")
            pass

        # Create commit
        try:
            author = repo.default_signature
            committer = repo.default_signature  # Get parent commits
            parents = []
            try:
                parents = [repo.head.target]
            except Exception:
                # This might be the first commit (no HEAD yet)
                pass

            commit_id = repo.create_commit(
                "HEAD", author, committer, message, tree_id, parents
            )

            logger.info(f"Changes staged and committed in the repository: {repo.path}")
            logger.debug(f"Created commit: {commit_id}")
            return GitStageCommitResult.COMMITTED

        except pygit2.GitError as e:
            _handle_git_error(
                GitOperationType.STAGE_COMMIT,
                e,
                config,
                context=f"creating commit in repository: {repo.path}",
            )
            return GitStageCommitResult.COMMIT_FAILED

    except pygit2.GitError as e:
        _handle_git_error(
            GitOperationType.STAGE_COMMIT, e, config, context=f"repository: {repo.path}"
        )
        return GitStageCommitResult.GIT_ERROR


def git_get_status(
    repo: Repository, config: Optional[GitOperationConfig] = None
) -> Optional[dict[str, List[str | tuple[str, str]]]]:
    """Get the status of files in a git repository.

    Args:
        repo: The repository to get status from.
        config: Configuration for the operation.

    Returns:
        Dictionary containing file status information with improved structure:
        {
            "staged": [("status", "filepath"), ...],
            "unstaged": [("status", "filepath"), ...],
            "untracked": ["filepath", ...],
            "ignored": ["filepath", ...]
        }
        Returns None if error occurs.
    """
    config = get_config(config)

    logger.debug(f"Getting status for git repository: {repo.path}")

    try:
        status = repo.status()
        status_dict: dict[str, List[str | tuple[str, str]]] = {
            "staged": [],
            "unstaged": [],
            "untracked": [],
            "ignored": [],
        }

        for filepath, flags in status.items():
            # Staged changes
            if flags & pygit2.GIT_STATUS_INDEX_NEW:
                status_dict["staged"].append(("new", filepath))
            elif flags & pygit2.GIT_STATUS_INDEX_MODIFIED:
                status_dict["staged"].append(("modified", filepath))
            elif flags & pygit2.GIT_STATUS_INDEX_DELETED:
                status_dict["staged"].append(("deleted", filepath))
            elif flags & pygit2.GIT_STATUS_INDEX_RENAMED:
                status_dict["staged"].append(("renamed", filepath))

            # Working tree changes
            if flags & pygit2.GIT_STATUS_WT_NEW:
                status_dict["untracked"].append(filepath)
            elif flags & pygit2.GIT_STATUS_WT_MODIFIED:
                status_dict["unstaged"].append(("modified", filepath))
            elif flags & pygit2.GIT_STATUS_WT_DELETED:
                status_dict["unstaged"].append(("deleted", filepath))
            elif flags & pygit2.GIT_STATUS_WT_RENAMED:
                status_dict["unstaged"].append(("renamed", filepath))

            # Ignored files
            if flags & pygit2.GIT_STATUS_IGNORED:
                status_dict["ignored"].append(filepath)

        logger.debug(
            f"Repository status: {sum(len(v) for v in status_dict.values())} files with changes"
        )
        return status_dict

    except pygit2.GitError as e:
        _handle_git_error(
            GitOperationType.STATUS, e, config, context=f"repository: {repo.path}"
        )
        return None


def git_get_commit_info(
    repo: Repository,
    commit_id: Optional[str] = None,
    config: Optional[GitOperationConfig] = None,
) -> Optional[dict[str, Any]]:
    """Get information about a specific commit.

    Args:
        repo: The repository to get commit info from.
        commit_id: The commit ID to get info for. If None, uses HEAD.
        config: Configuration for the operation.

    Returns:
        Dictionary containing commit information:
        {
            "id": str,
            "short_id": str,
            "message": str,
            "subject": str,  # First line of commit message
            "body": str,     # Rest of commit message
            "author": dict,
            "committer": dict,
            "parents": List[str],
            "timestamp": int
        }
        Returns None if error occurs.
    """
    config = get_config(config)

    try:
        if commit_id is None:
            if repo.head_is_unborn:
                logger.info("Repository has no commits yet")
                return None
            commit = cast(pygit2.Commit, repo[repo.head.target])
        else:
            commit = cast(pygit2.Commit, repo[commit_id])

        message_lines = commit.message.strip().split("\n", 1)
        subject = message_lines[0]
        body = message_lines[1].strip() if len(message_lines) > 1 else ""

        commit_info = {
            "id": str(commit.id),
            "short_id": str(commit.id)[:7],
            "message": commit.message.strip(),
            "subject": subject,
            "body": body,
            "author": {
                "name": commit.author.name,
                "email": commit.author.email,
                "time": commit.author.time,
            },
            "committer": {
                "name": commit.committer.name,
                "email": commit.committer.email,
                "time": commit.committer.time,
            },
            "parents": [str(parent) for parent in commit.parent_ids],
            "timestamp": commit.commit_time,
        }

        logger.debug(f"Retrieved commit info for: {commit_info['short_id']}")
        return commit_info

    except (pygit2.GitError, KeyError, ValueError) as e:
        _handle_git_error(
            GitOperationType.COMMIT_INFO,
            e,
            config,
            context=f"commit {commit_id or 'HEAD'}",
        )
        return None


def git_cleanup(repo: Repository) -> None:
    """Clean up the repository state and free resources.

    Args:
        repo: The repository to clean up.
    """
    repo.state_cleanup()
    repo.free()
    logger.debug(f"Git repository cleaned up: {repo.path}")


def git_stash(
    repo: Repository,
    message: Optional[str] = None,
    apply: bool = False,
    drop: bool = False,
    pop: bool = False,
    config: Optional[GitOperationConfig] = None,
) -> GitStashResult:
    """Stash changes in a git repository.

    Args:
        repo: The repository to stash changes in.
        message: The stash message.
        apply: Whether to apply the stash after creating it.
        drop: Whether to drop the stash after applying.
        pop: Whether to pop the stash (apply and drop).
        config: Configuration for the operation.

    Returns:
        Result of the stash operation.
    """
    config = get_config(config)

    logger.info(f"Stashing changes in git repository: {repo.path}")

    try:
        if pop:
            # Pop the stash (apply and drop)
            try:
                repo.stash_pop()

                # Check for conflicts after stash pop
                status = repo.status()
                conflict_files = []
                for filepath, flags in status.items():
                    if flags & pygit2.GIT_STATUS_CONFLICTED:
                        conflict_files.append(filepath)

                if conflict_files:
                    logger.warning(
                        f"Conflicts detected during stash pop in files: {conflict_files}"
                    )
                    return GitStashResult.STASH_POP_CONFLICT

                logger.info("Stash popped successfully")
                return GitStashResult.STASH_POP_SUCCESS
            except pygit2.GitError as e:
                logger.info(f"No stash to pop or stash pop failed: {e}")
                return GitStashResult.NO_CHANGES

        if apply:
            # Apply the stash without dropping
            try:
                repo.stash_apply()
                logger.info("Stash applied successfully")
                return GitStashResult.STASH_APPLIED
            except pygit2.GitError:
                logger.info("No stash to apply")
                return GitStashResult.NO_CHANGES

        # Create a new stash
        stasher = repo.default_signature
        stash_message = message or "Auto-stash before pull"

        stash_oid = repo.stash(stasher, stash_message)

        if stash_oid:
            logger.info("Changes stashed successfully")
            return GitStashResult.STASHED
        else:
            logger.info("No changes to stash")
            return GitStashResult.NO_CHANGES

    except pygit2.GitError as e:
        logger.error(f"Failed to perform stash operation: {e}")
        if config.notify_errors:
            config.get_handler().show_error(
                title="Git Stash Error",
                message="Failed to stash changes",
                details=str(e),
            )
        return GitStashResult.GIT_ERROR


def git_stash_list(
    repo: Repository, config: Optional[GitOperationConfig] = None
) -> List[str]:
    """List stashes in the repository.

    Args:
        repo: The repository to list stashes from.
        config: Configuration for the operation.

    Returns:
        List of stash references.
    """
    config = get_config(config)

    logger.info(f"Listing stashes in git repository: {repo.path}")
    try:
        stashes = repo.listall_stashes()
        stash_list = [f"stash@{{{i}}}: {message}" for i, message in enumerate(stashes)]

        logger.info(f"Stashes found: {len(stash_list)}")
        return stash_list

    except pygit2.GitError as e:
        logger.error(f"Failed to list stashes in the repository: {repo.path}: {e}")
        if config.notify_errors:
            config.get_handler().show_error(
                title="Git Stash List Error",
                message="Failed to list stashes",
                details=str(e),
            )
        return []


def git_stash_drop(
    repo: Repository,
    stash_index: int,
    config: Optional[GitOperationConfig] = None,
) -> GitStashResult:
    """Drop a stash from the repository.

    Args:
        repo: The repository to drop the stash from.
        stash_index: The index of the stash to drop.
        config: Configuration for the operation.

    Returns:
        Result of the drop operation.
    """
    config = get_config(config)

    logger.info(f"Dropping stash {stash_index} from git repository: {repo.path}")
    try:
        repo.stash_drop(stash_index)
        logger.info(f"Stash {stash_index} dropped successfully")
        return GitStashResult.STASH_DROPPED

    except pygit2.GitError as e:
        logger.error(f"Failed to drop stash in the repository: {repo.path}: {e}")
        if config.notify_errors:
            config.get_handler().show_error(
                title="Git Stash Drop Error",
                message="Failed to drop stash",
                details=str(e),
            )
        return GitStashResult.GIT_ERROR


def git_has_uncommitted_changes(
    repo: Repository, config: Optional[GitOperationConfig] = None
) -> bool:
    """Check if the repository has uncommitted changes.

    Args:
        repo: The repository to check for uncommitted changes.
        config: Configuration for the operation.

    Returns:
        True if there are uncommitted changes (staged or unstaged), False otherwise.
    """
    config = get_config(config)

    try:
        status = repo.status()

        # Fast check: if status is empty, no changes
        if not status:
            return False

        # Check if there are any changes (staged, unstaged, or untracked files)
        # Use bitwise operations for faster checking
        change_flags = (
            pygit2.GIT_STATUS_INDEX_NEW
            | pygit2.GIT_STATUS_INDEX_MODIFIED
            | pygit2.GIT_STATUS_INDEX_DELETED
            | pygit2.GIT_STATUS_INDEX_RENAMED
            | pygit2.GIT_STATUS_WT_NEW
            | pygit2.GIT_STATUS_WT_MODIFIED
            | pygit2.GIT_STATUS_WT_DELETED
            | pygit2.GIT_STATUS_WT_RENAMED
        )

        for filepath, flags in status.items():
            if flags & change_flags:
                logger.debug(f"Found uncommitted changes in: {filepath}")
                return True

        return False

    except pygit2.GitError as e:
        logger.error(f"Failed to check for uncommitted changes: {e}")
        if config.notify_errors:
            config.get_handler().show_error(
                title="Git Status Check Error",
                message="Failed to check for uncommitted changes",
                details=str(e),
            )
        return False


def git_is_repository(path: str | Path) -> bool:
    """Check if a path contains a git repository.

    Args:
        path: The path to check.

    Returns:
        True if the path contains a git repository, False otherwise.
    """
    try:
        repo_path = pygit2.discover_repository(str(path))
        return repo_path is not None
    except pygit2.GitError:
        return False


def git_get_current_branch(
    repo: Repository, config: Optional[GitOperationConfig] = None
) -> Optional[str]:
    """Get the current branch name.

    Args:
        repo: The repository to get the branch from.
        config: Configuration for the operation.

    Returns:
        The current branch name, or None if HEAD is detached or on error.
    """
    config = get_config(config)

    try:
        if repo.head_is_detached:
            logger.debug("Repository HEAD is detached")
            return None

        if repo.head_is_unborn:
            logger.debug("Repository has no commits yet")
            return None

        return repo.head.shorthand

    except pygit2.GitError as e:
        logger.debug(f"Failed to get current branch: {e}")
        return None


def git_get_remote_url(
    repo: Repository,
    remote_name: str = "origin",
    config: Optional[GitOperationConfig] = None,
) -> Optional[str]:
    """Get the URL of a remote.

    Args:
        repo: The repository to get the remote URL from.
        remote_name: The name of the remote.
        config: Configuration for the operation.

    Returns:
        The remote URL, or None if not found.
    """
    config = get_config(config)

    try:
        for remote in repo.remotes:
            if remote.name == remote_name:
                return remote.url

        logger.debug(f"Remote '{remote_name}' not found")
        return None

    except pygit2.GitError as e:
        logger.debug(f"Failed to get remote URL: {e}")
        return None


def git_is_clean(repo: Repository, config: Optional[GitOperationConfig] = None) -> bool:
    """Check if the working directory is clean (no uncommitted changes).

    Args:
        repo: The repository to check.
        config: Configuration for the operation.

    Returns:
        True if the working directory is clean, False otherwise.
    """
    return not git_has_uncommitted_changes(repo, config)

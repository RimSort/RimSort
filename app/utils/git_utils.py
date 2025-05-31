"""This module contains a collection of utility functions for working with git repositories."""

from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Generator, Optional, Protocol

import pygit2
from loguru import logger
from pygit2.enums import CheckoutStrategy, ResetMode, SortMode
from pygit2.remotes import Remote
from pygit2.repository import Repository
from PySide6.QtWidgets import QMessageBox

from app.utils.generic import delete_files_with_condition
from app.views.dialogue import InformationBox


class GitError(Exception):
    """Base exception for git operations."""

    pass


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
    if config is None:
        config = GitOperationConfig()

    logger.info(f"Attempting to discover git repository at: {path}")
    path_str = str(path)

    try:
        repo_path = pygit2.discover_repository(path_str)
        if repo_path is None:
            logger.info(f"No git repository found at: {path}")
            return None

        logger.info(f"Git repository found at: {repo_path}")
        return Repository(repo_path)

    except pygit2.GitError as e:
        logger.error(f"Failed to discover git repository at: {path}: {e}")
        if config.notify_errors:
            config.get_handler().show_error(
                title="Git Repository Discovery Error",
                message=f"Failed to discover git repository at: {path}",
                details=str(e),
            )
        return None


def git_get_repo_name(repo_url: str) -> str:
    """Gets the repository folder name if the url is cloned.

    :param repo_url: The URL of the repository.
    :type repo_url: str
    :return: The repository folder name. If the URL is not a valid git URL, returns an empty string.
    :rtype: str
    """
    try:
        return repo_url.split("/")[-1].split(".")[0]
    except Exception:
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
    if config is None:
        config = GitOperationConfig()

    logger.info(f"Attempting git cloning: {repo_url} to {repo_path}")
    repo_path_str = str(repo_path)
    repo_path_obj = Path(repo_path_str)

    # Validate path
    if repo_path_obj.exists() and not repo_path_obj.is_dir():
        error_msg = "The path is not a directory."
        logger.error(
            f"Failed to clone repository: {repo_url} to {repo_path} - {error_msg}"
        )
        if config.notify_errors:
            config.get_handler().show_error(
                title="Git Clone Error",
                message=f"Failed to clone repository: {repo_url} to {repo_path}",
                details=error_msg,
            )
        return None, GitCloneResult.PATH_NOT_DIR

    # Check if directory is empty
    if repo_path_obj.exists() and any(repo_path_obj.iterdir()):
        if not force:
            error_msg = f"The path is not empty: {repo_path}"
            logger.error(
                f"Failed to clone repository: {repo_url} to {repo_path} - {error_msg}"
            )
            if config.notify_errors:
                config.get_handler().show_error(
                    title="Git Clone Error",
                    message=f"Failed to clone repository: {repo_url} to {repo_path}",
                    details=error_msg,
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
        logger.error(f"Failed to clone repository: {repo_url} to {repo_path}: {e}")
        if config.notify_errors:
            config.get_handler().show_error(
                title="Git Clone Error",
                message=f"Failed to clone repository: {repo_url} to {repo_path}",
                details=str(e),
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
    if config is None:
        config = GitOperationConfig()

    logger.info(f"Checking for updates in git repository: {repo.path}")
    try:
        remote = repo.remotes["origin"]
        remote.fetch()
        local_oid = repo.head.target
        remote_oid = repo.references[
            f"refs/remotes/origin/{repo.head.shorthand}"
        ].target

        if local_oid == remote_oid:
            logger.info("No updates found in the repository.")
            return None

        logger.info("Updates found in the repository.")
        walker = repo.walk(remote_oid, SortMode.TOPOLOGICAL)
        walker.hide(local_oid)
        return walker

    except pygit2.GitError as e:
        logger.error(f"Failed to check for updates in the repository: {repo.path}: {e}")
        if config.notify_errors:
            config.get_handler().show_error(
                title="Git Update Check Error",
                message=f"Failed to check for updates in repository: {repo.path}",
                details=str(e),
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
    if config is None:
        config = GitOperationConfig()

    logger.info(f"Pulling updates from git repository: {repo.path}")

    if branch is None:
        branch = repo.head.shorthand

    for remote in repo.remotes:
        if remote.name != remote_name:
            continue

        try:
            remote.fetch()

            remote_master_id = repo.lookup_reference(
                f"refs/remotes/{remote.name}/{branch}"
            ).target

            merge_result, _ = repo.merge_analysis(remote_master_id)

            if merge_result & pygit2.enums.MergeAnalysis.UP_TO_DATE:
                logger.info("Repository is already up to date.")
                return GitPullResult.UP_TO_DATE

            repo_get = repo.get(remote_master_id)
            if repo_get is None:
                raise pygit2.GitError("Failed to get remote master id.")

            if force:
                logger.debug("Forcing merge operation.")
                repo.checkout_tree(repo_get, strategy=CheckoutStrategy.FORCE)
                repo.head.set_target(remote_master_id)
                logger.info("Repository updated successfully with force merge.")
                return GitPullResult.FORCE_CHECKOUT

            if reset_working_tree:
                logger.info("Resetting working tree.")
                repo.reset(repo.head.target, ResetMode.HARD)

            if merge_result & pygit2.enums.MergeAnalysis.FASTFORWARD:
                repo.checkout_tree(repo_get)
                repo.head.set_target(remote_master_id)
                logger.info("Repository updated successfully with fast-forward merge.")
                return GitPullResult.FAST_FORWARD

            elif merge_result & pygit2.enums.MergeAnalysis.NORMAL:
                repo.merge(remote_master_id)

                if repo.index.conflicts is not None:
                    logger.warning("Conflicts encountered during merge.")

                    for conflict in repo.index.conflicts:
                        try:
                            conflict_file = conflict[0]
                            path_value = getattr(conflict_file, "path", None)
                            if path_value:
                                logger.warning(f"Conflict found in: {path_value}")
                            else:
                                logger.warning("Conflict found in unknown file")
                        except Exception:
                            logger.warning("Conflict found in unknown file")

                    if config.notify_errors:
                        config.get_handler().show_error(
                            title="Git Merge Conflict",
                            message="Conflicts encountered during merge.",
                        )

                    return GitPullResult.CONFLICT
                else:
                    # No Conflicts merge
                    user = repo.default_signature
                    tree = repo.index.write_tree()
                    repo.create_commit(
                        "HEAD",
                        user,
                        user,
                        "Merge: %s" % (branch),
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
            logger.error(
                f"Failed to pull updates from the repository: {repo.path}: {e}"
            )
            raise

    logger.error(f"Remote not found in the repository: {repo.path}")
    return GitPullResult.UNKNOWN_REMOTE


def git_push(
    remote: Remote, refname: str, config: Optional[GitOperationConfig] = None
) -> bool:
    """Push updates to a git repository.

    Args:
        remote: The remote to push updates to.
        refname: The reference name to push.
        config: Configuration for the operation.

    Returns:
        Whether the push operation was successful.
    """
    if config is None:
        config = GitOperationConfig()

    logger.debug(f"Pushing updates to git repository: {remote.url}")

    try:
        remote.push([refname])
        logger.info(f"Updates pushed to the repository: {remote.url}")
        return True
    except pygit2.GitError as e:
        logger.error(f"Failed to push updates to the repository: {remote.url}: {e}")
        if config.notify_errors:
            config.get_handler().show_error(
                title="Git Push Error",
                message=f"Failed to push updates to the repository: {remote.url}",
                details=str(e),
            )
        return False


def git_stage_commit(
    repo: Repository,
    message: str,
    paths: Optional[list[str]] = None,
    all: bool = False,
    config: Optional[GitOperationConfig] = None,
) -> bool:
    """Stage and commit changes in a git repository.

    Args:
        repo: The repository to stage and commit changes in.
        message: The commit message.
        paths: The paths to stage.
        all: Whether to stage all changes.
        config: Configuration for the operation.

    Returns:
        Whether the stage and commit operation was successful.
    """
    if config is None:
        config = GitOperationConfig()
    if paths is None:
        paths = []

    logger.debug(f"Staging and committing changes in git repository: {repo.path}")

    try:
        index = repo.index
        if all:
            index.add_all()
        else:
            for path in paths:
                index.add(path)

        index.write()
        tree = index.write_tree()
        author = repo.default_signature
        committer = repo.default_signature
        repo.create_commit("HEAD", author, committer, message, tree, [repo.head.target])

        logger.info(f"Changes staged and committed in the repository: {repo.path}")
        return True
    except pygit2.GitError as e:
        logger.error(
            f"Failed to stage and commit changes in the repository: {repo.path}: {e}"
        )
        if config.notify_errors:
            config.get_handler().show_error(
                title="Git Stage and Commit Error",
                message=f"Failed to stage and commit changes in the repository: {repo.path}",
                details=str(e),
            )
        return False


def git_cleanup(repo: Repository) -> None:
    """Runs state cleanup and frees the repository object.

    :param repo: The repository to cleanup.
    :type repo: Repository
    """
    repo.state_cleanup()
    repo.free()
    logger.debug(f"Git repository cleaned up: {repo.path}")

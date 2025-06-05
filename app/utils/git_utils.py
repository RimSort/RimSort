"""This module contains a collection of utility functions for working with git repositories."""

from enum import Enum
from pathlib import Path

import pygit2
from loguru import logger
from pygit2.enums import CheckoutStrategy, ResetMode, SortMode
from pygit2.repository import Repository
from PySide6.QtWidgets import QMessageBox

from app.utils.generic import rmtree
from app.views.dialogue import InformationBox


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


def git_discover(path: str | Path, notify_errors: bool = True) -> Repository | None:
    """Helper function to discover a git repository at a given path.
    :param path: The path to discover the git repository.
    :type path: str | Path
    :param notify_errors: Whether to notify the user of any errors, defaults to True
    :type notify_errors: bool, optional
    :return: The repository object if found, otherwise None.
    :rtype: pygit2.repository.Repository | None
    """
    logger.info(f"Attempting to discover git repository at: {path}")
    if not isinstance(path, str):
        path = str(path)

    try:
        repo_path = pygit2.discover_repository(path)

        if repo_path is None:
            logger.info(f"No git repository found at: {path}")
            return None

        logger.info(f"Git repository found at: {repo_path}")
        return Repository(repo_path)
    except pygit2.GitError as e:
        logger.error(f"Failed to discover git repository at: {path}")
        logger.error(e)

        if notify_errors:
            InformationBox(
                title="Git Repository Discovery Error",
                text=f"Failed to discover git repository at: {path}",
                icon=QMessageBox.Icon.Critical,
                details=str(e),
            ).exec()

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
    checkout_branch: str | None = None,
    depth: int = 1,
    force: bool = False,
    notify_errors: bool = True,
) -> tuple[Repository | None, GitCloneResult]:
    """Helper function to clone a git repository.
    :param repo_url: The URL of the repository to clone.
    :type repo_url: str
    :param repo_path: The path to clone the repository to.
    :type repo_path: str | Path
    :param checkout_branch: The branch to checkout if any, defaults to None
    :type checkout_branch: str | None, optional
    :param depth: The clone depth, defaults to 1
    :type depth: int, optional
    :param force: Whether to force the clone operation, even if the path is not empty, defaults to False
    :type force: bool, optional
    :param notify_errors: Whether to notify the user of any errors, defaults to True
    :type notify_errors: bool, optional
    :return: The cloned repository object if successful, otherwise None.
    :rtype: pygit2.repository.Repository | None
    """
    logger.info(f"Attempting git cloning: {repo_url} to {repo_path}")
    if not isinstance(repo_path, str):
        repo_path = str(repo_path)

    repo_folder = git_get_repo_name(repo_url)
    full_repo_path = Path(repo_path) / repo_folder
    logger.debug(f"Inferred full local repository path: {full_repo_path}")

    # Ensure the path is a directory if it does exist
    if Path(full_repo_path).exists() and not Path(full_repo_path).is_dir():
        logger.error(f"Failed to clone repository: {repo_url} to {repo_path}")
        logger.error("The path is not a directory.")

        if notify_errors:
            InformationBox(
                title="Git Clone Error",
                text=f"Failed to clone repository: {repo_url} to {repo_path}",
                information="The path is not a directory.",
                icon=QMessageBox.Icon.Critical,
            ).exec()
        return None, GitCloneResult.PATH_NOT_DIR
    elif (
        Path(full_repo_path).exists() and len(list(Path(full_repo_path).iterdir())) > 0
    ):
        # Directory is not empty

        if not force:
            logger.error(f"Failed to clone repository: {repo_url} to {repo_path}")
            logger.error("The path is not empty.")

            if notify_errors:
                InformationBox(
                    title="Git Clone Error",
                    text=f"Failed to clone repository: {repo_url} to {repo_path}",
                    icon=QMessageBox.Icon.Critical,
                    details=f"The path is not empty: {full_repo_path}",
                ).exec()
            return None, GitCloneResult.PATH_NOT_EMPTY
        else:
            # Force the clone operation by deleting the directory
            logger.warning(
                f"Force cloning repository by deleting the local directory: {full_repo_path}"
            )
            success = rmtree(full_repo_path)
            if not success:
                logger.error(f"Failed to delete the local directory: {full_repo_path}")
                return None, GitCloneResult.PATH_DELETE_ERROR

    try:
        return pygit2.clone_repository(
            repo_url, repo_path, checkout_branch=checkout_branch, depth=depth
        ), GitCloneResult.CLONED
    except pygit2.GitError as e:
        logger.error(f"Failed to clone repository: {repo_url} to {repo_path}")
        logger.error(e)

        if notify_errors:
            InformationBox(
                title="Git Clone Error",
                text=f"Failed to clone repository: {repo_url} to {repo_path}",
                icon=QMessageBox.Icon.Critical,
                details=str(e),
            ).exec()
    return None, GitCloneResult.GIT_ERROR


def git_check_updates(
    repo: Repository, notify_errors: bool = True
) -> pygit2.Walker | None:
    """Helper function to check for updates in a git repository in the current branch.

    :param repo: The repository to check for updates in.
    :type repo: Repository
    :param notify_errors: Whether to notify the user of any errors, defaults to True
    :type notify_errors: bool, optional
    :return: A walker object if updates are found, otherwise None.
    """
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
        walker = repo.walk(local_oid, SortMode.TOPOLOGICAL)
        return walker
    except pygit2.GitError as e:
        logger.error(f"Failed to check for updates in the repository: {repo.path}")
        logger.error(e)

        if notify_errors:
            InformationBox(
                title="Git Update Check Error",
                text=f"Failed to check for updates in the repository: {repo.path}",
                icon=QMessageBox.Icon.Critical,
                details=str(e),
            ).exec()

    return None


def git_pull(
    repo: Repository,
    remote_name: str = "origin",
    branch: str | None = None,
    reset_working_tree: bool = True,
    force: bool = False,
    notify_errors: bool = True,
) -> GitPullResult:
    """Helper function to pull updates from a git repository.

    :param repo: The repository to pull updates from.
    :type repo: Repository
    :param remote_name: The name of the remote to pull from, defaults to "origin"
    :type remote_name: str, optional
    :param branch: The branch to pull from, defaults to None
    :type branch: str | None, optional
    :param reset_working_tree: Whether to discard uncommitted changes, defaults to True
    :type reset_working_tree: bool, optional
    :param force: Whether to force the pull operation via forced checkout, defaults to False
    :type force: bool, optional
    :param notify_errors: Whether to notify the user of any errors, defaults to True
    :type notify_errors: bool, optional
    :return: Whether the pull operation was successful, including if the repo was already up to date."""
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

            if merge_result & pygit2.GIT_MERGE_ANALYSIS_UP_TO_DATE:
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

            if merge_result & pygit2.GIT_MERGE_ANALYSIS_FASTFORWARD:
                repo.checkout_tree(repo_get)
                repo.head.set_target(remote_master_id)
                logger.info("Repository updated successfully with fast-forward merge.")
                return GitPullResult.FAST_FORWARD

            elif merge_result & pygit2.GIT_MERGE_ANALYSIS_NORMAL:
                repo.merge(remote_master_id)

                if repo.index.conflicts is not None:
                    logger.warning("Conflicts encountered during merge.")

                    for conflict in repo.index.conflicts:
                        logger.warning(f"Conflict found in: {conflict[0].path}")

                    if notify_errors:
                        InformationBox(
                            title="Git Merge Conflict",
                            text="Conflicts encountered during merge.",
                            icon=QMessageBox.Icon.Critical,
                            details=str(repo.index.conflicts),
                        ).exec()

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
            logger.error(f"Failed to pull updates from the repository: {repo.path}")
            logger.error(e)

            if notify_errors:
                InformationBox(
                    title="Git Pull Error",
                    text=f"Failed to pull updates from the repository: {repo.path}",
                    icon=QMessageBox.Icon.Critical,
                    details=str(e),
                ).exec()

            return GitPullResult.GIT_ERROR

    logger.error(f"Remote not found in the repository: {repo.path}")
    return GitPullResult.UNKNOWN_REMOTE


def git_push(remote: pygit2.Remote, refname: str, notify_errors: bool = True) -> bool:
    """Helper function to push updates to a git repository.

    :param remote: The remote to push updates to.
    :type remote: pygit2.Remote
    :param notify_errors: Whether to notify the user of any errors, defaults to True
    :type notify_errors: bool, optional
    :return: Whether the push operation was successful."""
    logger.debug(f"Pushing updates to git repository: {remote.url}")

    try:
        remote.push([refname])
        logger.info(f"Updates pushed to the repository: {remote.url}")
        return True
    except pygit2.GitError as e:
        logger.error(f"Failed to push updates to the repository: {remote.url}")
        logger.error(e)

        if notify_errors:
            InformationBox(
                title="Git Push Error",
                text=f"Failed to push updates to the repository: {remote.url}",
                icon=QMessageBox.Icon.Critical,
                details=str(e),
            ).exec()
        return False


def git_stage_commit(
    repo: Repository,
    message: str,
    paths: list[str] = [],
    all: bool = False,
    notify_errors: bool = True,
) -> bool:
    """Helper function to stage and commit changes in a git repository.

    :param repo: The repository to stage and commit changes in.
    :type repo: Repository
    :param message: The commit message.
    :type message: str
    :param paths: The paths to stage, defaults to []
    :type paths: list[str], optional
    :param all: Whether to stage all changes, defaults to False
    :type all: bool, optional
    :param notify_errors: Whether to notify the user of any errors, defaults to True
    :type notify_errors: bool, optional
    :return: Whether the stage and commit operation was successful."""
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
            f"Failed to stage and commit changes in the repository: {repo.path}"
        )
        logger.error(e)

        if notify_errors:
            InformationBox(
                title="Git Stage and Commit Error",
                text=f"Failed to stage and commit changes in the repository: {repo.path}",
                icon=QMessageBox.Icon.Critical,
                details=str(e),
            ).exec()
        return False


def git_cleanup(repo: Repository) -> None:
    """Runs state cleanup and frees the repository object.

    :param repo: The repository to cleanup.
    :type repo: Repository
    """
    repo.state_cleanup()
    repo.free()
    logger.debug(f"Git repository cleaned up: {repo.path}")

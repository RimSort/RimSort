from pathlib import Path

from dulwich import porcelain
from dulwich.client import FetchPackResult
from dulwich.repo import Repo
from loguru import logger

from app.utils.generic import delete_file_dir


def git_discover(path: str | Path) -> Repo | None:
    """Discover the git repository at the given path if it exists.

    :param path: The path to the repository.
    :type path: str | Path
    :return: The repository object if it exists, otherwise None.
    :rtype: Repo |None
    """

    str_path = str(path)
    if not Path(str_path).exists():
        return None

    try:
        repo = Repo(str_path)
        logger.debug(f"Discovered git repository at {str_path}")
        return repo
    except Exception:
        return None


def git_get_repo_name(repo_url: str) -> str | None:
    """Gets the repository folder name if the url is cloned.
    :param repo_url: The URL of the repository.
    :type repo_url: str
    :return: The repository folder name. If the URL is not a valid git URL, returns None.
    :rtype: str | None
    """
    try:
        return repo_url.split("/")[-1].split(".")[0]
    except Exception:
        return None


def git_clone(
    source: str,
    repo_path: str | Path,
    branch: str | None = None,
    depth: int = 1,
    force: bool = False,
) -> Repo | None:
    """Clone a git repository to the given path.

    :param source: The URL of the repository.
    :type source: str
    :param repo_path: The path to clone the repository to.
    :type repo_path: str | Path
    :param branch: The branch to checkout after cloning.
    :type branch: str | None
    :param depth: The depth of the clone.
    :type depth: int
    :param force: If True, force the clone even if the path already exists.
    :type force: bool
    :return: The repository object if the clone was successful, otherwise None.
    :rtype: Repo | None
    """
    logger.info(f"Attempting git cloning: {source} to {repo_path}")
    if not isinstance(repo_path, str):
        repo_path = str(repo_path)

    repo_folder = git_get_repo_name(source)

    if repo_folder is None:
        logger.error(f"Invalid git URL: {source}")
        raise ValueError(f"Invalid git URL: {source}")

    full_repo_path = Path(repo_path) / repo_folder
    logger.debug(f"Inferred full local repository path: {full_repo_path}")

    # Check and cleanup path if needed
    if Path(full_repo_path).exists() and (
        not Path(full_repo_path).is_dir()
        or len(list(Path(full_repo_path).iterdir())) > 0
    ):
        if not force:
            logger.error(
                f"Git clone target path {full_repo_path} already exists and is not an empty directory directory."
            )
            raise FileExistsError(
                f"Git clone target path {full_repo_path} already exists and is not an emptry directory."
            )

        logger.warning(
            f"Force cloning repository to {full_repo_path} by deleting the existing file/directory with the same name."
        )
        success = delete_file_dir(full_repo_path)

        if not success:
            logger.error(
                f"Failed to delete existing file/directory at {full_repo_path}."
            )
            raise IOError(
                f"Failed to delete existing file/directory at {full_repo_path}."
            )

    return porcelain.clone(
        source, full_repo_path, depth=depth, branch=branch, checkout=True
    )


def git_check_update(repo: Repo) -> FetchPackResult:
    """Check if the repository has any updates without pulling them.

    :param repo: The repository object.

    :return: The result of the fetch operation."""
    logger.info(f"Checking for updates in repository at {repo.path}")
    return porcelain.fetch(repo, repo.path)  # type: ignore


def git_pull(repo: Repo, force: bool = False) -> FetchPackResult:
    """Pull the latest changes from the repository.

    :param repo: The repository object.

    :return: The result of the pull operation."""
    logger.info(f"Pulling latest changes in repository at {repo.path}")
    return porcelain.pull(repo, repo.path, force=force)  # type: ignore


def git_push(repo: Repo, force: bool = False) -> FetchPackResult:
    """Push the latest changes to the repository.

    :param repo: The repository object.

    :return: The result of the push operation."""
    logger.info(f"Pushing latest changes in repository at {repo.path}")
    return porcelain.push(repo, repo.path, force=force)  # type: ignore


def git_stage_commit(repo: Repo, message: str) -> None:
    """Stage and commit all changes in the repository.

    :param repo: The repository object.
    :param message: The commit message.
    """
    logger.info(f"Staging and committing changes in repository at {repo.path}")
    porcelain.add(repo, repo.path)  # type: ignore
    porcelain.commit(repo, message)  # type: ignore
    logger.info(f"Committed changes in repository at {repo.path}")


def git_repo_cleanup(repo: Repo) -> None:
    """Cleans up the repository object.

    :param repo: The repository object.
    """
    repo.close()  # type: ignore
    logger.info(f"Cleaned up repository at {repo.path}")

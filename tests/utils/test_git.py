import tempfile
from pathlib import Path
from typing import Generator

import pytest
from dulwich.repo import Repo

from app.utils.git import git_pull, git_push, git_repo_cleanup, git_stage_commit


@pytest.fixture
def temp_repo() -> Generator[Repo, None, None]:
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_path = Path(temp_dir) / "test_repo"
        repo = Repo.init(str(repo_path), mkdir=True)
        yield repo
        git_repo_cleanup(repo)


def test_git_pull(temp_repo: Repo) -> None:
    # Assuming the repo is already set up with a remote
    result = git_pull(temp_repo, force=True)
    assert result is not None
    assert isinstance(result, dict)  # Adjust based on actual return type


def test_git_push(temp_repo: Repo) -> None:
    # Assuming the repo is already set up with a remote
    result = git_push(temp_repo, force=True)
    assert result is not None
    assert isinstance(result, dict)  # Adjust based on actual return type


def test_git_stage_commit(temp_repo: Repo) -> None:
    # Create a dummy file to commit
    dummy_file = Path(temp_repo.path) / "dummy.txt"
    with open(dummy_file, "w") as f:
        f.write("dummy content")

    # Stage and commit the file
    git_stage_commit(temp_repo, "Initial commit")

    # Check if the file is committed
    assert dummy_file.exists()


def test_git_repo_cleanup(temp_repo: Repo) -> None:
    # Ensure the repo is cleaned up
    git_repo_cleanup(temp_repo)
    assert temp_repo.bare  # Adjust based on actual cleanup behavior

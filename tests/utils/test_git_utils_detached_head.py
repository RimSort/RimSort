"""Regression tests: checking/pulling updates for a repo with a detached HEAD.

Before the fix, ``repo.head.shorthand`` was ``"HEAD"`` for a detached HEAD, so
the code looked up ``refs/remotes/origin/HEAD`` — a symbolic ref whose
``target`` is the string ``"refs/remotes/origin/master"`` rather than an Oid.
``repo.walk()`` then raised ``InvalidError('refs/remotes/origin/master')`` and
every git mod showed a "Git Pull Error" with that ref name as the only detail.
"""

import subprocess
from pathlib import Path

import pytest

from app.utils.git_utils import GitPullResult, git_check_updates, git_pull
from app.utils.pygit2_loader import Repository


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.fixture
def detached_clone(tmp_path: Path) -> tuple[Path, Path]:
    """An upstream with 3 commits and a clone detached at commit 1, fetched."""
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    _git(upstream, "init", "-q", "-b", "master")
    for i in range(2):
        (upstream / "About.xml").write_text(f"v{i}")
        _git(upstream, "add", ".")
        _git(upstream, "commit", "-q", "-m", f"c{i}")

    clone = tmp_path / "clone"
    _git(tmp_path, "clone", "-q", str(upstream), str(clone))
    _git(clone, "checkout", "-q", "HEAD~1")  # detach

    (upstream / "About.xml").write_text("v2")
    _git(upstream, "commit", "-q", "-am", "c2")
    _git(clone, "fetch", "-q")
    return upstream, clone


def test_check_updates_with_detached_head(detached_clone: tuple[Path, Path]) -> None:
    _, clone = detached_clone
    repo = Repository(str(clone))
    assert repo.head_is_detached

    walker = git_check_updates(repo)

    assert walker is not None
    assert [c.message.strip() for c in walker] == ["c2", "c1"]


def test_pull_with_detached_head_reattaches_and_updates(
    detached_clone: tuple[Path, Path],
) -> None:
    upstream, clone = detached_clone
    repo = Repository(str(clone))

    result = git_pull(repo, force=True)

    assert result == GitPullResult.FORCE_CHECKOUT
    assert not repo.head_is_detached
    assert repo.head.shorthand == "master"
    assert _git(clone, "rev-parse", "HEAD") == _git(upstream, "rev-parse", "HEAD")
    assert (clone / "About.xml").read_text() == "v2"


def test_check_updates_attached_head_unchanged(
    detached_clone: tuple[Path, Path],
) -> None:
    _, clone = detached_clone
    _git(clone, "checkout", "-q", "master")
    _git(clone, "reset", "-q", "--hard", "origin/master")
    repo = Repository(str(clone))

    assert git_check_updates(repo) is None

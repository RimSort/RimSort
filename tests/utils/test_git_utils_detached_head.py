"""Regression tests: checking/pulling updates for a repo with a detached HEAD.

Before the fix, ``repo.head.shorthand`` was ``"HEAD"`` for a detached HEAD, so
the code looked up ``refs/remotes/origin/HEAD`` — a symbolic ref whose
``target`` is the string ``"refs/remotes/origin/master"`` rather than an Oid.
``repo.walk()`` then raised ``InvalidError('refs/remotes/origin/master')`` and
every git mod showed a "Git Pull Error" with that ref name as the only detail.

Repositories are built with pygit2 only (no ``git`` executable is needed).
"""

from pathlib import Path

import pytest

from app.utils.git_utils import GitPullResult, git_check_updates, git_pull
from app.utils.pygit2_loader import Repository, pygit2

SIG = pygit2.Signature("t", "t@t")


def _commit_file(repo: Repository, content: str, message: str) -> pygit2.Oid:
    """Write About.xml with ``content`` and commit it on the current branch."""
    Path(repo.workdir, "About.xml").write_text(content)
    repo.index.add("About.xml")
    repo.index.write()
    tree = repo.index.write_tree()
    parents = [] if repo.head_is_unborn else [repo.head.target]
    return repo.create_commit("HEAD", SIG, SIG, message, tree, parents)


@pytest.fixture
def detached_clone(tmp_path: Path) -> tuple[Repository, Repository]:
    """An upstream with 3 commits and a clone detached at commit 1, fetched."""
    pygit2.init_repository(str(tmp_path / "upstream"), initial_head="master")
    upstream = Repository(str(tmp_path / "upstream"))
    _commit_file(upstream, "v0", "c0")
    _commit_file(upstream, "v1", "c1")

    pygit2.clone_repository(str(tmp_path / "upstream"), str(tmp_path / "clone"))
    clone = Repository(str(tmp_path / "clone"))
    first = clone.revparse_single("HEAD~1")
    clone.checkout_tree(first, strategy=pygit2.enums.CheckoutStrategy.FORCE)
    clone.set_head(first.id)  # detach

    _commit_file(upstream, "v2", "c2")
    clone.remotes["origin"].fetch()
    return upstream, clone


def test_check_updates_with_detached_head(
    detached_clone: tuple[Repository, Repository],
) -> None:
    _, clone = detached_clone
    assert clone.head_is_detached

    walker = git_check_updates(clone)

    assert walker is not None
    assert [c.message.strip() for c in walker] == ["c2", "c1"]


def test_pull_with_detached_head_reattaches_and_updates(
    detached_clone: tuple[Repository, Repository],
) -> None:
    upstream, clone = detached_clone

    result = git_pull(clone, force=True)

    assert result == GitPullResult.FORCE_CHECKOUT
    assert not clone.head_is_detached
    assert clone.head.shorthand == "master"
    assert clone.head.target == upstream.head.target
    assert Path(clone.workdir, "About.xml").read_text() == "v2"


def test_check_updates_attached_head_unchanged(
    detached_clone: tuple[Repository, Repository],
) -> None:
    _, clone = detached_clone
    remote_oid = clone.references["refs/remotes/origin/master"].target
    clone.branches.local["master"].set_target(remote_oid)
    clone.set_head("refs/heads/master")
    clone.reset(remote_oid, pygit2.enums.ResetMode.HARD)

    assert git_check_updates(clone) is None

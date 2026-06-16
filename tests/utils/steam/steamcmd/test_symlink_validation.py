import os
from pathlib import Path

import pytest

from app.utils.symlink import resolve_symlink_target


class TestResolveSymlinkTarget:
    def test_valid_symlink_returns_target(self, tmp_path: Path) -> None:
        target = tmp_path / "target_dir"
        target.mkdir()
        link = tmp_path / "link"
        os.symlink(str(target), str(link))

        result = resolve_symlink_target(str(link))
        assert result == str(target)

    def test_dangling_symlink_returns_none(self, tmp_path: Path) -> None:
        target = tmp_path / "nonexistent"
        link = tmp_path / "link"
        os.symlink(str(target), str(link))

        result = resolve_symlink_target(str(link))
        assert result is None

    def test_not_a_symlink_returns_none(self, tmp_path: Path) -> None:
        regular_dir = tmp_path / "regular"
        regular_dir.mkdir()

        result = resolve_symlink_target(str(regular_dir))
        assert result is None

    def test_nonexistent_path_returns_none(self, tmp_path: Path) -> None:
        result = resolve_symlink_target(str(tmp_path / "nope"))
        assert result is None

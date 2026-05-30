import os
import sys
from pathlib import Path

import pytest

from app.utils.symlink import (
    SymlinkCreationError,
    SymlinkDstIsFileError,
    SymlinkDstNotEmptyError,
    SymlinkDstParentNotExistError,
    SymlinkSrcNotDirError,
    SymlinkSrcNotExistError,
    create_symlink,
    is_junction_or_link,
)


class TestExceptions:
    def test_base_exception_stores_paths(self) -> None:
        err = SymlinkCreationError("msg", "/src", "/dst")
        assert err.src_path == Path("/src")
        assert err.dst_path == Path("/dst")
        assert str(err) == "msg"

    def test_subclass_hierarchy(self) -> None:
        assert issubclass(SymlinkDstNotEmptyError, SymlinkCreationError)
        assert issubclass(SymlinkDstIsFileError, SymlinkCreationError)
        assert issubclass(SymlinkSrcNotExistError, SymlinkCreationError)
        assert issubclass(SymlinkSrcNotDirError, SymlinkCreationError)
        assert issubclass(SymlinkDstParentNotExistError, SymlinkCreationError)


class TestIsJunctionOrLink:
    def test_regular_file_returns_false(self, tmp_path: Path) -> None:
        f = tmp_path / "file.txt"
        f.write_text("data")
        assert is_junction_or_link(f) is False

    def test_regular_dir_returns_false(self, tmp_path: Path) -> None:
        d = tmp_path / "dir"
        d.mkdir()
        assert is_junction_or_link(d) is False

    def test_symlink_returns_true(self, tmp_path: Path) -> None:
        target = tmp_path / "target"
        target.mkdir()
        link = tmp_path / "link"
        os.symlink(target, link)
        assert is_junction_or_link(link) is True

    def test_nonexistent_returns_false(self, tmp_path: Path) -> None:
        assert is_junction_or_link(tmp_path / "nope") is False


@pytest.mark.skipif(sys.platform == "win32", reason="Unix symlink tests")
class TestCreateSymlink:
    def test_basic_symlink_creation(self, tmp_path: Path) -> None:
        src = tmp_path / "source"
        src.mkdir()
        dst = tmp_path / "link"
        create_symlink(str(src), str(dst))
        assert dst.is_symlink()
        assert os.readlink(dst) == str(src)

    def test_src_not_exist_raises(self, tmp_path: Path) -> None:
        with pytest.raises(SymlinkSrcNotExistError):
            create_symlink(str(tmp_path / "missing"), str(tmp_path / "link"))

    def test_src_is_file_raises(self, tmp_path: Path) -> None:
        src = tmp_path / "file.txt"
        src.write_text("data")
        with pytest.raises(SymlinkSrcNotDirError):
            create_symlink(str(src), str(tmp_path / "link"))

    def test_dst_existing_symlink_recreated(self, tmp_path: Path) -> None:
        src1 = tmp_path / "src1"
        src1.mkdir()
        src2 = tmp_path / "src2"
        src2.mkdir()
        dst = tmp_path / "link"
        os.symlink(src1, dst)
        create_symlink(str(src2), str(dst))
        assert os.readlink(dst) == str(src2)

    def test_dst_empty_dir_removed(self, tmp_path: Path) -> None:
        src = tmp_path / "source"
        src.mkdir()
        dst = tmp_path / "dest"
        dst.mkdir()
        create_symlink(str(src), str(dst))
        assert dst.is_symlink()

    def test_dst_nonempty_dir_raises_without_force(self, tmp_path: Path) -> None:
        src = tmp_path / "source"
        src.mkdir()
        dst = tmp_path / "dest"
        dst.mkdir()
        (dst / "file.txt").write_text("content")
        with pytest.raises(SymlinkDstNotEmptyError):
            create_symlink(str(src), str(dst))

    def test_dst_nonempty_dir_force(self, tmp_path: Path) -> None:
        src = tmp_path / "source"
        src.mkdir()
        dst = tmp_path / "dest"
        dst.mkdir()
        (dst / "file.txt").write_text("content")
        create_symlink(str(src), str(dst), force=True)
        assert dst.is_symlink()

    def test_dst_is_file_raises_without_force(self, tmp_path: Path) -> None:
        src = tmp_path / "source"
        src.mkdir()
        dst = tmp_path / "dest_file"
        dst.write_text("data")
        with pytest.raises(SymlinkDstIsFileError):
            create_symlink(str(src), str(dst))

    def test_dst_is_file_force(self, tmp_path: Path) -> None:
        src = tmp_path / "source"
        src.mkdir()
        dst = tmp_path / "dest_file"
        dst.write_text("data")
        create_symlink(str(src), str(dst), force=True)
        assert dst.is_symlink()

    def test_dst_parent_not_exist_raises(self, tmp_path: Path) -> None:
        src = tmp_path / "source"
        src.mkdir()
        with pytest.raises(SymlinkDstParentNotExistError):
            create_symlink(str(src), str(tmp_path / "deep" / "nested" / "link"))

    def test_dst_parent_not_exist_force_creates_parents(self, tmp_path: Path) -> None:
        src = tmp_path / "source"
        src.mkdir()
        dst = tmp_path / "deep" / "nested" / "link"
        create_symlink(str(src), str(dst), force=True)
        assert dst.is_symlink()

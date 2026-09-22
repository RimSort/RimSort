"""Tests for app.utils.platform.windows directory entry helpers."""

from pathlib import Path

from app.utils.platform.windows import WIN32_FIND_DATAW, Win32DirEntry

FILE_ATTRIBUTE_DIRECTORY = 0x10
FILE_ATTRIBUTE_REPARSE_POINT = 0x400


def _make_entry(attributes: int, name: str = "entry") -> Win32DirEntry:
    """Build a Win32DirEntry with the given file attributes."""
    find_data = WIN32_FIND_DATAW()
    find_data.dwFileAttributes = attributes
    find_data.cFileName = name
    return Win32DirEntry(Path("C:/mods/mod"), find_data)


class TestWin32DirEntry:
    def test_plain_directory(self) -> None:
        entry = _make_entry(FILE_ATTRIBUTE_DIRECTORY)
        assert entry.is_dir() is True
        assert entry.is_file() is False
        assert entry.is_reparse_point() is False

    def test_plain_file(self) -> None:
        entry = _make_entry(0)
        assert entry.is_dir() is False
        assert entry.is_file() is True
        assert entry.is_reparse_point() is False

    def test_junction_directory_is_reparse_point(self) -> None:
        entry = _make_entry(FILE_ATTRIBUTE_DIRECTORY | FILE_ATTRIBUTE_REPARSE_POINT)
        assert entry.is_dir() is True
        assert entry.is_reparse_point() is True

    def test_reparse_point_file(self) -> None:
        entry = _make_entry(FILE_ATTRIBUTE_REPARSE_POINT)
        assert entry.is_file() is True
        assert entry.is_reparse_point() is True

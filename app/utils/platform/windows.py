import ctypes
import sys
from collections import namedtuple
from ctypes import wintypes
from pathlib import Path
from typing import Any, Generator

from loguru import logger


class WIN32_FIND_DATAW(ctypes.Structure):
    _fields_ = [
        ("dwFileAttributes", wintypes.DWORD),
        ("ftCreationTime", wintypes.FILETIME),
        ("ftLastAccessTime", wintypes.FILETIME),
        ("ftLastWriteTime", wintypes.FILETIME),
        ("nFileSizeHigh", wintypes.DWORD),
        ("nFileSizeLow", wintypes.DWORD),
        ("dwReserved0", wintypes.DWORD),
        ("dwReserved1", wintypes.DWORD),
        ("cFileName", wintypes.WCHAR * 260),
        ("cAlternateFileName", wintypes.WCHAR * 14),
    ]


class Win32DirEntry:
    def __init__(self, path: Path, find_data: WIN32_FIND_DATAW):
        self.name = find_data.cFileName
        self.path = str(path / self.name)
        self.size = (find_data.nFileSizeHigh << 32) + find_data.nFileSizeLow
        self._dwFileAttributes = find_data.dwFileAttributes
        self.FILE_ATTRIBUTE_DIRECTORY = 0x10

    def is_dir(self) -> bool:
        return bool(self._dwFileAttributes & self.FILE_ATTRIBUTE_DIRECTORY)

    def is_file(self) -> bool:
        return not self.is_dir()

    def stat(self) -> Any:
        _Win32StatResult = namedtuple("_Win32StatResult", ["st_size"])
        return _Win32StatResult(self.size)


def scanpath_win32(path: Path | str) -> Generator[Win32DirEntry, None, None]:
    """Windows-specific scanpath implementation using Win32 API."""
    if sys.platform != "win32":
        return
    try:
        INVALID_HANDLE_VALUE = -1

        find_data = WIN32_FIND_DATAW()
        kernel32 = ctypes.windll.kernel32

        # Define function prototypes
        kernel32.FindFirstFileW.argtypes = [
            wintypes.LPCWSTR,
            ctypes.POINTER(WIN32_FIND_DATAW),
        ]
        kernel32.FindFirstFileW.restype = wintypes.HANDLE
        kernel32.FindNextFileW.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(WIN32_FIND_DATAW),
        ]
        kernel32.FindNextFileW.restype = wintypes.BOOL
        kernel32.FindClose.argtypes = [wintypes.HANDLE]
        kernel32.FindClose.restype = wintypes.BOOL

        p = Path(path)

        handle = kernel32.FindFirstFileW(str(p / "*"), ctypes.byref(find_data))

        if handle == INVALID_HANDLE_VALUE:
            last_error = ctypes.get_last_error()
            if last_error != 2:  # File not found
                raise ctypes.WinError(last_error)
            return

        try:
            while True:
                if find_data.cFileName not in (".", ".."):
                    yield Win32DirEntry(p, find_data)
                if not kernel32.FindNextFileW(handle, ctypes.byref(find_data)):
                    last_error = ctypes.get_last_error()
                    if last_error in (0, 18):  # No more files
                        return
                    else:
                        raise ctypes.WinError(last_error)
        finally:
            kernel32.FindClose(handle)
    except OSError as e:
        logger.error(f"An unexpected Win32 API error for scanpath occurred: {e}")
        raise

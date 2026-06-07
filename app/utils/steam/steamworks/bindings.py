"""
ctypes bindings for the rimsort_steam native library.

Loads the compiled C++ shim and declares type-safe interfaces for all
exported functions and callback structs. If the native library is not
found, _lib is set to None and the wrapper layer handles graceful
degradation.

The loaded library is exposed as module-level ``_lib`` for monkeypatching
in tests.
"""

import ctypes
import platform
import sys
from pathlib import Path

from loguru import logger

# --------------------------------------------------------------------------- #
# Struct definitions -- field order MUST match the C++ shim / SDK layout       #
# --------------------------------------------------------------------------- #


class SubscriptionResult(ctypes.Structure):
    """Result struct for subscribe/unsubscribe callbacks."""

    _fields_ = [
        ("result", ctypes.c_int32),
        ("published_file_id", ctypes.c_uint64),
    ]


class GetAppDependenciesResult(ctypes.Structure):
    """Result struct for GetAppDependencies callback."""

    _fields_ = [
        ("result", ctypes.c_int32),
        ("published_file_id", ctypes.c_uint64),
        ("array_app_dependencies", ctypes.POINTER(ctypes.c_uint32)),
        ("array_num_app_dependencies", ctypes.c_uint32),
        ("total_num_app_dependencies", ctypes.c_uint32),
    ]

    def get_app_dependencies_list(self) -> list[int]:
        """Extract the dependency array as a Python list."""
        return [
            self.array_app_dependencies[i]
            for i in range(self.array_num_app_dependencies)
        ]


class DownloadItemResult(ctypes.Structure):
    """Result struct for DownloadItem callback."""

    _fields_ = [
        ("app_id", ctypes.c_uint32),
        ("published_file_id", ctypes.c_uint64),
        ("result", ctypes.c_int32),
    ]


class ItemInstalledResult(ctypes.Structure):
    """Result struct for ItemInstalled callback."""

    _fields_ = [
        ("app_id", ctypes.c_uint32),
        ("published_file_id", ctypes.c_uint64),
        ("legacy_content", ctypes.c_uint64),
        ("manifest_id", ctypes.c_uint64),
    ]


# --------------------------------------------------------------------------- #
# Callback function pointer types                                              #
# --------------------------------------------------------------------------- #

SubscriptionCallback = ctypes.CFUNCTYPE(None, SubscriptionResult)
AppDepsCallback = ctypes.CFUNCTYPE(None, GetAppDependenciesResult)
DownloadItemResultCallback = ctypes.CFUNCTYPE(None, DownloadItemResult)
ItemInstalledCallback = ctypes.CFUNCTYPE(None, ItemInstalledResult)

# --------------------------------------------------------------------------- #
# Library loading                                                              #
# --------------------------------------------------------------------------- #

_SYSTEM = platform.system()
_LIB_NAMES = {
    "Darwin": "rimsort_steam.dylib",
    "Linux": "rimsort_steam.so",
    "Windows": "rimsort_steam.dll",
}


def _resolve_library_path() -> Path:
    """
    Resolve the path to the rimsort_steam native library.

    :return: Path to the native library file
    :raises OSError: If the library cannot be found or the platform is unsupported
    """
    lib_name = _LIB_NAMES.get(_SYSTEM)
    if lib_name is None:
        raise OSError(f"Unsupported platform: {_SYSTEM}")

    paths_checked: list[Path] = []

    # Nuitka compiled build -- library is adjacent to the executable
    if "__compiled__" in globals():
        exe_dir = Path(sys.argv[0]).resolve().parent
        candidate = exe_dir / lib_name
        paths_checked.append(candidate)
        if candidate.exists():
            return candidate

    # Running from source -- look in libs/
    source_root = (
        Path(__file__).resolve().parents[4]
    )  # app/utils/steam/steamworks -> root
    candidate = source_root / "libs" / lib_name
    paths_checked.append(candidate)
    if candidate.exists():
        return candidate

    checked_str = ", ".join(str(p) for p in paths_checked)
    raise OSError(
        f"Could not find {lib_name}. Checked: {checked_str}. "
        f"See libs/rimsort_steam/README.md for build instructions."
    )


def _load_library() -> ctypes.CDLL | None:
    """
    Load the native library and declare all function signatures.

    :return: Loaded CDLL instance, or None if the library is not found (non-fatal)
    """
    try:
        lib_path = _resolve_library_path()
    except OSError as e:
        logger.warning(f"rimsort_steam native library not available: {e}")
        return None

    lib = ctypes.CDLL(str(lib_path))

    # Lifecycle
    lib.RS_SteamAPI_Init.restype = ctypes.c_int
    lib.RS_SteamAPI_Init.argtypes = []

    lib.RS_SteamAPI_Shutdown.restype = None
    lib.RS_SteamAPI_Shutdown.argtypes = []

    lib.RS_SteamAPI_RunCallbacks.restype = None
    lib.RS_SteamAPI_RunCallbacks.argtypes = []

    lib.RS_SteamAPI_IsInitialized.restype = ctypes.c_bool
    lib.RS_SteamAPI_IsInitialized.argtypes = []

    # Workshop
    lib.RS_Workshop_SubscribeItem.restype = None
    lib.RS_Workshop_SubscribeItem.argtypes = [ctypes.c_uint64]

    lib.RS_Workshop_UnsubscribeItem.restype = None
    lib.RS_Workshop_UnsubscribeItem.argtypes = [ctypes.c_uint64]

    lib.RS_Workshop_GetAppDependencies.restype = None
    lib.RS_Workshop_GetAppDependencies.argtypes = [ctypes.c_uint64]

    lib.RS_Workshop_DownloadItem.restype = ctypes.c_bool
    lib.RS_Workshop_DownloadItem.argtypes = [ctypes.c_uint64, ctypes.c_bool]

    # Callback registration
    lib.RS_Workshop_SetItemSubscribedCallback.restype = None
    lib.RS_Workshop_SetItemSubscribedCallback.argtypes = [SubscriptionCallback]

    lib.RS_Workshop_SetItemUnsubscribedCallback.restype = None
    lib.RS_Workshop_SetItemUnsubscribedCallback.argtypes = [SubscriptionCallback]

    lib.RS_Workshop_SetGetAppDependenciesResultCallback.restype = None
    lib.RS_Workshop_SetGetAppDependenciesResultCallback.argtypes = [AppDepsCallback]

    lib.RS_Workshop_SetDownloadItemResultCallback.restype = None
    lib.RS_Workshop_SetDownloadItemResultCallback.argtypes = [
        DownloadItemResultCallback
    ]

    lib.RS_Workshop_SetItemInstalledCallback.restype = None
    lib.RS_Workshop_SetItemInstalledCallback.argtypes = [ItemInstalledCallback]

    return lib


_lib = _load_library()

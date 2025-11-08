import http.client
import os
import platform
import shutil
import socket
import subprocess
import sys
import webbrowser
from collections import namedtuple
from datetime import datetime
from errno import EACCES
from io import TextIOWrapper
from pathlib import Path
from re import search, sub
from stat import S_IRWXG, S_IRWXO, S_IRWXU
from time import localtime, strftime
from typing import TYPE_CHECKING, Any, Callable, Generator, Tuple

import requests
import vdf  # type: ignore
from loguru import logger
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

import app.views.dialogue as dialogue
from app.utils.app_info import AppInfo

if TYPE_CHECKING or sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

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


_Win32StatResult = namedtuple("_Win32StatResult", ["st_size"])


class Win32DirEntry:
    def __init__(self, path: Path, find_data: Any):
        self.name = find_data.cFileName
        self.path = str(path / self.name)
        self.size = (find_data.nFileSizeHigh << 32) + find_data.nFileSizeLow
        self._dwFileAttributes = find_data.dwFileAttributes
        self.FILE_ATTRIBUTE_DIRECTORY = 0x10

    def is_dir(self) -> bool:
        return bool(self._dwFileAttributes & self.FILE_ATTRIBUTE_DIRECTORY)

    def is_file(self) -> bool:
        return not self.is_dir()

    def stat(self) -> _Win32StatResult:
        return _Win32StatResult(self.size)


translate = QCoreApplication.translate


def chunks(_list: list[Any], limit: int) -> Generator[list[Any], None, None]:
    """
    Split list into chunks no larger than the configured limit

    :param list: a list to break into chunks
    :param limit: maximum size of the returned list
    """
    for i in range(0, len(_list), limit):
        yield _list[i : i + limit]


def copy_to_clipboard_safely(text: str) -> None:
    """
    Safely copies text to clipboard

    :param text: text to copy to clipboard
    """
    try:
        clipboard = QApplication.clipboard()
        clipboard.setText(text)
    except Exception as e:
        logger.error(f"Failed to copy to clipboard: {e}")
        dialogue.show_fatal_error(
            title=translate("copy_to_clipboard_safely", "Failed to copy to clipboard."),
            text=translate(
                "copy_to_clipboard_safely",
                "RimSort failed to copy the text to your clipboard. Please copy it manually.",
            ),
            details=str(e),
        )


def rmtree(path: str | Path, **kwargs: Any) -> bool:
    """Wrapper for improved rmtree error handling.
    Checks if the path exists and is a directory before attempting to delete it.
    If any OSErrors occur, a warning dialog is shown to the user.

    :param path: Path to directory to be deleted.
    :type path: str | Path
    :param kwargs: Additional keyword arguments to pass to shutil.rmtree.
    :return: True if the directory was successfully deleted, False otherwise.
    """
    if isinstance(path, str):
        path = Path(path)

    if not path.exists():
        logger.error(f"Tried to delete directory that does not exist: {path}")
        dialogue.show_warning(
            title=translate("rmtree", "Failed to remove directory"),
            text=translate(
                "rmtree", "RimSort tried to remove a directory that does not exist."
            ),
            details=translate("rmtree", "Directory does not exist: {path}").format(
                path=path
            ),
        )
        return False

    if not path.is_dir():
        logger.error(f"rmtree path is not a directory: {path}")
        dialogue.show_warning(
            title=translate("rmtree", "Failed to remove directory"),
            text=translate(
                "rmtree", "RimSort tried to remove a directory that is not a directory."
            ),
            details=translate("rmtree", "Path is not a directory: {path}").format(
                path=path
            ),
        )
        return False

    try:
        shutil.rmtree(path, **kwargs)
    except OSError as e:
        if sys.platform == "win32":
            error_code = e.winerror
        else:
            error_code = e.errno
        logger.error(f"Failed to remove directory: {e}")
        dialogue.show_warning(
            title=translate("rmtree", "Failed to remove directory"),
            text=translate(
                "rmtree", "An OSError occurred while trying to remove a directory."
            ),
            information=translate(
                "rmtree",
                "{e.strerror} occurred at {e.filename} with error code {error_code}.",
            ).format(
                e=e,
                error_code=error_code,
            ),
            details=str(e),
        )
        return False

    return True


def delete_files_with_condition(
    directory: Path | str, condition: Callable[[str], bool]
) -> bool:
    for root, dirs, files in os.walk(directory):
        for file in files:
            if condition(file):
                file_path = str((Path(root) / file))
                try:
                    os.remove(file_path)
                except OSError as e:
                    attempt_chmod(os.remove, file_path, e)
                finally:
                    logger.debug(f"Deleted: {file_path}")

    for root, dirs, _ in os.walk(directory, topdown=False):
        for _dir in dirs:
            dir_path = str((Path(root) / _dir))
            if not os.listdir(dir_path):
                shutil.rmtree(
                    dir_path,
                    ignore_errors=False,
                    onexc=attempt_chmod,
                )
                logger.debug(f"Deleted: {dir_path}")
    if not os.listdir(directory):
        shutil.rmtree(
            directory,
            ignore_errors=False,
            onexc=attempt_chmod,
        )
        logger.debug(f"Deleted: {directory}")
        return True
    else:
        return False


def delete_files_except_extension(directory: Path | str, extension: str) -> bool:
    return delete_files_with_condition(
        directory, lambda file: not file.endswith(extension)
    )


def delete_files_only_extension(directory: Path | str, extension: str) -> bool:
    return delete_files_with_condition(directory, lambda file: file.endswith(extension))


def scanpath(
    path: Path | str,
) -> Generator[os.DirEntry[str] | Win32DirEntry, None, None]:
    if sys.platform == "win32" and "ctypes" in globals():
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
    else:
        try:
            with os.scandir(path) as it:
                yield from it
        except OSError as e:
            logger.error(f"os.scandir failed for directory {path}: {e}")


def directories(mods_path: Path | str) -> list[str]:
    try:
        return [entry.path for entry in scanpath(mods_path) if entry.is_dir()]
    except OSError as e:
        logger.error(f"Error reading directory {mods_path}: {e}")
        return []


def attempt_chmod(
    func: Callable[[str], Any], path: str, excinfo: BaseException
) -> bool:
    if excinfo is not None and isinstance(excinfo, OSError):
        if (
            func in (os.rmdir, os.remove, os.unlink, os.listdir)
            and excinfo.errno == EACCES
        ):
            os.chmod(path, S_IRWXU | S_IRWXG | S_IRWXO)  # 0777
            try:
                func(path)
                return True
            except Exception as e:
                logger.warning(
                    f"attempt_chmod for {func.__name__} double failure at {path}: {e}"
                )
                return False

    return False


# TODO: This function signature corresponds to the depreciated onerror param of shutil.rmtree
# in general, new code should use attempt_chmod instead
def handle_remove_read_only(
    func: Callable[[str], Any],
    path: str,
    exc: tuple[type[BaseException], BaseException, Any] | tuple[None, None, None],
) -> None:
    excvalue = exc[1]
    if excvalue is not None and isinstance(excvalue, OSError):
        if func in (os.rmdir, os.remove, os.unlink) and excvalue.errno == EACCES:
            os.chmod(path, S_IRWXU | S_IRWXG | S_IRWXO)  # 0777
            func(path)
        else:
            raise


def get_executable_path(game_install_path: Path) -> str | None:
    """
    Determine the executable path for RimWorld based on the platform.

    :param game_install_path: Path to the game folder.
    :return: Executable path as string or None if not found.
    """
    system_name = platform.system()

    # Define platform-specific executable checks
    platform_checks = {
        "Darwin": lambda p: str(p) if p.suffix == ".app" and p.is_dir() else None,
        "Linux": lambda p: next(
            (
                str(exe)
                for exe in [
                    p / "RimWorldLinux",
                    p / "RimWorldWin64.exe",
                    p / "RimWorldWin.exe",
                ]
                if exe.exists()
                and (exe.name != "RimWorldLinux" or os.access(exe, os.X_OK))
            ),
            None,
        ),
        "Windows": lambda p: next(
            (
                str(exe)
                for exe in [p / "RimWorldWin64.exe", p / "RimWorldWin.exe"]
                if exe.exists()
            ),
            None,
        ),
    }

    check_func = platform_checks.get(system_name)
    if check_func:
        return check_func(game_install_path)
    else:
        logger.error(f"Unsupported platform for game launch: {system_name}")
        return None


def launch_game_process(game_install_path: Path, args: list[str]) -> None:
    """
    This function starts the Rimworld game process in it's own Process,
    by launching the executable found in the configured game directory.

    This function initializes the Steamworks API to be used by the RimWorld game.

    The game will be launched with the game install path being the working directory.

    :param game_install_path: is a path to the game folder
    :param args: is a list of strings representing the args to pass to the generated executable path
    """
    if not game_install_path:
        logger.error("The path to the game folder is empty")
        dialogue.show_warning(
            title=translate("launch_game_process", "Game launch failed"),
            text=translate("launch_game_process", "Unable to launch RimWorld"),
            information=(
                translate(
                    "launch_game_process",
                    "RimSort could not start RimWorld as the game folder is empty or invalid: [{game_install_path}] "
                    "Please check that the game folder is properly set and that the RimWorld executable exists in it.",
                ).format(game_install_path=game_install_path)
            ),
        )
        return

    logger.info(f"Attempting to launch the game from folder {game_install_path}")

    # Get the executable path
    executable_path = get_executable_path(game_install_path)
    if not executable_path:
        logger.error("Game executable validation failed - no valid executable found")
        dialogue.show_warning(
            title=translate("launch_game_process", "Invalid game folder"),
            text=translate("launch_game_process", "Unable to launch RimWorld"),
            information=(
                translate(
                    "launch_game_process",
                    "RimSort could not validate the RimWorld executable in the specified folder: {game_install_path}. Please check that this directory is correct and contains a valid RimWorld game executable.",
                ).format(game_install_path=game_install_path)
            ),
        )
        return

    logger.info(
        f"Launching the game with subprocess.Popen(): `{executable_path}` with args: {args}"
    )
    pid, popen_args = launch_process(executable_path, args, str(game_install_path))
    logger.info(
        f"Launched independent RimWorld game process with PID {pid} using args {popen_args}"
    )


def validate_game_executable(game_folder: str) -> bool:
    """
    Validate if the provided game folder contains a valid RimWorld executable.

    :param game_folder: Path to the game folder as a string.
    :return: True if a valid executable is found, False otherwise.
    """
    if not game_folder or not game_folder.strip():
        logger.info("Game folder path is empty or None")
        return False

    game_install_path = Path(game_folder)
    if not game_install_path.exists() or not game_install_path.is_dir():
        logger.info(
            f"Game folder does not exist or is not a directory: {game_install_path}"
        )
        return False

    # Use the new get_executable_path function for validation
    executable_path = get_executable_path(game_install_path)
    if executable_path:
        logger.debug(f"Valid RimWorld executable found: {executable_path}")
        return True

    system_name = platform.system()
    logger.info(
        f"No valid RimWorld executable found for {system_name} in: {game_install_path}"
    )
    return False


def launch_process(
    executable_path: str, args: list[str], cwd: str
) -> Tuple[int, list[str]]:
    pid = -1
    # https://stackoverflow.com/a/21805723
    if platform.system() == "Darwin":  # MacOS
        popen_args = ["open", executable_path, "--args"]
        popen_args.extend(args)
        p = subprocess.Popen(popen_args)
        pid = p.pid
    else:
        popen_args = [executable_path]
        popen_args.extend(args)

        if sys.platform == "win32":
            p = subprocess.Popen(
                popen_args,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                shell=True,
                cwd=cwd,
            )
            pid = p.pid
        else:
            # not Windows, so assume POSIX; if not, we'll get a usable exception
            p = subprocess.Popen(popen_args, start_new_session=True, cwd=cwd)
            pid = p.pid
    return pid, popen_args


def open_url_browser(url: str) -> None:
    """
    Open a url in a user's default web browser
    """
    logger.info(f"USER ACTION: Opening url {url}")
    webbrowser.open(url)


def platform_specific_open(path: str | Path) -> None:
    """
    Function to open a folder in the platform-specific file-explorer app
    or a file in the relevant system default application. On mac, if the path
    is a directory or an .app file, open the path in Finder using -R
    (i.e. treat .app as directory).

    :param path: path to open
    :type path: str | Path
    :param as_posix: if True, convert the path to a posix path regardless of the platform. This is useful for steam links.
    :type as_posix: bool
    """
    logger.info(f"USER ACTION: opening {path}")
    p = Path(path)
    path = str(path)
    if sys.platform == "darwin":
        logger.info(f"Opening {path} with subprocess open on MacOS")
        if p.is_dir() and p.suffix == ".app":
            subprocess.Popen(["open", path, "-R"])
        else:
            subprocess.Popen(["open", path])
    elif sys.platform == "win32":
        logger.info(f"Opening {path} with startfile on Windows")
        try:
            os.startfile(path)
        except OSError as e:
            # Handle cases where no default application is associated
            if e.winerror == -2147221003:  # Application not found
                logger.warning(
                    f"No default application found for {path}, trying notepad"
                )
                # Try to open with notepad as fallback
                try:
                    subprocess.Popen(["notepad.exe", path])
                except Exception as notepad_error:
                    logger.error(f"Failed to open with notepad: {notepad_error}")
                    dialogue.show_warning(
                        title="Failed to open file",
                        text="Could not open the file",
                        information=f"No default application is associated with this file type: {p.suffix}\n\nPlease manually associate an application with {p.suffix} files or open the file manually.",
                        details=str(e),
                    )
            else:
                # Re-raise other OSErrors
                raise
    elif sys.platform == "linux":
        logger.info(f"Opening {path} with xdg-open on Linux")
        subprocess.Popen(["xdg-open", path], env=dict(os.environ, LD_LIBRARY_PATH=""))
    else:
        logger.error("Attempting to open directory on an unknown system")


def sanitize_filename(filename: str) -> str:
    # Remove forbidden characters for all platforms
    forbidden_chars = r'[<>:"/\|?*\0]'
    sanitized_filename = sub(forbidden_chars, "", filename)

    # Windows filenames shouldn't end with a space or period
    sanitized_filename = sanitized_filename.rstrip(". ")

    return sanitized_filename


def flatten_to_list(obj: Any) -> list[Any] | dict[Any, Any] | Any:
    """Function to recursively flatten a nested object as much as possible.
        Converts all sets to lists. If the object is a dictionary, it maintains the keys and
        recurses on the values. If the object cannot be flattened further, the function returns the object as is.

    :param obj: The object to be flattened
    :type obj: Any
    :return: The flattened object
    :rtype: list[Any] | dict[Any, Any]
    """
    if isinstance(obj, set):
        return list(obj)
    elif isinstance(obj, list):
        return [flatten_to_list(e) for e in obj]
    elif isinstance(obj, tuple):
        # Convert tuples to lists and recurse into elements
        return [flatten_to_list(e) for e in obj]
    elif isinstance(obj, dict):
        return {k: flatten_to_list(v) for k, v in obj.items()}
    else:
        return obj


def format_file_size(size_in_bytes: int) -> str:
    """Format bytes to a human-readable string."""
    if size_in_bytes < 1024:
        return f"{size_in_bytes} B"
    elif size_in_bytes < 1024 * 1024:
        return f"{size_in_bytes / 1024:.1f} KB"
    elif size_in_bytes < 1024 * 1024 * 1024:
        return f"{size_in_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_in_bytes / (1024 * 1024 * 1024):.2f} GB"


def upload_data_to_0x0_st(path: str) -> tuple[bool, str]:
    """
    Function to upload data to https://0x0.st/

    :param path: a string path to a file containing data to upload
    :return: a string that is the URL returned from https://0x0.st/
    """
    logger.info(f"Uploading data to https://0x0.st/: {path}")
    try:
        with open(path, "rb") as f:
            headers = {"User-Agent": f"RimSort/{AppInfo().app_version}"}
            request = requests.post(
                url="https://0x0.st/",
                files={"file": (Path(path).name, f)},
                headers=headers,
            )
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Connection Error. Failed to upload data to https://0x0.st: {e}")
        return False, str(e)
    except requests.exceptions.RequestException as e:
        logger.error(f"Request Error. Failed to upload data to https://0x0.st: {e}")
        return False, str(e)

    if request.status_code == 200:
        url = request.text.strip()
        logger.info(f"Uploaded! Uploaded data can be found at: {url}")
        return True, url
    else:
        body_snippet = request.text.strip()
        logger.warning(
            f"Failed to upload data to https://0x0.st. Status code: {request.status_code}; body: {body_snippet[:200]}"
        )
        return False, f"Status code: {request.status_code}\n{body_snippet}"


def extract_git_dir_name(url: str) -> str:
    """
    Function to extract the directory name from a git url

    :param url: a string url to a git repository
    :return: a string that is the directory name of the git repository
    """
    return url.rstrip("/").rsplit("/", maxsplit=1)[-1].removesuffix(".git")


def extract_git_user_or_org(url: str) -> str:
    """
    Function to extract the organization or user name from a git url

    :param url: a string url to a git repository
    :return: a string that is the organization name of the git repository
    """
    return url.rstrip("/").rsplit("/", maxsplit=2)[-2].removesuffix(".git")


def extract_page_title_steam_browser(title: str) -> str | None:
    """
    Function to extract the page title from the current Workshop Browser page

    :param title: a string that is the current title of the page
    :return str | None: an optional string that is the page title of the current page
    """
    if match := search(r"Steam (?:Community|Workshop)::(.*)", title):
        return match.group(1)
    else:
        return None


def check_valid_http_git_url(url: str) -> bool:
    """
    Function to check if a given url is a valid http/s git url

    :param url: a string url to a git repository
    :return: a boolean indicating whether the url is a valid git url
    """
    return url and url != "" and url.startswith("http://") or url.startswith("https://")


def get_path_up_to_string(
    path: Path, stop_string: str, exclude: bool = False
) -> Path | str:
    """
    Returns a Path up to the stop_string.

    :param path: Path to search
    :param stop_string: str that path is returned up to.
    :param exclude: bool, decides if stop_string is excluded from returned path
    :return: Path up to stop_string or empty str if stop_string is not present
    """
    parts = path.parts

    try:
        stop_idx = parts.index(stop_string)
        if exclude:
            return Path(*parts[:stop_idx])
        else:
            return Path(*parts[: stop_idx + 1])
    except ValueError:
        # Stop string is not present
        return ""


def find_steam_rimworld(steam_folder: Path | str) -> str:
    """
    This should be compatible cross-platform.

    Given a steam installation path, find and read the libraryfolders.vdf
    and from this file retrieve the RimWorld steam isntallation path.

    :param steam_folder: Path to steam installation
    :return: Rimworld Path if found, blank str otherwise
    """

    def __load_data(f: TextIOWrapper) -> str:
        """
        Helper function that returns RimWorld path from libraryfolders.vdf
        if found inside, empty string otherwise.
        """
        rimworld_path = ""
        data = vdf.load(f)
        library_folders = data.get("libraryfolders", None)
        if not library_folders:
            return ""
        # Find 294100 (RimWorld)
        for _, folder in library_folders.items():
            if "294100" in folder.get("apps", {}):
                rimworld_path = folder.get("path", "")
                break
        return rimworld_path

    rimworld_path = ""
    steam_folder = Path(steam_folder)

    primary_library = "config/libraryfolders.vdf"
    backup_library = "steamapps/libraryfolders.vdf"

    if os.path.exists(steam_folder / primary_library):
        logger.debug(f"Attempting to get RimWorld path from {primary_library}")
        with open(steam_folder / primary_library, "r") as f:
            rimworld_path = __load_data(f)
    elif os.path.exists(steam_folder / backup_library):
        logger.debug(f"Attempting to get RimWorld path from {backup_library}")
        with open(steam_folder / backup_library, "r") as f:
            rimworld_path = __load_data(f)
    else:
        logger.warning("Failed retrieving RimWorld path from libraryfolders.vdf")
        return rimworld_path

    full_rimworld_path = Path(rimworld_path) / "steamapps/common/RimWorld"

    return str(full_rimworld_path) if rimworld_path else rimworld_path


def check_internet_connection(
    primary_host: str = "8.8.8.8",
    fallback_host: str = "1.1.1.1",
    port: int = 53,
    fallback_port: int = 443,
    timeout: float = 10,
) -> bool:
    """
    Check if there is an active internet connection by attempting to connect to a known host (DNS),
    As a fallback, try an HTTP request to a well-known google website.
    """
    socket.setdefaulttimeout(timeout)

    def try_connect(host: str, port_to_try: int) -> bool:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.connect((host, port_to_try))
            return True
        except OSError as e:
            logger.warning(f"Socket connection to {host}:{port_to_try} failed: {e}")
            return False

    # Try connecting to the primary host on both ports
    if try_connect(primary_host, port) or try_connect(primary_host, fallback_port):
        return True

    # Try connecting to the fallback host on both ports
    if try_connect(fallback_host, port) or try_connect(fallback_host, fallback_port):
        return True

    # Fallback: try HTTP request to a well-known site
    try:  # Try google.com first
        conn = http.client.HTTPSConnection("www.google.com", timeout=timeout)
        conn.request("HEAD", "/")
        response = conn.getresponse()
        if response.status < 500:
            return True
    except Exception as e:
        logger.warning(f"HTTP connection to www.google.com failed: {e}")

    try:  # Try cloudflare fallback site
        conn = http.client.HTTPSConnection("www.cloudflare.com", timeout=timeout)
        conn.request("HEAD", "/")
        response = conn.getresponse()
        if response.status < 500:
            return True
    except Exception as e:
        logger.warning(f"HTTP connection to www.cloudflare.com failed: {e}")

    try:  # Try microsoft.com as another fallback site
        conn = http.client.HTTPSConnection("www.microsoft.com", timeout=timeout)
        conn.request("HEAD", "/")
        response = conn.getresponse()
        if response.status < 500:
            return True
    except Exception as e:
        logger.warning(f"HTTP connection to www.microsoft.com failed: {e}")

    logger.error("No internet connection detected.")

    try:  # Try additional fallback: try curl command to google.com
        result = subprocess.run(
            ["curl", "-Is", "https://www.google.com"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
        if result.returncode == 0 and b"HTTP" in result.stdout:
            return True
    except Exception as e:
        logger.warning(f"Curl command to www.google.com failed: {e}")

    try:  # Try additional fallback: try curl command to cloudflare.com
        result = subprocess.run(
            ["curl", "-Is", "https://www.cloudflare.com"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
        if result.returncode == 0 and b"HTTP" in result.stdout:
            return True
    except Exception as e:
        logger.warning(f"Curl command to www.cloudflare.com failed: {e}")

    try:  # Try additional fallback: try curl command to microsoft.com
        result = subprocess.run(
            ["curl", "-Is", "https://www.microsoft.com"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
        if result.returncode == 0 and b"HTTP" in result.stdout:
            return True
    except Exception as e:
        logger.warning(f"Curl command to www.microsoft.com failed: {e}")

    return False


def restart_application() -> None:
    if getattr(sys, "frozen", False):
        cmd = [sys.executable] + sys.argv[1:]
    else:
        cmd = [sys.executable] + sys.argv

    subprocess.Popen(cmd)

    instance = QApplication.instance()
    if instance:
        logger.info("Restarting the application")
        instance.quit()
    else:
        logger.warning("No QApplication instance found, cannot restart the application")


def get_relative_time(timestamp: int) -> str:
    """
    Convert a timestamp to a relative time string (e.g. "2 days ago").

    Args:
        timestamp (int): Unix timestamp to convert.

    Returns:
        str: Human-readable relative time string, or "Invalid timestamp" if conversion fails.
    """
    try:
        dt = datetime.fromtimestamp(timestamp)
        now = datetime.now()
        delta = now - dt

        if delta.days > 365:
            return f"{delta.days // 365} years ago"
        elif delta.days > 30:
            return f"{delta.days // 30} months ago"
        elif delta.days > 0:
            return f"{delta.days} days ago"
        elif delta.seconds > 3600:
            return f"{delta.seconds // 3600} hours ago"
        elif delta.seconds > 60:
            return f"{delta.seconds // 60} minutes ago"
        else:
            return "Just now"
    except (ValueError, TypeError):
        return "Invalid timestamp"


def format_time_display(timestamp: int | None) -> tuple[str, int | None]:
    """
    Format a timestamp into absolute and relative time strings for display.

    Args:
        timestamp (int | None): Unix timestamp to format, or None if unknown.

    Returns:
        tuple[str, int | None]: A tuple of (formatted_time_string, timestamp).
                                 If timestamp is None, returns ("Unknown", None).
    """
    if timestamp is None:
        return "Unknown", None

    try:
        abs_time = strftime("%Y-%m-%d %H:%M:%S", localtime(timestamp))
        rel_time = get_relative_time(timestamp)
        return f"{abs_time} | {rel_time}", timestamp
    except (ValueError, TypeError, OSError):
        return "Invalid timestamp", None

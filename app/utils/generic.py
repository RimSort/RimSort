import os
import platform
import shutil
import subprocess
import sys
import webbrowser
from errno import EACCES
from pathlib import Path
from re import sub
from stat import S_IRWXG, S_IRWXO, S_IRWXU
from typing import Any, Callable, Generator

import requests
from loguru import logger
from pyperclip import (  # type: ignore # Stubs don't exist for pyperclip
    copy as copy_to_clipboard,
)
from requests import post as requests_post

import app.views.dialogue as dialogue


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
        copy_to_clipboard(text)
    except Exception as e:
        logger.error(f"Failed to copy to clipboard: {e}")
        dialogue.show_fatal_error(
            title="Failed to copy to clipboard.",
            text="RimSort failed to copy the text to your clipboard. Please copy it manually.",
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
            title="Failed to remove directory",
            text="RimSort tried to remove a directory that does not exist.",
            details=f"Directory does not exist: {path}",
        )
        return False

    if not path.is_dir():
        logger.error(f"rmtree path is not a directory: {path}")
        dialogue.show_warning(
            title="Failed to remove directory",
            text="RimSort tried to remove a directory that is not a directory.",
            details=f"Path is not a directory: {path}",
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
            title="Failed to remove directory",
            text="An OSError occurred while trying to remove a directory.",
            information=f"{e.strerror} occurred at {e.filename} with error code {error_code}.",
            details=str(e),
        )
        return False

    return True


def delete_files_with_condition(
    directory: Path | str, condition: Callable[[str], bool]
) -> None:
    for root, dirs, files in os.walk(directory):
        for file in files:
            if condition(file):
                file_path = str((Path(root) / file))
                try:
                    os.remove(file_path)
                except OSError:
                    handle_remove_read_only(os.remove, file_path, sys.exc_info())
                finally:
                    logger.debug(f"Deleted: {file_path}")

    for root, dirs, _ in os.walk(directory, topdown=False):
        for _dir in dirs:
            dir_path = str((Path(root) / _dir))
            if not os.listdir(dir_path):
                shutil.rmtree(
                    dir_path,
                    ignore_errors=False,
                    onerror=handle_remove_read_only,
                )
                logger.debug(f"Deleted: {dir_path}")
    if not os.listdir(directory):
        shutil.rmtree(
            directory,
            ignore_errors=False,
            onerror=handle_remove_read_only,
        )
        logger.debug(f"Deleted: {directory}")


def delete_files_except_extension(directory: Path | str, extension: str) -> None:
    delete_files_with_condition(directory, lambda file: not file.endswith(extension))


def delete_files_only_extension(directory: Path | str, extension: str) -> None:
    delete_files_with_condition(directory, lambda file: file.endswith(extension))


def directories(mods_path: Path | str) -> list[str]:
    try:
        with os.scandir(mods_path) as directories:
            return [directory.path for directory in directories if directory.is_dir()]
    except OSError as e:
        logger.error(f"Error reading directory {mods_path}: {e}")
        return []


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


def launch_game_process(game_install_path: Path, args: list[str]) -> None:
    """
    This function starts the Rimworld game process in it's own Process,
    by launching the executable found in the configured game directory.

    This function initializes the Steamworks API to be used by the RimWorld game.

    The game will be launched with the game install path being the working directory.

    :param game_install_path: is a path to the game folder
    :param args: is a list of strings representing the args to pass to the generated executable path
    """
    logger.info(f"Attempting to find the game in the game folder {game_install_path}")
    if game_install_path:
        system_name = platform.system()
        if system_name == "Darwin":
            # MacOS
            executable_path = str(game_install_path)
        elif system_name == "Linux":
            # Linux
            executable_path = str((game_install_path / "RimWorldLinux"))
        elif system_name == "Windows":
            # Windows
            executable_path = str((game_install_path / "RimWorldWin64.exe"))
        else:
            logger.error("Unable to launch the game on an unknown system")
        logger.info(f"Path to game executable generated: {executable_path}")
        if os.path.exists(executable_path):
            logger.info(
                "Launching the game with subprocess.Popen(): `"
                + executable_path
                + "` with args: `"
                + str(args)
                + "`"
            )
            # https://stackoverflow.com/a/21805723
            if system_name == "Darwin":  # MacOS
                popen_args = ["open", executable_path, "--args"]
                popen_args.extend(args)
                p = subprocess.Popen(popen_args)
            else:
                popen_args = [executable_path]
                popen_args.extend(args)

                if sys.platform == "win32":
                    p = subprocess.Popen(
                        popen_args,
                        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                        shell=True,
                        cwd=game_install_path,
                    )
                else:
                    # not Windows, so assume POSIX; if not, we'll get a usable exception
                    p = subprocess.Popen(
                        popen_args, start_new_session=True, cwd=game_install_path
                    )

            logger.info(
                f"Launched independent RimWorld game process with PID {p.pid} using args {popen_args}"
            )
        else:
            logger.debug("The game executable path does not exist")
            dialogue.show_warning(
                title="File not found",
                text="Unable to launch game process",
                information=(
                    "RimSort could not start RimWorld as the game executable does "
                    f"not exist at the specified path: {executable_path}. Please check "
                    "that this directory is correct and the RimWorld game executable "
                    "exists in it."
                ),
            )
    else:
        logger.error("The path to the game folder is empty")
        dialogue.show_warning(
            title="Game launch failed",
            text="Unable to launch RimWorld",
            information=(
                f"RimSort could not start RimWorld as the game folder is empty or invalid: [{game_install_path}] "
                "Please check that the game folder is properly set and that the RimWorld executable exists in it."
            ),
        )


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
        os.startfile(path)
    elif sys.platform == "linux":
        logger.info(f"Opening {path} with xdg-open on Linux")
        subprocess.Popen(["xdg-open", path])
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
    elif isinstance(obj, dict):
        return {k: flatten_to_list(v) for k, v in obj.items()}
    else:
        return obj


def upload_data_to_0x0_st(path: str) -> tuple[bool, str]:
    """
    Function to upload data to http://0x0.st/

    :param path: a string path to a file containing data to upload
    :return: a string that is the URL returned from http://0x0.st/
    """
    logger.info(f"Uploading data to http://0x0.st/: {path}")
    try:
        request = requests_post(
            url="http://0x0.st/", files={"file": (path, open(path, "rb"))}
        )
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Connection Error. Failed to upload data to http://0x0.st: {e}")
        return False, str(e)

    if request.status_code == 200:
        url = request.text.strip()
        logger.info(f"Uploaded! Uploaded data can be found at: {url}")
        return True, url
    else:
        logger.warning(
            f"Failed to upload data to http://0x0.st. Status code: {request.status_code}"
        )
        return False, f"Status code: {request.status_code}"


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


def check_valid_http_git_url(url: str) -> bool:
    """
    Function to check if a given url is a valid http/s git url

    :param url: a string url to a git repository
    :return: a boolean indicating whether the url is a valid git url
    """
    return url and url != "" and url.startswith("http://") or url.startswith("https://")

import os
import platform
import shutil
import subprocess
import sys
import webbrowser
from errno import EACCES
from pathlib import Path
from re import sub
from stat import S_IRWXU, S_IRWXG, S_IRWXO

from loguru import logger
from requests import post as requests_post

from app.models.dialogue import show_warning


def chunks(_list: list, limit: int):
    """
    Split list into chunks no larger than the configured limit

    :param list: a list to break into chunks
    :param limit: maximum size of the returned list
    """
    for i in range(0, len(_list), limit):
        yield _list[i : i + limit]


def delete_files_except_extension(directory, extension):
    for root, dirs, files in os.walk(directory):
        for file in files:
            if not file.endswith(extension):
                file_path = str((Path(root) / file))
                try:
                    os.remove(file_path)
                except OSError as e:
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


def directories(mods_path):
    try:
        with os.scandir(mods_path) as directories:
            return [directory.path for directory in directories if directory.is_dir()]
    except OSError as e:
        logger.error(f"Error reading directory {mods_path}: {e}")
        return []


def handle_remove_read_only(func, path: str, exc):
    excvalue = exc[1]
    if func in (os.rmdir, os.remove, os.unlink) and excvalue.errno == EACCES:
        os.chmod(path, S_IRWXU | S_IRWXG | S_IRWXO)  # 0777
        func(path)
    else:
        raise


def launch_game_process(game_install_path: Path, args: list) -> None:
    """
    This function starts the Rimworld game process in it's own Process,
    by launching the executable found in the configured game directory.

    This function initializes the Steamworks API to be used by the RimWorld game.

    :param game_install_path: is a string path to the game folder
    :param args: is a string representing the args to pass to the generated executable path
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
        elif "Windows":
            # Windows
            executable_path = str((game_install_path / "RimWorldWin64.exe"))
        else:
            logger.error("Unable to launch the game on an unknown system")
        logger.info(f"Path to game executable generated: {executable_path}")
        if os.path.exists(executable_path):
            logger.info(
                f"Launching the game with subprocess.Popen(): `"
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
                try:
                    subprocess.CREATE_NEW_PROCESS_GROUP
                except (
                    AttributeError
                ):  # not Windows, so assume POSIX; if not, we'll get a usable exception
                    p = subprocess.Popen(
                        popen_args,
                        start_new_session=True,
                    )
                else:  # Windows
                    p = subprocess.Popen(
                        popen_args,
                        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                        shell=True,
                    )
            logger.info(
                f"Launched independent RimWorld game process with PID {p.pid} using args {popen_args}"
            )
        else:
            logger.debug("The game executable path does not exist")
            show_warning(
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
        show_warning(
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


def platform_specific_open(path: str) -> None:
    """
    Function to open a file/folder in the platform-specific file-explorer app.

    :param path: path to open
    """
    logger.info(f"USER ACTION: opening {path}")
    p = Path(path)
    system_name = platform.system()
    if system_name == "Darwin":
        logger.info(f"Opening {path} with subprocess open on MacOS")
        if p.is_file() or (p.is_dir() and p.suffix == ".app"):
            subprocess.Popen(["open", path, "-R"])
        else:
            subprocess.Popen(["open", path])
    elif system_name == "Windows":
        logger.info(f"Opening {path} with startfile on Windows")
        os.startfile(path)  # type: ignore
    elif system_name == "Linux":
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


def set_to_list(obj):
    if isinstance(obj, set):
        return list(obj)
    elif isinstance(obj, list):
        return [set_to_list(e) for e in obj]
    elif isinstance(obj, dict):
        return {k: set_to_list(v) for k, v in obj.items()}
    else:
        return obj


def upload_data_to_0x0_st(path: str) -> str:
    """
    Function to upload data to http://0x0.st/

    :param path: a string path to a file containing data to upload
    :return: a string that is the URL returned from http://0x0.st/
    """
    logger.info(f"Uploading data to http://0x0.st/: {path}")
    request = requests_post(
        url="http://0x0.st/", files={"file": (path, open(path, "rb"))}
    )
    if request.status_code == 200:
        url = request.text.strip()
        logger.info(f"Uploaded! Uploaded data can be found at: {url}")
        return url
    else:
        logger.warning(f"Failed to upload data to http://0x0.st")
        return None

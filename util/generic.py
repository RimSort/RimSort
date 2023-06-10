from logger_tt import logger
from errno import EACCES
import os
import platform
from pyperclip import copy as copy_to_clipboard
from stat import S_IRWXU, S_IRWXG, S_IRWXO
import subprocess
from requests import post as requests_post
import webbrowser

from model.dialogue import show_information, show_warning


def chunks(_list: list, limit: int):
    """
    Split list into chunks no larger than the configured limit

    :param list: a list to break into chunks
    :param limit: maximum size of the returned list
    """
    for i in range(0, len(_list), limit):
        yield _list[i : i + limit]

def handle_remove_read_only(func, path: str, exc):
    excvalue = exc[1]
    if func in (os.rmdir, os.remove, os.unlink) and excvalue.errno == EACCES:
        os.chmod(path, S_IRWXU|S_IRWXG| S_IRWXO) # 0777
        func(path)
    else:
        raise

def launch_game_process(game_executable: str, args: str) -> None:
    """
    This function starts the Rimworld game process in it's own Process,
    by launching the executable found in the configured game directory.

    This function initializes the Steamworks API to be used by the RimWorld game.

    :param game_executable: is a string path to the game folder
    :param args: is a string representing the args to pass to the generated executable path
    """
    logger.info(f"Attempting to find the game in the game folder {game_executable}")
    if game_executable:
        system_name = platform.system()
        if system_name == "Darwin":
            executable_path = os.path.join(game_executable, "RimWorldMac.app")
        elif system_name == "Linux":
            # Linux
            executable_path = os.path.join(game_executable, "RimWorldLinux")
        elif "Windows":
            # Windows
            executable_path = os.path.join(game_executable, "RimWorldWin64.exe")
        else:
            logger.error("Unable to launch the game on an unknown system")
        logger.info(f"Path to game executable generated: {executable_path}")
        if os.path.exists(executable_path):
            logger.info(
                f"Launching the game with subprocess.Popen(): `"
                + executable_path
                + "` with args: `"
                + args
                + "`"
            )
            # https://stackoverflow.com/a/21805723
            if system_name == "Darwin":  # MacOS
                p = subprocess.Popen(["open", executable_path, "--args", args])
            else:
                try:
                    subprocess.CREATE_NEW_PROCESS_GROUP
                except (
                    AttributeError
                ):  # not Windows, so assume POSIX; if not, we'll get a usable exception
                    p = subprocess.Popen(
                        [executable_path, args], start_new_session=True
                    )
                else:  # Windows
                    p = subprocess.Popen(
                        [executable_path, args],
                        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                        shell=True,
                    )
            logger.info(f"Launched independent RimWorld game process with PID: {p.pid}")
        else:
            logger.warning("The game executable path does not exist")
            show_warning(
                text="Error Starting the Game",
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
            text="Error Starting the Game",
            information=(
                "RimSort could not start RimWorld as the game folder is empty or invalid: [{game_executable}] "
                "Please check that the game folder is properly set and that the RimWorld executable "
                "exists in it."
            ),
        )


def open_url_browser(url: str) -> None:
    """
    Open the url of a mod of a url in a user's default web browser
    """
    browser = webbrowser.get().name
    logger.info(f"USER ACTION: Opening mod url {url} in " + f"{browser}")
    webbrowser.open_new_tab(url)


def platform_specific_open(path: str) -> None:
    """
    Function to open a file/folder in the platform-specific file-explorer app.

    :param path: path to open
    """
    logger.info(f"USER ACTION: opening {path}")
    system_name = platform.system()
    if system_name == "Darwin":
        logger.info(f"Opening {path} with subprocess open on MacOS")
        subprocess.Popen(["open", path])
    elif system_name == "Windows":
        logger.info(f"Opening {path} with startfile on Windows")
        os.startfile(path)  # type: ignore
    elif system_name == "Linux":
        logger.info(f"Opening {path} with xdg-open on Linux")
        subprocess.Popen(["xdg-open", path])
    else:
        logger.error("Attempting to open directory on an unknown system")


def upload_data_to_0x0_st(path: str) -> None:
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
        copy_to_clipboard(url)
        show_information(
            title="Uploaded file to http://0x0.st/",
            text=f"Uploaded active mod list report to http://0x0.st!",
            information=f"The URL has been copied to your clipboard:\n\n{url}",
        )
    else:
        logger.warning(f"Failed to upload data to http://0x0.st")

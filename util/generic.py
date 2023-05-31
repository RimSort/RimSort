from logger_tt import logger
import os
import platform
from pyperclip import copy as copy_to_clipboard
import subprocess
from requests import post as requests_post

from model.dialogue import show_information, show_warning


def chunks(list: list, limit: int):
    """
    Split list into chunks no larger than the configured limit

    :param list: a list to break into chunks
    :param limit: maximum size of the returned list
    """
    for i in range(0, len(list), limit):
        yield list[i : i + limit]


def launch_game_process(instruction: list) -> None:
    """
    This function starts the Rimworld game process in it's own Process,
    by launching the executable found in the configured game directory.

    This function initializes the Steamworks API to be used by the RimWorld game.

    :param instruction: a list containing [path: str, args: str] respectively
    :param override: a bool when if set to True, skips initiating Steamworks
    """
    game_path = instruction[0]
    args = instruction[1]
    logger.info(f"Attempting to find the game in the game folder {game_path}")
    if game_path:
        system_name = platform.system()
        if system_name == "Darwin":
            executable_path = os.path.join(game_path, "RimWorldMac.app")
        elif system_name == "Linux":
            # Linux
            executable_path = os.path.join(game_path, "RimWorldLinux")
        elif "Windows":
            # Windows
            executable_path = os.path.join(game_path, "RimWorldWin64.exe")
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
                "RimSort could not start RimWorld as the game folder is empty or invalid: [{game_path}] "
                "Please check that the game folder is properly set and that the RimWorld executable "
                "exists in it."
            ),
        )


def platform_specific_open(path: str) -> None:
    """
    Function to open a folder in the platform-specific
    explorer app.

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

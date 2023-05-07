from logger_tt import logger
import os
import platform
import subprocess
from requests import post


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
    request = post(url="http://0x0.st/", files={"file": (path, open(path, "rb"))})
    if request.status_code == 200:
        logger.info(f"Uploaded! Uploaded data can be found at: {request.text}")
    else:
        logger.warning(f"Failed to upload data to http://0x0.st")

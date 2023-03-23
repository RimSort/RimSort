import logging
import os
import platform
import subprocess

logger = logging.getLogger(__name__)
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

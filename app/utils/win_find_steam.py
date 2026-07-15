"""Windows registry based method to find where steam is installed"""

import os
import sys

from loguru import logger


def find_steam_folder() -> tuple[str, bool]:
    """Find the Steam installation folder by checking the Windows registry.

    Validates the path by checking if the steam executable is present.

    Returns:
        tuple[str, bool]: The path to the steam folder and a boolean indicating
            if the path was found.  On non-Windows platforms always returns
            ``("", False)``.
    """
    if sys.platform != "win32":
        return "", False

    import winreg

    candidate_reg_keys = [
        r"SOFTWARE\Wow6432Node\Valve\Steam",
        r"SOFTWARE\Valve\Steam",
    ]

    for reg_key in candidate_reg_keys:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_key) as key:
                value = winreg.QueryValueEx(key, "InstallPath")
                candidate_path = os.path.join(value[0], "steam.exe")

                if os.path.isfile(candidate_path):
                    return value[0], True

                logger.warning(
                    f"Steam executable not found at path defined by registry: {candidate_path}"
                )
        except FileNotFoundError:
            continue

    return "", False

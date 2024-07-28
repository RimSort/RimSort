"""Windows registry based method to find where steam is installed"""

import os
import sys
import winreg

from loguru import logger

if sys.platform == "win32":

    def find_steam_folder() -> tuple[str, bool]:
        """Windows only function to find the steam folder by checking the registry.
        The function will check the registry for the steam install path and return the path to the steam folder
        and a boolean indicating if the path was found or not.

        Validates the path by checking if the steam executable is present in the path.

        Returns:
            tuple[str, bool]: The path to the steam folder and a boolean indicating if the path was found
        """
        candidate_reg_keys = [
            "SOFTWARE\Wow6432Node\Valve\Steam",
            "SOFTWARE\Valve\Steam",
        ]

        for reg_key in candidate_reg_keys:
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_key)
                value = winreg.QueryValueEx(key, "InstallPath")
                candidate_path = os.path.join(value[0], "steam.exe")

                if os.path.isfile(candidate_path):
                    return value[0], True

                logger.warning(
                    f"Steam executable not found at path defined by registry: {candidate_path}"
                )
            except FileNotFoundError:
                # Registry key not found. Continue to the next candidate key
                continue

        return "", False

import os
import getpass
import platform

from util.exception import InvalidModsConfigFormat
from util.xml import xml_path_to_json


def get_default_game_executable_path() -> str:
    """
    Return the default location for the Rimworld game executable.
    
    :return: platform-specific path to game app
    """
    system_name = platform.system()
    if system_name == "Darwin":
        return f"/Users/{getpass.getuser()}/Library/Application Support/Steam/steamapps/common/Rimworld/RimWorldMac.app"
    if system_name == "Windows":
        return os.path.join("C:" + os.sep, "Program Files (x86)", "Steam", "steamapps", "common", "Rimworld", "RimWorldWin64.exe")
    if system_name == "Linux":
        return ""
    return "Unknown platform"


def get_default_mods_config_path() -> str:
    """
    Return the default location for the ModsConfig.xml
    
    :return: platform-specific path to ModsConfig.xml
    """
    system_name = platform.system()
    if system_name == "Darwin":
        return f"/Users/{getpass.getuser()}/Library/Application Support/Rimworld/Config/ModsConfig.xml"
    if system_name == "Windows":
        return os.path.join("C:" + os.sep, "Users", getpass.getuser(), "AppData", "LocalLow", "Ludeon Studios", "RimWorld by Ludeon Studios", "Config", "ModsConfig.xml")
    if system_name == "Linux":
        return ""
    return "Unknown platform"


def get_default_workshop_path() -> str:
    """
    Return the default location for the workshop mods folder
    
    :return: platform-specific path to workshop folder
    """
    system_name = platform.system()
    if system_name == "Darwin":
        return f"/Users/{getpass.getuser()}/Library/Application Support/Steam/steamapps/workshop/content/294100/"
    if system_name == "Windows":
        return os.path.join("C:" + os.sep, "Program Files (x86)", "Steam", "steamapps", "workshop", "content", "294100")
    if system_name == "Linux":
        return ""
    return "Unknown platform"


def get_game_version(path: str) -> str:
    """
    Given a path to a ModsConfig.xml, return the game version.

    :param path: path to the ModsConfig.xml
    :return: game version
    """
    mod_data = xml_path_to_json(path)
    try:
        return mod_data["ModsConfigData"]["version"]
    except:
        raise InvalidModsConfigFormat

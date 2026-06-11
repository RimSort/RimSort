"""Platform-specific Steam and RimWorld path detection.

Pure filesystem logic with no UI dependencies. Used by LocationsTabController
for autodetect functionality.
"""

import sys
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from app.utils.generic import find_steam_rimworld, get_path_up_to_string


@dataclass
class DetectedPaths:
    """Result of platform-specific path autodetection."""

    game_folder: Path
    config_folder: Path
    steam_mods_folder: Path
    steam_root: Path | None = None


def find_steam_root(candidates: list[Path]) -> Path | None:
    """Find the Steam installation root from a prioritized list of candidate paths.

    :param candidates: Ordered list of candidate Steam root paths
    :return: First valid Steam root, or None
    """
    for candidate in candidates:
        if not candidate.is_dir():
            logger.debug(f"Steam root candidate does not exist: {candidate}")
            continue
        has_steamapps = (candidate / "steamapps").is_dir()
        has_vdf = (candidate / "config" / "libraryfolders.vdf").is_file()
        if has_steamapps or has_vdf:
            logger.info(f"Found Steam root: {candidate}")
            return candidate
        logger.debug(
            f"Steam root candidate exists but has no steamapps/ or config/libraryfolders.vdf: {candidate}"
        )
    logger.warning("No valid Steam root found from any candidate path")
    return None


def get_darwin_paths() -> DetectedPaths:
    """Detect RimWorld paths on macOS."""
    user_home = Path.home()
    candidates = [
        user_home / "Library" / "Application Support" / "Steam",
    ]

    steam_root = find_steam_root(candidates)

    if steam_root:
        game_folder_str = find_steam_rimworld(steam_root)
        if game_folder_str:
            game_folder = Path(game_folder_str) / "RimworldMac.app"
        else:
            game_folder = (
                steam_root / "steamapps" / "common" / "Rimworld" / "RimworldMac.app"
            )

        steam_mods_folder_str = get_path_up_to_string(
            game_folder.parent, "common", exclude=True
        )
        if steam_mods_folder_str == "":
            steam_mods_folder = (
                steam_root / "steamapps" / "workshop" / "content" / "294100"
            )
        else:
            steam_mods_folder = (
                Path(steam_mods_folder_str) / "workshop" / "content" / "294100"
            )
    else:
        game_folder = (
            user_home
            / "Library"
            / "Application Support"
            / "Steam"
            / "steamapps"
            / "common"
            / "Rimworld"
            / "RimworldMac.app"
        )
        steam_mods_folder = (
            user_home
            / "Library"
            / "Application Support"
            / "Steam"
            / "steamapps"
            / "workshop"
            / "content"
            / "294100"
        )

    config_folder = (
        user_home / "Library" / "Application Support" / "Rimworld" / "Config"
    )

    return DetectedPaths(game_folder, config_folder, steam_mods_folder, steam_root)


def get_linux_paths() -> DetectedPaths:
    """Detect RimWorld paths on Linux."""
    user_home = Path.home()
    candidates = [
        user_home / ".steam" / "debian-installation",
        user_home / ".steam" / "steam",
        user_home / ".local" / "share" / "Steam",
        user_home
        / ".var"
        / "app"
        / "com.valvesoftware.Steam"
        / ".local"
        / "share"
        / "Steam",
        user_home / "snap" / "steam" / "common" / ".local" / "share" / "Steam",
    ]

    steam_root = find_steam_root(candidates)

    if steam_root:
        game_folder_str = find_steam_rimworld(steam_root)
        if game_folder_str:
            game_folder = Path(game_folder_str)
        else:
            game_folder = steam_root / "steamapps" / "common" / "RimWorld"

        steam_mods_folder_str = get_path_up_to_string(
            game_folder, "common", exclude=True
        )
        if steam_mods_folder_str == "":
            steam_mods_folder = (
                steam_root / "steamapps" / "workshop" / "content" / "294100"
            )
        else:
            steam_mods_folder = (
                Path(steam_mods_folder_str) / "workshop" / "content" / "294100"
            )
    else:
        game_folder = (
            user_home / ".steam" / "steam" / "steamapps" / "common" / "RimWorld"
        )
        steam_mods_folder = (
            user_home
            / ".steam"
            / "steam"
            / "steamapps"
            / "workshop"
            / "content"
            / "294100"
        )

    native_config = (
        user_home
        / ".config"
        / "unity3d"
        / "Ludeon Studios"
        / "RimWorld by Ludeon Studios"
        / "Config"
    )
    if steam_root:
        proton_config = (
            steam_root
            / "steamapps"
            / "compatdata"
            / "294100"
            / "pfx"
            / "drive_c"
            / "users"
            / "steamuser"
            / "AppData"
            / "LocalLow"
            / "Ludeon Studios"
            / "RimWorld by Ludeon Studios"
            / "Config"
        )
        if proton_config.exists():
            logger.info(f"Proton prefix detected for config: {proton_config}")
            config_folder = proton_config
        else:
            config_folder = native_config
    else:
        config_folder = native_config

    return DetectedPaths(game_folder, config_folder, steam_mods_folder, steam_root)


def get_windows_paths() -> DetectedPaths:
    """Detect RimWorld paths on Windows."""
    if sys.platform == "win32":
        user_home = Path.home()
        from app.utils.win_find_steam import find_steam_folder

        steam_folder, found = find_steam_folder()

        if not found:
            logger.error(
                "[win32] Could not find Steam folder. Using fallback assumptions"
            )
            steam_folder = "C:/Program Files (x86)/Steam"

        game_folder_str: str | Path = find_steam_rimworld(steam_folder)

        if game_folder_str == "":
            game_folder_str = f"{steam_folder}/steamapps/common/RimWorld"
        game_folder = Path(game_folder_str)

        config_folder = Path(
            f"{user_home}/AppData/LocalLow/Ludeon Studios/RimWorld by Ludeon Studios/Config"
        )

        steam_mods_folder_str = get_path_up_to_string(
            game_folder, "common", exclude=True
        )
        if steam_mods_folder_str == "":
            steam_mods_folder = Path(
                f"{steam_folder}/steamapps/workshop/content/294100"
            )
        else:
            steam_mods_folder = (
                Path(steam_mods_folder_str) / "workshop/content/294100"
            )

        return DetectedPaths(game_folder, config_folder, steam_mods_folder)
    else:
        raise ValueError("This function should only be called on Windows")


def detect_platform_paths() -> DetectedPaths:
    """Detect RimWorld paths for the current platform.

    :return: DetectedPaths with game, config, and workshop folder paths
    :raises RuntimeError: If running on an unsupported platform
    """
    from app.utils.system_info import SystemInfo

    if SystemInfo().operating_system == SystemInfo.OperatingSystem.MACOS:
        paths = get_darwin_paths()
        logger.info(f"Running on MacOS with the following paths: {paths}")
    elif SystemInfo().operating_system == SystemInfo.OperatingSystem.LINUX:
        paths = get_linux_paths()
        logger.info(f"Running on Linux with the following paths: {paths}")
    elif sys.platform == "win32":
        paths = get_windows_paths()
        logger.info(f"Running on Windows with the following paths: {paths}")
    else:
        raise RuntimeError("Attempting to autodetect paths on an unknown system")
    return paths

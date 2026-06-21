"""Service for auto-detecting RimWorld installation paths per platform."""

from pathlib import Path

from loguru import logger

from app.utils.generic import find_steam_rimworld, get_path_up_to_string
from app.utils.win_find_steam import find_steam_folder


class PathAutodetectService:
    """Detects RimWorld game, config, and workshop folder paths per platform."""

    def __init__(self) -> None:
        self._detected_steam_root: Path | None = None

    @property
    def detected_steam_root(self) -> Path | None:
        return self._detected_steam_root

    def get_darwin_paths(self) -> tuple[Path, Path, Path]:
        """Get paths for macOS.

        Uses VDF parsing to locate RimWorld in non-default Steam library
        folders, with hardcoded fallback.

        :return: (game_folder, config_folder, steam_mods_folder)
        """
        user_home = Path.home()
        candidates = [
            user_home / "Library" / "Application Support" / "Steam",
        ]

        steam_root = self._find_steam_root(candidates)
        self._detected_steam_root = steam_root

        if steam_root:
            game_folder_str = find_steam_rimworld(steam_root)
            if game_folder_str:
                game_folder = self._find_mac_app_bundle(Path(game_folder_str))
                logger.debug(f"VDF parsing found RimWorld at: {game_folder}")
            else:
                fallback_game_folder = steam_root / "steamapps" / "common" / "RimWorld"
                game_folder = self._find_mac_app_bundle(fallback_game_folder)
                logger.debug(
                    f"VDF parsing did not find RimWorld, using fallback_game_folder: {game_folder}"
                )

            steam_mods_folder_str = get_path_up_to_string(
                game_folder.parent, "common", exclude=True
            )
            if steam_mods_folder_str == "":
                steam_mods_folder: Path = (
                    steam_root / "steamapps" / "workshop" / "content" / "294100"
                )
            else:
                steam_mods_folder = (
                    Path(steam_mods_folder_str) / "workshop" / "content" / "294100"
                )
        else:
            fallback_game_folder = (
                user_home
                / "Library"
                / "Application Support"
                / "Steam"
                / "steamapps"
                / "common"
                / "RimWorld"
            )
            game_folder = self._find_mac_app_bundle(fallback_game_folder)
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

        return game_folder, config_folder, steam_mods_folder

    def get_linux_paths(self) -> tuple[Path, Path, Path]:
        """Get paths for Linux.

        Checks Debian, native, Flatpak, and Snap Steam installations in priority
        order. Uses VDF parsing to locate RimWorld in non-default library folders.
        Detects Proton prefix for config folder.

        :return: (game_folder, config_folder, steam_mods_folder)
        """
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

        steam_root = self._find_steam_root(candidates)
        self._detected_steam_root = steam_root

        if steam_root:
            game_folder_str = find_steam_rimworld(steam_root)
            if game_folder_str:
                game_folder = Path(game_folder_str)
                logger.debug(f"VDF parsing found RimWorld at: {game_folder}")
            else:
                game_folder = steam_root / "steamapps" / "common" / "RimWorld"
                logger.debug(
                    f"VDF parsing did not find RimWorld, using fallback: {game_folder}"
                )

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

        return game_folder, config_folder, steam_mods_folder

    def get_windows_paths(self) -> tuple[Path, Path, Path]:
        """Get the default paths for Windows.

        :return: (game_folder, config_folder, steam_mods_folder)
        """
        user_home = Path.home()

        steam_folder, found = find_steam_folder()

        if not found:
            logger.error(
                "[win32] Could not find Steam folder. Using fallback assumptions"
            )
            steam_folder = "C:/Program Files (x86)/Steam"

        game_folder: str | Path = find_steam_rimworld(steam_folder)

        if game_folder == "":
            game_folder = f"{steam_folder}/steamapps/common/RimWorld"
        game_folder = Path(game_folder)

        config_folder = Path(
            f"{user_home}/AppData/LocalLow/Ludeon Studios/RimWorld by Ludeon Studios/Config"
        )

        steam_mods_folder = get_path_up_to_string(game_folder, "common", exclude=True)
        if steam_mods_folder == "":
            steam_mods_folder = Path(
                f"{steam_folder}/steamapps/workshop/content/294100"
            )
        else:
            steam_mods_folder = Path(steam_mods_folder) / "workshop/content/294100"

        return game_folder, config_folder, steam_mods_folder

    def _find_steam_root(self, candidates: list[Path]) -> Path | None:
        """Find the Steam installation root from a prioritized list of paths.

        A candidate is valid if it exists as a directory and contains either
        a ``steamapps/`` directory or ``config/libraryfolders.vdf``.

        :param candidates: Ordered list of candidate Steam root paths
        :return: First valid Steam root, or None if no candidate matches
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

    @staticmethod
    def _find_mac_app_bundle(rimworld_dir: Path) -> Path:
        """Find the .app bundle in a RimWorld directory.

        Discovers the actual filesystem-cased name instead of hardcoding it,
        since macOS is case-insensitive but path comparisons are case-sensitive.
        """
        if rimworld_dir.is_dir():
            apps = list(rimworld_dir.glob("*.app"))
            if apps:
                return apps[0]
        return rimworld_dir / "RimWorldMac.app"

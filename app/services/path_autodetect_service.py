"""Service for auto-detecting RimWorld installation paths per platform."""

import fnmatch
import json
import os
import re
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

from loguru import logger

from app.utils.generic import find_steam_rimworld, get_path_up_to_string
from app.utils.win_find_steam import find_steam_folder


class PathAutodetectService:
    """Detects RimWorld game, config, and workshop folder paths per platform.

    Game-folder discovery runs as a pipeline, shared by all platforms:

    1. Steam installation via VDF parsing (unchanged behavior).
    2. Non-Steam launcher metadata (Heroic Games Launcher, GOG).
    3. Bounded, content-validated search over platform-standard roots.
    4. Legacy hardcoded fallback paths (unchanged, last resort).

    Security notes for the non-Steam discovery steps:

    - Detection is strictly read-only; nothing is executed and nothing is
      written.
    - Launcher metadata is parsed with the stdlib JSON parser from fixed,
      user-owned config locations; no shell, no interpolation, no network.
    - Filesystem searches are shallow, skip symlinked and hidden entries, and
      are entry-capped, so symlink loops or planted directory trees cannot
      make the scan unbounded.
    - Candidate folders must carry RimWorld content markers, so a look-alike
      folder cannot be picked up by its name alone.
    - Detection only pre-fills the settings dialog; the user still confirms
      every path before it is saved.
    """

    _VERSION_FILE_NAME = "Version.txt"
    # RimWorld Version.txt content, e.g. "1.6.4871 rev573"
    _VERSION_RE = re.compile(r"^\d+\.\d+")
    # Known game executables on Linux. RimWorldLinux64 ships with current
    # Steam and GOG builds; RimWorldLinux is the legacy name. The .exe names
    # cover Wine/Proton installs of the Windows build.
    _LINUX_GAME_EXECUTABLES = (
        "RimWorldLinux64",
        "RimWorldLinux",
        "RimWorldWin64.exe",
        "RimWorldWin.exe",
    )
    # GOG Galaxy (Windows) records installed games under this registry key;
    # each game gets a subkey named by its numeric ID whose "executable"
    # REG_SZ value points inside the install directory.
    _GOG_GALAXY_GAMES_KEY = "SOFTWARE\\WOW6432Node\\GOG.com\\Games"
    _MAX_SEARCH_DEPTH = 2
    _MAX_ENTRIES_PER_DIR = 500
    _MAX_METADATA_ENTRIES = 100
    _MAX_METADATA_FILE_BYTES = 5 * 1024 * 1024

    def __init__(self) -> None:
        self._detected_steam_root: Path | None = None

    @property
    def detected_steam_root(self) -> Path | None:
        return self._detected_steam_root

    def get_darwin_paths(self) -> tuple[Path, Path, Path]:
        """Get paths for macOS.

        Uses VDF parsing to locate RimWorld in non-default Steam library
        folders, with hardcoded fallback. When no Steam installation is
        found, non-Steam sources (e.g. GOG) are probed before the fallback.

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

        game_folder = self._fall_back_to_non_steam_game_folder(
            game_folder, self._find_non_steam_game_folder_macos
        )

        config_folder = (
            user_home / "Library" / "Application Support" / "Rimworld" / "Config"
        )

        return game_folder, config_folder, steam_mods_folder

    def get_linux_paths(self) -> tuple[Path, Path, Path]:
        """Get paths for Linux.

        Checks Debian, native, Flatpak, and Snap Steam installations in priority
        order. Uses VDF parsing to locate RimWorld in non-default library folders.
        Detects Proton prefix for config folder. When no Steam installation is
        found, non-Steam sources (e.g. GOG) are probed before the fallback.

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

        game_folder = self._fall_back_to_non_steam_game_folder(
            game_folder, self._find_non_steam_game_folder_linux
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

        game_folder = self._fall_back_to_non_steam_game_folder(
            game_folder, self._find_non_steam_game_folder_windows
        )

        return game_folder, config_folder, steam_mods_folder

    def _fall_back_to_non_steam_game_folder(
        self, game_folder: Path, non_steam_finder: Callable[[], Path | None]
    ) -> Path:
        """Replace a non-existing Steam-derived game folder with a non-Steam one.

        :param game_folder: Game folder resolved from Steam (may not exist).
        :param non_steam_finder: Zero-arg callable probing non-Steam sources.
        :return: The Steam-derived folder if it exists, otherwise the first
                 non-Steam folder found, otherwise the input unchanged.
        """
        if game_folder.exists():
            return game_folder
        non_steam_folder = non_steam_finder()
        if non_steam_folder is not None:
            logger.info(
                f"Steam detection did not find an installation; "
                f"using non-Steam game folder: {non_steam_folder}"
            )
            return non_steam_folder
        return game_folder

    def _find_non_steam_game_folder_macos(self) -> Path | None:
        """Search for a RimWorld .app bundle installed outside Steam (e.g. GOG).

        GOG Galaxy and the GOG offline installer place the game as
        ``RimWorld.app`` in an applications directory. Candidates must pass
        content validation before being returned.

        :return: Validated game folder, or None when nothing was found.
        """
        for root in self._macos_game_app_roots():
            if not root.is_dir():
                continue
            app_bundles: list[Path] = []
            for child in self._iter_shallow_dirs(root, 1):
                if fnmatch.fnmatch(child.name, "RimWorld*.app"):
                    app_bundles.append(child)
            # Prefer the canonical bundle name, then alphabetical order, so
            # the result is deterministic.
            app_bundles.sort(key=lambda p: (p.name != "RimWorld.app", p.name))
            for app_bundle in app_bundles:
                if self._looks_like_rimworld_mac_app(app_bundle):
                    self._log_non_steam_provenance(app_bundle)
                    logger.info(f"Found non-Steam RimWorld installation: {app_bundle}")
                    return app_bundle
        logger.debug("No non-Steam RimWorld .app bundle found")
        return None

    def _find_non_steam_game_folder_linux(self) -> Path | None:
        """Search for a RimWorld game folder installed outside Steam (e.g. GOG).

        :return: Validated game folder, or None when nothing was found.
        """
        heroic_folder = self._find_heroic_game_folder()
        if heroic_folder is not None:
            return heroic_folder
        for root in self._linux_game_search_roots():
            if not root.is_dir():
                continue
            for child in self._iter_shallow_dirs(root, self._MAX_SEARCH_DEPTH):
                if self._looks_like_rimworld_dir(child):
                    logger.info(f"Found non-Steam RimWorld installation: {child}")
                    return child
        logger.debug("No non-Steam RimWorld game folder found")
        return None

    def _find_non_steam_game_folder_windows(self) -> Path | None:
        """Search for a RimWorld game folder installed outside Steam (e.g. GOG).

        Consults the GOG Galaxy registry key for the game first (covers custom
        install drives), then Heroic metadata, then a bounded search over
        platform-standard roots. All candidates must pass content validation.

        :return: Validated game folder, or None when nothing was found.
        """
        gog_folder = self._find_gog_registry_game_folder()
        if gog_folder is not None:
            return gog_folder
        heroic_folder = self._find_heroic_game_folder()
        if heroic_folder is not None:
            return heroic_folder
        for root in self._windows_game_search_roots():
            if not root.is_dir():
                continue
            for child in self._iter_shallow_dirs(root, self._MAX_SEARCH_DEPTH):
                if self._looks_like_rimworld_windows_dir(child):
                    logger.info(f"Found non-Steam RimWorld installation: {child}")
                    return child
        logger.debug("No non-Steam RimWorld game folder found")
        return None

    def _find_heroic_game_folder(self) -> Path | None:
        """Read Heroic Games Launcher's GOG install metadata, if present.

        Heroic records installed GOG games in ``installed.json`` (a JSON array
        with ``install_path`` fields) under its config directory, which covers
        custom Heroic install locations without hardcoding them. Parsing is
        defensive: size-capped, shape-checked, and any malformed file is
        skipped rather than trusted.

        :return: Validated game folder, or None when nothing was found.
        """
        metadata_file = self._heroic_gog_metadata_file()
        if not metadata_file.is_file() or metadata_file.is_symlink():
            return None
        try:
            if metadata_file.stat().st_size > self._MAX_METADATA_FILE_BYTES:
                logger.warning("Heroic GOG metadata file is too large; skipping")
                return None
            installed = json.loads(metadata_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            logger.warning(
                "Failed to read Heroic GOG metadata; skipping", exc_info=True
            )
            return None
        if not isinstance(installed, list):
            return None
        for entry in installed[: self._MAX_METADATA_ENTRIES]:
            if not isinstance(entry, dict):
                continue
            install_path = entry.get("install_path")
            if not isinstance(install_path, str):
                continue
            candidate = Path(install_path).expanduser()
            validator = (
                self._looks_like_rimworld_windows_dir
                if sys.platform == "win32"
                else self._looks_like_rimworld_dir
            )
            if candidate.is_absolute() and validator(candidate):
                logger.info(f"Found RimWorld via Heroic metadata: {candidate}")
                return candidate
        return None

    def _macos_game_app_roots(self) -> tuple[Path, ...]:
        """Directories scanned for non-Steam RimWorld .app bundles.

        GOG Galaxy and the GOG offline installer default to /Applications;
        user-level installs live in ~/Applications. Kept as a method so tests
        can redirect the scan to a temporary tree.
        """
        return (Path("/Applications"), Path.home() / "Applications")

    def _linux_game_search_roots(self) -> tuple[Path, ...]:
        """Standard roots for GOG-style game installations on Linux.

        ``~/GOG Games`` is used by the official GOG offline installer (game
        files in ``<title>/game``) and by minigalaxy. ``~/Games`` is the
        default install root of both the Heroic Games Launcher
        (``~/Games/Heroic/...``) and Lutris (``~/Games/gog/...``). Names
        inside the roots do not matter; candidates are validated by content.
        """
        user_home = Path.home()
        return (user_home / "GOG Games", user_home / "Games")

    @staticmethod
    def _heroic_gog_metadata_file() -> Path:
        """Path to Heroic's GOG installed-games metadata, per platform."""
        user_home = Path.home()
        if sys.platform == "win32":
            return (
                user_home
                / "AppData"
                / "Roaming"
                / "heroic"
                / "gog_store"
                / "installed.json"
            )
        return user_home / ".config" / "heroic" / "gog_store" / "installed.json"

    def _windows_game_search_roots(self) -> tuple[Path, ...]:
        """Standard roots for GOG-style game installations on Windows.

        GOG Galaxy defaults to ``C:\\GOG Games``; the offline installer and
        Heroic default to ``%USERPROFILE%\\GOG Games``. Names inside the roots
        do not matter; candidates are validated by content.
        """
        user_home = Path.home()
        return (
            Path("C:/GOG Games"),
            user_home / "GOG Games",
            user_home / "Games",
        )

    def _find_gog_registry_game_folder(self) -> Path | None:
        """Read the game install directory from the GOG Galaxy registry key.

        GOG Galaxy writes a per-game subkey under
        ``HKLM\\SOFTWARE\\WOW6432Node\\GOG.com\\Games`` whose ``executable``
        value points at the game binary inside the install directory. Covers
        arbitrary custom install drives without any filesystem scanning.
        Read-only; returns None anywhere except Windows.

        :return: Validated game folder, or None when nothing was found.
        """
        if sys.platform != "win32":
            return None
        try:
            import winreg
        except ImportError:
            return None
        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE, self._GOG_GALAXY_GAMES_KEY
            ) as games_key:
                subkey_count = 0
                while subkey_count < self._MAX_METADATA_ENTRIES:
                    try:
                        subkey_name = winreg.EnumKey(games_key, subkey_count)
                    except OSError:
                        break
                    subkey_count += 1
                    try:
                        with winreg.OpenKey(games_key, subkey_name) as game_key:
                            exe_value = winreg.QueryValueEx(game_key, "executable")
                    except OSError:
                        continue
                    if not exe_value or not isinstance(exe_value[0], str):
                        continue
                    candidate = Path(exe_value[0]).parent
                    if self._looks_like_rimworld_windows_dir(candidate):
                        logger.info(
                            f"Found RimWorld via GOG Galaxy registry: {candidate}"
                        )
                        return candidate
        except OSError:
            logger.debug("GOG Galaxy registry key not present or not readable")
            return None
        return None

    @classmethod
    def _has_parsable_version_file(cls, path: Path) -> bool:
        """Check for a regular ``Version.txt`` whose first line parses as a
        RimWorld version (e.g. "1.6.4871 rev573").

        :param path: Candidate game directory.
        :return: True when the version marker is present and parsable.
        """
        version_file = path / cls._VERSION_FILE_NAME
        if not version_file.is_file() or version_file.is_symlink():
            return False
        try:
            with version_file.open("r", encoding="utf-8", errors="replace") as f:
                head = f.read(256)
        except OSError:
            return False
        lines = head.splitlines()
        first_line = lines[0].strip() if lines else ""
        return bool(cls._VERSION_RE.match(first_line))

    @classmethod
    def _looks_like_rimworld_dir(cls, path: Path) -> bool:
        """Validate that a directory carries RimWorld content markers.

        A directory counts as a RimWorld installation when it contains a
        parsable ``Version.txt`` (e.g. "1.6.4871 rev573") or one of the known
        game executables. Markers are content-based so folder names are
        irrelevant and look-alike folders are rejected.

        :param path: Candidate directory.
        :return: True when RimWorld content markers are present.
        """
        if not path.is_dir() or path.is_symlink():
            return False
        if cls._has_parsable_version_file(path):
            return True
        return any((path / exe).is_file() for exe in cls._LINUX_GAME_EXECUTABLES)

    @classmethod
    def _looks_like_rimworld_windows_dir(cls, path: Path) -> bool:
        """Validate that a directory carries Windows RimWorld content markers.

        Accepts a directory containing a parsable ``Version.txt`` or a known
        Windows game executable. Mirrors :meth:`_looks_like_rimworld_dir` for
        the Windows build of the game (GOG installs place ``Version.txt`` and
        the .exe next to ``Data/``/``Mods/`` at the install root).

        :param path: Candidate directory.
        :return: True when RimWorld content markers are present.
        """
        if not path.is_dir() or path.is_symlink():
            return False
        if cls._has_parsable_version_file(path):
            return True
        return (path / "RimWorldWin64.exe").is_file() or (
            path / "RimWorldWin.exe"
        ).is_file()

    @classmethod
    def _looks_like_rimworld_mac_app(cls, path: Path) -> bool:
        """Validate that a directory looks like a RimWorld .app bundle.

        Requires macOS bundle structure (``Contents/``) plus RimWorld content
        markers, so an arbitrary folder named ``RimWorld*.app`` is rejected.

        :param path: Candidate directory (must be named ``*.app``).
        :return: True when the bundle looks like a RimWorld installation.
        """
        if not path.name.endswith(".app") or path.is_symlink():
            return False
        contents_dir = path / "Contents"
        if not contents_dir.is_dir() or contents_dir.is_symlink():
            return False
        # Ludeon macOS bundles ship the game content at the bundle root.
        has_ludeon_layout = (path / "Data").is_dir() and (path / "Mods").is_dir()
        return has_ludeon_layout or (path / cls._VERSION_FILE_NAME).is_file()

    @classmethod
    def _iter_shallow_dirs(cls, root: Path, max_depth: int) -> Iterator[Path]:
        """Yield subdirectories of ``root`` up to ``max_depth`` levels deep.

        Bounded and symlink-safe: hidden entries are skipped, symlinked
        directories are never followed (so symlink loops cannot occur), and
        each scanned directory is entry-capped to guard against pathological
        trees.

        :param root: Directory to scan (not yielded itself).
        :param max_depth: Number of directory levels below ``root`` to scan.
        :return: Iterator over discovered subdirectories.
        """

        def _walk(current: Path, remaining_depth: int) -> Iterator[Path]:
            try:
                with os.scandir(current) as dir_entries:
                    entries = list(dir_entries)[: cls._MAX_ENTRIES_PER_DIR]
            except OSError:
                return
            for entry in entries:
                if entry.name.startswith("."):
                    continue
                try:
                    # follow_symlinks=False: symlinked directories are skipped
                    # entirely, so the walk cannot escape the scanned roots.
                    if not entry.is_dir(follow_symlinks=False):
                        continue
                except OSError:
                    continue
                child = Path(entry.path)
                yield child
                if remaining_depth > 1:
                    yield from _walk(child, remaining_depth - 1)

        return _walk(root, max_depth)

    @staticmethod
    def _log_non_steam_provenance(game_folder: Path) -> None:
        """Best-effort log of where a non-Steam installation appears to come from."""
        try:
            resources_dir = game_folder / "Contents" / "Resources"
            if (
                game_folder.name.endswith(".app")
                and resources_dir.is_dir()
                and any(resources_dir.glob("goggame-*.info"))
            ):
                logger.info(
                    "Installation appears to be GOG-distributed (goggame metadata present)"
                )
        except OSError:
            logger.debug("Could not inspect non-Steam installation provenance")

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

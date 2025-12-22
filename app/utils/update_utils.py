import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path
from tempfile import gettempdir
from typing import TYPE_CHECKING, Any, Dict, List, Optional, TypedDict, Union, cast

import requests
from loguru import logger
from PySide6.QtCore import QEventLoop, QObject, Signal
from PySide6.QtWidgets import QApplication, QMessageBox

import app.views.dialogue as dialogue
from app.utils.app_info import AppInfo
from app.utils.generic import check_internet_connection
from app.utils.zip_extractor import (
    BadZipFile,
    ZipExtractThread,
    create_zip_backup,
    get_zip_contents,
    validate_zip_integrity,
)
from app.views.task_progress_window import TaskProgressWindow
from packaging import version

# Pre-compiled regex patterns for performance
VERSION_PATTERN = re.compile(r"v?\d+[\.\-_]\d+")
TAG_PREFIX_PATTERN = re.compile(r"^v", re.IGNORECASE)

# API and network constants
GITHUB_API_URL = "https://api.github.com/repos/RimSort/RimSort/releases/latest"
API_TIMEOUT = 15
DOWNLOAD_TIMEOUT = 30

# File and archive constants
ZIP_EXTENSION = ".zip"
MSI_EXTENSION = ".msi"
DOWNLOAD_CHUNK_SIZE = 131072  # 128KB for better performance
MIN_UPDATE_SIZE = 1024  # Minimum reasonable size for an app update
UPDATER_LOG_FILENAME = "updater.log"

# Windows protected paths (application cannot write to these)
WINDOWS_PROTECTED_PATHS = [
    r"C:\PROGRAM FILES",
    r"C:\PROGRAM FILES (X86)",
    r"C:\WINDOWS",
]

# Thread timeouts and waits
BACKUP_TIMEOUT_SECONDS = 600  # 10 minutes for backup
EXTRACTION_THREAD_TIMEOUT_MS = 5000  # 5 seconds for thread cleanup
THREAD_JOIN_TIMEOUT = 5  # 5 seconds for thread join

# Platform-specific constants
# Note: TEMP_DIR_DARWIN and TEMP_DIR_DEFAULT are unused and can be removed

# No Version Dialog Constants
UNKNOWN_VERSION_TITLE = "Unknown Version Detected"
UNKNOWN_VERSION_TEXT = "Could not find version Information of RimSort, This may indicate that the application is not an offical release and may be a custom build."
UNKNOWN_VERSION_INFO = "Are you sure you want to still update anyway?"

# Standardized error messages
ERR_UPDATE_SKIPPED_TITLE = "Update skipped"
ERR_UPDATE_SKIPPED_TEXT = "You are running from Python interpreter."
ERR_UPDATE_SKIPPED_INFO = "Skipping update check..."
ERR_UPDATE_ERROR_TITLE = "RimSort Update Error"
ERR_NO_VALID_RELEASE_TITLE = "RimSort Update Error"
ERR_NO_VALID_RELEASE_TEXT = "Failed to find valid RimSort release for {system_info}"
ERR_API_CONNECTION_TITLE = "RimSort Update Error"
ERR_API_CONNECTION_TEXT = "Failed to connect to GitHub API: {error}"
ERR_DOWNLOAD_FAILED_TITLE = "Download failed"
ERR_DOWNLOAD_FAILED_TEXT = "Failed to download the update."
ERR_EXTRACTION_FAILED_TITLE = "Extraction failed"
ERR_EXTRACTION_FAILED_TEXT = "Failed to extract the downloaded update."
ERR_BACKUP_FAILED_TITLE = "Backup failed"
ERR_BACKUP_FAILED_TEXT = "Failed to create a backup before updating."
ERR_LAUNCH_FAILED_TITLE = "Launch failed"
ERR_LAUNCH_FAILED_TEXT = "Failed to launch the update script."
ERR_UPDATE_FAILED_TITLE = "Update failed"
ERR_UPDATE_FAILED_TEXT = "An unexpected error occurred during the update process."
ERR_RETRIEVE_RELEASE_TITLE = "Unable to retrieve latest release information"
ERR_RETRIEVE_RELEASE_TEXT = "Please check your internet connection and try again, You can also check 'https://github.com/RimSort/RimSort/releases' directly."

if TYPE_CHECKING:
    from app.utils.metadata import SettingsController


class UpdateError(Exception):
    """Base exception for update-related errors."""

    pass


class UpdateNetworkError(UpdateError):
    """Raised when network-related errors occur."""

    pass


class UpdateDownloadError(UpdateError):
    """Raised when download fails."""

    pass


class UpdateExtractionError(UpdateError):
    """Raised when extraction fails."""

    pass


class UpdateScriptLaunchError(UpdateError):
    """Raised when launching update script fails."""

    pass


class ReleaseInfo(TypedDict):
    """Type definition for release information dictionary."""

    version: version.Version
    tag_name: str
    download_url: str
    is_msi: bool


class DownloadInfo(TypedDict):
    """Type definition for download information dictionary."""

    url: str
    name: str
    is_msi: bool


class PlatformPatterns(TypedDict):
    """Type definition for platform pattern configuration."""

    patterns: List[str]
    arch_patterns: Dict[str, List[str]]


class ScriptConfig:
    """Configuration for platform-specific update scripts."""

    def __init__(
        self,
        script_name: str,
        start_new_session: Optional[bool],
        platform: str,
    ) -> None:
        self.script_name = script_name
        self.start_new_session = start_new_session
        self.platform = platform

    def get_script_path(self) -> Path:
        """Get the script path for this platform."""
        if self.platform == "Darwin":
            return (
                Path(sys.argv[0]).parent.parent.parent
                / "Contents"
                / "MacOS"
                / self.script_name
            )
        else:
            return AppInfo().application_folder / self.script_name

    def get_args(
        self,
        script_path: Path,
        temp_path: Path,
        log_path: Path,
        needs_elevation: bool = False,
        install_dir: Optional[Path] = None,
        update_manager: Optional["UpdateManager"] = None,
    ) -> Union[str, List[str]]:
        """
        Get the appropriate arguments for launching the update script based on platform and elevation needs.

        Args:
            script_path: Path to the update script
            temp_path: Path to the temporary extraction directory
            log_path: Path to the update log file
            needs_elevation: Whether elevated privileges are required
            install_dir: Installation directory (required for Linux)

        Returns:
            Arguments string or list for subprocess
        """
        base_args = [str(script_path), str(temp_path), str(log_path)]
        if self.platform == "Windows":
            base_args.append(str(AppInfo().application_folder))
        elif install_dir and self.platform == "Linux":
            base_args.append(str(install_dir))

        return self._build_platform_args(
            base_args, script_path, needs_elevation, update_manager
        )

    @staticmethod
    def _build_terminal_command(
        terminal: str, base_args: List[str], needs_elevation: bool
    ) -> str:
        """
        Build terminal-specific command string for launching update script.

        Args:
            terminal: Name of the terminal emulator (e.g., "gnome-terminal")
            base_args: Base arguments list [script_path, temp_path, log_path, install_dir?]
            needs_elevation: Whether to use sudo

        Returns:
            Command string for the terminal emulator

        Raises:
            ValueError: If terminal emulator is unknown
        """
        quoted_args = " ".join(shlex.quote(arg) for arg in base_args)

        # gnome-terminal uses -- instead of -e
        if terminal == "gnome-terminal":
            if needs_elevation:
                return f'gnome-terminal -- bash -c "sudo {quoted_args}"'
            else:
                return f'gnome-terminal -- bash -c "{quoted_args}; read -p \\"Press enter to close\\""'

        # konsole, xterm, and x-terminal-emulator use -e
        elif terminal in ["konsole", "xterm", "x-terminal-emulator"]:
            if needs_elevation:
                return f'{terminal} -e bash -c "sudo {quoted_args}"'
            else:
                return f'{terminal} -e bash -c "{quoted_args}; read -p \\"Press enter to close\\""'

        # xfce4-terminal and mate-terminal need nested quoting
        elif terminal in ["xfce4-terminal", "mate-terminal"]:
            if needs_elevation:
                return f"{terminal} -e \"bash -c 'sudo {quoted_args}'\""
            else:
                return f'{terminal} -e "bash -c \'{quoted_args}; read -p \\"Press enter to close\\"\'"'

        else:
            raise ValueError(f"Unknown terminal emulator: {terminal}")

    def _build_platform_args(
        self,
        base_args: List[str],
        script_path: Path,
        needs_elevation: bool,
        update_manager: Optional["UpdateManager"] = None,
    ) -> Union[str, List[str]]:
        """
        Build platform-specific arguments for launching the update script.

        Args:
            base_args: Base arguments list [script_path, temp_path, log_path, install_dir?]
            script_path: Path to the update script
            needs_elevation: Whether elevated privileges are required
            update_manager: UpdateManager instance (required for Linux platform)

        Returns:
            Arguments string or list for subprocess

        Raises:
            ValueError: If platform is unsupported or update_manager is None for Linux
        """
        if self.platform == "Darwin":
            quoted_args = " ".join(shlex.quote(arg) for arg in base_args)
            terminal_cmd = (
                f'/bin/bash {quoted_args}; read -p \\"Press enter to close\\"'
            )
            script_cmd = f"sudo {terminal_cmd}" if needs_elevation else terminal_cmd
            return f'osascript -e \'tell app "Terminal" to do script "{script_cmd}"\''
        elif self.platform == "Windows":
            if needs_elevation:
                return (
                    f"powershell.exe -NoProfile -ExecutionPolicy Bypass -Command \"Start-Process cmd -ArgumentList @('/k', "
                    f'\'cd /d \\"{script_path.parent}\\" && \\"{script_path}\\" \\"{base_args[1]}\\" \\"{base_args[2]}\\"\') '
                    '-Verb RunAs -WindowStyle Normal"'
                )
            else:
                return [
                    "cmd",
                    "/k",
                    str(script_path),
                    str(base_args[1]),
                    str(base_args[2]),
                ]
        elif self.platform == "Linux":
            if update_manager is None:
                raise ValueError("update_manager required for Linux platform")

            terminal = update_manager._detect_terminal_emulator()
            cmd = self._build_terminal_command(terminal, base_args, needs_elevation)
            logger.debug(f"Built terminal command using {terminal}")
            return cmd
        else:
            raise ValueError(f"Unsupported platform: {self.platform}")


class UpdateManager(QObject):
    update_progress = Signal(int, str)  # percent, message
    download_complete = Signal(bool, str)  # success, error_message

    # Class-level cached platform patterns for performance
    _platform_patterns = {
        "Darwin": {
            "patterns": ["Darwin", "macOS", "Mac"],
            "arch_patterns": {
                "64bit": ["x86_64", "intel"],
                "ARM64": ["arm64", "apple"],
            },
        },
        "Linux": {
            "patterns": ["Linux", "Ubuntu"],
            "arch_patterns": {
                "64bit": ["x86_64", "amd64"],
                "32bit": ["i386", "x86"],
            },
        },
        "Windows": {
            "patterns": ["Windows", "Win"],
            "arch_patterns": {
                "64bit": ["x86_64", "x64", "amd64"],
                "32bit": ["x86", "i386"],
            },
        },
    }

    # Platform-specific script configurations
    _script_configs: Dict[str, ScriptConfig] = {
        "Darwin": ScriptConfig(
            script_name="update.sh",
            start_new_session=False,
            platform="Darwin",
        ),
        "Windows": ScriptConfig(
            script_name="update.bat",
            start_new_session=None,  # Not used on Windows
            platform="Windows",
        ),
        "Linux": ScriptConfig(
            script_name="update.sh",
            start_new_session=True,
            platform="Linux",
        ),
    }

    def __init__(
        self,
        settings_controller: "SettingsController",
        main_content: Any,
        mod_info_panel: Optional[Any] = None,
    ) -> None:
        super().__init__()
        self.settings_controller = settings_controller
        self.main_content = main_content
        self.mod_info_panel = mod_info_panel
        self._update_content: bytes | None = None
        self._extracted_path: Path | None = None
        self._elevation_needed: Optional[bool] = None  # Cache elevation check result
        # Cache platform info to avoid repeated calls
        self._system = platform.system()
        self._arch = platform.architecture()[0]
        # Cache platform patterns for performance
        self._cached_patterns = (
            self._platform_patterns[self._system]
            if self._system in self._platform_patterns
            else None
        )
        self._download_cancelled = False
        self._detected_terminal: Optional[str] = (
            None  # Cache detected terminal emulator
        )
        # Progress window for update operations
        self._progress_widget: Optional[TaskProgressWindow] = None

    def _check_needs_elevation(self) -> bool:
        """
        Check if elevation is needed for the update process.
        Caches the result to avoid redundant system calls.

        Returns:
            bool: True if elevation is needed, False otherwise
        """
        if self._elevation_needed is not None:
            return self._elevation_needed

        if self._system == "Windows":
            if self._is_in_protected_path():
                self._elevation_needed = True
                return True

            # Test write access
            if self._test_write_access():
                self._elevation_needed = False
                return False
            else:
                self._elevation_needed = True
                return True
        else:
            # For non-Windows, use the original check
            self._elevation_needed = not os.access(
                AppInfo().application_folder, os.W_OK
            )
            return self._elevation_needed

    def _is_in_protected_path(self) -> bool:
        """Check if application is installed in Windows protected path."""
        app_folder = AppInfo().application_folder
        app_path_str = str(app_folder).replace("/", "\\").upper()

        for protected in WINDOWS_PROTECTED_PATHS:
            if protected in app_path_str:
                logger.info(
                    f"Application in protected path: {protected} - elevation required"
                )
                return True
        return False

    def _test_write_access(self) -> bool:
        """Test if write access is available in application folder."""
        app_folder = AppInfo().application_folder
        try:
            test_file = app_folder / "test_write.tmp"
            test_file.write_text("test")
            test_file.unlink()
            logger.debug("Write test passed; no elevation needed")
            return True
        except (OSError, IOError, PermissionError) as write_err:
            logger.info(f"Write access test failed ({write_err}); elevation required")
            return False

    def _detect_terminal_emulator(self) -> str:
        """
        Detect available terminal emulator on Linux systems.
        Caches the result to avoid redundant filesystem checks.

        Returns:
            str: Name of the detected terminal emulator

        Raises:
            UpdateScriptLaunchError: If no terminal emulator is found
        """
        if self._detected_terminal is not None:
            return self._detected_terminal

        # Priority order: desktop environment terminals first, then universal fallback
        terminal_candidates = [
            "gnome-terminal",
            "konsole",
            "xfce4-terminal",
            "mate-terminal",
            "xterm",
            "x-terminal-emulator",  # Debian/Ubuntu backward compatibility
        ]

        for terminal in terminal_candidates:
            if shutil.which(terminal) is not None:
                logger.debug(f"Detected terminal emulator: {terminal}")
                self._detected_terminal = terminal
                return terminal

        # No terminal found - provide helpful error
        raise UpdateScriptLaunchError(
            "No terminal emulator found on system. Please install one of: "
            "gnome-terminal, konsole, xfce4-terminal, mate-terminal, or xterm"
        )

    def do_check_for_update(self) -> None:
        """
        Check for RimSort updates and handle the update process.

        This method orchestrates the update process by delegating to focused sub-methods
        for better maintainability and testability.
        """
        start_time = datetime.now()
        logger.info("Starting update check process...")

        try:
            # Validate prerequisites
            if not self._validate_prerequisites():
                return

            # Fetch and compare versions
            update_info = self._fetch_and_compare_versions()
            if not update_info:
                logger.info("No update available or update declined by user")
                return

            # Handle the update process
            self._handle_update_process(update_info)

            total_time = (datetime.now() - start_time).total_seconds()
            logger.info(f"Update check process completed in {total_time:.2f}s")

        except Exception as e:
            total_time = (datetime.now() - start_time).total_seconds()
            logger.error(f"Update check failed after {total_time:.2f}s: {e}")
            dialogue.show_warning(
                title=self.tr(ERR_UPDATE_FAILED_TITLE),
                text=self.tr(ERR_UPDATE_FAILED_TEXT),
                information=f"Unexpected error during update check: {str(e)}",
                details=traceback.format_exc(),
            )

    def _validate_prerequisites(self) -> bool:
        """
        Validate all prerequisites for the update process.

        Returns:
            bool: True if all prerequisites are met, False otherwise
        """
        # Check for disable flag
        if os.getenv("RIMSORT_DISABLE_UPDATER"):
            logger.debug(
                "RIMSORT_DISABLE_UPDATER is set, skipping update check silently."
            )
            return False

        # Check if running from compiled binary built by Nuitka or running from Python interpreter
        if "__compiled__" not in globals():
            logger.debug(
                "You are running from Python interpreter. Skipping update check..."
            )
            dialogue.show_warning(
                title=ERR_UPDATE_SKIPPED_TITLE,
                text=ERR_UPDATE_SKIPPED_TEXT,
                information=ERR_UPDATE_SKIPPED_INFO,
            )
            return False

        # Check internet connection
        if not check_internet_connection():
            return False

        return True

    def _fetch_and_compare_versions(self) -> Optional[Dict[str, Any]]:
        """
        Fetch latest release information and compare versions.

        Returns:
            Dict containing update information if update is available and accepted,
            None if no update needed or update declined
        """
        # Determine if elevation is needed
        needs_elevation = self._check_needs_elevation()
        if self._system != "Windows" and needs_elevation:
            needs_elevation = False

        current_version = AppInfo().app_version
        logger.info(f"Current RimSort version: {current_version}")

        # Get the latest release info
        logger.info("Fetching latest release information from GitHub API...")
        latest_release_info = self._get_latest_release_info(needs_elevation)
        if not latest_release_info:
            logger.warning("Failed to retrieve latest release information")
            return None

        latest_version = latest_release_info["version"]
        latest_tag_name = latest_release_info["tag_name"]
        download_url = latest_release_info["download_url"]

        logger.info(f"Latest RimSort version: {latest_version}")
        logger.info(f"Update available: {latest_tag_name} ({latest_version})")

        # Compare versions
        current_version_parsed = self._parse_current_version(current_version)
        if current_version_parsed >= latest_version:
            logger.info("Already running the latest version")
            return None

        # Prompt user for update
        if not self._prompt_user_for_update(latest_tag_name, current_version):
            return None

        return {
            "download_url": download_url,
            "tag_name": latest_tag_name,
            "latest_version": latest_version,
            "needs_elevation": needs_elevation,
            "is_msi": latest_release_info.get("is_msi", False),
        }

    def _parse_current_version(self, current_version: str) -> version.Version:
        """
        Parse the current version string, handling special cases.

        Args:
            current_version: The current version string

        Returns:
            Parsed version object
        """
        try:
            if current_version == "Unknown version":
                logger.warning(
                    f"Current version is: {current_version}, assuming custom build"
                )
                answer = dialogue.show_dialogue_conditional(
                    title=self.tr(UNKNOWN_VERSION_TITLE),
                    text=self.tr(UNKNOWN_VERSION_TEXT),
                    information=self.tr(UNKNOWN_VERSION_INFO),
                )
                if answer == QMessageBox.StandardButton.Yes:
                    logger.info(f"User chose to update version: {current_version}")
                    # If user confirms, continue with update by returning a dummy version
                    return version.parse("0.0.0")
                else:
                    logger.info(f"User chose not to update version: {current_version}")
                    # If user declines, return a dummy version that's higher than any valid version
                    return version.parse("999.999.999")

            return version.parse(current_version)
        except Exception as e:
            logger.warning(f"Failed to parse version '{current_version}': {e}")
            return version.parse("0.0.0")

    def _prompt_user_for_update(
        self, latest_tag_name: str, current_version: str
    ) -> bool:
        """
        Prompt the user to confirm the update.

        Args:
            latest_tag_name: The tag name of the latest release
            current_version: The current version string

        Returns:
            True if user accepts update, False otherwise
        """
        answer = dialogue.show_dialogue_conditional(
            title=self.tr("RimSort update found"),
            text=self.tr(
                "An update to RimSort has been released: {latest_tag_name}"
            ).format(latest_tag_name=latest_tag_name),
            information=self.tr(
                "You are running RimSort {current_version}\nDo you want to update now?"
            ).format(current_version=current_version),
        )
        return answer == QMessageBox.StandardButton.Yes

    def _handle_update_process(self, update_info: Dict[str, Any]) -> None:
        """
        Handle the actual update process: download, extract, and launch.

        Args:
            update_info: Dictionary containing update information
        """
        download_url = update_info["download_url"]
        tag_name = update_info["tag_name"]

        is_msi = bool(update_info.get("is_msi", False))

        try:
            self._perform_update(download_url, tag_name, is_msi)
        except UpdateError as e:
            logger.error(f"Update process failed: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error during update: {e}")
            raise UpdateError(f"Update failed: {e}") from e

    def _get_latest_release_info(
        self, needs_elevation: bool = False
    ) -> ReleaseInfo | None:
        """
        Get the latest release information from GitHub API.

        Args:
            needs_elevation: Whether elevation is needed (affects Windows asset selection)

        Returns:
            Dictionary containing version, tag_name, download_url, and is_msi flag, or None if failed
        """
        try:
            # Use releases API for better asset information
            response = requests.get(GITHUB_API_URL, timeout=API_TIMEOUT)
            response.raise_for_status()
            release_data = response.json()

            tag_name = release_data.get("tag_name", "")
            # Normalize tag name by removing prefix 'v' if present
            normalized_tag = TAG_PREFIX_PATTERN.sub("", str(tag_name))

            # Parse version
            try:
                latest_version = version.parse(normalized_tag)
            except Exception as e:
                logger.warning(f"Failed to parse version from tag {tag_name}: {e}")
                self.show_update_error()
                return None

            # Get platform-specific download URL
            download_info = self._get_platform_download_url(
                release_data.get("assets", []), needs_elevation
            )
            if not download_info:
                system_info = f"{platform.system()} {platform.architecture()[0]} {platform.processor()}"
                dialogue.show_warning(
                    title=self.tr(ERR_NO_VALID_RELEASE_TITLE),
                    text=self.tr(ERR_NO_VALID_RELEASE_TEXT).format(
                        system_info=system_info
                    ),
                )
                return None

            return {
                "version": latest_version,
                "tag_name": tag_name,
                "download_url": download_info["url"],
                "is_msi": download_info.get("is_msi", False),
            }

        except requests.RequestException as e:
            logger.warning(f"Failed to fetch release information: {e}")
            dialogue.show_warning(
                title=self.tr(ERR_API_CONNECTION_TITLE),
                text=self.tr(ERR_API_CONNECTION_TEXT).format(error=str(e)),
            )
            return None
        except Exception as e:
            logger.warning(f"Unexpected error fetching release info: {e}")
            self.show_update_error()
            return None

    def _asset_matches(
        self,
        asset: Dict[str, Any],
        patterns: List[str],
        extension: str,
        require_arch: bool = False,
        arch_patterns: List[str] | None = None,
    ) -> bool:
        """
        Check if an asset matches the given patterns and extension.

        Args:
            asset: Asset dictionary from GitHub API
            patterns: List of patterns to match
            extension: File extension to check
            require_arch: Whether to require architecture match
            arch_patterns: Architecture patterns if require_arch is True

        Returns:
            True if asset matches, False otherwise
        """
        asset_name = asset.get("name", "")
        if isinstance(asset_name, list):
            asset_name = " ".join(asset_name)
        elif not isinstance(asset_name, str):
            asset_name = str(asset_name)
        asset_name_lower = asset_name.lower()

        # Early return if extension doesn't match
        if not asset_name_lower.endswith(extension):
            return False

        # Check system patterns
        if not any(pattern.lower() in asset_name_lower for pattern in patterns):
            return False

        # If architecture is required, check arch patterns
        if require_arch and arch_patterns:
            if not any(
                pattern.lower() in asset_name_lower for pattern in arch_patterns
            ):
                return False

        return True

    def _get_platform_download_url(
        self, assets: List[Dict[str, Any]], needs_elevation: bool = False
    ) -> DownloadInfo | None:
        """
        Get the appropriate download URL for the current platform.

        Args:
            assets: List of asset dictionaries from GitHub API
            needs_elevation: Whether elevation is needed (affects Windows asset selection)

        Returns:
            Dictionary with 'url', 'name', and 'is_msi' keys, or None if not found
        """
        if self._cached_patterns is None:
            logger.warning(f"Unsupported system: {self._system}")
            return None

        system_patterns = cast(List[str], self._cached_patterns["patterns"])
        arch_patterns_dict = cast(
            Dict[str, List[str]], self._cached_patterns["arch_patterns"]
        )
        arch_patterns = arch_patterns_dict.get(self._arch, [])

        # Determine preferred extension order
        if self._system == "Windows" and self._is_in_protected_path():
            preferred_order = [MSI_EXTENSION, ZIP_EXTENSION]
        else:
            preferred_order = (
                [ZIP_EXTENSION, MSI_EXTENSION]
                if self._system == "Windows"
                else [ZIP_EXTENSION]
            )

        logger.debug(
            f"Looking for asset matching system={self._system}, arch={self._arch}, patterns={system_patterns + arch_patterns}, order={preferred_order}"
        )

        for ext in preferred_order:
            candidate = self._find_best_asset_match(
                assets, system_patterns, arch_patterns, ext
            )
            if candidate:
                return candidate

        logger.warning(
            f"No matching asset found for {self._system} {self._arch} with extensions order {preferred_order}"
        )
        return None

    def _find_best_asset_match(
        self,
        assets: List[Dict[str, Any]],
        system_patterns: List[str],
        arch_patterns: List[str],
        preferred_extension: str,
    ) -> DownloadInfo | None:
        """
        Find the best matching asset from the list.

        Args:
            assets: List of asset dictionaries
            system_patterns: System name patterns to match
            arch_patterns: Architecture patterns to match
            preferred_extension: Preferred file extension (.zip or .msi)

        Returns:
            Dictionary with 'url', 'name', and 'is_msi' keys, or None if no match
        """
        candidate = None

        # Single pass: prefer arch-specific match, fallback to system-only
        for asset in assets:
            asset_name = str(asset.get("name", ""))
            download_url = asset.get("browser_download_url")

            if (
                download_url
                and arch_patterns
                and self._asset_matches(
                    asset,
                    system_patterns,
                    preferred_extension,
                    require_arch=True,
                    arch_patterns=arch_patterns,
                )
            ):
                logger.debug(
                    f"Found arch-specific matching asset: {asset_name} -> {download_url}"
                )
                return cast(
                    DownloadInfo,
                    {
                        "url": str(download_url),
                        "name": asset_name,
                        "is_msi": preferred_extension == MSI_EXTENSION,
                    },
                )
            elif download_url and self._asset_matches(
                asset, system_patterns, preferred_extension, require_arch=False
            ):
                logger.debug(
                    f"Found system-only matching asset: {asset_name} -> {download_url}"
                )
                if candidate is None:  # Only set if no arch-specific found
                    candidate = cast(
                        DownloadInfo,
                        {
                            "url": str(download_url),
                            "name": asset_name,
                            "is_msi": preferred_extension == MSI_EXTENSION,
                        },
                    )

        return candidate

    def _on_download_cancel(self) -> None:
        self._download_cancelled = True

    def _download_update_worker(self, url: str) -> None:
        try:
            self._download_update(url)
            self.download_complete.emit(True, "")
        except Exception as e:
            self.download_complete.emit(False, str(e))

    def _perform_update(self, download_url: str, tag_name: str, is_msi: bool) -> None:
        """
        Download and extract the update, then launch the update script.

        Args:
            download_url: URL to download the update from
            tag_name: Tag name of the release
        """
        try:
            logger.debug(
                f"Downloading & extracting RimSort release from: {download_url}"
            )

            # Download with progress widget
            self._download_cancelled = False
            self._progress_widget = TaskProgressWindow(
                title="RimSort Update",
                show_message=True,
                show_percent=True,
            )
            self._progress_widget.update_progress(
                0,
                self.tr("Downloading RimSort {tag_name} release...").format(
                    tag_name=tag_name
                ),
            )
            self._progress_widget.cancel_requested.connect(self._on_download_cancel)
            self.update_progress.connect(self._progress_widget.update_progress)

            download_result: dict[str, Any] = {"success": False, "error": ""}
            loop = QEventLoop()

            def on_complete(success: bool, error: str) -> None:
                download_result["success"] = success
                download_result["error"] = error
                loop.quit()
                try:
                    if self._progress_widget:
                        self._progress_widget.close()
                        # Remove from panel if it was added there
                        if self.mod_info_panel:
                            self.mod_info_panel.panel.removeWidget(
                                self._progress_widget
                            )
                except Exception:
                    pass

            self.download_complete.connect(on_complete)

            worker = threading.Thread(
                target=self._download_update_worker, args=(download_url,), daemon=True
            )
            worker.start()

            # Show progress widget in panel or as standalone window
            if self.mod_info_panel:
                self.mod_info_panel.info_panel_frame.hide()
                if hasattr(self.main_content, "disable_enable_widgets_signal"):
                    self.main_content.disable_enable_widgets_signal.emit(False)
                self.mod_info_panel.panel.addWidget(self._progress_widget)
                self._progress_widget.show()
            else:
                self._progress_widget.show()

            # Wait for download to complete without blocking event loop
            loop.exec()

            if not download_result["success"] or self._update_content is None:
                if self._download_cancelled:
                    raise UpdateDownloadError("Download cancelled by user")
                raise UpdateDownloadError(
                    download_result["error"] or "Download did not complete successfully"
                )

            # Extract or save with progress window
            try:
                self._extract_update_with_progress(is_msi)
            except Exception as e:
                logger.error(f"Extraction/preparation failed: {e}")
                raise UpdateExtractionError(f"Extraction failed: {str(e)}") from e

            update_source_path = self._extracted_path
            logger.info(f"Update extracted to: {update_source_path}")

            if update_source_path is None:
                raise UpdateExtractionError(
                    "Extraction/preparation did not complete successfully"
                )

            # Confirm installation
            answer = dialogue.show_dialogue_conditional(
                title=self.tr("Update downloaded"),
                text=self.tr("Do you want to proceed with the update?"),
                information=self.tr(
                    f"\nSuccessfully retrieved latest release.\nThe update will be installed from: {update_source_path}"
                ),
            )

            if answer != QMessageBox.StandardButton.Yes:
                logger.info("User declined update")
                # Restore panel if it was hidden
                if self.mod_info_panel:
                    self.mod_info_panel.info_panel_frame.show()
                return

            # Check if backup is enabled in settings
            if self.settings_controller.settings.enable_backup_before_update:
                # Create backup of current installation with progress window
                self._create_backup_with_progress()
                # Clean up old backups after successful backup creation
                self._cleanup_old_backups()

            # Prepare for update script execution
            logger.info("Preparing to launch update...")
            log_path = self._prepare_update_log(self._system)
            needs_elevation = self._check_needs_elevation()

            # Launch update script or MSI installer
            self._launch_update_script(
                update_source_path, log_path, needs_elevation, is_msi
            )

        except UpdateDownloadError as e:
            logger.error(f"Update download failed: {e}")
            dialogue.show_warning(
                title=self.tr(ERR_DOWNLOAD_FAILED_TITLE),
                text=self.tr(ERR_DOWNLOAD_FAILED_TEXT),
                information=f"Error: {str(e)}\nURL: {download_url}",
            )
        except UpdateExtractionError as e:
            logger.error(f"Update extraction failed: {e}")
            dialogue.show_warning(
                title=self.tr(ERR_EXTRACTION_FAILED_TITLE),
                text=self.tr(ERR_EXTRACTION_FAILED_TEXT),
                information=f"Error: {str(e)}",
            )
        except UpdateScriptLaunchError as e:
            logger.error(f"Update script launch failed: {e}")
            dialogue.show_warning(
                title=self.tr(ERR_LAUNCH_FAILED_TITLE),
                text=self.tr(ERR_LAUNCH_FAILED_TEXT),
                information=f"Error: {str(e)}",
            )
        except Exception as e:
            logger.error(f"Unexpected update process failure: {e}")
            dialogue.show_warning(
                title=self.tr(ERR_UPDATE_FAILED_TITLE),
                text=self.tr(ERR_UPDATE_FAILED_TEXT),
                information=f"Error: {str(e)}\nURL: {download_url}",
                details=traceback.format_exc(),
            )
        finally:
            # Always restore the panel if it was hidden
            if self.mod_info_panel:
                try:
                    self.mod_info_panel.info_panel_frame.show()
                    if hasattr(self.main_content, "disable_enable_widgets_signal"):
                        self.main_content.disable_enable_widgets_signal.emit(True)
                except Exception:
                    pass

    def _get_file_size(self, url: str) -> int:
        """
        Get the file size from the URL for progress tracking.

        Args:
            url: URL to check

        Returns:
            File size in bytes, or 0 if unable to determine
        """
        try:
            head_response = requests.head(
                url, timeout=API_TIMEOUT, allow_redirects=True
            )
            return int(head_response.headers.get("content-length", 0))
        except Exception as e:
            logger.debug(f"Failed to get file size: {e}")
            return 0

    def _format_size(self, n: int) -> str:
        units = ["B", "KB", "MB", "GB", "TB"]
        size = float(n)
        i = 0
        while size >= 1024 and i < len(units) - 1:
            size /= 1024.0
            i += 1
        if i == 0:
            return f"{int(size)} {units[i]}"
        return f"{size:.1f} {units[i]}"

    def _download_with_progress(
        self, response: requests.Response, total_size: int
    ) -> bytes:
        """
        Download content with progress tracking.

        Args:
            response: Streaming response object
            total_size: Total file size for progress calculation

        Returns:
            Downloaded content as bytes
        """
        content = bytearray()
        downloaded_size = 0
        chunk_count = 0
        downloaded_since_last_emit = 0
        start_time = datetime.now()

        if total_size <= 0:
            self.update_progress.emit(-1, "Downloading...")

        for chunk in response.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
            if self._download_cancelled:
                raise UpdateDownloadError("Download cancelled by user")
            if chunk:
                content.extend(chunk)
                downloaded_size += len(chunk)
                chunk_count += 1
                downloaded_since_last_emit += len(chunk)

                # Emit progress approximately every 512KB
                emit_update = downloaded_since_last_emit >= 512 * 1024

                if emit_update:
                    elapsed = (datetime.now() - start_time).total_seconds()
                    speed = downloaded_size / elapsed if elapsed > 0 else 0

                    if total_size > 0:
                        progress = (downloaded_size / total_size) * 100
                        logger.debug(
                            f"Download progress: {progress:.1f}% ({downloaded_size}/{total_size} bytes) - Speed: {speed:.2f} B/s"
                        )
                        self.update_progress.emit(
                            int(progress),
                            f"Downloading... {progress:.1f}% ({self._format_size(downloaded_size)}/{self._format_size(total_size)})",
                        )
                    else:  # total_size <= 0
                        self.update_progress.emit(
                            -1,
                            f"Downloading... {self._format_size(downloaded_size)}",
                        )

                    downloaded_since_last_emit = 0  # reset counter

        total_time = (datetime.now() - start_time).total_seconds()
        avg_speed = len(content) / total_time if total_time > 0 else 0
        logger.debug(
            f"Downloaded {len(content)} bytes in {chunk_count} chunks over {total_time:.2f}s (avg speed: {avg_speed:.2f} B/s)"
        )
        if self._download_cancelled:
            raise UpdateDownloadError("Download cancelled by user")

        if total_size > 0:
            self.update_progress.emit(100, "Download complete")
        else:
            self.update_progress.emit(
                100, f"Download complete ({self._format_size(len(content))})"
            )
        return bytes(content)

    def _validate_download(self, content: bytes) -> None:
        """
        Validate downloaded content.

        Args:
            content: Downloaded content

        Raises:
            UpdateDownloadError: If validation fails
        """
        if len(content) == 0:
            raise UpdateDownloadError("Downloaded file is empty")
        if len(content) < MIN_UPDATE_SIZE:
            raise UpdateDownloadError(
                f"Downloaded file too small ({len(content)} bytes)"
            )

    def _download_update(self, url: str) -> None:
        """
        Download the update to memory using requests with progress tracking.

        Args:
            url: URL to download from

        Raises:
            UpdateDownloadError: If download fails
        """
        logger.info(f"Starting download from URL: {url}")
        try:
            # Get file size first for progress tracking
            total_size = self._get_file_size(url)
            if total_size:
                logger.info(f"File size: {total_size / (1024 * 1024):.2f} MB")

            response = requests.get(url, timeout=DOWNLOAD_TIMEOUT, stream=True)
            response.raise_for_status()
            logger.debug(f"HTTP response status: {response.status_code}")

            # Download with progress tracking
            content = self._download_with_progress(response, total_size)

            # Validate downloaded content
            self._validate_download(content)

            self._update_content = content
            logger.info("Update downloaded and validated successfully")

        except requests.RequestException as e:
            logger.error(f"Download failed: {e}")
            raise UpdateDownloadError(f"Failed to download update: {e}") from e
        except UpdateError:
            raise
        except Exception as e:
            logger.error(f"Unexpected error during download: {e}")
            raise UpdateDownloadError(f"Failed to download update: {e}") from e

    def _create_temp_dir(self) -> Path:
        """
        Create a unique temporary directory for update extraction.

        Returns:
            Path to the created temporary directory
        """
        temp_base = (
            Path(gettempdir())
            / f"RimSort_update_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
        temp_base.mkdir(exist_ok=True)
        return temp_base

    def _extract_zip(self, content: bytes, temp_base: Path) -> int:
        """
        Extract ZIP content to the temporary directory using ZipExtractThread with UI progress.

        Args:
            content: ZIP file content as bytes
            temp_base: Temporary directory to extract to

        Returns:
            Number of files extracted

        Raises:
            UpdateExtractionError: If ZIP is corrupted or extraction fails
        """
        logger.info("Extracting update from ZIP")

        # Write content to temporary ZIP file for extraction
        temp_zip_path = temp_base.parent / f"{temp_base.name}.zip"
        temp_zip_path.write_bytes(content)

        try:
            # Validate ZIP integrity
            is_valid, error_msg = validate_zip_integrity(temp_zip_path)
            if not is_valid:
                logger.error(f"ZIP validation failed: {error_msg}")
                raise UpdateExtractionError(error_msg)

            # Get ZIP contents
            zip_contents = get_zip_contents(temp_zip_path)
            extracted_files = len(zip_contents)
            logger.info(f"ZIP contains {extracted_files} files")

            # Create and display extraction progress widget
            self._progress_widget = TaskProgressWindow(
                title="Extracting Update",
                show_message=True,
                show_percent=True,
            )
            self._progress_widget.set_message("Extracting files...")

            # Show progress widget in panel or as standalone window
            if self.mod_info_panel:
                self.mod_info_panel.info_panel_frame.hide()
                self.mod_info_panel.panel.addWidget(self._progress_widget)
                self._progress_widget.show()
            else:
                self._progress_widget.show()

            # Create and run extraction thread
            extraction_result: dict[str, Any] = {
                "success": False,
                "error": "",
                "done": False,
            }
            loop = QEventLoop()

            def on_extraction_progress(percent: int, message: str) -> None:
                if self._progress_widget:
                    self._progress_widget.update_progress(percent, message)

            def on_extraction_finished(success: bool, message: str) -> None:
                extraction_result["success"] = success
                extraction_result["error"] = message
                extraction_result["done"] = True
                loop.quit()
                try:
                    if self._progress_widget:
                        self._progress_widget.close()
                        # Remove from panel if it was added there
                        if self.mod_info_panel:
                            self.mod_info_panel.panel.removeWidget(
                                self._progress_widget
                            )
                            # Restore panel visibility
                            self.mod_info_panel.info_panel_frame.show()
                except Exception as e:
                    logger.debug(f"Error closing progress widget: {e}")

            extract_thread = ZipExtractThread(
                zip_path=str(temp_zip_path),
                target_path=str(temp_base),
                overwrite_all=True,
                delete=True,
            )
            extract_thread.progress.connect(on_extraction_progress)
            extract_thread.finished.connect(on_extraction_finished)
            extract_thread.start()

            # Wait for extraction to complete without blocking event loop
            loop.exec()

            # Ensure thread is properly cleaned up before continuing
            extract_thread.wait(EXTRACTION_THREAD_TIMEOUT_MS)
            if extract_thread.isRunning():
                logger.warning(
                    "Extraction thread still running after timeout, forcing quit"
                )
                extract_thread.quit()
                extract_thread.wait(2000)  # Final attempt to stop thread

            if not extraction_result["success"]:
                raise UpdateExtractionError(
                    f"Extraction failed: {extraction_result['error']}"
                )

            logger.info(f"Extracted {extracted_files} files from ZIP")
            return extracted_files

        except BadZipFile as e:
            raise UpdateExtractionError(f"Invalid ZIP file: {e}") from e
        finally:
            # Clean up temporary ZIP file if it still exists
            if temp_zip_path.exists():
                try:
                    temp_zip_path.unlink()
                except Exception as e:
                    logger.debug(f"Failed to clean up temp ZIP file: {e}")

    def _normalize_structure(self, temp_base: Path, extracted_files: int) -> None:
        """
        Normalize the extracted structure by moving contents to root if wrapped.

        Args:
            temp_base: Temporary directory containing extracted files
            extracted_files: Number of files extracted
        """
        logger.info("Normalizing extracted structure")

        # Create and display normalization progress widget
        self._progress_widget = TaskProgressWindow(
            title="Normalizing Update",
            show_message=True,
            show_percent=False,
        )
        self._progress_widget.set_message("Normalizing extracted structure...")

        # Show progress widget in panel or as standalone window
        if self.mod_info_panel:
            self.mod_info_panel.info_panel_frame.hide()
            self.mod_info_panel.panel.addWidget(self._progress_widget)
            self._progress_widget.show()
        else:
            self._progress_widget.show()

        # Use a thread and event loop to keep UI responsive during normalization
        normalization_result: dict[str, Any] = {"success": False, "error": None}
        loop = QEventLoop()

        def worker_func() -> None:
            try:
                self._normalize_extracted_structure(temp_base, extracted_files)
                normalization_result["success"] = True
            except Exception as e:
                normalization_result["error"] = e
            finally:
                logger.debug("Structure normalization worker thread completed")
                loop.quit()

        thread = threading.Thread(target=worker_func, daemon=False)
        thread.start()

        loop.exec()

        try:
            if self._progress_widget:
                self._progress_widget.close()
                # Remove from panel if it was added there
                if self.mod_info_panel:
                    self.mod_info_panel.panel.removeWidget(self._progress_widget)
                    # Restore panel visibility
                    self.mod_info_panel.info_panel_frame.show()
        except Exception:
            pass

        if not normalization_result["success"]:
            error = normalization_result["error"]
            if isinstance(error, UpdateExtractionError):
                raise error
            raise UpdateExtractionError(
                f"Structure normalization failed: {error}"
            ) from error

        logger.debug(f"Normalized update ready at: {temp_base}")

    def _extract_update(self, is_msi: bool = False) -> Path:
        """
        Extract the downloaded update to a dedicated temporary directory and normalize structure,
        or save MSI file to temp location.

        Args:
            is_msi: Whether the update is an MSI installer (don't extract, just save)

        Raises:
            UpdateExtractionError: If extraction or saving fails
        """
        logger.info("Extracting update")
        try:
            if self._update_content is None:
                logger.error("No update content available")
                raise UpdateExtractionError(
                    "No update content available for extraction"
                )

            if is_msi:
                # For MSI, just save the file to temp location
                temp_base = self._create_temp_dir()
                msi_path = temp_base / "RimSort_Update.msi"
                msi_path.write_bytes(self._update_content)
                logger.info("MSI prepared")
                self._extracted_path = msi_path
                return msi_path
            else:
                # Create unique temp dir for ZIP extraction
                temp_base = self._create_temp_dir()

                # Extract ZIP content
                extracted_files = self._extract_zip(self._update_content, temp_base)
                logger.info(f"Extracted {extracted_files} files")

                # Normalize structure
                self._normalize_structure(temp_base, extracted_files)

                logger.info("Update extraction complete")

                self._extracted_path = temp_base
                return temp_base

        except BadZipFile as e:
            logger.error(f"Invalid ZIP file: {e}")
            raise UpdateExtractionError(
                f"Downloaded file is not a valid ZIP archive: {e}"
            ) from e
        except UpdateError:
            raise
        except Exception as e:
            logger.error(f"Extraction failed: {e}")
            raise UpdateExtractionError(f"Failed to extract update: {e}") from e

    def _should_unwrap_directory(self, top_dir: Path) -> bool:
        """
        Determine if a directory should be unwrapped based on platform-specific rules.

        Args:
            top_dir: The directory to check

        Returns:
            True if the directory should be unwrapped, False otherwise
        """
        top_dir_name = top_dir.name.lower()

        # Common wrapper patterns
        if any(
            keyword in top_dir_name for keyword in ["app", "application", "release"]
        ):
            return True

        # Version-like directory names
        if VERSION_PATTERN.match(top_dir_name):
            return True

        # Platform-specific rules
        if self._system == "Darwin":
            return top_dir_name != "rimsort.app"
        elif self._system == "Windows":
            return True
        elif self._system == "Linux":
            return top_dir_name.lower() not in ["rimsort", "rimsort.app"]

        return False

    def _move_directory_contents(self, source_dir: Path, dest_dir: Path) -> int:
        """
        Move all contents from source directory to destination directory safely.

        Args:
            source_dir: Source directory to move contents from
            dest_dir: Destination directory to move contents to

        Returns:
            Number of items successfully moved
        """
        moved_items = 0
        for item in source_dir.iterdir():
            if not item.exists():
                logger.warning(f"Item {item} does not exist, skipping")
                continue
            dest = dest_dir / item.name
            try:
                if dest.exists():
                    if dest.is_dir():
                        shutil.rmtree(dest)
                    else:
                        dest.unlink()
                shutil.move(str(item), str(dest_dir))
                moved_items += 1
            except (OSError, IOError, FileNotFoundError) as e:
                logger.warning(
                    f"Failed to move {item} to {dest_dir}: {e}. Skipping item."
                )
                continue
        return moved_items

    def _validate_executable_presence(
        self, extract_path: Path, children: List[Path]
    ) -> None:
        """
        Validate that the expected executable is present in the extracted structure.

        Args:
            extract_path: Path to the extracted contents
            children: List of child paths in extract_path

        Raises:
            UpdateExtractionError: If executable is not found
        """
        expected_executable = "RimSort.exe" if self._system == "Windows" else "RimSort"
        executable_found = False

        if self._system == "Darwin":
            # Look for .app bundle
            for child in children:
                if child.is_dir() and child.name.endswith(".app"):
                    app_bundle = child
                    executable_path = (
                        app_bundle / "Contents" / "MacOS" / expected_executable
                    )
                    if executable_path.exists():
                        executable_found = True
                        logger.info("Found macOS executable")
                        break
            if not executable_found:
                logger.error("RimSort.app bundle not found")
                raise UpdateExtractionError(
                    "Expected RimSort.app bundle with executable not found after normalization"
                )
        else:
            # Look for executable directly
            executable_path = extract_path / expected_executable
            if executable_path.exists():
                executable_found = True
                logger.info(f"Found executable: {expected_executable}")
            else:
                # Fallback: check if executable is in any subdirectory
                for child in children:
                    if child.is_dir():
                        candidate_path = child / expected_executable
                        if candidate_path.exists():
                            executable_found = True
                            logger.info("Found executable in subdirectory")
                            break

            if not executable_found:
                logger.error(
                    f"Expected executable '{expected_executable}' not found after normalization. Children: {[c.name for c in children]}"
                )
                # Log all files recursively for debugging
                all_files = []
                for root, dirs, files in os.walk(extract_path):
                    for file in files:
                        rel_path = os.path.relpath(
                            os.path.join(root, file), extract_path
                        )
                        all_files.append(rel_path)
                logger.error(
                    f"All files in extract_path: {all_files[:50]}..."
                )  # Limit to first 50
                raise UpdateExtractionError(
                    f"Expected executable '{expected_executable}' not found at expected location after normalization"
                )

    def _normalize_extracted_structure(
        self, extract_path: Path, num_files: int
    ) -> None:
        """
        Normalize the extracted ZIP structure by moving contents to root if wrapped.

        Args:
            extract_path: Path to the extracted contents
            num_files: Number of files extracted (for validation)

        Raises:
            UpdateExtractionError: If normalization fails
        """
        try:
            if not extract_path.exists():
                raise UpdateExtractionError(
                    "Extracted path does not exist after extraction"
                )

            children = list(extract_path.iterdir())
            logger.debug(f"Initial extracted children: {[c.name for c in children]}")
            if len(children) == 0:
                raise UpdateExtractionError("No files extracted from ZIP")

            # Check for common ZIP wrapping patterns, unwrap recursively if needed
            while len(children) == 1 and children[0].is_dir():
                top_dir = children[0]

                if not self._should_unwrap_directory(top_dir):
                    logger.debug(
                        f"No unwrapping needed for '{top_dir.name}'; using existing structure"
                    )
                    break

                logger.debug(
                    f"Detected wrapped structure in '{top_dir.name}'; normalizing"
                )
                logger.debug(
                    f"Wrapper '{top_dir.name}' children: {[c.name for c in top_dir.iterdir()]}"
                )

                # Move all contents from top_dir to extract_path
                moved_items = self._move_directory_contents(top_dir, extract_path)

                if moved_items == 0:
                    logger.warning(
                        "No items were successfully moved during normalization"
                    )
                    break

                # Remove empty top_dir if possible
                try:
                    top_dir.rmdir()
                    logger.debug("Structure normalized: contents moved to root")
                except OSError as e:
                    logger.warning(f"Failed to remove wrapper dir {top_dir}: {e}")

                # Refresh children list after unwrapping
                children = list(extract_path.iterdir())
                logger.debug(
                    f"Post-normalization children: {[c.name for c in children]}"
                )

            # Validate expected structure based on platform
            self._validate_executable_presence(extract_path, children)
        except Exception as e:
            logger.error(f"Unexpected error during structure normalization: {e}")
            logger.error(f"Extract path: {extract_path}")
            logger.error(
                f"Children: {[c.name for c in extract_path.iterdir()] if extract_path.exists() else 'N/A'}"
            )
            raise UpdateExtractionError(
                f"Structure normalization failed: {str(e)}"
            ) from e

    def _launch_update_script(
        self,
        update_source_path: Path,
        log_path: Path,
        needs_elevation: bool,
        is_msi: bool = False,
    ) -> None:
        """
        Launch the appropriate update script or MSI installer for the current platform.

        This method has been refactored to separate platform-specific launch logic
        into dedicated methods for better maintainability and separation of concerns.
        """
        # Stop watchdog before update
        logger.info("Stopping watchdog Observer thread before update...")
        self.main_content.stop_watchdog_signal.emit()

        if is_msi:
            if self._system != "Windows":
                raise UpdateScriptLaunchError(
                    "MSI installers are only supported on Windows"
                )
            # Validate MSI path
            if not update_source_path.exists() or not update_source_path.is_file():
                raise UpdateScriptLaunchError(
                    f"MSI file not found or is not a file: {update_source_path}"
                )
            self._launch_msi_installer(update_source_path, log_path, needs_elevation)
            return

        try:
            script_path, args_repr, start_new_session, install_dir = (
                self._get_script_info(update_source_path, log_path, needs_elevation)
            )

            # Validate script exists before proceeding
            if not script_path.exists():
                raise UpdateScriptLaunchError(f"Update script not found: {script_path}")

            # For Windows, copy update.bat to app_storage_folder to avoid conflicts during update
            if self._system == "Windows":
                app_storage_folder = AppInfo().app_storage_folder
                temp_script_path = app_storage_folder / "update.bat"

                # Copy update.bat to app storage folder
                try:
                    shutil.copy2(str(script_path), str(temp_script_path))
                    logger.debug(
                        f"Copied update.bat to app storage: {temp_script_path}"
                    )
                    script_path = temp_script_path

                    # Rebuild args with new script path
                    config = self._script_configs[self._system]
                    args_repr = config.get_args(
                        script_path,
                        update_source_path,
                        log_path,
                        needs_elevation,
                        install_dir,
                        update_manager=self,
                    )
                    logger.debug(f"Updated script path to: {script_path}")
                except Exception as e:
                    logger.warning(
                        f"Failed to copy update.bat to app storage, using original: {e}"
                    )

            if self._system == "Windows":
                p = self._launch_windows_update_script(
                    script_path, args_repr, needs_elevation
                )
            else:
                p = self._launch_posix_update_script(
                    script_path,
                    args_repr,
                    needs_elevation,
                    update_source_path,
                    log_path,
                    install_dir,
                )

            logger.debug(f"External updater script launched with PID: {p.pid}")
            logger.debug(f"Arguments used: {args_repr}")

            # Give subprocess time to initialize before exit
            time.sleep(1)

            # Exit the application to allow update
            sys.exit(0)

        except Exception as e:
            raise UpdateScriptLaunchError(f"Failed to launch update script: {e}") from e

    def _launch_windows_update_script(
        self,
        script_path: Path,
        args_repr: Union[str, List[str]],
        needs_elevation: bool,
    ) -> subprocess.Popen[Any]:
        """
        Launch the update script on Windows platform.

        Args:
            script_path: Path to the update script
            args_repr: Arguments for the script
            needs_elevation: Whether to run with elevated privileges

        Returns:
            The subprocess.Popen object for the launched script
        """
        cwd = str(AppInfo().application_folder)
        if needs_elevation:
            # Use PowerShell to run as administrator
            p = subprocess.Popen(
                args_repr,
                shell=True,
                cwd=cwd,
            )
        else:
            # Convert list args to string command for proper window display and argument passing
            if isinstance(args_repr, list):
                # Build command string with proper quoting for paths with spaces
                cmd_parts = []
                for arg in args_repr:
                    arg_str = str(arg)
                    # Quote arguments that contain spaces
                    if " " in arg_str:
                        cmd_parts.append(f'"{arg_str}"')
                    else:
                        cmd_parts.append(arg_str)
                cmd_str = " ".join(cmd_parts)
            else:
                cmd_str = args_repr

            logger.debug(f"Launching update script with command: {cmd_str}")

            # Use 'start' command to ensure visible console window
            start_cmd = f'start "RimSort Update" /D "{cwd}" {cmd_str}'
            logger.debug(f"Using start command: {start_cmd}")

            p = subprocess.Popen(
                start_cmd,
                shell=True,
                cwd=cwd,
            )
        return p

    def _launch_posix_update_script(
        self,
        script_path: Path,
        args_repr: Union[str, List[str]],
        needs_elevation: bool,
        update_source_path: Path,
        log_path: Path,
        install_dir: Path,
    ) -> subprocess.Popen[Any]:
        """
        Launch the update script on POSIX systems (Linux/macOS).

        Args:
            script_path: Path to the update script
            args_repr: Arguments for the script
            needs_elevation: Whether to run with elevated privileges
            update_source_path: Path to the update source
            log_path: Path to the log file
            install_dir: Installation directory

        Returns:
            The subprocess.Popen object for the launched script
        """
        # Ensure script is executable
        if script_path.exists() and not os.access(script_path, os.X_OK):
            try:
                os.chmod(script_path, 0o755)
                logger.debug(f"Made script executable: {script_path}")
            except OSError as e:
                logger.warning(f"Could not make script executable: {e}")

        # For systems requiring elevation, copy script to temp location to avoid permission issues
        if needs_elevation:
            temp_script_path = os.path.join(
                tempfile.gettempdir(), os.path.basename(script_path)
            )
            shutil.copy2(str(script_path), temp_script_path)
            os.chmod(temp_script_path, 0o755)
            logger.debug(f"Copied script to temp location: {temp_script_path}")
            script_path = Path(temp_script_path)
            # Rebuild args_repr with the new script path
            config = self._script_configs[self._system]
            args_repr = config.get_args(
                script_path,
                update_source_path,
                log_path,
                needs_elevation,
                install_dir,
                update_manager=self,
            )

        # Launch in terminal emulator
        p = subprocess.Popen(
            args_repr,
            shell=True,
            cwd=str(AppInfo().application_folder),
        )
        return p

    def _launch_msi_installer(
        self, msi_path: Path, log_path: Path, needs_elevation: bool
    ) -> None:
        """
        Launch the MSI installer on Windows.

        The MSI is configured with CustomActions to automatically launch RimSort.exe
        after installation completes. Windows handles UAC elevation if required.

        Args:
            msi_path: Path to the MSI file
            log_path: Path to the installation log file
            needs_elevation: Whether the app is installed in a protected location

        Raises:
            UpdateScriptLaunchError: If MSI launch fails
        """
        # Validate MSI file exists
        if not msi_path.exists():
            raise UpdateScriptLaunchError(f"MSI file not found: {msi_path}")

        if not msi_path.is_file():
            raise UpdateScriptLaunchError(f"MSI path is not a file: {msi_path}")

        # Ensure log directory exists
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
        except (OSError, IOError) as e:
            logger.warning(f"Could not create log directory: {e}")

        # Build msiexec command
        cmd = f'msiexec /i "{msi_path}" /passive /norestart /log "{log_path}"'

        try:
            logger.info(f"Launching MSI installer: {msi_path}")
            subprocess.Popen(cmd, shell=True)
            self.update_progress.emit(100, "Update launched!")
            logger.info("MSI launched, exiting RimSort to allow file replacement")

            # Give subprocess time to initialize before exit
            time.sleep(1)

        except FileNotFoundError as e:
            raise UpdateScriptLaunchError(f"msiexec executable not found: {e}") from e
        except Exception as e:
            raise UpdateScriptLaunchError(f"Failed to launch MSI: {e}") from e

        # Exit immediately to allow MSI to replace files and process
        sys.exit(0)

    def _prepare_update_log(self, system: str) -> Path:
        """
        Prepare the update log file and write prologue.

        Args:
            system: The current platform system

        Returns:
            Path to the log file
        """
        log_dir = AppInfo().user_log_folder
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / UPDATER_LOG_FILENAME

        # Small prologue in the updater log to aid debugging
        try:
            with open(log_path, "a", encoding="utf-8", errors="ignore") as lf:
                lf.write(
                    f"\n===== RimSort updater launched: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ({system}) =====\n"
                )
        except Exception:
            # Non-fatal; continue without preface
            pass

        return log_path

    def _get_script_info(
        self, update_source_path: Path, log_path: Path, needs_elevation: bool
    ) -> tuple[Path, Union[str, List[str]], Optional[bool], Path]:
        """
        Get the script path, arguments representation, and session flag for the platform.

        Args:
            update_source_path: Path to the extracted update directory
            log_path: Path to the log file
            needs_elevation: Whether to run with elevated privileges

        Returns:
            Tuple of (script_path, args_repr, start_new_session, install_dir)
        """
        config = self._script_configs[self._system]
        script_path = config.get_script_path()
        install_dir = script_path.parent
        args_repr = config.get_args(
            script_path,
            update_source_path,
            log_path,
            needs_elevation,
            install_dir,
            update_manager=self,
        )
        start_new_session = config.start_new_session

        return script_path, args_repr, start_new_session, install_dir

    def _extract_update_with_progress(self, is_msi: bool = False) -> None:
        """
        Extract or prepare the update with a progress window.

        For ZIP files, _extract_zip creates its own progress window with ZipExtractThread.
        MSI preparation is instant (just writes bytes) so no UI needed.
        Extraction runs on main thread to ensure Qt operations work correctly.

        Args:
            is_msi: Whether the update is an MSI installer
        """
        # Run extraction on main thread (Qt operations require main thread)
        self._extracted_path = self._extract_update_thread_worker(is_msi)

    def _extract_update_thread_worker(self, is_msi: bool = False) -> Path:
        """Worker thread for extraction."""
        return self._extract_update(is_msi)

    def _show_progress_widget(
        self, progress_widget: TaskProgressWindow, cancellable: bool = True
    ) -> None:
        """Show progress widget in panel or as standalone window."""
        progress_widget.set_cancel_enabled(cancellable)

        if self.mod_info_panel:
            self.mod_info_panel.info_panel_frame.hide()
            if hasattr(self.main_content, "disable_enable_widgets_signal"):
                self.main_content.disable_enable_widgets_signal.emit(False)
            self.mod_info_panel.panel.addWidget(progress_widget)
            progress_widget.show()
        else:
            progress_widget.show()

    def _hide_progress_widget(
        self, progress_widget: Optional[TaskProgressWindow]
    ) -> None:
        """Close and remove progress widget from panel."""
        try:
            if progress_widget:
                progress_widget.close()
                if self.mod_info_panel:
                    self.mod_info_panel.panel.removeWidget(progress_widget)
                    self.mod_info_panel.info_panel_frame.show()
        except Exception as e:
            logger.error(f"Error cleaning up progress widget: {e}")

    def _create_backup_with_progress(self) -> None:
        """Create a backup with a progress widget."""
        self._progress_widget = TaskProgressWindow(
            title="Creating Backup",
            show_message=True,
            show_percent=True,
        )
        self._progress_widget.set_message(
            self.tr("Creating backup... (this may take several minutes)")
        )

        # Show progress widget (backup cannot be cancelled)
        self._show_progress_widget(self._progress_widget, cancellable=False)

        # Run backup in a thread (not daemon - ensure proper cleanup)
        backup_thread = threading.Thread(target=self._create_backup)
        backup_thread.daemon = False
        backup_thread.start()

        # Wait for thread to complete with timeout
        start_time = time.time()
        while backup_thread.is_alive():
            QApplication.processEvents()
            time.sleep(1)
            elapsed = time.time() - start_time
            if elapsed > BACKUP_TIMEOUT_SECONDS:
                logger.warning(f"Backup thread timeout after {elapsed:.0f} seconds")
                break

        # Ensure thread is joined before cleanup
        backup_thread.join(timeout=THREAD_JOIN_TIMEOUT)
        if backup_thread.is_alive():
            logger.warning("Backup thread still alive after join timeout")

        self._hide_progress_widget(self._progress_widget)

    def _create_backup(self) -> None:
        """
        Create a compressed backup of the current RimSort installation as a ZIP file.
        Updates progress widget during backup.
        """
        app_folder = AppInfo().application_folder
        backup_folder = AppInfo().backup_folder

        # Generate backup ZIP filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"RimSort_Backup_{timestamp}.zip"
        backup_path = backup_folder / backup_filename

        logger.info("Creating backup of RimSort installation")

        def update_backup_progress(current: int, total: int) -> None:
            """Update progress widget during backup (thread-safe)."""
            if self._progress_widget and total > 0:
                percent = int((current / total) * 100)
                message = f"Backing up files: {current} / {total}"
                # Use emit for thread safety, or call directly if on main thread
                try:
                    self._progress_widget.update_progress(percent, message)
                except Exception as e:
                    logger.debug(f"Error updating backup progress: {e}")

        try:
            # Create ZIP backup of the application folder with progress updates
            create_zip_backup(
                app_folder, backup_path, progress_callback=update_backup_progress
            )

            # Verify backup was created
            if backup_path.exists():
                backup_size = backup_path.stat().st_size
                logger.info(
                    f"Backup created successfully ({backup_size / (1024 * 1024):.2f} MB)"
                )
            else:
                logger.warning("Backup file not created")

        except Exception as e:
            logger.warning(f"Failed to create backup: {e}")
            logger.error(f"Backup creation error traceback: {traceback.format_exc()}")
            # show dialog and ask user to if they want to proceed with update anyway
            answer = dialogue.show_dialogue_conditional(
                title=self.tr(ERR_BACKUP_FAILED_TITLE),
                text=self.tr(ERR_BACKUP_FAILED_TEXT),
                information=f"{e}",
                details=f"{traceback.format_exc()}",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            # Continue with update even if backup fails

    def _cleanup_old_backups(self) -> None:
        """
        Clean up old backups, keeping only the most recent ones based on max_backups setting.
        """
        backup_folder = AppInfo().backup_folder
        max_backups = self.settings_controller.settings.max_backups

        try:
            # Get all backup files
            backup_files = list(backup_folder.glob("RimSort_Backup_*.zip"))
            if len(backup_files) <= max_backups:
                logger.debug(
                    f"Backup count ({len(backup_files)}) is within limit ({max_backups})"
                )
                return

            # Sort by modification time (newest first)
            backup_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)

            # Remove old backups
            backups_to_remove = backup_files[max_backups:]
            for backup_file in backups_to_remove:
                try:
                    backup_file.unlink()
                    logger.info(f"Removed old backup: {backup_file.name}")
                except Exception as e:
                    logger.warning(
                        f"Failed to remove old backup {backup_file.name}: {e}"
                    )

            logger.info(
                f"Cleaned up {len(backups_to_remove)} old backups, keeping {max_backups} most recent"
            )

        except Exception as e:
            logger.warning(f"Failed to cleanup old backups: {e}")

    def show_update_error(self) -> None:
        dialogue.show_warning(
            title=self.tr(ERR_RETRIEVE_RELEASE_TITLE),
            text=self.tr(ERR_RETRIEVE_RELEASE_TEXT),
        )

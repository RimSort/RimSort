import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import traceback
from datetime import datetime
from functools import partial
from io import BytesIO
from pathlib import Path
from tempfile import gettempdir
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    List,
    Optional,
    TypedDict,
    Union,
    cast,
)
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

import requests
from loguru import logger
from packaging import version
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QMessageBox

import app.views.dialogue as dialogue
from app.utils.app_info import AppInfo
from app.utils.event_bus import EventBus
from app.utils.generic import check_internet_connection

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

        return self._build_platform_args(base_args, script_path, needs_elevation)

    def _build_platform_args(
        self, base_args: List[str], script_path: Path, needs_elevation: bool
    ) -> Union[str, List[str]]:
        """
        Build platform-specific arguments for launching the update script.

        Args:
            base_args: Base arguments list [script_path, temp_path, log_path, install_dir?]
            script_path: Path to the update script
            needs_elevation: Whether elevated privileges are required

        Returns:
            Arguments string or list for subprocess

        Raises:
            ValueError: If platform is unsupported
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
            quoted_args = " ".join(shlex.quote(arg) for arg in base_args)
            if needs_elevation:
                return f'x-terminal-emulator -e "sudo {quoted_args}"'
            else:
                return f'x-terminal-emulator -e bash -c "{quoted_args}; read -p \\"Press enter to close\\""'
        else:
            raise ValueError(f"Unsupported platform: {self.platform}")


class UpdateManager(QObject):
    update_progress = Signal(int, str)  # percent, message

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
        self, settings_controller: "SettingsController", main_content: Any
    ) -> None:
        super().__init__()
        self.settings_controller = settings_controller
        self.main_content = main_content
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
            app_folder = AppInfo().application_folder
            app_path_str = str(app_folder).replace("/", "\\").upper()
            protected_paths = [
                r"C:\PROGRAM FILES",
                r"C:\PROGRAM FILES (X86)",
                r"C:\WINDOWS",
            ]

            # Check if in protected path
            for protected in protected_paths:
                if protected in app_path_str:
                    logger.debug(f"Elevation forced due to protected path: {protected}")
                    self._elevation_needed = True
                    return True

            # Test write access
            try:
                test_file = app_folder / "test_write.tmp"
                test_file.write_text("test")
                test_file.unlink()
                logger.debug("Write test passed; no elevation needed")
                self._elevation_needed = False
                return False
            except (OSError, IOError, PermissionError) as write_err:
                logger.debug(f"Write test failed ({write_err}); elevation needed")
                self._elevation_needed = True
                return True
        else:
            # For non-Windows, use the original check
            self._elevation_needed = not os.access(
                AppInfo().application_folder, os.W_OK
            )
            return self._elevation_needed

    def do_check_for_update(self) -> None:
        """
        Check for RimSort updates and handle the update process.

        This method orchestrates the update process by delegating to focused sub-methods
        for better maintainability and testability.
        """
        start_time = datetime.now()
        logger.debug("Starting update check process...")

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
            dialogue.show_internet_connection_error()
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
        logger.debug(f"Current RimSort version: {current_version}")

        # Get the latest release info
        logger.info("Fetching latest release information from GitHub API...")
        latest_release_info = self._get_latest_release_info(needs_elevation)
        if not latest_release_info:
            logger.warning("Failed to retrieve latest release information")
            return None

        latest_version = latest_release_info["version"]
        latest_tag_name = latest_release_info["tag_name"]
        download_url = latest_release_info["download_url"]

        logger.debug(f"Latest RimSort version: {latest_version}")
        logger.info(f"Update available: {latest_tag_name} ({latest_version})")

        # Compare versions
        current_version_parsed = self._parse_current_version(current_version)
        if current_version_parsed >= latest_version:
            logger.info("Up to date!")
            return None

        # Prompt user for update
        if not self._prompt_user_for_update(latest_tag_name, current_version):
            return None

        return {
            "download_url": download_url,
            "tag_name": latest_tag_name,
            "latest_version": latest_version,
            "needs_elevation": needs_elevation,
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
                    return version.parse("0.0.0")
                else:
                    logger.info(f"User chose not to update version: {current_version}")
                    raise UpdateError(
                        f"User chose not to update version: {current_version}"
                    )

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

        try:
            self._perform_update(download_url, tag_name)
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

        # Prefer ZIP for all platforms except Windows installations installed in protected paths
        preferred_extension = ZIP_EXTENSION
        # Determine preferred extension based on platform and installation path
        if self._system == "Windows":
            app_folder = AppInfo().application_folder
            app_path_str = str(app_folder).replace("/", "\\").upper()
            protected_paths = [
                r"C:\PROGRAM FILES",
                r"C:\PROGRAM FILES (X86)",
                r"C:\WINDOWS",
            ]
            if any(protected in app_path_str for protected in protected_paths):
                preferred_extension = MSI_EXTENSION

        logger.debug(
            f"Looking for asset matching system={self._system}, arch={self._arch}, patterns={system_patterns + arch_patterns}, extension={preferred_extension}"
        )

        # Find best matching asset
        candidate = self._find_best_asset_match(
            assets, system_patterns, arch_patterns, preferred_extension
        )
        if candidate:
            return candidate

        logger.warning(
            f"No matching asset found for {self._system} {self._arch} with extension {preferred_extension}"
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

    def _perform_update(self, download_url: str, tag_name: str) -> None:
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

            # Download with progress animation
            EventBus().do_threaded_loading_animation.emit(
                str(AppInfo().theme_data_folder / "default-icons" / "refresh.gif"),
                partial(
                    self._download_update,
                    url=download_url,
                ),
                self.tr("Downloading RimSort {tag_name} release...").format(
                    tag_name=tag_name
                ),
            )

            if self._update_content is None:
                raise UpdateDownloadError("Download did not complete successfully")

            # Get release info to determine if MSI
            latest_release_info = self._get_latest_release_info(
                self._check_needs_elevation()
            )
            if not latest_release_info:
                raise UpdateDownloadError(
                    "Failed to retrieve release info for extraction"
                )
            is_msi = latest_release_info.get("is_msi", False)

            # Extract or save with progress animation
            EventBus().do_threaded_loading_animation.emit(
                str(AppInfo().theme_data_folder / "default-icons" / "refresh.gif"),
                partial(self._extract_update, is_msi=is_msi),
                self.tr("Extracting update files...")
                if not is_msi
                else self.tr("Preparing update installer..."),
            )

            if self._extracted_path is None:
                raise UpdateExtractionError(
                    "Extraction/preparation did not complete successfully"
                )

            update_source_path = self._extracted_path

            # Confirm installation
            answer = dialogue.show_dialogue_conditional(
                title=self.tr("Update downloaded"),
                text=self.tr("Do you want to proceed with the update?"),
                information=f"\nSuccessfully retrieved latest release.\nThe update will be installed from: {update_source_path}",
            )

            if answer != QMessageBox.StandardButton.Yes:
                return

            # Check if backup is enabled in settings
            if self.settings_controller.settings.enable_backup_before_update:
                # Create backup of current installation with progress animation
                EventBus().do_threaded_loading_animation.emit(
                    str(AppInfo().theme_data_folder / "default-icons" / "refresh.gif"),
                    partial(self._create_backup),
                    self.tr("Creating backup..."),
                )
            # Clean up old backups Aflways even when not creating new one
            self._cleanup_old_backups()

            # Prepare for launch
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

    def _get_file_size(self, url: str) -> int:
        """
        Get the file size from the URL for progress tracking.

        Args:
            url: URL to check

        Returns:
            File size in bytes, or 0 if unable to determine
        """
        try:
            head_response = requests.head(url, timeout=API_TIMEOUT)
            return int(head_response.headers.get("content-length", 0))
        except Exception as e:
            logger.debug(f"Failed to get file size: {e}")
            return 0

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
        start_time = datetime.now()

        for chunk in response.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
            if chunk:
                content.extend(chunk)
                downloaded_size += len(chunk)
                chunk_count += 1

                # Log progress for large downloads and emit signal
                if total_size > 0 and downloaded_size % (1024 * 1024) == 0:  # Every MB
                    progress = (downloaded_size / total_size) * 100
                    elapsed = (datetime.now() - start_time).total_seconds()
                    speed = downloaded_size / elapsed if elapsed > 0 else 0
                    logger.debug(
                        f"Download progress: {progress:.1f}% ({downloaded_size}/{total_size} bytes) - Speed: {speed:.2f} B/s"
                    )
                    self.update_progress.emit(
                        int(progress),
                        f"Downloading... {progress:.1f}% ({downloaded_size}/{total_size} bytes)",
                    )

        total_time = (datetime.now() - start_time).total_seconds()
        avg_speed = len(content) / total_time if total_time > 0 else 0
        logger.debug(
            f"Downloaded {len(content)} bytes in {chunk_count} chunks over {total_time:.2f}s (avg speed: {avg_speed:.2f} B/s)"
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
        logger.debug(f"Starting download from URL: {url}")
        logger.debug(
            f"Download timeout: {DOWNLOAD_TIMEOUT}s, API timeout: {API_TIMEOUT}s"
        )
        try:
            logger.debug("Entering _download_update method")
            logger.debug(f"Starting update download from {url}")

            # Get file size first for progress tracking
            total_size = self._get_file_size(url)
            logger.debug(f"Total file size: {total_size} bytes")

            logger.debug("Starting download with streaming")
            response = requests.get(url, timeout=DOWNLOAD_TIMEOUT, stream=True)
            response.raise_for_status()
            logger.debug(f"HTTP response status: {response.status_code}")

            # Download with progress tracking
            content = self._download_with_progress(response, total_size)

            # Validate downloaded content
            self._validate_download(content)

            self._update_content = content
            logger.debug("Update downloaded and validated successfully")

        except requests.RequestException as e:
            logger.debug(f"Request exception during download: {e}")
            raise UpdateDownloadError(f"Failed to download update: {e}") from e
        except UpdateError:
            raise
        except Exception as e:
            logger.debug(f"Unexpected exception during download: {e}")
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
        logger.debug(f"Using extraction temp dir: {temp_base}")
        return temp_base

    def _extract_zip(self, content: bytes, temp_base: Path) -> int:
        """
        Extract ZIP content to the temporary directory.

        Args:
            content: ZIP file content as bytes
            temp_base: Temporary directory to extract to

        Returns:
            Number of files extracted

        Raises:
            UpdateExtractionError: If ZIP is corrupted or extraction fails
        """
        logger.debug("Extracting update to temporary directory")
        with ZipFile(BytesIO(content)) as zipobj:
            # Test ZIP integrity before extracting
            logger.debug("Testing ZIP file integrity")
            corruption_info = zipobj.testzip()
            if corruption_info is not None:
                logger.debug(f"ZIP file corrupted at: {corruption_info}")
                raise UpdateExtractionError(
                    f"ZIP file is corrupted at: {corruption_info}"
                )

            logger.debug("ZIP integrity check passed, starting extraction")
            zipobj.extractall(temp_base)
            extracted_files = len(zipobj.namelist())
            logger.info(f"Extracted {extracted_files} files from ZIP to {temp_base}")
            logger.debug(f"ZIP file list (first 10): {zipobj.namelist()[:10]}")
            return extracted_files

    def _normalize_structure(self, temp_base: Path, extracted_files: int) -> None:
        """
        Normalize the extracted structure by moving contents to root if wrapped.

        Args:
            temp_base: Temporary directory containing extracted files
            extracted_files: Number of files extracted
        """
        logger.debug("Starting structure normalization")
        self._normalize_extracted_structure(temp_base, extracted_files)
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
        logger.debug("Starting update extraction/preparation")
        try:
            logger.debug("Entering _extract_update method")
            if self._update_content is None:
                logger.debug("No update content available for extraction")
                raise UpdateExtractionError(
                    "No update content available for extraction"
                )

            logger.debug(f"Update content size: {len(self._update_content)} bytes")

            if is_msi:
                # For MSI, just save the file to temp location
                temp_base = self._create_temp_dir()
                msi_path = temp_base / "RimSort_Update.msi"
                msi_path.write_bytes(self._update_content)
                logger.debug(f"MSI file saved to: {msi_path}")
                self._extracted_path = msi_path
                return msi_path
            else:
                # Create unique temp dir for ZIP extraction
                temp_base = self._create_temp_dir()

                # Extract ZIP content
                extracted_files = self._extract_zip(self._update_content, temp_base)

                # Normalize structure
                self._normalize_structure(temp_base, extracted_files)

                logger.debug("Update extracted and normalized successfully")

                self._extracted_path = temp_base
                return temp_base

        except BadZipFile as e:
            logger.debug(f"BadZipFile exception during extraction: {e}")
            raise UpdateExtractionError(
                f"Downloaded file is not a valid ZIP archive: {e}"
            ) from e
        except UpdateError:
            raise
        except Exception as e:
            logger.debug(f"Unexpected exception during extraction: {e}")
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
                        logger.debug(f"Verified macOS executable at: {executable_path}")
                        break
            if not executable_found:
                raise UpdateExtractionError(
                    "Expected RimSort.app bundle with executable not found after normalization"
                )
        else:
            # Look for executable directly
            executable_path = extract_path / expected_executable
            if executable_path.exists():
                executable_found = True
                logger.debug(f"Verified executable at: {executable_path}")
            else:
                # Fallback: check if executable is in any subdirectory
                for child in children:
                    if child.is_dir():
                        candidate_path = child / expected_executable
                        if candidate_path.exists():
                            executable_found = True
                            logger.debug(f"Verified executable at: {candidate_path}")
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

            logger.debug(f"Detected wrapped structure in '{top_dir.name}'; normalizing")
            logger.debug(
                f"Wrapper '{top_dir.name}' children: {[c.name for c in top_dir.iterdir()]}"
            )

            # Move all contents from top_dir to extract_path
            moved_items = self._move_directory_contents(top_dir, extract_path)

            if moved_items == 0:
                logger.warning("No items were successfully moved during normalization")
                break

            # Remove empty top_dir if possible
            try:
                top_dir.rmdir()
                logger.debug("Structure normalized: contents moved to root")
            except OSError as e:
                logger.warning(f"Failed to remove wrapper dir {top_dir}: {e}")

            # Refresh children list after unwrapping
            children = list(extract_path.iterdir())
            logger.debug(f"Post-normalization children: {[c.name for c in children]}")

        # Validate expected structure based on platform
        self._validate_executable_presence(extract_path, children)

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
            self._launch_msi_installer(update_source_path, needs_elevation)
            return

        try:
            script_path, args_repr, start_new_session, install_dir = (
                self._get_script_info(update_source_path, log_path, needs_elevation)
            )

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
            )

        # Launch in terminal emulator
        p = subprocess.Popen(
            args_repr,
            shell=True,
            cwd=str(AppInfo().application_folder),
        )
        return p

    def _launch_msi_installer(self, msi_path: Path, needs_elevation: bool) -> None:
        """
        Launch the MSI installer on Windows.

        Args:
            msi_path: Path to the MSI file
            needs_elevation: Whether to run with elevated privileges

        Raises:
            UpdateScriptLaunchError: If MSI launch fails
        """
        if needs_elevation:
            # Use PowerShell to run msiexec with elevated privileges
            cmd = (
                f'powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Start-Process msiexec.exe '
                f"-ArgumentList @('/i', '{str(msi_path)}') -Verb RunAs -WindowStyle Normal\""
            )
            logger.debug(f"Launching MSI with elevation: {cmd}")
            try:
                subprocess.run(cmd, shell=True, check=True)
                logger.info("MSI installer launched successfully with elevation")
            except subprocess.CalledProcessError as e:
                raise UpdateScriptLaunchError(
                    f"Failed to launch MSI installer: {e}"
                ) from e
        else:
            # Launch MSI normally
            cmd = f'msiexec /i "{msi_path}" /quiet /norestart'
            logger.debug(f"Launching MSI: {cmd}")
            try:
                subprocess.run(cmd, shell=True, check=True)
                logger.info("MSI installer launched successfully")
            except subprocess.CalledProcessError as e:
                raise UpdateScriptLaunchError(
                    f"Failed to launch MSI installer: {e}"
                ) from e

        # Exit the application after launching MSI
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
            script_path, update_source_path, log_path, needs_elevation, install_dir
        )
        start_new_session = config.start_new_session

        return script_path, args_repr, start_new_session, install_dir

    def _create_backup(self) -> None:
        """
        Create a compressed backup of the current RimSort installation as a ZIP file.
        """
        app_folder = AppInfo().application_folder
        backup_folder = AppInfo().backup_folder

        # Generate backup ZIP filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"RimSort_Backup_{timestamp}.zip"
        backup_path = backup_folder / backup_filename

        logger.info(
            f"Creating compressed backup of current installation to: {backup_path}"
        )

        try:
            # Create ZIP backup of the application folder
            with ZipFile(backup_path, "w", ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(app_folder):
                    for file in files:
                        file_path = Path(root) / file
                        arcname = file_path.relative_to(app_folder)
                        zipf.write(file_path, arcname)
            logger.info("Compressed backup created successfully")
        except Exception as e:
            logger.warning(f"Failed to create backup: {e}")
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

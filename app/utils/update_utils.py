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
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Union, cast

if TYPE_CHECKING:
    from app.utils.metadata import SettingsController

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


class UpdateError(Exception):
    """Base exception for update-related errors."""

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


class ScriptConfig:
    """Configuration for platform-specific update scripts."""

    def __init__(
        self,
        script_path_func: Callable[[], Path],
        start_new_session: Optional[bool],
        elevated_args_func: Callable[..., str],
        normal_args_func: Callable[..., Union[str, List[str]]],
    ) -> None:
        self.script_path_func = script_path_func
        self.start_new_session = start_new_session
        self.elevated_args_func = elevated_args_func
        self.normal_args_func = normal_args_func

    def get_script_path(self) -> Path:
        """Get the script path for this platform."""
        return self.script_path_func()

    def get_args(
        self,
        script_path: Path,
        temp_path: Optional[Path] = None,
        log_path: Optional[Path] = None,
        needs_elevation: bool = False,
        install_dir: Optional[Path] = None,
    ) -> Union[str, List[str]]:
        """Get the appropriate arguments string based on elevation needs."""
        if needs_elevation:
            if (
                temp_path is not None
                and log_path is not None
                and install_dir is not None
                and "temp_path" in self.elevated_args_func.__code__.co_varnames
                and "log_path" in self.elevated_args_func.__code__.co_varnames
                and "install_dir" in self.elevated_args_func.__code__.co_varnames
            ):
                return self.elevated_args_func(
                    script_path, temp_path, log_path, install_dir
                )
            elif (
                temp_path is not None
                and log_path is not None
                and "temp_path" in self.elevated_args_func.__code__.co_varnames
                and "log_path" in self.elevated_args_func.__code__.co_varnames
            ):
                return self.elevated_args_func(script_path, temp_path, log_path)
            elif (
                temp_path is not None
                and "temp_path" in self.elevated_args_func.__code__.co_varnames
            ):
                return self.elevated_args_func(script_path, temp_path)
            return self.elevated_args_func(script_path)
        else:
            if (
                temp_path is not None
                and log_path is not None
                and install_dir is not None
                and "temp_path" in self.normal_args_func.__code__.co_varnames
                and "log_path" in self.normal_args_func.__code__.co_varnames
                and "install_dir" in self.normal_args_func.__code__.co_varnames
            ):
                return self.normal_args_func(
                    script_path, temp_path, log_path, install_dir
                )
            elif (
                temp_path is not None
                and log_path is not None
                and "temp_path" in self.normal_args_func.__code__.co_varnames
                and "log_path" in self.normal_args_func.__code__.co_varnames
            ):
                return self.normal_args_func(script_path, temp_path, log_path)
            elif (
                temp_path is not None
                and "temp_path" in self.normal_args_func.__code__.co_varnames
            ):
                return self.normal_args_func(script_path, temp_path)
            return self.normal_args_func(script_path)


class UpdateManager(QObject):
    update_progress = Signal(int, str)  # percent, message

    # Class-level constants
    GITHUB_API_URL = "https://api.github.com/repos/LionelColaso/RimSort/releases/latest"
    API_TIMEOUT = 15
    DOWNLOAD_TIMEOUT = 30
    ZIP_EXTENSION = ".zip"
    UPDATER_LOG_FILENAME = "updater.log"
    TEMP_DIR_DARWIN = "RimSort.app"
    TEMP_DIR_DEFAULT = "RimSort"

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
            script_path_func=lambda: Path(sys.argv[0]).parent.parent.parent
            / "Contents"
            / "MacOS"
            / "update.sh",
            start_new_session=False,
            elevated_args_func=lambda script_path,
            temp_path,
            log_path,
            install_dir=None: f'osascript -e \'tell app "Terminal" to do script "sudo /bin/bash {shlex.quote(str(script_path))} {shlex.quote(str(temp_path))} {shlex.quote(str(log_path))}; read -p \\\\\\"Press enter to close\\\\\\"\'"',
            normal_args_func=lambda script_path,
            temp_path,
            log_path,
            install_dir=None: f'osascript -e \'tell app "Terminal" to do script "/bin/bash {shlex.quote(str(script_path))} {shlex.quote(str(temp_path))} {shlex.quote(str(log_path))}; read -p \\\\\\"Press enter to close\\\\\\"\'"',
        ),
        "Windows": ScriptConfig(
            script_path_func=lambda: AppInfo().application_folder / "update.bat",
            start_new_session=None,  # Not used on Windows
            elevated_args_func=lambda script_path,
            temp_path,
            log_path,
            install_dir=None: "powershell.exe -NoProfile -ExecutionPolicy Bypass -Command \"Start-Process cmd -ArgumentList @('/k', '"
            + f'cd /d \\"{script_path.parent}\\" && \\"{script_path}\\" \\"{temp_path}\\" \\"{log_path}\\"'
            + "') -Verb RunAs -WindowStyle Normal\"",
            normal_args_func=lambda script_path,
            temp_path,
            log_path,
            install_dir=None: [
                "cmd",
                "/k",
                str(script_path),
                str(temp_path),
                str(log_path),
            ],
        ),
        "Linux": ScriptConfig(
            script_path_func=lambda: AppInfo().application_folder / "update.sh",
            start_new_session=True,
            elevated_args_func=lambda script_path,
            temp_path,
            log_path,
            install_dir: f'x-terminal-emulator -e "sudo {shlex.quote(str(script_path))} {shlex.quote(str(temp_path))} {shlex.quote(str(log_path))} {shlex.quote(str(install_dir))}"',
            normal_args_func=lambda script_path,
            temp_path,
            log_path,
            install_dir: f'x-terminal-emulator -e bash -c "{shlex.quote(str(script_path))} {shlex.quote(str(temp_path))} {shlex.quote(str(log_path))} {shlex.quote(str(install_dir))}; read -p \\"Press enter to close\\""',
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
        # Cache platform info to avoid repeated calls
        self._system = platform.system()
        self._arch = platform.architecture()[0]
        # Cache platform patterns for performance
        self._cached_patterns = (
            self._platform_patterns[self._system]
            if self._system in self._platform_patterns
            else None
        )

    def do_check_for_update(self) -> None:
        """
        Check for RimSort updates and handle the update process.

        This method:
        1. Validates prerequisites (compiled binary, internet connection)
        2. Fetches latest release information from GitHub
        3. Compares versions and prompts user if update is available
        4. Downloads and extracts the update if user confirms
        5. Launches the appropriate update script for the platform
        """
        if os.getenv("RIMSORT_DISABLE_UPDATER"):
            logger.debug(
                "RIMSORT_DISABLE_UPDATER is set, skipping update check silently."
            )
            return

        logger.debug("Checking for RimSort update...")

        # NOT NUITKA
        if "__compiled__" not in globals():
            logger.debug(
                "You are running from Python interpreter. Skipping update check..."
            )
            dialogue.show_warning(
                title=self.tr("Update skipped"),
                text=self.tr("You are running from Python interpreter."),
                information=self.tr("Skipping update check..."),
            )
            return

        # Check internet connection before attempting task
        if not check_internet_connection():
            dialogue.show_internet_connection_error()
            return

        current_version = AppInfo().app_version
        logger.debug(f"Current RimSort version: {current_version}")

        # Get the latest release info and download URL
        logger.info("Fetching latest release information from GitHub API...")
        latest_release_info = self._get_latest_release_info()
        if not latest_release_info:
            logger.warning("Failed to retrieve latest release information")
            return

        latest_version = latest_release_info["version"]
        latest_tag_name = latest_release_info["tag_name"]
        download_url = latest_release_info["download_url"]

        logger.debug(f"Latest RimSort version: {latest_version}")
        logger.info(f"Update available: {latest_tag_name} ({latest_version})")

        # Compare versions
        try:
            current_version_parsed = version.parse(current_version)
        except Exception:
            logger.warning(f"Failed to parse current version: {current_version}")
            current_version_parsed = version.parse("0.0.0")

        if current_version_parsed >= latest_version:
            # No update needed then return and log the check no need to notify user
            logger.info("Up to date!")
            return

        # Show update prompt
        answer = dialogue.show_dialogue_conditional(
            title=self.tr("RimSort update found"),
            text=self.tr(
                "An update to RimSort has been released: {latest_tag_name}"
            ).format(latest_tag_name=latest_tag_name),
            information=self.tr(
                "You are running RimSort {current_version}\nDo you want to update now?"
            ).format(current_version=current_version),
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        # Perform update
        self._perform_update(download_url, latest_tag_name)

    def _get_latest_release_info(self) -> dict[str, Any] | None:
        """
        Get the latest release information from GitHub API.

        Returns:
            Dictionary containing version, tag_name, and download_url, or None if failed
        """
        try:
            # Use releases API for better asset information
            response = requests.get(self.GITHUB_API_URL, timeout=self.API_TIMEOUT)
            response.raise_for_status()
            release_data = response.json()

            tag_name = release_data.get("tag_name", "")
            # Normalize tag name by removing prefix 'v' if present
            normalized_tag = re.sub(r"^v", "", str(tag_name), flags=re.IGNORECASE)

            # Parse version
            try:
                latest_version = version.parse(normalized_tag)
            except Exception as e:
                logger.warning(f"Failed to parse version from tag {tag_name}: {e}")
                self.show_update_error()
                return None

            # Get platform-specific download URL
            download_url = self._get_platform_download_url(
                release_data.get("assets", [])
            )
            if not download_url:
                system_info = f"{platform.system()} {platform.architecture()[0]} {platform.processor()}"
                dialogue.show_warning(
                    title=self.tr("Unable to complete update"),
                    text=self.tr(
                        "Failed to find valid RimSort release for {system_info}"
                    ).format(system_info=system_info),
                )
                return None

            return {
                "version": latest_version,
                "tag_name": tag_name,
                "download_url": download_url,
            }

        except requests.RequestException as e:
            logger.warning(f"Failed to fetch release information: {e}")
            dialogue.show_warning(
                title=self.tr("Unable to retrieve release information"),
                text=self.tr("Failed to connect to GitHub API: {error}").format(
                    error=str(e)
                ),
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
        asset_name_lower = asset_name.lower()

        # Early return if extension doesn't match
        if not asset_name_lower.endswith(extension):
            return False

        # Check system patterns
        if not any(pattern.lower() in asset_name_lower for pattern in patterns):
            return False

        # If architecture is required, check arch patterns
        if require_arch and arch_patterns:
            return any(pattern.lower() in asset_name_lower for pattern in arch_patterns)

        return True

    def _get_platform_download_url(self, assets: List[Dict[str, Any]]) -> str | None:
        """
        Get the appropriate download URL for the current platform.

        Args:
            assets: List of asset dictionaries from GitHub API

        Returns:
            Download URL string or None if not found
        """
        if self._cached_patterns is None:
            logger.warning(f"Unsupported system: {self._system}")
            return None

        system_patterns = cast(List[str], self._cached_patterns["patterns"])
        arch_patterns_dict = cast(
            Dict[str, List[str]], self._cached_patterns["arch_patterns"]
        )
        arch_patterns = arch_patterns_dict.get(self._arch, [])

        logger.debug(
            f"Looking for asset matching system={self._system}, arch={self._arch}, patterns={system_patterns + arch_patterns}"
        )

        # Find best matching asset
        candidate = self._find_best_asset_match(assets, system_patterns, arch_patterns)
        if candidate:
            return candidate["url"]

        logger.warning(f"No matching asset found for {self._system} {self._arch}")
        return None

    def _find_best_asset_match(
        self,
        assets: List[Dict[str, Any]],
        system_patterns: List[str],
        arch_patterns: List[str],
    ) -> Dict[str, str] | None:
        """
        Find the best matching asset from the list.

        Args:
            assets: List of asset dictionaries
            system_patterns: System name patterns to match
            arch_patterns: Architecture patterns to match

        Returns:
            Dictionary with 'url' and 'name' keys, or None if no match
        """
        extension = self.ZIP_EXTENSION
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
                    extension,
                    require_arch=True,
                    arch_patterns=arch_patterns,
                )
            ):
                logger.debug(
                    f"Found arch-specific matching asset: {asset_name} -> {download_url}"
                )
                return {"url": str(download_url), "name": asset_name}
            elif download_url and self._asset_matches(
                asset, system_patterns, extension, require_arch=False
            ):
                logger.debug(
                    f"Found system-only matching asset: {asset_name} -> {download_url}"
                )
                if candidate is None:  # Only set if no arch-specific found
                    candidate = {"url": str(download_url), "name": asset_name}

        if candidate:
            # Strict verification: ensure asset name contains system pattern
            asset_name_lower = candidate["name"].lower()
            if not any(
                pattern.lower() in asset_name_lower for pattern in system_patterns
            ):
                logger.warning(
                    f"Candidate asset '{candidate['name']}' does not contain system patterns {system_patterns}; rejecting"
                )
                return None
            return candidate

        return None

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

            # Extract with progress animation
            EventBus().do_threaded_loading_animation.emit(
                str(AppInfo().theme_data_folder / "default-icons" / "refresh.gif"),
                partial(self._extract_update),
                self.tr("Extracting update files..."),
            )

            if self._extracted_path is None:
                raise UpdateExtractionError("Extraction did not complete successfully")

            update_source_path = self._extracted_path

            # Confirm installation
            answer = dialogue.show_dialogue_conditional(
                title=self.tr("Update downloaded"),
                text=self.tr("Do you want to proceed with the update?"),
                information=f"\nSuccessfully retrieved latest release.\nThe update will be installed from: {update_source_path}",
            )

            if answer != QMessageBox.StandardButton.Yes:
                return

            # Ask user if they want to create a backup
            backup_answer = dialogue.show_dialogue_conditional(
                title=self.tr("Create Backup?"),
                text=self.tr("Would you like to create a backup before updating?"),
                information=self.tr(
                    "Creating a backup is recommended to preserve your current installation."
                ),
            )

            if backup_answer == QMessageBox.StandardButton.Yes:
                # Create backup of current installation with progress animation
                EventBus().do_threaded_loading_animation.emit(
                    str(AppInfo().theme_data_folder / "default-icons" / "refresh.gif"),
                    partial(self._create_backup),
                    self.tr("Creating backup..."),
                )

            # Prepare for launch
            log_path = self._prepare_update_log(self._system)
            needs_elevation = False
            if self._system == "Windows":
                app_folder = AppInfo().application_folder
                app_path_str = (
                    str(app_folder).replace("/", "\\").upper()
                )  # Normalize slashes
                protected_paths = [
                    r"C:\PROGRAM FILES",
                    r"C:\PROGRAM FILES (X86)",
                    r"C:\WINDOWS",
                ]
                for protected in protected_paths:
                    if protected in app_path_str:
                        needs_elevation = True
                        logger.debug(
                            f"Elevation forced due to protected path match: {protected} in {app_path_str}"
                        )
                        break
                else:
                    logger.debug(
                        f"No protected path match for {app_path_str}; checking write access"
                    )
                    # Fallback write test only if not in protected path
                    try:
                        test_file = app_folder / "test_write.tmp"
                        test_file.write_text("test")
                        test_file.unlink()
                        logger.debug("Write test passed; no elevation needed")
                    except (OSError, IOError, PermissionError) as write_err:
                        needs_elevation = True
                        logger.debug(
                            f"Write test failed ({write_err}); elevation needed"
                        )
            else:
                # For non-Windows, use the original check
                needs_elevation = not os.access(AppInfo().application_folder, os.W_OK)

            # Launch update script
            self._launch_update_script(update_source_path, log_path, needs_elevation)

        except UpdateDownloadError as e:
            logger.error(f"Update download failed: {e}")
            dialogue.show_warning(
                title=self.tr("Download failed"),
                text=self.tr("Failed to download the update."),
                information=f"Error: {str(e)}\nURL: {download_url}",
            )
        except UpdateExtractionError as e:
            logger.error(f"Update extraction failed: {e}")
            dialogue.show_warning(
                title=self.tr("Extraction failed"),
                text=self.tr("Failed to extract the downloaded update."),
                information=f"Error: {str(e)}",
            )
        except UpdateScriptLaunchError as e:
            logger.error(f"Update script launch failed: {e}")
            dialogue.show_warning(
                title=self.tr("Launch failed"),
                text=self.tr("Failed to launch the update script."),
                information=f"Error: {str(e)}",
            )
        except Exception as e:
            logger.error(f"Unexpected update process failure: {e}")
            dialogue.show_warning(
                title=self.tr("Update failed"),
                text=self.tr("An unexpected error occurred during the update process."),
                information=f"Error: {str(e)}\nURL: {download_url}",
                details=traceback.format_exc(),
            )

    def _download_update(self, url: str) -> None:
        """
        Download the update to memory using requests with progress tracking.

        Args:
            url: URL to download from

        Raises:
            UpdateDownloadError: If download fails
        """
        try:
            logger.debug(f"Downloading update from {url}")

            # Get file size first for progress tracking
            head_response = requests.head(url, timeout=self.API_TIMEOUT)
            total_size = int(head_response.headers.get("content-length", 0))

            response = requests.get(url, timeout=self.DOWNLOAD_TIMEOUT, stream=True)
            response.raise_for_status()

            # Download with chunked reading for memory efficiency
            content = bytearray()
            downloaded_size = 0

            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    content.extend(chunk)
                    downloaded_size += len(chunk)

                    # Log progress for large downloads and emit signal
                    if (
                        total_size > 0 and downloaded_size % (1024 * 1024) == 0
                    ):  # Every MB
                        progress = (downloaded_size / total_size) * 100
                        logger.debug(
                            f"Download progress: {progress:.1f}% ({downloaded_size}/{total_size} bytes)"
                        )
                        self.update_progress.emit(
                            int(progress),
                            f"Downloading... {progress:.1f}% ({downloaded_size}/{total_size} bytes)",
                        )

            self._update_content = bytes(content)
            logger.debug(f"Downloaded {len(self._update_content)} bytes")

            # Basic validation: check if content is not empty and reasonable size
            assert self._update_content is not None
            if len(self._update_content) == 0:
                raise UpdateDownloadError("Downloaded file is empty")
            if (
                len(self._update_content) < 1024
            ):  # Minimum reasonable size for an app update
                raise UpdateDownloadError(
                    f"Downloaded file too small ({len(self._update_content)} bytes)"
                )

            logger.debug("Update downloaded successfully")

        except requests.RequestException as e:
            raise UpdateDownloadError(f"Failed to download update: {e}") from e
        except UpdateError:
            raise
        except Exception as e:
            raise UpdateDownloadError(f"Failed to download update: {e}") from e

    def _extract_update(self) -> Path:
        """
        Extract the downloaded update to a dedicated temporary directory and normalize structure.

        Raises:
            UpdateExtractionError: If extraction or normalization fails
        """
        try:
            if self._update_content is None:
                raise UpdateExtractionError(
                    "No update content available for extraction"
                )

            # Create unique temp dir for this extraction
            temp_base = (
                Path(gettempdir())
                / f"RimSort_update_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            )
            temp_base.mkdir(exist_ok=True)
            logger.debug(f"Using extraction temp dir: {temp_base}")

            logger.debug("Extracting update to temporary directory")
            with ZipFile(BytesIO(self._update_content)) as zipobj:
                # Test ZIP integrity before extracting
                corruption_info = zipobj.testzip()
                if corruption_info is not None:
                    raise UpdateExtractionError(
                        f"ZIP file is corrupted at: {corruption_info}"
                    )

                zipobj.extractall(temp_base)
                extracted_files = len(zipobj.namelist())
                logger.info(
                    f"Extracted {extracted_files} files from ZIP to {temp_base}"
                )

            # Normalize structure: move contents to expected root if wrapped in a folder
            self._normalize_extracted_structure(temp_base, extracted_files)

            logger.debug(f"Normalized update ready at: {temp_base}")

            logger.debug("Update extracted and normalized successfully")

            self._extracted_path = temp_base
            return temp_base

        except BadZipFile as e:
            raise UpdateExtractionError(
                f"Downloaded file is not a valid ZIP archive: {e}"
            ) from e
        except UpdateError:
            raise
        except Exception as e:
            raise UpdateExtractionError(f"Failed to extract update: {e}") from e

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
            top_dir_name = top_dir.name.lower()

            # Only unwrap if it looks like a wrapper directory (not the actual app structure)
            should_unwrap = (
                # Common wrapper patterns
                any(
                    keyword in top_dir_name
                    for keyword in ["app", "application", "release"]
                )
                or
                # Version-like directory names
                re.match(r"v?\d+[\.\-_]\d+", top_dir_name)
                or
                # For Darwin, unwrap unless it's the expected .app bundle
                (self._system == "Darwin" and top_dir_name != "rimsort.app")
                or
                # For Windows, always unwrap single directories
                (self._system == "Windows")
                or
                # For Linux, unwrap unless it's the expected app directory
                (
                    self._system == "Linux"
                    and top_dir_name.lower() not in ["rimsort", "rimsort.app"]
                )
            )

            if not should_unwrap:
                logger.debug(
                    f"No unwrapping needed for '{top_dir.name}'; using existing structure"
                )
                break

            logger.debug(f"Detected wrapped structure in '{top_dir.name}'; normalizing")
            logger.debug(
                f"Wrapper '{top_dir.name}' children: {[c.name for c in top_dir.iterdir()]}"
            )

            # Move all contents from top_dir to extract_path with robust error handling
            moved_items = 0
            for item in top_dir.iterdir():
                if not item.exists():
                    logger.warning(f"Item {item} does not exist, skipping")
                    continue
                dest = extract_path / item.name
                try:
                    if dest.exists():
                        if dest.is_dir():
                            shutil.rmtree(dest)
                        else:
                            dest.unlink()
                    shutil.move(str(item), str(extract_path))
                    moved_items += 1
                except (OSError, IOError, FileNotFoundError) as e:
                    logger.warning(
                        f"Failed to move {item} to {extract_path}: {e}. Skipping item."
                    )
                    # No fallback; skip to avoid further errors from invalid items
                    continue

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

    def _launch_update_script(
        self, update_source_path: Path, log_path: Path, needs_elevation: bool
    ) -> None:
        """
        Launch the appropriate update script for the current platform.
        """
        # Stop watchdog before update
        logger.info("Stopping watchdog Observer thread before update...")
        self.main_content.stop_watchdog_signal.emit()

        try:
            script_path, args_repr, start_new_session, install_dir = (
                self._get_script_info(update_source_path, log_path, needs_elevation)
            )
            p = self._launch_script_process(
                script_path,
                args_repr,
                start_new_session,
                log_path,
                needs_elevation,
                install_dir,
                update_source_path,
            )

            logger.debug(f"External updater script launched with PID: {p.pid}")
            logger.debug(f"Arguments used: {args_repr}")

            # Exit the application to allow update
            sys.exit(0)

        except Exception as e:
            raise UpdateScriptLaunchError(f"Failed to launch update script: {e}") from e

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
        log_path = log_dir / self.UPDATER_LOG_FILENAME

        # Small prologue in the updater log to aid debugging
        try:
            with open(log_path, "a", encoding="utf-8", errors="ignore") as lf:
                lf.write(
                    f"\n===== RimSort updater launched: {datetime.now().isoformat()} ({system}) =====\n"
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

    def _launch_script_process(
        self,
        script_path: Path,
        args_repr: Union[str, List[str]],
        start_new_session: Optional[bool],
        log_path: Path,
        needs_elevation: bool,
        install_dir: Path,
        update_source_path: Path,
    ) -> subprocess.Popen[bytes]:
        """
        Launch the update script process.

        Args:
            script_path: Path to the script
            args_repr: String representation of arguments
            start_new_session: Whether to start in new session
            log_path: Path to the log file
            needs_elevation: Whether to run with elevated privileges

        Returns:
            The subprocess.Popen object
        """
        # Ensure script is executable on POSIX systems
        if (
            self._system != "Windows"
            and script_path.exists()
            and not os.access(script_path, os.X_OK)
        ):
            try:
                os.chmod(script_path, 0o755)
                logger.debug(f"Made script executable: {script_path}")
            except OSError as e:
                logger.warning(f"Could not make script executable: {e}")

        # For POSIX systems requiring elevation, copy script to temp location to avoid permission issues
        if self._system != "Windows" and needs_elevation:
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

        if needs_elevation:
            if self._system == "Windows":
                # For Windows, args_repr includes runas, no redirection to show prompts
                p = subprocess.Popen(
                    args_repr,
                    shell=True,
                    cwd=str(AppInfo().application_folder),
                )
            else:
                # For POSIX, use the full terminal command to show prompts and pass args
                p = subprocess.Popen(
                    args_repr,
                    shell=True,
                    cwd=str(AppInfo().application_folder),
                )
        else:
            if self._system == "Windows":
                creationflags_value = (
                    subprocess.CREATE_NEW_PROCESS_GROUP
                    if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP")
                    else 0
                )
                p = subprocess.Popen(
                    args_repr,
                    creationflags=creationflags_value,
                    shell=True,
                    cwd=str(AppInfo().application_folder),
                )
            else:
                # For POSIX, use the full terminal command to show prompts and pass args
                p = subprocess.Popen(
                    args_repr,
                    shell=True,
                    cwd=str(AppInfo().application_folder),
                )

        return p

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

    def show_update_error(self) -> None:
        dialogue.show_warning(
            title=self.tr("Unable to retrieve latest release information"),
            text=self.tr(
                "Please check your internet connection and try again, You can also check 'https://github.com/RimSort/RimSort/releases' directly."
            ),
        )

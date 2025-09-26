import os
import platform
import re
import shlex
import subprocess
import sys
import traceback
from datetime import datetime
from functools import partial
from io import BytesIO
from pathlib import Path
from tempfile import gettempdir
from typing import TYPE_CHECKING, Any, Dict, List, cast

if TYPE_CHECKING:
    from app.utils.metadata import SettingsController
from zipfile import BadZipFile, ZipFile

import requests
from loguru import logger
from packaging import version
from PySide6.QtCore import QObject
from PySide6.QtWidgets import QMessageBox

import app.views.dialogue as dialogue
from app.utils.app_info import AppInfo
from app.utils.event_bus import EventBus
from app.utils.generic import check_internet_connection


class UpdateManager(QObject):
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

    def __init__(
        self, settings_controller: "SettingsController", main_content: Any
    ) -> None:
        super().__init__()
        self.settings_controller = settings_controller
        self.main_content = main_content

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
        latest_release_info = self._get_latest_release_info()
        if not latest_release_info:
            return

        latest_version = latest_release_info["version"]
        latest_tag_name = latest_release_info["tag_name"]
        download_url = latest_release_info["download_url"]

        logger.debug(f"Latest RimSort version: {latest_version}")

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
            releases_url = (
                "https://api.github.com/repos/RimSort/RimSort/releases/latest"
            )
            response = requests.get(releases_url, timeout=15)
            response.raise_for_status()
            release_data = response.json()

            tag_name = release_data.get("tag_name", "")
            # Normalize tag name by removing prefix 'v' if present
            normalized_tag = re.sub(r"^v", "", tag_name, flags=re.IGNORECASE)

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
        asset: dict[str, Any],
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

        if not asset_name_lower.endswith(extension):
            return False

        system_match = any(pattern.lower() in asset_name_lower for pattern in patterns)

        if not system_match:
            return False

        if require_arch and arch_patterns:
            arch_match = any(
                pattern.lower() in asset_name_lower for pattern in arch_patterns
            )
            return arch_match

        return True

    def _get_platform_download_url(self, assets: list[dict[str, Any]]) -> str | None:
        """
        Get the appropriate download URL for the current platform.

        Args:
            assets: List of asset dictionaries from GitHub API

        Returns:
            Download URL string or None if not found
        """
        system = platform.system()
        arch = platform.architecture()[0]

        if system not in self._platform_patterns:
            logger.warning(f"Unsupported system: {system}")
            return None

        platform_info = self._platform_patterns[system]
        system_patterns = cast(List[str], platform_info["patterns"])
        arch_patterns_dict = cast(Dict[str, List[str]], platform_info["arch_patterns"])
        arch_patterns = arch_patterns_dict.get(arch, [])
        extension = ".zip"

        logger.debug(
            f"Looking for asset matching system={system}, arch={arch}, patterns={system_patterns + arch_patterns}"
        )

        # Single loop: prefer arch match, fallback to system match
        for asset in assets:
            if arch_patterns:
                if self._asset_matches(
                    asset,
                    system_patterns,
                    extension,
                    require_arch=True,
                    arch_patterns=arch_patterns,
                ):
                    download_url = asset.get("browser_download_url")
                    logger.debug(
                        f"Found matching asset: {asset.get('name')} -> {download_url}"
                    )
                    return download_url
            else:
                # No arch patterns, direct system match
                if self._asset_matches(asset, system_patterns, extension):
                    download_url = asset.get("browser_download_url")
                    logger.debug(
                        f"Found matching asset: {asset.get('name')} -> {download_url}"
                    )
                    return download_url

            # Fallback to system-only match if arch failed or not required
            if self._asset_matches(asset, system_patterns, extension):
                download_url = asset.get("browser_download_url")
                logger.debug(
                    f"Found fallback asset: {asset.get('name')} -> {download_url}"
                )
                return download_url

        logger.warning(f"No matching asset found for {system} {arch}")
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
                    self._download_and_extract_update,
                    url=download_url,
                ),
                self.tr("Downloading RimSort {tag_name} release...").format(
                    tag_name=tag_name
                ),
            )

            # Get temp directory path
            system = platform.system()
            temp_dir = "RimSort.app" if system == "Darwin" else "RimSort"
            temp_path = os.path.join(gettempdir(), temp_dir)

            # Confirm installation
            answer = dialogue.show_dialogue_conditional(
                title=self.tr("Update downloaded"),
                text=self.tr("Do you want to proceed with the update?"),
                information=f"\nSuccessfully retrieved latest release.\nThe update will be installed from: {temp_path}",
            )

            if answer != QMessageBox.StandardButton.Yes:
                return

            # Launch update script
            self._launch_update_script()

        except Exception as e:
            logger.error(f"Update process failed: {e}")
            dialogue.show_warning(
                title=self.tr("Failed to download update"),
                text=self.tr("Failed to download latest RimSort release!"),
                information=f"Error: {str(e)}\nURL: {download_url}",
                details=traceback.format_exc(),
            )

    def _download_and_extract_update(self, url: str) -> None:
        """
        Download and extract the update to temporary directory.

        Args:
            url: URL to download from
        """
        try:
            # Download with better error handling and progress
            response = requests.get(url, timeout=30, stream=True)
            response.raise_for_status()

            # Extract to temp directory
            with ZipFile(BytesIO(response.content)) as zipobj:
                zipobj.extractall(gettempdir())

        except requests.RequestException as e:
            raise Exception(f"Failed to download update: {e}")
        except BadZipFile as e:
            raise Exception(f"Downloaded file is not a valid ZIP archive: {e}")
        except Exception as e:
            raise Exception(f"Failed to extract update: {e}")

    def _launch_update_script(self) -> None:
        """
        Launch the appropriate update script for the current platform.
        """
        system = platform.system()

        # Stop watchdog before update
        logger.info("Stopping watchdog Observer thread before update...")
        self.main_content.stop_watchdog_signal.emit()

        try:
            # Ensure updater logs are captured to a persistent location
            log_dir = AppInfo().user_log_folder
            log_dir.mkdir(parents=True, exist_ok=True)
            log_path = log_dir / "updater.log"

            # Small prologue in the updater log to aid debugging
            try:
                with open(log_path, "a", encoding="utf-8", errors="ignore") as lf:
                    lf.write(
                        f"\n===== RimSort updater launched: {datetime.now().isoformat()} ({system}) =====\n"
                    )
            except Exception:
                # Non-fatal; continue without preface
                pass

            args_repr: str = ""

            if system == "Darwin":  # MacOS
                current_dir = os.path.dirname(
                    os.path.dirname(os.path.dirname(os.path.abspath(sys.argv[0])))
                )
                script_path = Path(current_dir) / "Contents" / "MacOS" / "update.sh"
                popen_args = ["/bin/bash", str(script_path)]
                args_repr = " ".join(shlex.quote(a) for a in popen_args)
                with open(log_path, "ab", buffering=0) as lf:
                    p = subprocess.Popen(
                        popen_args,
                        stdout=lf,
                        stderr=subprocess.STDOUT,
                    )

            elif system == "Windows":
                script_path = AppInfo().application_folder / "update.bat"
                # Redirect batch output into the updater log for diagnostics
                # Using a single command string to support shell redirection
                cmd_str = f'cmd /c ""{script_path}"" >> "{log_path}" 2>&1'
                creationflags_value = (
                    subprocess.CREATE_NEW_PROCESS_GROUP
                    if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP")
                    else 0
                )
                p = subprocess.Popen(
                    cmd_str,
                    creationflags=creationflags_value,
                    shell=True,
                    cwd=str(AppInfo().application_folder),
                )
                args_repr = cmd_str

            else:  # Linux and other POSIX systems
                script_path = AppInfo().application_folder / "update.sh"
                popen_args = ["/bin/bash", str(script_path)]
                args_repr = " ".join(shlex.quote(a) for a in popen_args)
                with open(log_path, "ab", buffering=0) as lf:
                    p = subprocess.Popen(
                        popen_args,
                        start_new_session=True,
                        stdout=lf,
                        stderr=subprocess.STDOUT,
                    )

            logger.debug(f"External updater script launched with PID: {p.pid}")
            logger.debug(f"Arguments used: {args_repr}")

            # Exit the application to allow update
            sys.exit(0)

        except Exception as e:
            logger.error(f"Failed to launch update script: {e}")
            dialogue.show_warning(
                title=self.tr("Failed to launch update"),
                text=self.tr("Could not start the update process."),
                information=f"Error: {str(e)}",
            )

    def show_update_error(self) -> None:
        dialogue.show_warning(
            title=self.tr("Unable to retrieve latest release information"),
            text=self.tr(
                "Please check your internet connection and try again, You can also check 'https://github.com/RimSort/RimSort/releases' directly."
            ),
        )

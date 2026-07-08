import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger

from app.models.settings import Settings
from app.utils.app_info import AppInfo


@dataclass
class RimWorldVersion:
    manifest_id: str
    version_string: str
    status: str
    dlcs: dict[str, str]  # DLC name -> manifest ID


class VersionDataService:
    """Service to load and query RimWorld versions and Steam depots from external DB."""

    def __init__(self) -> None:
        self.settings = Settings()
        self.versions_path = Path(self.settings.external_rimworld_versions_file_path)

        self._versions_data: dict[str, Any] = {}
        self._depots_data: dict[str, Any] = {}
        
        self._load_data()

    def _load_data(self) -> None:
        if self.versions_path.exists():
            try:
                with open(self.versions_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._depots_data = data.get("depots", {})
                    self._versions_data = data.get("versions", {})
            except Exception as e:
                logger.error(f"Failed to load versions data from {self.versions_path}: {e}")
        else:
            logger.warning(
                f"RimWorld versions DB not found at {self.versions_path}. "
                "Ensure that the database is configured and downloaded in Settings -> Databases."
            )

    def get_available_versions(self, platform: str) -> list[RimWorldVersion]:
        """Get all available versions for a specific platform (e.g., 'win64', 'mac', 'linux')."""
        versions = []
        platform_data: list[dict[str, Any]] = self._versions_data.get(platform, [])
        
        for details in platform_data:
            versions.append(
                RimWorldVersion(
                    manifest_id=details.get("manifest_id", ""),
                    version_string=details.get("version", "Unknown"),
                    status=details.get("status", "Unknown"),
                    dlcs=details.get("dlcs", {})
                )
            )
            
        # Sort by version string in reverse order (newest first)
        versions.sort(key=lambda x: x.version_string, reverse=True)
        return versions

    def get_depot_id(self, item_name: str, platform: str) -> int | None:
        """
        Get the depot ID for an item (e.g., 'base_game', 'royalty') and platform.
        """
        return self._depots_data.get(item_name, {}).get(platform)

    def get_platform_key(self) -> str:
        """Helper to get the current platform key used in the JSON files."""
        import platform
        sys_name = platform.system().lower()
        if sys_name == "windows":
            # For modern systems, default to win64, but could check bitness
            return "win64" if platform.architecture()[0] == "64bit" else "win32"
        elif sys_name == "darwin":
            return "mac"
        elif sys_name == "linux":
            return "linux"
        return "win64"  # Safe fallback

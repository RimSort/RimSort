from dataclasses import dataclass
from typing import Any

from loguru import logger

from app.utils.generic import format_time_display

# Module-level constants for better access
UNKNOWN = "Unknown"
STEAM_CMD = "SteamCMD"
STEAM = "Steam"
LOCAL = "Local"
DATABASE = "database"


@dataclass
class ModInfo:
    """Standardized mod information structure."""

    uuid: str | None
    name: str
    authors: str
    packageid: str
    published_file_id: str
    supported_versions: str
    source: str
    path: str
    downloaded_time_raw: float | None
    updated_time_raw: float | None
    workshop_url: str
    type: str  # Type of mod (e.g., "Original", "Replacement")
    installed_status: str  # Installation status (e.g., "Installed", "Not Installed")

    def __post_init__(self) -> None:
        """Validate required fields after initialization."""
        if not self.packageid or not self.packageid.strip():
            raise ValueError("packageid cannot be empty or whitespace-only")
        if not self.name or not self.name.strip():
            self.name = UNKNOWN  # Set to UNKNOWN if empty, but allow it

    @classmethod
    def from_metadata(cls, uuid: str | None, metadata: dict[str, Any]) -> "ModInfo":
        """Create ModInfo from metadata dictionary."""
        try:
            name = cls._parse_name(metadata)
            authors = cls._parse_authors(metadata)
            packageid = metadata.get("packageid", "")
            published_file_id = metadata.get("publishedfileid", "")
            supported_versions = cls._parse_supported_versions_static(
                metadata.get("supportedversions")
            )
            source = ""
            if metadata.get("steamcmd"):
                source = STEAM_CMD
            elif metadata.get("data_source") == "workshop":
                source = STEAM
            elif metadata.get("data_source") == "local" and not metadata.get(
                "steamcmd"
            ):
                source = LOCAL
            else:
                source = DATABASE
            path = metadata.get("path", "")
            downloaded_time_raw = metadata.get("internal_time_touched")
            updated_time_raw = metadata.get("external_time_updated")
            workshop_url = cls._generate_workshop_url(published_file_id)
            type = metadata.get("type", "")
            installed_status = metadata.get("installed_status", "")

            # Input validation for required fields
            if not isinstance(packageid, str) or not packageid.strip():
                logger.warning(
                    f"Invalid or missing packageid in metadata for UUID {uuid}"
                )
            if not isinstance(name, str) or not name.strip():
                logger.warning(f"Invalid or missing name in metadata for UUID {uuid}")
            if not isinstance(published_file_id, str):
                logger.warning(f"Invalid published_file_id in metadata for UUID {uuid}")

            return cls(
                uuid,
                name,
                authors,
                packageid,
                published_file_id,
                supported_versions,
                source,
                path,
                downloaded_time_raw,
                updated_time_raw,
                workshop_url,
                type,
                installed_status,
            )
        except Exception as e:
            # Log detailed error information and raise exception instead of returning minimal ModInfo
            metadata_keys = (
                list(metadata.keys())
                if isinstance(metadata, dict)
                else "Invalid metadata type"
            )
            logger.error(
                f"Error creating ModInfo from metadata for UUID {uuid}: {e}. Metadata keys: {metadata_keys}"
            )
            raise ValueError(f"Failed to create ModInfo from metadata: {e}") from e

    @staticmethod
    def _parse_name(metadata: dict[str, Any]) -> str:
        """Parse mod name from metadata with fallbacks."""
        try:
            return metadata.get("name", metadata.get("steamName", ""))
        except Exception:
            return UNKNOWN

    @staticmethod
    def _parse_authors(metadata: dict[str, Any]) -> str:
        """Parse authors from metadata, handling different formats."""
        try:
            authors = metadata.get("authors", "")
            if isinstance(authors, list):
                return ", ".join(str(author) for author in authors)
            elif isinstance(authors, str):
                return authors
            return UNKNOWN
        except Exception:
            return UNKNOWN

    @staticmethod
    def _normalize_version(version: str) -> str:
        """Normalize a version string to major.minor format if it has more parts."""
        if not isinstance(version, str):
            return str(version)
        parts = version.split(".")
        if len(parts) > 2:
            return ".".join(parts[:2])
        return version.strip()

    @staticmethod
    def _parse_supported_versions_static(
        supported_versions: dict[str, Any] | list[str] | str | None,
    ) -> str:
        """
        Parse supported versions from metadata into a normalized, sorted, comma-separated string.

        Args:
            supported_versions: The supported versions data from metadata.
                - dict: Expected to have 'li' key with list of versions or single version string.
                - list: List of version strings.
                - str: Single version string.
                - None: No versions specified.

        Returns:
            str: Comma-separated string of normalized versions, or "Unknown" if None or empty.
        """
        if supported_versions is None:
            return UNKNOWN

        versions = []
        if isinstance(supported_versions, dict):
            if "li" in supported_versions:
                li = supported_versions["li"]
                if isinstance(li, list):
                    versions = [ModInfo._normalize_version(v) for v in li if v]
                elif isinstance(li, str):
                    normalized = ModInfo._normalize_version(li)
                    if normalized:
                        versions = [normalized]
        elif isinstance(supported_versions, list):
            versions = [ModInfo._normalize_version(v) for v in supported_versions if v]
        elif isinstance(supported_versions, str):
            normalized = ModInfo._normalize_version(supported_versions)
            if normalized:
                versions = [normalized]

        if versions:
            # Remove duplicates, sort for consistency, and join
            unique_versions = sorted(set(versions), key=str)
            return ", ".join(unique_versions)
        return UNKNOWN

    @staticmethod
    def _generate_workshop_url(published_file_id: str) -> str:
        """Generate workshop URL from published file ID."""
        if published_file_id and published_file_id.isdigit():
            return f"https://steamcommunity.com/sharedfiles/filedetails/?id={published_file_id}"
        return ""

    @property
    def downloaded_time(self) -> str:
        """Get formatted downloaded time."""
        if self.downloaded_time_raw is not None:
            return format_time_display(int(self.downloaded_time_raw))[0]
        return UNKNOWN

    @property
    def updated_on_workshop(self) -> str:
        """Get formatted workshop update time."""
        if self.updated_time_raw is not None:
            return format_time_display(int(self.updated_time_raw))[0]
        return UNKNOWN

from dataclasses import dataclass
from typing import Any

from loguru import logger

from app.models.metadata.metadata_structure import AboutXmlMod, ListedMod, ModType
from app.utils.constants import DEFAULT_MISSING_PACKAGEID
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

    key: str | None
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
    def from_metadata(cls, key: str | None, metadata: dict[str, Any]) -> "ModInfo":
        """Create ModInfo from metadata dictionary."""
        try:
            name = cls._parse_name(metadata)
            authors = cls._parse_authors(metadata)
            packageid = str(
                metadata.get("packageid", "")
            )  # make sure packageid is a string
            published_file_id = str(
                metadata.get("publishedfileid", "")
            )  # make sure published_file_id is a string
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
            # Prefer acf_time_touched (ACF WorkshopItemsInstalled.timetouched)
            # as the actual download time for SteamCMD mods.  Falls back to
            # internal_time_touched (file mtime) for other mod types.
            acf_time_touched = metadata.get("acf_time_touched")
            downloaded_time_raw = (
                acf_time_touched
                if acf_time_touched is not None
                else metadata.get("internal_time_touched")
            )
            updated_time_raw = metadata.get("external_time_updated")
            workshop_url = cls._generate_workshop_url(published_file_id)
            type = metadata.get("type", "")
            installed_status = metadata.get("installed_status", "")

            # Input validation for required fields
            if not isinstance(packageid, str) or not packageid.strip():
                logger.warning(
                    f"Invalid or missing packageid in metadata for key {key}"
                )
            if not isinstance(name, str) or not name.strip():
                logger.warning(f"Invalid or missing name in metadata for key {key}")
            if not isinstance(published_file_id, str):
                logger.warning(f"Invalid published_file_id in metadata for key {key}")

            return cls(
                key,
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
                f"Error creating ModInfo from metadata for key {key}: {e}. Metadata keys: {metadata_keys}"
            )
            raise ValueError(f"Failed to create ModInfo from metadata: {e}") from e

    @classmethod
    def from_listed_mod(
        cls,
        mod: ListedMod,
        *,
        type: str = "",
        installed_status: str = "",
        acf_time_touched: int | None = None,
        external_time_updated: int | None = None,
    ) -> "ModInfo":
        """Create ModInfo from a typed ListedMod object.

        :param mod: The ListedMod (or AboutXmlMod) to convert
        :param type: Override type label (e.g. "Original", "Replacement")
        :param installed_status: Override installed status label
        :param acf_time_touched: ACF timetouched (actual download time for
            SteamCMD mods).  When provided, used as downloaded_time_raw in
            preference to internal_time_touched.
        :param external_time_updated: Workshop update time from Steam API
            or ACF fallback.  When provided, used as updated_time_raw.
        :return: A populated ModInfo instance
        """
        name = mod.name or UNKNOWN
        packageid = (
            str(mod.package_id)
            if isinstance(mod, AboutXmlMod)
            else DEFAULT_MISSING_PACKAGEID
        )
        published_file_id = mod.published_file_id or ""
        supported_versions = cls._parse_supported_versions_static(
            sorted(mod.supported_versions) if mod.supported_versions else None
        )

        # Map ModType to source string
        source_map = {
            ModType.LUDEON: "expansion",
            ModType.LOCAL: LOCAL,
            ModType.STEAM_WORKSHOP: STEAM,
            ModType.STEAM_CMD: STEAM_CMD,
            ModType.GIT: "git",
        }
        source = source_map.get(mod.mod_type, UNKNOWN)

        # Authors
        if isinstance(mod, AboutXmlMod) and mod.authors:
            authors = ", ".join(str(a) for a in mod.authors)
        else:
            authors = UNKNOWN

        path = str(mod.mod_path) if mod.mod_path else ""

        # Prefer ACF timetouched as the actual download time when available
        downloaded_time_raw: float | None
        if acf_time_touched is not None and acf_time_touched > 0:
            downloaded_time_raw = float(acf_time_touched)
        elif mod.internal_time_touched >= 0:
            downloaded_time_raw = float(mod.internal_time_touched)
        else:
            downloaded_time_raw = None

        updated_time_raw: float | None
        if external_time_updated is not None and external_time_updated > 0:
            updated_time_raw = float(external_time_updated)
        else:
            updated_time_raw = None

        workshop_url = cls._generate_workshop_url(published_file_id)

        return cls(
            key=None,
            name=name,
            authors=authors,
            packageid=packageid,
            published_file_id=published_file_id,
            supported_versions=supported_versions,
            source=source,
            path=path,
            downloaded_time_raw=downloaded_time_raw,
            updated_time_raw=updated_time_raw,
            workshop_url=workshop_url,
            type=type,
            installed_status=installed_status,
        )

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
        supported_versions: dict[str, Any] | list[str] | set[str] | str | None,
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
        elif isinstance(supported_versions, (list, set)):
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

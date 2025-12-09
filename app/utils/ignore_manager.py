import json
from pathlib import Path
from typing import Any

from loguru import logger

from app.utils.app_info import AppInfo


class IgnoreManager:
    """
    Manager for handling ignored mods list.

    This class provides functionality to read and write a list of mods
    to ignore when checking for missing properties. Ignored mods are
    identified by their package ID (the stable mod identifier) and
    stored in a JSON file managed by AppInfo.

    Note: No caching is used to ensure real-time updates when ignore.json
    is modified during runtime (e.g., when mods are added to ignore list).
    """

    @staticmethod
    def get_ignore_file_path() -> Path:
        """
        Get the path to the ignore mods file.

        Returns:
            Path to ignore.json file
        """
        return AppInfo().ignore_mods_file

    @staticmethod
    def load_ignored_mods() -> set[str]:
        """
        Load the list of ignored mod package IDs from the ignore file.

        Returns:
            Set of mod package IDs that should be ignored
        """
        ignore_file = IgnoreManager.get_ignore_file_path()

        if not ignore_file.exists():
            return set()

        try:
            with open(ignore_file, encoding="utf-8") as f:
                data = json.load(f)

            # Support both list and dict format with metadata
            if isinstance(data, dict) and "ignored_mods" in data:
                return set(data["ignored_mods"])
            elif isinstance(data, list):
                return set(data)
            else:
                logger.warning(
                    f"Invalid format in ignore file: {ignore_file}. Expected list or dict with 'ignored_mods' key."
                )
                return set()
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse ignore file {ignore_file}: {e}")
            return set()
        except Exception as e:
            logger.error(f"Failed to load ignored mods from {ignore_file}: {e}")
            return set()

    @staticmethod
    def save_ignored_mods(ignored_mods: set[str]) -> bool:
        """
        Save the list of ignored mod package IDs to the ignore file.

        Args:
            ignored_mods: Set of mod package IDs to ignore

        Returns:
            True if successful, False otherwise
        """
        ignore_file = IgnoreManager.get_ignore_file_path()

        try:
            # Create directory if it doesn't exist
            ignore_file.parent.mkdir(parents=True, exist_ok=True)

            # Save with metadata for future reference
            data: dict[str, Any] = {
                "ignored_mods": sorted(ignored_mods),
                "description": "Mods to ignore when checking for missing properties (identified by packageid)",
            }

            with open(ignore_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)

            logger.info(f"Saved {len(ignored_mods)} ignored mods to {ignore_file}")
            return True
        except Exception as e:
            logger.error(f"Failed to save ignored mods to {ignore_file}: {e}")
            return False

    @staticmethod
    def add_ignored_mod(mod_packageid: str) -> bool:
        """
        Add a mod package ID to the ignore list.

        Args:
            mod_packageid: Package ID of the mod to ignore

        Returns:
            True if successful, False otherwise
        """
        ignored_mods = IgnoreManager.load_ignored_mods()
        if mod_packageid not in ignored_mods:
            ignored_mods.add(mod_packageid)
            return IgnoreManager.save_ignored_mods(ignored_mods)
        return True

    @staticmethod
    def add_ignored_mods(mod_packageids: list[str] | set[str]) -> bool:
        """
        Add multiple mod package IDs to the ignore list.

        Args:
            mod_packageids: List or set of package IDs to ignore

        Returns:
            True if successful, False otherwise
        """
        if not mod_packageids:
            return True

        ignored_mods = IgnoreManager.load_ignored_mods()
        initial_count = len(ignored_mods)
        ignored_mods.update(mod_packageids)

        # Only save if we actually added something new
        if len(ignored_mods) > initial_count:
            return IgnoreManager.save_ignored_mods(ignored_mods)
        return True

    @staticmethod
    def remove_ignored_mod(mod_packageid: str) -> bool:
        """
        Remove a mod package ID from the ignore list.

        Args:
            mod_packageid: Package ID of the mod to remove from ignore list

        Returns:
            True if successful, False otherwise
        """
        ignored_mods = IgnoreManager.load_ignored_mods()
        if mod_packageid in ignored_mods:
            ignored_mods.discard(mod_packageid)
            return IgnoreManager.save_ignored_mods(ignored_mods)
        return True

    @staticmethod
    def remove_ignored_mods(mod_packageids: list[str] | set[str]) -> bool:
        """
        Remove multiple mod package IDs from the ignore list.

        Args:
            mod_packageids: List or set of package IDs to remove

        Returns:
            True if successful, False otherwise
        """
        if not mod_packageids:
            return True

        ignored_mods = IgnoreManager.load_ignored_mods()
        initial_count = len(ignored_mods)
        ignored_mods.difference_update(mod_packageids)

        # Only save if we actually removed something
        if len(ignored_mods) < initial_count:
            return IgnoreManager.save_ignored_mods(ignored_mods)
        return True

    @staticmethod
    def clear_ignored_mods() -> bool:
        """
        Clear all ignored mods.

        Returns:
            True if successful, False otherwise
        """
        return IgnoreManager.save_ignored_mods(set())

    @staticmethod
    def is_mod_ignored(mod_packageid: str) -> bool:
        """
        Check if a mod package ID is in the ignore list.

        Args:
            mod_packageid: Package ID to check

        Returns:
            True if mod is ignored, False otherwise
        """
        return mod_packageid in IgnoreManager.load_ignored_mods()

    @staticmethod
    def get_ignored_mods_count() -> int:
        """
        Get the count of ignored mods.

        Returns:
            Number of ignored mods
        """
        return len(IgnoreManager.load_ignored_mods())

"""
Secure settings model that uses keyring for sensitive data storage.
"""

import logging
from typing import Any, Optional

from app.utils.keyring_manager import KeyringManager, get_keyring_manager

logger = logging.getLogger(__name__)


class SecureSettings:
    """
    Handles secure storage and retrieval of sensitive settings.
    Uses system keyring when available, falls back to plaintext storage.
    """

    def __init__(self) -> None:
        self.keyring_manager = get_keyring_manager()
        self._migration_completed = False

    def get_github_token(self, username: str) -> Optional[str]:
        """Get GitHub token from secure storage."""
        return self.keyring_manager.get_secret(
            KeyringManager.GITHUB_TOKEN, username or "default"
        )

    def set_github_token(self, username: str, token: str) -> bool:
        """Store GitHub token in secure storage."""
        return self.keyring_manager.store_secret(
            KeyringManager.GITHUB_TOKEN, username or "default", token
        )

    def get_steam_api_key(self, username: str = "default") -> Optional[str]:
        """Get Steam API key from secure storage."""
        return self.keyring_manager.get_secret(KeyringManager.STEAM_API_KEY, username)

    def set_steam_api_key(self, api_key: str, username: str = "default") -> bool:
        """Store Steam API key in secure storage."""
        return self.keyring_manager.store_secret(
            KeyringManager.STEAM_API_KEY, username, api_key
        )

    def get_rentry_auth_code(self, username: str = "default") -> Optional[str]:
        """Get Rentry auth code from secure storage."""
        return self.keyring_manager.get_secret(
            KeyringManager.RENTRY_AUTH_CODE, username
        )

    def set_rentry_auth_code(self, auth_code: str, username: str = "default") -> bool:
        """Store Rentry auth code in secure storage."""
        return self.keyring_manager.store_secret(
            KeyringManager.RENTRY_AUTH_CODE, username, auth_code
        )

    def delete_github_token(self, username: str) -> bool:
        """Delete GitHub token from secure storage."""
        return self.keyring_manager.delete_secret(
            KeyringManager.GITHUB_TOKEN, username or "default"
        )

    def delete_steam_api_key(self, username: str = "default") -> bool:
        """Delete Steam API key from secure storage."""
        return self.keyring_manager.delete_secret(
            KeyringManager.STEAM_API_KEY, username
        )

    def delete_rentry_auth_code(self, username: str = "default") -> bool:
        """Delete Rentry auth code from secure storage."""
        return self.keyring_manager.delete_secret(
            KeyringManager.RENTRY_AUTH_CODE, username
        )

    def migrate_from_plaintext_settings(self, settings_dict: dict[str, str]) -> bool:
        """
        Migrate secrets from plaintext settings to secure storage.

        Args:
            settings_dict: Dictionary containing plaintext settings

        Returns:
            True if migration was successful or not needed
        """
        if self._migration_completed or not self.keyring_manager.is_available():
            return True

        migrated_any = False

        # Migrate GitHub token
        github_token = settings_dict.get("github_token", "")
        github_username = settings_dict.get("github_username", "default")
        if github_token:
            if self.keyring_manager.migrate_from_plaintext(
                KeyringManager.GITHUB_TOKEN, github_username, github_token
            ):
                migrated_any = True
                logger.info("Migrated GitHub token to secure storage")

        # Migrate Steam API key
        steam_api_key = settings_dict.get("steam_apikey", "")
        if steam_api_key:
            if self.keyring_manager.migrate_from_plaintext(
                KeyringManager.STEAM_API_KEY, "default", steam_api_key
            ):
                migrated_any = True
                logger.info("Migrated Steam API key to secure storage")

        # Migrate Rentry auth code
        rentry_auth = settings_dict.get("rentry_auth_code", "")
        if rentry_auth:
            if self.keyring_manager.migrate_from_plaintext(
                KeyringManager.RENTRY_AUTH_CODE, "default", rentry_auth
            ):
                migrated_any = True
                logger.info("Migrated Rentry auth code to secure storage")

        if migrated_any:
            logger.info("Migration to secure storage completed")

        self._migration_completed = True
        return True

    def is_keyring_available(self) -> bool:
        """Check if secure keyring storage is available."""
        return self.keyring_manager.is_available()

    def get_storage_info(self) -> dict[str, Any]:
        """Get information about current storage backend."""
        return {
            "keyring_available": self.keyring_manager.is_available(),
            "storage_type": "keyring"
            if self.keyring_manager.is_available()
            else "plaintext",
            "migration_completed": self._migration_completed,
        }

"""
Helper utilities for migrating settings and secrets.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict

from app.models.secure_settings import SecureSettings
from app.utils.app_info import AppInfo

logger = logging.getLogger(__name__)


class MigrationHelper:
    """Helper class for migrating settings and secrets."""

    def __init__(self) -> None:
        self.secure_settings = SecureSettings()
        self.settings_file = AppInfo().app_settings_file
        self.backup_suffix = ".backup_before_secure_migration"

    def needs_migration(self) -> bool:
        """Check if migration is needed."""
        if not self.secure_settings.is_keyring_available():
            return False

        try:
            with open(self.settings_file, "r") as f:
                data = json.load(f)

            # Check if any sensitive data exists in plaintext
            sensitive_keys = ["steam_apikey", "github_token", "rentry_auth_code"]
            return any(data.get(key) for key in sensitive_keys)
        except (FileNotFoundError, json.JSONDecodeError):
            return False

    def migrate_settings(self) -> bool:
        """
        Migrate sensitive settings from plaintext to secure storage.

        Returns:
            True if migration was successful or not needed
        """
        if not self.secure_settings.is_keyring_available():
            logger.info("Keyring not available, skipping migration")
            return True

        if not self.needs_migration():
            logger.info("No migration needed")
            return True

        try:
            # Create backup
            self._create_backup()

            # Load current settings
            with open(self.settings_file, "r") as f:
                data = json.load(f)

            # Migrate secrets
            migrated = self._migrate_secrets(data)

            if migrated:
                # Remove secrets from plaintext and save
                self._remove_secrets_from_data(data)
                with open(self.settings_file, "w") as f:
                    json.dump(data, f, indent=4)

                logger.info("Settings migration completed successfully")
                return True
            else:
                logger.warning("No secrets were migrated")
                return True

        except Exception as e:
            logger.error(f"Migration failed: {e}")
            return False

    def _create_backup(self) -> None:
        """Create a backup of the current settings file."""
        backup_path = Path(str(self.settings_file) + self.backup_suffix)
        if self.settings_file.exists():
            with open(self.settings_file, "r") as src, open(backup_path, "w") as dst:
                dst.write(src.read())
            logger.info(f"Created settings backup at {backup_path}")

    def _migrate_secrets(self, data: Dict[str, Any]) -> bool:
        """Migrate secrets from data dictionary to secure storage."""
        migrated_any = False

        # Migrate Steam API key
        steam_key = data.get("steam_apikey", "").strip()
        if steam_key:
            if self.secure_settings.set_steam_api_key(steam_key):
                logger.info("Migrated Steam API key to secure storage")
                migrated_any = True

        # Migrate GitHub token
        github_token = data.get("github_token", "").strip()
        github_username = data.get("github_username", "default").strip()
        if github_token:
            if self.secure_settings.set_github_token(github_username, github_token):
                logger.info("Migrated GitHub token to secure storage")
                migrated_any = True

        # Migrate Rentry auth code
        rentry_auth = data.get("rentry_auth_code", "").strip()
        if rentry_auth:
            if self.secure_settings.set_rentry_auth_code(rentry_auth):
                logger.info("Migrated Rentry auth code to secure storage")
                migrated_any = True

        return migrated_any

    def _remove_secrets_from_data(self, data: Dict[str, Any]) -> None:
        """Remove sensitive data from the settings dictionary."""
        secrets_to_remove = ["steam_apikey", "github_token", "rentry_auth_code"]
        for secret in secrets_to_remove:
            if secret in data:
                del data[secret]

    def rollback_migration(self) -> bool:
        """
        Rollback migration by restoring from backup.

        Returns:
            True if rollback was successful
        """
        backup_path = Path(str(self.settings_file) + self.backup_suffix)

        if not backup_path.exists():
            logger.warning("No backup file found for rollback")
            return False

        try:
            with open(backup_path, "r") as src, open(self.settings_file, "w") as dst:
                dst.write(src.read())
            logger.info("Migration rollback completed")
            return True
        except Exception as e:
            logger.error(f"Rollback failed: {e}")
            return False

    def cleanup_backup(self) -> None:
        """Remove backup file after successful migration."""
        backup_path = Path(str(self.settings_file) + self.backup_suffix)
        if backup_path.exists():
            backup_path.unlink()
            logger.info("Removed migration backup file")


def run_migration_if_needed() -> bool:
    """
    Run migration if needed during application startup.

    Returns:
        True if migration was successful or not needed
    """
    helper = MigrationHelper()
    if helper.needs_migration():
        logger.info("Starting automatic settings migration...")
        return helper.migrate_settings()
    return True

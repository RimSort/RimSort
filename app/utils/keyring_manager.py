"""
Secure keyring manager for storing sensitive information like API keys and tokens.
Provides a unified interface for Windows Credential Manager, macOS Keychain, and Linux keyring.
"""

import logging
from typing import Optional

import keyring

logger = logging.getLogger(__name__)

# Try to import keyring library
try:
    import keyring

    KEYRING_AVAILABLE = True
except ImportError:
    KEYRING_AVAILABLE = False
    logger.warning(
        "keyring library not available. Secrets will be stored in plaintext."
    )


class KeyringManager:
    """
    Manages secure storage of secrets using the system keyring/credential store.
    Falls back to plaintext storage if keyring is not available.
    """

    SERVICE_NAME = "RimSort"

    # Secret types
    GITHUB_TOKEN = "github_token"
    STEAM_API_KEY = "steam_api_key"
    RENTRY_AUTH_CODE = "rentry_auth_code"

    def __init__(self) -> None:
        """Initialize the KeyringManager and check keyring availability."""
        self._available = KEYRING_AVAILABLE
        if self._available:
            try:
                # Test if keyring is working by getting the backend

                backend = keyring.get_keyring()
                logger.warning(f"Using keyring backend: {backend.__class__.__name__}")
                logger.warning(f"Keyring backend: {keyring.get_keyring()}")
                logger.warning(f"Backend type: {type(backend)}")
                try:
                    keyring.set_password("test_service", "test_user", "test_password")
                    logger.warning("Set password succeeded")
                    pw = keyring.get_password("test_service", "test_user")
                    logger.warning(f"Got password: {pw}")
                except Exception as e:
                    logger.warning(f"Keyring operation failed: {e}")
            except Exception as e:
                logger.warning(f"Keyring backend not working: {e}")
                self._available = False

        if not self._available:
            logger.warning("Keyring not available, secrets will be stored in plaintext")

    def is_available(self) -> bool:
        """Check if secure keyring storage is available."""
        return self._available

    def store_secret(self, secret_type: str, username: str, secret: str) -> bool:
        """
        Store a secret in the system keyring.

        Args:
            secret_type: Type of secret (e.g., GITHUB_TOKEN, STEAM_API_KEY)
            username: Username or identifier associated with the secret
            secret: The secret value to store

        Returns:
            True if successfully stored, False otherwise
        """
        if not self._available:
            return False

        try:
            service_name = f"{self.SERVICE_NAME}_{secret_type}"
            keyring.set_password(service_name, username, secret)
            return True
        except Exception:
            return False

    def get_secret(self, secret_type: str, username: str) -> Optional[str]:
        """
        Retrieve a secret from the system keyring.

        Args:
            secret_type: Type of secret (e.g., GITHUB_TOKEN, STEAM_API_KEY)
            username: Username or identifier associated with the secret

        Returns:
            The secret value if found, None otherwise
        """
        if not self._available:
            return None

        try:
            service_name = f"{self.SERVICE_NAME}_{secret_type}"
            secret = keyring.get_password(service_name, username)
            return secret
        except Exception:
            return None

    def delete_secret(self, secret_type: str, username: str) -> bool:
        """
        Delete a secret from the system keyring.

        Args:
            secret_type: Type of secret (e.g., GITHUB_TOKEN, STEAM_API_KEY)
            username: Username or identifier associated with the secret

        Returns:
            True if successfully deleted, False otherwise
        """
        if not self._available:
            return False

        try:
            service_name = f"{self.SERVICE_NAME}_{secret_type}"
            keyring.delete_password(service_name, username)
            return True
        except Exception:
            return False

    def migrate_from_plaintext(
        self, secret_type: str, username: str, plaintext_value: str
    ) -> bool:
        """
        Migrate a secret from plaintext storage to secure keyring.

        Args:
            secret_type: Type of secret
            username: Username or identifier
            plaintext_value: The plaintext value to migrate

        Returns:
            True if successfully migrated, False otherwise
        """
        if not plaintext_value or not self._available:
            return False

        if self.store_secret(secret_type, username, plaintext_value):
            return True
        return False

    def list_stored_secrets(self) -> list[tuple[str, str]]:
        """
        List all secrets stored for RimSort.

        Returns:
            List of (secret_type, username) tuples
        """
        # This is a basic implementation - keyring doesn't provide a standard way to list all entries
        # We'll need to track this in settings or implement platform-specific solutions
        logger.debug("list_stored_secrets called - limited implementation")
        return []


# Global instance
_keyring_manager = None


def get_keyring_manager() -> KeyringManager:
    """Get the global KeyringManager instance."""
    global _keyring_manager
    if _keyring_manager is None:
        _keyring_manager = KeyringManager()
    return _keyring_manager

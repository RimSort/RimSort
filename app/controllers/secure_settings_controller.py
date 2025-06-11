"""
Controller for secure settings management.
"""

import logging

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QMessageBox

from app.models.settings import Settings
from app.views.secure_settings_widget import SecureSettingsWidget

logger = logging.getLogger(__name__)


class SecureSettingsController(QObject):
    """Controller for managing secure settings."""

    secrets_cleared = Signal()

    def __init__(self, settings: Settings, widget: SecureSettingsWidget):
        super().__init__()
        self.settings = settings
        self.widget = widget

        # Connect signals
        self.widget.clear_secrets_button.clicked.connect(self._on_clear_secrets)

        # Update display
        self.update_display()

    def update_display(self) -> None:
        """Update the widget display with current storage information."""
        storage_info = self.settings.get_storage_info()
        self.widget.update_storage_info(storage_info)

    def _on_clear_secrets(self) -> None:
        """Handle clearing all stored secrets."""
        reply = QMessageBox.question(
            self.widget,
            "Clear All Secrets",
            "Are you sure you want to clear all stored secrets?\n\n"
            "This will remove:\n"
            "• GitHub personal access token\n"
            "• Steam WebAPI key\n"
            "• Rentry authentication code\n\n"
            "You will need to re-enter these values in the settings.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            success = self._clear_all_secrets()
            if success:
                QMessageBox.information(
                    self.widget,
                    "Secrets Cleared",
                    "All stored secrets have been successfully cleared.",
                )
                self.secrets_cleared.emit()
            else:
                QMessageBox.warning(
                    self.widget,
                    "Clear Failed",
                    "Some secrets could not be cleared. Please check the logs for details.",
                )

    def _clear_all_secrets(self) -> bool:
        """Clear all stored secrets."""
        try:
            # Clear GitHub token
            if self.settings.github_username:
                self.settings._secure_settings.delete_github_token(
                    self.settings.github_username
                )

            # Clear Steam API key
            self.settings._secure_settings.delete_steam_api_key()

            # Clear Rentry auth code
            self.settings._secure_settings.delete_rentry_auth_code()

            logger.info("All secrets cleared successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to clear secrets: {e}")
            return False

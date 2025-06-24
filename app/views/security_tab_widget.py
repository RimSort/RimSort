"""
Security tab widget for settings window.
Displays secure storage state and allows secret management.
"""

from typing import Optional

from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from app.utils.keyring_manager import get_keyring_manager


class SecurityTabWidget(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.keyring_manager = get_keyring_manager()
        self.init_ui()

    def init_ui(self) -> None:
        layout = QVBoxLayout()
        self.status_label = QLabel()
        self.update_status_label()
        layout.addWidget(self.status_label)

        migrate_btn = QPushButton("Migrate Legacy Secrets")
        migrate_btn.clicked.connect(self.migrate_secrets)
        layout.addWidget(migrate_btn)

        clear_btn = QPushButton("Clear All Stored Secrets")
        clear_btn.clicked.connect(self.clear_secrets)
        layout.addWidget(clear_btn)

        self.msg_label = QLabel()
        layout.addWidget(self.msg_label)

        self.setLayout(layout)

    def update_status_label(self) -> None:
        status = (
            "Available"
            if self.keyring_manager.is_available()
            else "Not available (falling back to plaintext)"
        )
        self.status_label.setText(f"Secure Storage: <b>{status}</b>")

    def migrate_secrets(self) -> None:
        try:
            from app.utils.migration_helper import run_migration_if_needed

            migrated = run_migration_if_needed()
            self.msg_label.setText(
                f"Migration {'succeeded' if migrated else 'failed or not needed'}."
            )
        except Exception as e:
            self.msg_label.setText(f"Migration error: {e}")
        self.update_status_label()

    def clear_secrets(self) -> None:
        try:
            # Remove all known secrets for 'default' user
            self.keyring_manager.delete_secret("github_token", "default")
            self.keyring_manager.delete_secret("steam_api_key", "default")
            self.keyring_manager.delete_secret("rentry_auth_code", "default")
            self.msg_label.setText("All stored secrets cleared.")
        except Exception as e:
            self.msg_label.setText(f"Error clearing secrets: {e}")
        self.update_status_label()

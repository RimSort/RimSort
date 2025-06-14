"""
Widget for displaying secure storage status and managing secrets.
"""

from PySide6.QtWidgets import (
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class SecureSettingsWidget(QWidget):
    """Widget for displaying secure storage information and managing secrets."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self) -> None:
        """Setup the user interface."""
        layout = QVBoxLayout(self)

        # Storage status group
        status_group = QGroupBox("Secure Storage Status")
        layout.addWidget(status_group)

        status_layout = QVBoxLayout(status_group)

        # Storage backend info
        self.storage_info_label = QLabel()
        self.storage_info_label.setWordWrap(True)
        status_layout.addWidget(self.storage_info_label)

        # Migration status
        self.migration_status_label = QLabel()
        self.migration_status_label.setWordWrap(True)
        status_layout.addWidget(self.migration_status_label)

        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(separator)

        # Security information
        info_group = QGroupBox("Security Information")
        layout.addWidget(info_group)

        info_layout = QVBoxLayout(info_group)

        security_info = QTextEdit()
        security_info.setReadOnly(True)
        security_info.setMaximumHeight(150)
        security_info.setPlainText(
            "RimSort uses your system's secure credential storage when available:\n\n"
            "• Windows: Windows Credential Manager\n"
            "• macOS: Keychain Access\n"
            "• Linux: Desktop Environment keyring (GNOME Keyring, KDE Wallet, etc.)\n\n"
            "If secure storage is not available, secrets will be stored in plaintext "
            "in your settings file. This is less secure but maintains compatibility."
        )
        info_layout.addWidget(security_info)

        # Management buttons
        buttons_layout = QHBoxLayout()
        info_layout.addLayout(buttons_layout)

        buttons_layout.addStretch()

        self.clear_secrets_button = QPushButton("Clear All Stored Secrets")
        self.clear_secrets_button.setToolTip(
            "Remove all secrets from secure storage. "
            "You will need to re-enter them in the settings."
        )
        buttons_layout.addWidget(self.clear_secrets_button)

        layout.addStretch()

    def update_storage_info(self, storage_info: dict[str, object]) -> None:
        """Update the storage information display."""
        if storage_info.get("keyring_available", False):
            status_text = "✅ Secure storage is available and active"
            status_color = "color: green;"
        else:
            status_text = "⚠️ Secure storage is not available - using plaintext storage"
            status_color = "color: orange;"

        self.storage_info_label.setText(
            f"<span style='{status_color}'>{status_text}</span>"
        )

        # Migration status
        if storage_info.get("migration_completed", False):
            migration_text = "✅ Secret migration completed"
            migration_color = "color: green;"
        else:
            migration_text = "ℹ️ No migration needed or pending"
            migration_color = "color: gray;"

        self.migration_status_label.setText(
            f"<span style='{migration_color}'>{migration_text}</span>"
        )

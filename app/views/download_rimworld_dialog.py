from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from app.services.version_data_service import VersionDataService
from app.utils.steam.steamcmd.wrapper import SteamcmdInterface
from app.views.dialogue import show_warning


class DownloadRimWorldDialog(QDialog):
    """Dialog to download a specific RimWorld version via SteamCMD."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Download RimWorld Version"))
        self.setMinimumWidth(400)
        self.version_service = VersionDataService()
        self._setup_ui()
        self._load_versions()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        # Version Dropdown (filterable)
        self.version_combo = QComboBox()
        self.version_combo.setEditable(True)
        self.version_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.version_combo.completer().setCompletionMode(self.version_combo.completer().CompletionMode.PopupCompletion)
        self.version_combo.completer().setFilterMode(Qt.MatchFlag.MatchContains)
        form_layout.addRow(self.tr("Version:"), self.version_combo)

        # Destination Path
        path_layout = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.browse_button = QPushButton(self.tr("Browse"))
        self.browse_button.clicked.connect(self._on_browse)
        path_layout.addWidget(self.path_edit)
        path_layout.addWidget(self.browse_button)
        form_layout.addRow(self.tr("Destination:"), path_layout)

        # Steam Username
        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText(self.tr("Steam Username"))
        form_layout.addRow(self.tr("Steam Username:"), self.username_edit)

        layout.addLayout(form_layout)

        # Download Button
        self.download_button = QPushButton(self.tr("Download"))
        self.download_button.clicked.connect(self._on_download)
        
        # Add a note explaining the console will appear
        from PySide6.QtWidgets import QLabel
        note_label = QLabel(self.tr("Note: An interactive console will open. You will be prompted to enter your password and Steam Guard code if required."))
        note_label.setWordWrap(True)
        layout.addWidget(note_label)
        
        layout.addWidget(self.download_button)

    def _load_versions(self) -> None:
        platform = self.version_service.get_platform_key()
        self.versions = self.version_service.get_available_versions(platform)
        
        for version in self.versions:
            display_text = f"{version.version_string} ({version.status})"
            self.version_combo.addItem(display_text, userData=version)

    def _on_browse(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self, self.tr("Select Destination Folder"), ""
        )
        if directory:
            self.path_edit.setText(directory)

    def _on_download(self) -> None:
        version_data = self.version_combo.currentData()
        install_dir = self.path_edit.text().strip()
        username = self.username_edit.text().strip()

        if not version_data:
            show_warning(self.tr("Error"), self.tr("Please select a version."))
            return
        if not install_dir:
            show_warning(self.tr("Error"), self.tr("Please select a destination folder."))
            return
        if not username:
            show_warning(self.tr("Error"), self.tr("Please enter your Steam username."))
            return
            
        # Collect manifests to download
        platform = self.version_service.get_platform_key()
        manifests_to_download = []
        
        # Base game
        base_depot_id = self.version_service.get_depot_id("base_game", platform)
        if base_depot_id and version_data.manifest_id:
            manifests_to_download.append((base_depot_id, version_data.manifest_id))
            
        # DLCs
        for dlc_name, manifest_id in version_data.dlcs.items():
            dlc_depot_id = self.version_service.get_depot_id(dlc_name, platform)
            if dlc_depot_id and manifest_id:
                manifests_to_download.append((dlc_depot_id, manifest_id))

        if not manifests_to_download:
            show_warning(self.tr("Error"), self.tr("Could not determine depot IDs for this platform."))
            return

        try:
            steamcmd_interface = SteamcmdInterface.instance()
            if not steamcmd_interface.setup:
                show_warning(
                    self.tr("Error"),
                    self.tr("SteamCMD is not set up. Please set it up in the settings first.")
                )
                return
                
            steamcmd_interface.download_game_version(
                username=username,
                install_dir=install_dir,
                manifests=manifests_to_download
            )
            
            QMessageBox.information(
                self,
                self.tr("Download Started"),
                self.tr("SteamCMD has been launched in a new terminal window.\nPlease follow the prompts to complete the download.")
            )
        except Exception as e:
            show_warning(self.tr("Error"), self.tr(f"Failed to start download: {e}"))

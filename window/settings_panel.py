import logging
from functools import partial

from PySide2.QtCore import QStandardPaths, Qt, Signal
from PySide2.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from util.filesystem import platform_specific_open

logger = logging.getLogger(__name__)


class SettingsPanel(QDialog):
    clear_paths_signal = Signal(str)
    dupe_mods_warning_signal = Signal(str)
    metadata_by_appid_signal = Signal(str)
    metadata_comparison_signal = Signal(str)
    set_webapi_query_expiry_signal = Signal(str)
    steam_mods_update_check_signal = Signal(str)

    def __init__(self) -> None:
        logger.info("Starting SettingsPanel initialization")
        super(SettingsPanel, self).__init__()

        # Create window
        self.setFixedSize(400, 400)
        self.setWindowTitle("Settings")

        # Allow for styling
        self.setObjectName("settingsPanel")

        # Create main layout
        self.layout = QVBoxLayout()
        self.layout.setAlignment(Qt.AlignTop)

        # Create widgets
        self.sorting_algorithm_label = QLabel("Sorting Algorithm")
        self.sorting_algorithm_label.setObjectName("summaryValue")
        self.sorting_algorithm_cb = QComboBox()
        self.sorting_algorithm_cb.addItems(["RimPy", "Topological"])
        self.external_metadata_label = QLabel("External Metadata Source")
        self.external_metadata_label.setObjectName("externalMetadataSource")
        self.external_metadata_label.setStyleSheet("QLabel { color : white; }")
        self.external_metadata_cb = QComboBox()
        self.external_metadata_cb.addItems(
            ["RimPy Mod Manager Database", "Rimsort Dynamic Query"]
        )
        self.metadata_by_appid_button = QPushButton(
            "Generate external metadata by appid"
        )
        self.metadata_by_appid_button.clicked.connect(
            partial(self.metadata_by_appid_signal.emit, 294100)
        )
        self.comparison_report_button = QPushButton("External metadata comparison")
        self.comparison_report_button.clicked.connect(
            partial(
                self.metadata_comparison_signal.emit, "external_metadata_comparison"
            )
        )
        self.set_webapi_query_expiry_button = QPushButton("Set WebAPI Query Expiry")
        self.set_webapi_query_expiry_button.setToolTip("Default: 30 min (1800 seconds)")
        self.set_webapi_query_expiry_button.clicked.connect(
            partial(self.set_webapi_query_expiry_signal.emit, "set_webapi_query_expiry")
        )
        self.clear_paths_button = QPushButton("Clear Paths")
        self.clear_paths_button.clicked.connect(
            partial(self.clear_paths_signal.emit, "clear_paths")
        )
        self.open_storage_button = QPushButton("Open Storage Dir")
        self.open_storage_button.clicked.connect(
            partial(
                platform_specific_open,
                QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation),
            )
        )
        self.duplicate_mods_checkbox = QCheckBox(
            "Show duplicate mods warning on refresh"
        )
        # self.duplicate_mods_checkbox.setStyleSheet("QCheckBox { color : white; }")
        self.duplicate_mods_checkbox.stateChanged.connect(
            self.dupe_mods_warning_signal.emit
        )
        self.steam_mods_update_checkbox = QCheckBox(
            "Show Steam mods update check on refresh"
        )
        # self.steam_mods_update_checkbox.setStyleSheet("QCheckBox { color : white; }")
        self.steam_mods_update_checkbox.stateChanged.connect(
            self.steam_mods_update_check_signal.emit
        )
        # Add widgets to layout
        self.layout.addWidget(self.sorting_algorithm_label)
        self.layout.addWidget(self.sorting_algorithm_cb)
        self.layout.addWidget(self.external_metadata_label)
        self.layout.addWidget(self.external_metadata_cb)
        self.layout.addWidget(self.metadata_by_appid_button)
        self.layout.addWidget(self.comparison_report_button)
        self.layout.addWidget(self.set_webapi_query_expiry_button)
        self.layout.addWidget(self.clear_paths_button)
        self.layout.addWidget(self.open_storage_button)
        self.layout.addWidget(self.duplicate_mods_checkbox)
        self.layout.addWidget(self.steam_mods_update_checkbox)

        # Display items
        self.setLayout(self.layout)

        logger.info("Finished SettingsPanel initialization")

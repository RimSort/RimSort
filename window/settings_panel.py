from functools import partial
from logger_tt import logger
import os
from pathlib import Path
import sys

from PySide6.QtCore import QStandardPaths, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from util.generic import platform_specific_open, upload_data_to_0x0_st


class SettingsPanel(QDialog):
    appidquery_signal = Signal(str)
    clear_paths_signal = Signal(str)
    metadata_comparison_signal = Signal(str)
    set_webapi_query_expiry_signal = Signal(str)

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
        self.general_label = QLabel("General")
        self.general_label.setObjectName("summaryValue")
        self.clear_paths_button = QPushButton("Clear Paths")
        self.clear_paths_button.clicked.connect(
            partial(self.clear_paths_signal.emit, "clear_paths")
        )
        self.open_log_button = QPushButton("Open RimSort Log")
        self.open_log_button.clicked.connect(
            partial(
                platform_specific_open,
                os.path.join(os.path.dirname(sys.argv[0]), "RimSort.log"),
            )
        )
        self.upload_log_button = QPushButton("Upload RimSort Log")
        self.upload_log_button.setToolTip(
            "Log will be uploaded to http://0x0.st/ and\n"
            + "the URL will be copied to your clipboard."
        )
        self.upload_log_button.clicked.connect(
            partial(
                upload_data_to_0x0_st,
                os.path.join(os.path.dirname(sys.argv[0]), "RimSort.log"),
            )
        )
        self.open_storage_button = QPushButton("Open Storage Dir")
        self.open_storage_button.clicked.connect(
            partial(
                platform_specific_open,
                QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation),
            )
        )

        # sorting algorithm
        self.sorting_algorithm_label = QLabel("Sorting Algorithm")
        self.sorting_algorithm_label.setObjectName("summaryValue")
        self.sorting_algorithm_cb = QComboBox()
        self.sorting_algorithm_cb.addItems(["RimPy", "Topological"])

        # metadata
        self.metadata_label = QLabel("Metadata")
        self.metadata_label.setObjectName("summaryValue")
        self.external_metadata_cb = QComboBox()
        self.external_metadata_cb.addItems(
            ["RimPy Mod Manager Database", "RimSort Dynamic Query", "None"]
        )
        self.appidquery_button = QPushButton("Cache AppIDQuery")
        self.appidquery_button.clicked.connect(
            partial(self.appidquery_signal.emit, 294100)
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

        # duplicate mods warning
        self.duplicate_mods_checkbox = QCheckBox(
            "Show duplicate mods warning on refresh"
        )
        self.duplicate_mods_checkbox.setObjectName("summaryValue")
        # steam mods update check
        self.steam_mods_update_checkbox = QCheckBox(
            "Show Steam mods update check on refresh"
        )
        self.steam_mods_update_checkbox.setObjectName("summaryValue")
        self.steam_mods_update_checkbox.setToolTip(
            "This option requires you to have a Steam apikey configured with\n"
            + 'the below "Metadata" option set to "RimSort Dynamic Query"\n\n'
            + '"Metadata" should be set to RimPy MMDB when sorting for now.'
        )

        # todds
        self.todds_label = QLabel("todds options")
        self.todds_label.setObjectName("summaryValue")
        self.todds_presets_cb = QComboBox()
        self.todds_presets_cb.addItems(
            [
                "Low (for toasters)",
                "Medium (recommended)",
                "High (supercomputers!)",
            ]
        )
        self.todds_active_mods_target_checkbox = QCheckBox(
            "Force todds to only target mods in the active mods list"
        )
        self.todds_active_mods_target_checkbox.setToolTip(
            "If unchecked, todds will convert textures for all\n"
            + "applicable mods parsed from a mod data source."
        )
        self.todds_active_mods_target_checkbox.setObjectName("summaryValue")
        self.todds_dry_run_checkbox = QCheckBox(
            'Force todds to use a special "dry run" mode'
        )
        self.todds_dry_run_checkbox.setToolTip(
            "You can save this output to file using the action in the runner panel.\n"
            + "This will not write any changes to the disk, and is useful to get a list\n"
            + "of all input files that will be converted to .dds format by todds."
        )
        self.todds_dry_run_checkbox.setObjectName("summaryValue")
        self.todds_overwrite_checkbox = QCheckBox(
            "Force todds to overwrite existing optimized textures"
        )
        self.todds_overwrite_checkbox.setToolTip(
            "By default, if an optimized texture already exists,\n"
            + "but the existing texture is older than the input file,\n"
            + "it will be overwritten with a newly optimized texture.\n\n"
            + "This option will force all textures to be converted again."
        )
        self.todds_overwrite_checkbox.setObjectName("summaryValue")

        # Add widgets to layout
        self.layout.addWidget(self.general_label)
        self.layout.addWidget(self.clear_paths_button)
        self.layout.addWidget(self.open_log_button)
        self.layout.addWidget(self.upload_log_button)
        self.layout.addWidget(self.open_storage_button)
        self.layout.addWidget(self.duplicate_mods_checkbox)
        self.layout.addWidget(self.steam_mods_update_checkbox)

        self.layout.addWidget(self.metadata_label)
        self.layout.addWidget(self.external_metadata_cb)
        self.layout.addWidget(self.appidquery_button)
        self.layout.addWidget(self.comparison_report_button)
        self.layout.addWidget(self.set_webapi_query_expiry_button)

        self.layout.addWidget(self.sorting_algorithm_label)
        self.layout.addWidget(self.sorting_algorithm_cb)

        self.layout.addWidget(self.todds_label)
        self.layout.addWidget(self.todds_presets_cb)
        self.layout.addWidget(self.todds_active_mods_target_checkbox)
        self.layout.addWidget(self.todds_dry_run_checkbox)
        self.layout.addWidget(self.todds_overwrite_checkbox)

        # Display items
        self.setLayout(self.layout)

        logger.info("Finished SettingsPanel initialization")

import json
from typing import Any

from loguru import logger
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class CompanionPanel(QWidget):
    """
    Panel for the RimWorld companion mod integration.

    Displays connection status and provides controls for interacting
    with a running RimWorld instance via the companion mod's JSON-RPC
    server. Uses a QStackedWidget to switch between disconnected and
    connected states.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        logger.debug("Initializing CompanionPanel")

        self._setup_ui()

        # Start in disconnected state
        self.show_disconnected()

        logger.debug("Finished CompanionPanel initialization")

    def _setup_ui(self) -> None:
        """Build the stacked widget with disconnected and connected pages."""
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(5, 5, 5, 5)
        self.setLayout(main_layout)

        self.stack = QStackedWidget()
        main_layout.addWidget(self.stack)

        self._build_disconnected_page()
        self._build_connected_page()

    # ------------------------------------------------------------------
    # Disconnected page
    # ------------------------------------------------------------------

    def _build_disconnected_page(self) -> None:
        page = QWidget()
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        page.setLayout(layout)

        self.status_label = QLabel(self.tr("Not Connected"))
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(self.status_label)

        description = QLabel(
            self.tr(
                "The companion feature connects RimSort to a running RimWorld instance\n"
                "via the RimSort Companion mod. Start RimWorld with the companion mod\n"
                "enabled to establish a connection."
            )
        )
        description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        description.setWordWrap(True)
        layout.addWidget(description)

        self.error_label = QLabel()
        self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_label.setStyleSheet("color: red;")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        layout.addWidget(self.error_label)

        self.stack.addWidget(page)

    # ------------------------------------------------------------------
    # Connected page
    # ------------------------------------------------------------------

    def _build_connected_page(self) -> None:
        page = QWidget()
        layout = QVBoxLayout()
        page.setLayout(layout)

        self._build_status_group(layout)
        self._build_diagnostics_group(layout)
        self._build_actions_group(layout)

        self.stack.addWidget(page)

    def _build_status_group(self, parent_layout: QVBoxLayout) -> None:
        group = QGroupBox(self.tr("Status"))
        group_layout = QHBoxLayout()
        group.setLayout(group_layout)

        self.connection_label = QLabel(self.tr("Connected"))
        self.connection_label.setStyleSheet("color: green; font-weight: bold;")
        group_layout.addWidget(self.connection_label)

        self.game_version_label = QLabel()
        group_layout.addWidget(self.game_version_label)

        self.game_state_label = QLabel()
        group_layout.addWidget(self.game_state_label)

        self.tps_label = QLabel()
        group_layout.addWidget(self.tps_label)

        group_layout.addStretch()

        parent_layout.addWidget(group)

    def _build_diagnostics_group(self, parent_layout: QVBoxLayout) -> None:
        group = QGroupBox(self.tr("Diagnostics"))
        group_layout = QVBoxLayout()
        group.setLayout(group_layout)

        button_row = QHBoxLayout()

        self.fetch_load_order_button = QPushButton(self.tr("Get Load Order"))
        button_row.addWidget(self.fetch_load_order_button)

        self.fetch_mod_errors_button = QPushButton(self.tr("Get Mod Errors"))
        button_row.addWidget(self.fetch_mod_errors_button)

        self.fetch_harmony_button = QPushButton(self.tr("Get Harmony Patches"))
        button_row.addWidget(self.fetch_harmony_button)

        group_layout.addLayout(button_row)

        self.diagnostics_output = QTextEdit()
        self.diagnostics_output.setReadOnly(True)
        self.diagnostics_output.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        group_layout.addWidget(self.diagnostics_output)

        parent_layout.addWidget(group, stretch=1)

    def _build_actions_group(self, parent_layout: QVBoxLayout) -> None:
        group = QGroupBox(self.tr("Actions"))
        group_layout = QHBoxLayout()
        group.setLayout(group_layout)

        self.apply_mod_list_button = QPushButton(self.tr("Apply Mod List & Restart"))
        group_layout.addWidget(self.apply_mod_list_button)

        group_layout.addStretch()

        parent_layout.addWidget(group)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def show_disconnected(self, error: str | None = None) -> None:
        """
        Switch to the disconnected page.

        :param error: optional error message to display
        """
        self.stack.setCurrentIndex(0)
        if error:
            self.error_label.setText(error)
            self.error_label.show()
        else:
            self.error_label.hide()

    def show_connected(self, handshake_data: dict[str, Any]) -> None:
        """
        Switch to the connected page and populate initial data.

        :param handshake_data: dict[str, Any] from the companion handshake containing
            ``game_version`` and ``active_mods`` (count).
        """
        self.stack.setCurrentIndex(1)
        self.error_label.hide()

        game_version = handshake_data.get("game_version", self.tr("Unknown"))
        self.game_version_label.setText(
            self.tr("Game: {version}").format(version=game_version)
        )

        mod_count = len(handshake_data.get("active_mods", []))
        self.game_state_label.setText(
            self.tr("{count} mods active").format(count=mod_count)
        )

        self.tps_label.setText(self.tr("TPS: —"))

    def update_game_state(self, state: str) -> None:
        """
        Update the game state label.

        :param state: raw state string (e.g. ``"playing_map"``)
        """
        display = state.replace("_", " ").title()
        self.game_state_label.setText(display)

    def update_heartbeat(self, data: dict[str, Any]) -> None:
        """
        Update the TPS label from heartbeat data.

        :param data: dict[str, Any] with an optional ``tps`` key
        """
        tps = data.get("tps")
        if tps is None:
            self.tps_label.setText(self.tr("TPS: —"))
        else:
            self.tps_label.setText(self.tr("TPS: {tps}").format(tps=tps))

    def set_apply_pending(self, pending: bool) -> None:
        """
        Toggle the apply button between normal and pending states.

        :param pending: when True, show a waiting message and disable the button
        """
        if pending:
            self.apply_mod_list_button.setText(self.tr("Applying..."))
            self.apply_mod_list_button.setEnabled(False)
        else:
            self.apply_mod_list_button.setText(self.tr("Apply Mod List & Restart"))
            self.apply_mod_list_button.setEnabled(True)

    def set_diagnostics_enabled(self, enabled: bool) -> None:
        """
        Enable or disable all diagnostic buttons.

        :param enabled: whether the buttons should be clickable
        """
        self.fetch_load_order_button.setEnabled(enabled)
        self.fetch_mod_errors_button.setEnabled(enabled)
        self.fetch_harmony_button.setEnabled(enabled)

    def display_diagnostics(self, title: str, data: dict[str, Any]) -> None:
        """
        Format diagnostic data as JSON and display it in the output area.

        :param title: heading shown above the JSON payload
        :param data: dict[str, Any] to pretty-print
        """
        formatted = json.dumps(data, indent=2, ensure_ascii=False)
        self.diagnostics_output.setText(f"--- {title} ---\n\n{formatted}")

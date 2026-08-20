from loguru import logger
from PySide6.QtCore import Slot

from app.controllers.settings_tabs.base_tab_controller import BaseTabController


class AdvancedTabController(BaseTabController):
    """Controller for the Advanced settings tab.

    Manages: debug logging, watchdog, clear/DLC behavior, mod update checks,
    DB auto-update, mod name search scope, backup policy,
    save-comparison indicators, Auxiliary DB settings, MCP server settings,
    and Authentication fields.
    """

    def connect_signals(self) -> None:
        try:
            self.dialog.show_save_comparison_indicators_checkbox.toggled.connect(
                self._on_toggle_show_save_comparison_indicators
            )
        except (AttributeError, TypeError):
            logger.warning(
                "show_save_comparison_indicators_checkbox not available for signal wiring"
            )

        self.dialog.include_mod_notes_in_mod_name_filter_checkbox.stateChanged.connect(
            self._on_include_mod_notes_in_mod_name_filter_changed
        )
        self.dialog.mcp_server_port.valueChanged.connect(self._update_mcp_snippet)
        self.dialog.mcp_server_token.textChanged.connect(self._update_mcp_snippet)

    def update_view_from_model(self) -> None:
        try:
            self.dialog.show_save_comparison_indicators_checkbox.setChecked(
                self.settings.show_save_comparison_indicators
            )
        except (AttributeError, TypeError):
            logger.warning(
                "show_save_comparison_indicators_checkbox not available for view update"
            )

        self.dialog.debug_logging_checkbox.setChecked(
            self.settings.debug_logging_enabled
        )
        self.dialog.watchdog_checkbox.setChecked(self.settings.watchdog_toggle)
        self.dialog.backup_saves_on_launch_checkbox.setChecked(
            self.settings.backup_saves_on_launch
        )
        self.dialog.auto_backup_retention_count_spinbox.setValue(
            self.settings.auto_backup_retention_count
        )
        self.dialog.auto_backup_compression_count_spinbox.setValue(
            self.settings.auto_backup_compression_count
        )
        self.dialog.clear_moves_dlc_checkbox.setChecked(self.settings.clear_moves_dlc)
        self.dialog.show_mod_updates_checkbox.setChecked(
            self.settings.steam_mods_update_check
        )
        self.dialog.update_databases_on_startup_checkbox.setChecked(
            self.settings.update_databases_on_startup
        )
        self.dialog.include_mod_notes_in_mod_name_filter_checkbox.setChecked(
            self.settings.include_mod_notes_in_mod_name_filter
        )
        self.dialog.enable_backup_before_update_checkbox.setChecked(
            self.settings.enable_backup_before_update
        )
        self.dialog.max_backups_spinbox.setValue(self.settings.max_backups)

        # Auxiliary DB
        self.dialog.aux_db_time_limit.setText(str(self.settings.aux_db_time_limit))
        self.dialog.enable_aux_db_behavior_editing.setChecked(
            self.settings.enable_aux_db_behavior_editing
        )

        # Authentication
        self.dialog.rentry_auth_code.setText(self.settings.rentry_auth_code)
        self.dialog.rentry_auth_code.setCursorPosition(0)
        self.dialog.github_username.setText(self.settings.github_username)
        self.dialog.github_username.setCursorPosition(0)
        self.dialog.github_token.setText(self.settings.github_token)
        self.dialog.github_token.setCursorPosition(0)

        self.dialog.mcp_server_enabled_checkbox.setChecked(
            self.settings.mcp_server_enabled
        )
        self.dialog.mcp_server_port.setValue(self.settings.mcp_server_port)
        self.dialog.mcp_server_token.setText(self.settings.mcp_server_token)
        self.dialog.mcp_server_token.setCursorPosition(0)
        self._update_mcp_snippet()

    def _update_mcp_snippet(self) -> None:
        port = self.dialog.mcp_server_port.value()
        token = self.dialog.mcp_server_token.text().strip()
        auth = ""
        if token:
            auth = (
                ',\n      "headers": {'
                f'"Authorization": "Bearer {token}"'
                "}"
            )
        snippet = (
            '{\n  "mcpServers": {\n    "rimsort": {\n'
            f'      "url": "http://127.0.0.1:{port}/mcp"{auth}\n'
            "    }\n  }\n}"
        )
        self.dialog.mcp_config_snippet.setText(snippet)

    def update_model_from_view(self) -> None:
        self.settings.debug_logging_enabled = (
            self.dialog.debug_logging_checkbox.isChecked()
        )
        self.settings.watchdog_toggle = self.dialog.watchdog_checkbox.isChecked()
        self.settings.backup_saves_on_launch = (
            self.dialog.backup_saves_on_launch_checkbox.isChecked()
        )
        self.settings.auto_backup_retention_count = (
            self.dialog.auto_backup_retention_count_spinbox.value()
        )
        self.settings.auto_backup_compression_count = (
            self.dialog.auto_backup_compression_count_spinbox.value()
        )
        self.settings.clear_moves_dlc = self.dialog.clear_moves_dlc_checkbox.isChecked()
        self.settings.steam_mods_update_check = (
            self.dialog.show_mod_updates_checkbox.isChecked()
        )
        self.settings.update_databases_on_startup = (
            self.dialog.update_databases_on_startup_checkbox.isChecked()
        )
        self.settings.include_mod_notes_in_mod_name_filter = (
            self.dialog.include_mod_notes_in_mod_name_filter_checkbox.isChecked()
        )
        self.settings.enable_backup_before_update = (
            self.dialog.enable_backup_before_update_checkbox.isChecked()
        )
        self.settings.max_backups = self.dialog.max_backups_spinbox.value()

        # Auxiliary DB
        try:
            self.settings.aux_db_time_limit = int(self.dialog.aux_db_time_limit.text())
        except Exception:
            logger.warning("Failed setting Aux DB time limit, falling back to -1")
            self.settings.aux_db_time_limit = -1
        self.settings.enable_aux_db_behavior_editing = (
            self.dialog.enable_aux_db_behavior_editing.isChecked()
        )

        # Authentication
        self.settings.rentry_auth_code = self.dialog.rentry_auth_code.text()
        self.settings.github_username = self.dialog.github_username.text()
        self.settings.github_token = self.dialog.github_token.text()

        self.settings.mcp_server_enabled = (
            self.dialog.mcp_server_enabled_checkbox.isChecked()
        )
        self.settings.mcp_server_port = self.dialog.mcp_server_port.value()
        self.settings.mcp_server_token = self.dialog.mcp_server_token.text()

    @Slot(bool)
    def _on_toggle_show_save_comparison_indicators(self, checked: bool) -> None:
        self.settings.show_save_comparison_indicators = checked
        self.settings.save()

    @Slot()
    def _on_include_mod_notes_in_mod_name_filter_changed(self) -> None:
        self.settings.include_mod_notes_in_mod_name_filter = (
            self.dialog.include_mod_notes_in_mod_name_filter_checkbox.isChecked()
        )

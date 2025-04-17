from loguru import logger
from PySide6.QtCore import QObject, Qt, Signal, Slot

from app.utils.event_bus import EventBus
from app.views.mods_panel import ModsPanel
from app.views.mods_panel_list_widget import ModListWidget


class ModsPanelController(QObject):
    reset_warnings_signal = Signal()

    def __init__(self, view: ModsPanel) -> None:
        super().__init__()

        self.mods_panel = view

        self.reset_warnings_signal.connect(self._on_menu_bar_reset_warnings_triggered)

        # Only one label can be active at a time; these are used only in the active modlist.
        self.warnings_label_active = False
        self.errors_label_active = False

        self.mods_panel.warnings_text.clicked.connect(
            self._toggle_visibility_of_mods_with_warnings
        )
        self.mods_panel.errors_text.clicked.connect(
            self._toggle_visibility_of_mods_with_errors
        )
        EventBus().filters_changed_in_active_modlist.connect(
            self._on_filters_changed_in_active_modlist
        )
        EventBus().filters_changed_in_inactive_modlist.connect(
            self._on_filters_changed_in_inactive_modlist
        )

    @Slot()
    def _on_filters_changed_in_active_modlist(self) -> None:
        """When filters are changed in the active modlist."""
        self._reset_active_labels()

    @Slot()
    def _on_filters_changed_in_inactive_modlist(self) -> None:
        """When filters are changed in the inactive modlist."""
        self._reset_active_labels()

    def _reset_active_labels(self) -> None:
        """Reset the visibility of warning/error labels based on their active state."""
        if self.warnings_label_active:
            self.mods_panel.warnings_text.clicked.emit()
        elif self.errors_label_active:
            self.mods_panel.errors_text.clicked.emit()

    @Slot()
    def _on_menu_bar_reset_warnings_triggered(self) -> None:
        """Resets all warning and error toggles for active and inactive mods."""
        self._reset_mods_warnings_and_errors(self.mods_panel.active_mods_list)
        self._reset_mods_warnings_and_errors(self.mods_panel.inactive_mods_list)

    def _reset_mods_warnings_and_errors(self, mod_list: ModListWidget) -> None:
        mods = mod_list.get_all_loaded_and_toggled_mod_list_items()
        for mod in mods:
            mod_data = mod.data(Qt.ItemDataRole.UserRole)
            if mod_data["warning_toggled"]:
                mod_data["warning_toggled"] = False
                mod.setData(Qt.ItemDataRole.UserRole, mod_data)
                package_id = mod_data["uuid"]
                self._remove_from_all_ignore_lists(package_id)
                logger.debug(f"Reset warning toggle for: {package_id}")
        mod_list.recalculate_warnings_signal.emit()

    def _remove_from_all_ignore_lists(self, package_id: str) -> None:
        active_mods_list = self.mods_panel.active_mods_list.ignore_warning_list
        if package_id in active_mods_list:
            active_mods_list.remove(package_id)
        inactive_mods_list = self.mods_panel.inactive_mods_list.ignore_warning_list
        if package_id in inactive_mods_list:
            inactive_mods_list.remove(package_id)

    @Slot()
    def _toggle_visibility_of_mods_with_warnings(self) -> None:
        """Toggle visibility of mods with warnings."""
        self._toggle_visibility_of_mods("warnings")

    @Slot()
    def _toggle_visibility_of_mods_with_errors(self) -> None:
        """Toggle visibility of mods with errors."""
        self._toggle_visibility_of_mods("errors")

    def _toggle_visibility_of_mods(self, mod_type: str) -> None:
        """Toggle visibility of mods based on the specified type (warnings or errors)."""
        if mod_type == "warnings":
            if self.errors_label_active:
                self.mods_panel.errors_text.clicked.emit()
            self.warnings_label_active = not self.warnings_label_active
        else:
            if self.warnings_label_active:
                self.mods_panel.warnings_text.clicked.emit()
            self.errors_label_active = not self.errors_label_active

        active_mods = self.mods_panel.active_mods_list.get_all_mod_list_items()
        for mod in active_mods:
            mod_data = mod.data(Qt.ItemDataRole.UserRole)
            if mod_data[mod_type] == "":
                if (mod_type == "warnings" and self.warnings_label_active) or (
                    mod_type == "errors" and self.errors_label_active
                ):
                    mod.setHidden(True)
                elif not mod_data["hidden_by_filter"]:
                    mod.setHidden(False)
        self.mods_panel.update_count("Active")
        logger.debug(f"Finished hiding mods without {mod_type}.")

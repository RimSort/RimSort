from loguru import logger
from PySide6.QtCore import QObject, Qt, Signal, Slot

from app.views.mods_panel import ModListWidget, ModsPanel


class ModsPanelController(QObject):
    reset_warnings_signal = Signal()
    
    def __init__(self, view: ModsPanel) -> None:
        super().__init__()

        self.mods_panel = view
        #TODO: Probably wanna make it activate filters_active variable... or somehow integrate with other filters?? Look into it
        # Only one label can be active at a time
        self.warnings_label_active = False
        self.errors_label_active = False

        self.mods_panel.warnings_text.clicked.connect(self._show_mods_with_warnings)
        self.mods_panel.errors_text.clicked.connect(self._show_mods_with_errors)
        self.reset_warnings_signal.connect(self._on_menu_bar_reset_warnings_triggered)

    @Slot()
    def _on_menu_bar_reset_warnings_triggered(self) -> None:
        """
        Resets all warning and error toggles for active and inactive mods.
        """
        active_mods = self.mods_panel.active_mods_list.get_all_loaded_and_toggled_mod_list_items()
        inactive_mods = self.mods_panel.inactive_mods_list.get_all_loaded_and_toggled_mod_list_items()
        for mod in active_mods + inactive_mods:
            mod_data = mod.data(Qt.ItemDataRole.UserRole)
            if mod_data["warning_toggled"]:
                mod_data["warning_toggled"] = False
                mod.setData(Qt.ItemDataRole.UserRole, mod_data)
                widget = mod.listWidget()
                # Widget should always be of type ModListWidget
                if isinstance(widget, ModListWidget):
                    package_id = widget.metadata_manager.internal_local_metadata[mod_data["uuid"]]["packageid"]
                    self._remove_from_all_ignore_lists(package_id)
                    logger.debug(f"Reset warning toggle for: {package_id}")
        self.mods_panel.active_mods_list.recalculate_warnings_signal.emit()
        self.mods_panel.inactive_mods_list.recalculate_warnings_signal.emit()
        
    def _remove_from_all_ignore_lists(self, package_id: str) -> None:
        active_mods_list = self.mods_panel.active_mods_list.ignore_warning_list
        if package_id in active_mods_list:
            active_mods_list.remove(package_id)
        inactive_mods_list = self.mods_panel.inactive_mods_list.ignore_warning_list
        if package_id in inactive_mods_list:
            inactive_mods_list.remove(package_id)

    @Slot()
    def _show_mods_with_warnings(self) -> None:
        """
        Dynamically shows/hides all mods that have warnings.
        """
        # If the other label is active, disable it
        if self.errors_label_active:
            self.mods_panel.errors_text.clicked.emit()

        self.warnings_label_active = not self.warnings_label_active

        active_mods = self.mods_panel.active_mods_list.get_all_mod_list_items()
        for mod in active_mods:
            mod_data = mod.data(Qt.ItemDataRole.UserRole)
            if mod_data["warnings"] == '':
                if self.warnings_label_active:
                    mod.setHidden(True)
                else:
                    mod.setHidden(False)


    @Slot()
    def _show_mods_with_errors(self) -> None:
        """
        Dynamically shows/hides all mods that have errors.
        """
        # If the other label is active, disable it
        if self.warnings_label_active:
            self.mods_panel.warnings_text.clicked.emit()

        self.errors_label_active = not self.errors_label_active

        active_mods = self.mods_panel.active_mods_list.get_all_mod_list_items()
        for mod in active_mods:
            mod_data = mod.data(Qt.ItemDataRole.UserRole)
            if mod_data["errors"] == '':
                if self.errors_label_active:
                    mod.setHidden(True)
                else:
                    mod.setHidden(False)

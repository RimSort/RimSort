from PySide6.QtCore import QObject, Signal, Slot

from app.views.mods_panel import ModsPanel


class ModsPanelController(QObject):
    reset_warnings_signal = Signal()
    
    def __init__(self, view: ModsPanel) -> None:
        super().__init__()
        
        self.mods_panel = view
        
        self.reset_warnings_signal.connect(self._on_menu_bar_reset_warnings_triggered)
        
    @Slot()
    def _on_menu_bar_reset_warnings_triggered(self) -> None:
        """
        Resets all warning and error toggles for active and inactive mods.
        """
        active_mods = self.mods_panel.active_mods_list.get_all_loaded_and_toggled_mod_list_items()
        inactive_mods = self.mods_panel.inactive_mods_list.get_all_loaded_and_toggled_mod_list_items()
        for mod_item in active_mods:
            package_id = mod_item.metadata_manager.internal_local_metadata[mod_item.uuid]["packageid"]
            mod_item.reset_warning_signal.emit(package_id)
        self.mods_panel.active_mods_list.recalculate_warnings_signal.emit()
        for mod_item in inactive_mods:
            package_id = mod_item.metadata_manager.internal_local_metadata[mod_item.uuid]["packageid"]
            mod_item.reset_warning_signal.emit(package_id)
        self.mods_panel.inactive_mods_list.recalculate_warnings_signal.emit()
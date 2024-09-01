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
        Resets all warning/error toggles.
        """
        active_and_inactive_mods = self.mods_panel.collect_mod_list_items()
        active_mods = active_and_inactive_mods[0]
        inactive_mods = active_and_inactive_mods[1]
        for mod_item in active_mods:
            package_id = mod_item.metadata_manager.internal_local_metadata[mod_item.uuid]["packageid"]
            mod_item.reset_warning_signal.emit(package_id)
        for mod_item in inactive_mods:
            package_id = mod_item.metadata_manager.internal_local_metadata[mod_item.uuid]["packageid"]
            mod_item.reset_warning_signal.emit(package_id)
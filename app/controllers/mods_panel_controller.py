from loguru import logger
from PySide6.QtCore import QObject, Qt, Signal, Slot

from app.utils.event_bus import EventBus
from app.views.mods_panel import ModListWidget, ModsPanel


class ModsPanelController(QObject):
    reset_warnings_signal = Signal()

    def __init__(self, view: ModsPanel) -> None:
        super().__init__()

        self.mods_panel = view

        self.reset_warnings_signal.connect(self._on_menu_bar_reset_warnings_triggered)

        # Only one label can be active at a time; these are used only in the active modlist.

        self.warnings_label_active = False
        self.errors_label_active = False
        self.news_label_active = False

        self.mods_panel.warnings_text.clicked.connect(
            self._change_visibility_of_mods_with_warnings
        )
        self.mods_panel.errors_text.clicked.connect(
            self._change_visibility_of_mods_with_errors
        )
        # New mods filter label
        if hasattr(self.mods_panel, "new_text"):
            self.mods_panel.new_text.clicked.connect(
                self._change_visibility_of_new_mods
            )
        self.reset_warnings_signal.connect(self._on_menu_bar_reset_warnings_triggered)
        EventBus().filters_changed_in_active_modlist.connect(
            self._on_filters_changed_in_active_modlist
        )
        EventBus().filters_changed_in_inactive_modlist.connect(
            self._on_filters_changed_in_inactive_modlist
        )

    @Slot()
    def _on_filters_changed_in_active_modlist(self) -> None:
        """When filters are changed in the active modlist."""

        # On filter change, disable warning/error label if active
        if self.warnings_label_active:
            self.mods_panel.warnings_text.clicked.emit()
        elif self.errors_label_active:
            self.mods_panel.errors_text.clicked.emit()
        elif self.news_label_active and hasattr(self.mods_panel, "new_text"):
            self.mods_panel.new_text.clicked.emit()

    @Slot()
    def _on_filters_changed_in_inactive_modlist(self) -> None:
        """When filters are changed in the inactive modlist."""

        # On filter change, disable warning/error label if active
        if self.warnings_label_active:
            self.mods_panel.warnings_text.clicked.emit()
        elif self.errors_label_active:
            self.mods_panel.errors_text.clicked.emit()
        elif self.news_label_active and hasattr(self.mods_panel, "new_text"):
            self.mods_panel.new_text.clicked.emit()

    @Slot()
    def _on_menu_bar_reset_warnings_triggered(self) -> None:
        """Resets all warning and error toggles for active and inactive mods."""

        active_mods = (
            self.mods_panel.active_mods_list.get_all_loaded_and_toggled_mod_list_items()
        )
        inactive_mods = self.mods_panel.inactive_mods_list.get_all_loaded_and_toggled_mod_list_items()
        for mod in active_mods + inactive_mods:
            mod_data = mod.data(Qt.ItemDataRole.UserRole)
            if mod_data["warning_toggled"]:
                mod_data["warning_toggled"] = False
                mod.setData(Qt.ItemDataRole.UserRole, mod_data)
                widget = mod.listWidget()
                # Widget should always be of type ModListWidget
                if isinstance(widget, ModListWidget):
                    package_id = widget.metadata_manager.internal_local_metadata[
                        mod_data["uuid"]
                    ]["packageid"]
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
    def _change_visibility_of_mods_with_warnings(self) -> None:
        """When on, shows only mods that have warnings.

        When off, shows all mods.

        Works with filters, meaning it won't show mods with warnings if they don't match the filters."""

        # If the other label is active, disable it
        if self.errors_label_active:
            self.mods_panel.errors_text.clicked.emit()
        if self.news_label_active and hasattr(self.mods_panel, "new_text"):
            self.mods_panel.new_text.clicked.emit()

        self.warnings_label_active = not self.warnings_label_active

        active_mods = self.mods_panel.active_mods_list.get_all_mod_list_items()
        for mod in active_mods:
            mod_data = mod.data(Qt.ItemDataRole.UserRole)
            # If a mod is already hidden becasue of filters, dont unhide it
            if mod_data["warnings"] == "":
                if self.warnings_label_active:
                    mod.setHidden(True)
                elif not mod_data["hidden_by_filter"]:
                    mod.setHidden(False)
        self.mods_panel.update_count("Active")
        self.mods_panel.active_mods_list.check_widgets_visible()
        logger.debug("Finished hiding mods without warnings.")

    @Slot()
    def _change_visibility_of_mods_with_errors(self) -> None:
        """When on, shows only mods that have errors.

        When off, shows all mods.

        Works with filters, meaning it won't show mods with errors if they don't match the filters."""

        # If the other label is active, disable it
        if self.warnings_label_active:
            self.mods_panel.warnings_text.clicked.emit()
        if self.news_label_active and hasattr(self.mods_panel, "new_text"):
            self.mods_panel.new_text.clicked.emit()

        self.errors_label_active = not self.errors_label_active

        active_mods = self.mods_panel.active_mods_list.get_all_mod_list_items()
        for mod in active_mods:
            mod_data = mod.data(Qt.ItemDataRole.UserRole)
            # If a mod is already hidden because of filters, dont unhide it
            if mod_data["errors"] == "":
                if self.errors_label_active:
                    mod.setHidden(True)
                elif not mod_data["hidden_by_filter"]:
                    mod.setHidden(False)
        self.mods_panel.update_count("Active")
        self.mods_panel.active_mods_list.check_widgets_visible()
        logger.debug("Finished hiding mods without errors.")

    @Slot()
    def _change_visibility_of_new_mods(self) -> None:
        """When on, shows only active mods that are not in the latest save file.

        When off, shows all mods. Respects other active filters.
        """

        # If the other labels are active, disable them
        if self.warnings_label_active:
            self.mods_panel.warnings_text.clicked.emit()
        if self.errors_label_active:
            self.mods_panel.errors_text.clicked.emit()

        self.news_label_active = not self.news_label_active

        active_mods = self.mods_panel.active_mods_list.get_all_mod_list_items()
        for mod in active_mods:
            mod_data = mod.data(Qt.ItemDataRole.UserRole)
            is_new = bool(mod_data.__dict__.get("is_new", False))
            # If a mod is already hidden because of filters, dont unhide it
            if not is_new:
                if self.news_label_active:
                    mod.setHidden(True)
                elif not mod_data["hidden_by_filter"]:
                    mod.setHidden(False)
        self.mods_panel.update_count("Active")
        self.mods_panel.active_mods_list.check_widgets_visible()
        logger.debug("Finished hiding mods that are in save (showing only new).")

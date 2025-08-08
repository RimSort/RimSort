from datetime import datetime, timedelta, timezone
from pathlib import Path

from loguru import logger
from PySide6.QtCore import QObject, Qt, Slot
from sqlalchemy import delete, update

from app.controllers.metadata_db_controller import AuxMetadataController
from app.controllers.settings_controller import SettingsController
from app.models.metadata.metadata_db import AuxMetadataEntry
from app.utils.app_info import AppInfo
from app.utils.event_bus import EventBus
from app.views.mods_panel import ModListWidget, ModsPanel


class ModsPanelController(QObject):

    def __init__(self, view: ModsPanel, settings_controller: SettingsController) -> None:
        super().__init__()

        self.mods_panel = view
        self.settings_controller = settings_controller

        # Only one label can be active at a time; these are used only in the active modlist.

        self.warnings_label_active = False
        self.errors_label_active = False

        self.mods_panel.warnings_text.clicked.connect(
            self._change_visibility_of_mods_with_warnings
        )
        self.mods_panel.errors_text.clicked.connect(
            self._change_visibility_of_mods_with_errors
        )
        EventBus().reset_warnings_signal.connect(
            self._on_menu_bar_reset_warnings_triggered
        )
        EventBus().reset_mod_colors_signal.connect(
            self._on_menu_bar_reset_mod_colors_triggered
        )
        EventBus().do_change_mod_coloring_mode.connect(
            self._on_change_mod_coloring_mode
        )
        EventBus().filters_changed_in_active_modlist.connect(
            self._on_filters_changed_in_active_modlist
        )
        EventBus().filters_changed_in_inactive_modlist.connect(
            self._on_filters_changed_in_inactive_modlist
        )
        EventBus().do_delete_outdated_entries_in_aux_db.connect(
            self.delete_outdated_aux_db_entries
        )
        EventBus().do_set_all_entries_in_aux_db_as_outdated.connect(
            self.do_all_entries_in_aux_db_as_outdated
        )

    @Slot()
    def _on_filters_changed_in_active_modlist(self) -> None:
        """When filters are changed in the active modlist."""

        # On filter change, disable warning/error label if active
        if self.warnings_label_active:
            self.mods_panel.warnings_text.clicked.emit()
        elif self.errors_label_active:
            self.mods_panel.errors_text.clicked.emit()

    @Slot()
    def _on_filters_changed_in_inactive_modlist(self) -> None:
        """When filters are changed in the inactive modlist."""

        # On filter change, disable warning/error label if active
        if self.warnings_label_active:
            self.mods_panel.warnings_text.clicked.emit()
        elif self.errors_label_active:
            self.mods_panel.errors_text.clicked.emit()

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

    def _on_menu_bar_reset_mod_colors_triggered(self) -> None:
        """
        Resets all mod colors to the default color.
        """
        active_mods = self.mods_panel.active_mods_list.get_all_mod_list_items()
        inactive_mods = self.mods_panel.inactive_mods_list.get_all_mod_list_items()
        for mod in active_mods :
            mod_data = mod.data(Qt.ItemDataRole.UserRole)
            uuid = mod_data["uuid"]
            self.mods_panel.active_mods_list.reset_mod_color(uuid)
        for mod in inactive_mods:
            mod_data = mod.data(Qt.ItemDataRole.UserRole)
            uuid = mod_data["uuid"]
            self.mods_panel.inactive_mods_list.reset_mod_color(uuid)

    def _on_change_mod_coloring_mode(self) -> None:
        active_mods = self.mods_panel.active_mods_list.get_all_mod_list_items()
        inactive_mods = self.mods_panel.inactive_mods_list.get_all_mod_list_items()
        for mod in active_mods:
            mod_data = mod.data(Qt.ItemDataRole.UserRole)
            uuid = mod_data["uuid"]
            mod_color = mod_data["mod_color"]
            if mod_color:
                self.mods_panel.active_mods_list.change_mod_color(uuid, mod_color)

        for mod in inactive_mods:
            mod_data = mod.data(Qt.ItemDataRole.UserRole)
            uuid = mod_data["uuid"]
            mod_color = mod_data["mod_color"]
            if mod_color:
                self.mods_panel.inactive_mods_list.change_mod_color(uuid, mod_color)

    @Slot()
    def _change_visibility_of_mods_with_warnings(self) -> None:
        """When on, shows only mods that have warnings.

        When off, shows all mods.

        Works with filters, meaning it won't show mods with warnings if they don't match the filters."""

        # If the other label is active, disable it
        if self.errors_label_active:
            self.mods_panel.errors_text.clicked.emit()

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
        logger.debug("Finished hiding mods without warnings.")

    @Slot()
    def _change_visibility_of_mods_with_errors(self) -> None:
        """When on, shows only mods that have errors.

        When off, shows all mods.

        Works with filters, meaning it won't show mods with errors if they don't match the filters."""

        # If the other label is active, disable it
        if self.warnings_label_active:
            self.mods_panel.warnings_text.clicked.emit()

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
        logger.debug("Finished hiding mods without errors.")

    def do_all_entries_in_aux_db_as_outdated(self) -> None:
        """
        Sets all entries in the aux db as outdated if not already outdated.

        This means the previously outdated items DO NOT have their db_time_touched updated.
        """
        time_limit = self.settings_controller.settings.aux_db_time_limit
        if time_limit < 0:
            logger.debug("Skipping updating all items as outdated because time limit is negative.")
            return

        instance_name = self.settings_controller.settings.current_instance
        instance_path = Path(AppInfo().app_storage_folder) / "instances" / instance_name
        aux_metadata_controller = AuxMetadataController.get_or_create_cached_instance(
            instance_path / "aux_metadata.db"
        )
        with aux_metadata_controller.Session() as aux_metadata_session:
            stmt = (
                update(AuxMetadataEntry)
                .where(not AuxMetadataEntry.outdated)  # type: ignore
                .values(outdated=True)
            )
            aux_metadata_session.execute(stmt)
            aux_metadata_session.commit()
        logger.debug("Finished setting entries as outdated.")

    def delete_outdated_aux_db_entries(self) -> None:
        """
        Based on settings option, it deletes aux db entries
        after a certain time limit they have not been touched.

        This is used at init phases of the applicaiton. Keeps DB
        udpated even if mods have been deleted etc. outside of RimSort.
        """
        time_limit = self.settings_controller.settings.aux_db_time_limit
        if time_limit < 0:
            logger.debug("Skipping the deletion of outdated entries because time limit is negative.")
            return

        instance_name = self.settings_controller.settings.current_instance
        instance_path = Path(AppInfo().app_storage_folder) / "instances" / instance_name
        aux_metadata_controller = AuxMetadataController.get_or_create_cached_instance(
            instance_path / "aux_metadata.db"
        )
        with aux_metadata_controller.Session() as aux_metadata_session:
            limit = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=time_limit)
            stmt = (
                delete(AuxMetadataEntry)
                .where(AuxMetadataEntry.outdated)
                .where(AuxMetadataEntry.db_time_touched < limit)
            )
            aux_metadata_session.execute(stmt)
            aux_metadata_session.commit()
        logger.debug("Finished deleting outdated entries.")

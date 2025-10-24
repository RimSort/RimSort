from datetime import datetime, timedelta, timezone
from functools import partial

from loguru import logger
from PySide6.QtCore import QObject, Qt, Slot
from sqlalchemy import delete, update

from app.controllers.metadata_db_controller import AuxMetadataController
from app.controllers.settings_controller import SettingsController
from app.models.metadata.metadata_db import AuxMetadataEntry
from app.utils.event_bus import EventBus
from app.views.mods_panel import ModListWidget, ModsPanel


class ModsPanelController(QObject):
    def __init__(
        self, view: ModsPanel, settings_controller: SettingsController
    ) -> None:
        super().__init__()

        self.mods_panel = view
        self.settings_controller = settings_controller

        # Only one label can be active at a time; these are used only in the active modlist.

        self.warnings_label_active = False
        self.errors_label_active = False
        self.news_label_active = False

        self.mods_panel.warnings_text.clicked.connect(
            partial(self._change_visibility_of_mods_with_warnings_errors, "warnings")
        )
        self.mods_panel.errors_text.clicked.connect(
            partial(self._change_visibility_of_mods_with_warnings_errors, "errors")
        )
        # New mods filter label (only when save-comparison feature enabled)
        if (
            hasattr(self.mods_panel, "new_text")
            and self.settings_controller.settings.show_save_comparison_indicators
        ):
            self.mods_panel.new_text.clicked.connect(
                self._change_visibility_of_new_mods
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

    def _reemit_active_filter_signal(self) -> None:
        """Re-emit the active filter label's click signal to reapply filtering."""

        if self.warnings_label_active:
            self.mods_panel.warnings_text.clicked.emit()
        elif self.errors_label_active:
            self.mods_panel.errors_text.clicked.emit()
        elif (
            self.news_label_active
            and hasattr(self.mods_panel, "new_text")
            and self.settings_controller.settings.show_save_comparison_indicators
        ):
            self.mods_panel.new_text.clicked.emit()

    @Slot()
    def _on_filters_changed_in_active_modlist(self) -> None:
        """When filters are changed in the active modlist."""

        self._reemit_active_filter_signal()

    @Slot()
    def _on_filters_changed_in_inactive_modlist(self) -> None:
        """When filters are changed in the inactive modlist."""

        self._reemit_active_filter_signal()

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
                    # Update Aux DB
                    aux_metadata_controller = (
                        AuxMetadataController.get_or_create_cached_instance(
                            self.settings_controller.settings.aux_db_path
                        )
                    )
                    uuid = mod_data["uuid"]
                    if not uuid:
                        logger.error(
                            "Unable to retrieve uuid when saving toggle_warning to Aux DB after menu bar reset."
                        )
                        return
                    with aux_metadata_controller.Session() as aux_metadata_session:
                        mod_path = widget.metadata_manager.internal_local_metadata[
                            uuid
                        ]["path"]
                        aux_metadata_controller.update(
                            aux_metadata_session,
                            mod_path,
                            ignore_warnings=mod_data["warning_toggled"],
                        )
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
        for mod in active_mods:
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
    def _change_visibility_of_mods_with_warnings_errors(self, type: str) -> None:
        """
        When on, shows only mods have either warnings or errors. Based on passed in type.

        When off, shows all mods.

        Works partially with filters, meaning it won't show mods with warnings if they don't match the filters.
        """
        # If the other labels are active, disable them
        if self.news_label_active:
            self.mods_panel.new_text.clicked.emit()
        if type == "warnings":
            if self.errors_label_active:
                self.mods_panel.errors_text.clicked.emit()
            self.warnings_label_active = not self.warnings_label_active
            label_active = self.warnings_label_active
        else:
            if self.warnings_label_active:
                self.mods_panel.warnings_text.clicked.emit()
            self.errors_label_active = not self.errors_label_active
            label_active = self.errors_label_active

        self.__change_visibility_helper(label_active, type)
        logger.debug("Finished hiding mods without " + type)

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

        self.__change_visibility_helper(self.news_label_active, "new_text")
        logger.debug("Finished hiding mods that are in save (showing only new).")

    def __change_visibility_helper(self, label_active: bool, type: str) -> None:
        active_mods = self.mods_panel.active_mods_list.get_all_mod_list_items()
        for mod in active_mods:
            mod_data = mod.data(Qt.ItemDataRole.UserRole)
            if type == "new_text":
                apply_filter = not bool(mod_data.__dict__.get("is_new", False))
            else:
                apply_filter = mod_data[type] == ""

            # If a mod is already hidden becasue of filters, dont unhide it
            if apply_filter:
                if label_active:
                    mod.setHidden(True)
                elif not mod_data["hidden_by_filter"]:
                    mod.setHidden(False)
        self.mods_panel.update_count("Active")
        self.mods_panel.active_mods_list.repaint()
        self.mods_panel.active_mods_list.check_widgets_visible()

    def do_all_entries_in_aux_db_as_outdated(self) -> None:
        """
        Sets all entries in the aux db as outdated if not already outdated.

        This means the previously outdated items DO NOT have their db_time_touched updated.
        """
        # This is more performant, but we dont update db_time_touched. But that should be ok
        time_limit = self.settings_controller.settings.aux_db_time_limit
        if time_limit < 0:
            logger.debug(
                "Skipping the setting entries as outdated because time limit is negative."
            )
            return

        aux_metadata_controller = AuxMetadataController.get_or_create_cached_instance(
            self.settings_controller.settings.aux_db_path
        )
        with aux_metadata_controller.Session() as aux_metadata_session:
            stmt = (
                update(AuxMetadataEntry)
                .where(AuxMetadataEntry.outdated.is_(False))
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
        updated even if mods have been deleted etc. outside of RimSort.
        """
        time_limit = self.settings_controller.settings.aux_db_time_limit
        if time_limit < 0:
            logger.debug(
                "Skipping the deletion of outdated entries because time limit is negative."
            )
            return

        aux_metadata_controller = AuxMetadataController.get_or_create_cached_instance(
            self.settings_controller.settings.aux_db_path
        )
        with aux_metadata_controller.Session() as aux_metadata_session:
            limit = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
                seconds=time_limit
            )
            stmt = (
                delete(AuxMetadataEntry)
                .where(AuxMetadataEntry.outdated)
                .where(AuxMetadataEntry.db_time_touched < limit)
            )
            aux_metadata_session.execute(stmt)
            aux_metadata_session.commit()
        logger.debug("Finished deleting outdated entries.")

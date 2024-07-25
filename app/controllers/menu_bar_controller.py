from functools import partial

from PySide6.QtCore import QObject, Slot
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QLineEdit, QPlainTextEdit, QTextEdit

from app.controllers.settings_controller import SettingsController
from app.utils.event_bus import EventBus
from app.utils.generic import open_url_browser
from app.views.menu_bar import MenuBar


class MenuBarController(QObject):
    def __init__(self, view: MenuBar, settings_controller: SettingsController) -> None:
        super().__init__()

        self.menu_bar = view
        self.settings_controller = settings_controller

        # Application menu
        instance = QApplication.instance()
        if instance is None:
            raise RuntimeError("QApplication instance not found")
        self.menu_bar.quit_action.triggered.connect(instance.quit)

        # TODO: updates not implemented yet
        # self.menu_bar.check_for_updates_action.triggered.connect(
        #     EventBus().do_check_for_application_update.emit
        # )

        # self.menu_bar.check_for_updates_on_startup_action.toggled.connect(
        #     self._on_menu_bar_check_for_updates_on_startup_triggered
        # )

        # self.menu_bar.check_for_updates_on_startup_action.setChecked(
        #     self.settings_controller.settings.check_for_update_startup
        # )

        self.menu_bar.settings_action.triggered.connect(
            self.settings_controller.show_settings_dialog
        )

        # File menu

        self.menu_bar.open_mod_list_action.triggered.connect(
            EventBus().do_open_mod_list.emit
        )

        self.menu_bar.save_mod_list_action.triggered.connect(
            EventBus().do_save_mod_list_as.emit
        )

        self.menu_bar.import_from_rentry_action.triggered.connect(
            EventBus().do_import_mod_list_from_rentry
        )

        self.menu_bar.import_from_workshop_collection_action.triggered.connect(
            EventBus().do_import_mod_list_from_workshop_collection
        )

        self.menu_bar.export_to_clipboard_action.triggered.connect(
            EventBus().do_export_mod_list_to_clipboard
        )

        self.menu_bar.export_to_rentry_action.triggered.connect(
            EventBus().do_export_mod_list_to_rentry
        )
        self.menu_bar.upload_rimsort_log_action.triggered.connect(
            EventBus().do_upload_rimsort_log
        )

        self.menu_bar.upload_rimsort_old_log_action.triggered.connect(
            EventBus().do_upload_rimsort_old_log
        )

        self.menu_bar.upload_rimworld_log_action.triggered.connect(
            EventBus().do_upload_rimworld_log
        )

        self.menu_bar.open_app_directory_action.triggered.connect(
            EventBus().do_open_app_directory
        )

        self.menu_bar.open_settings_directory_action.triggered.connect(
            EventBus().do_open_settings_directory
        )

        self.menu_bar.open_rimsort_logs_directory_action.triggered.connect(
            EventBus().do_open_rimsort_logs_directory
        )

        self.menu_bar.open_rimworld_logs_directory_action.triggered.connect(
            EventBus().do_open_rimworld_logs_directory
        )

        # Edit menu

        self.menu_bar.cut_action.triggered.connect(self._on_menu_bar_cut_triggered)

        self.menu_bar.copy_action.triggered.connect(self._on_menu_bar_copy_triggered)

        self.menu_bar.paste_action.triggered.connect(self._on_menu_bar_paste_triggered)

        self.menu_bar.rule_editor_action.triggered.connect(EventBus().do_rule_editor)

        # Download menu

        self.menu_bar.add_git_mod_action.triggered.connect(
            EventBus().do_add_git_mod.emit
        )

        self.menu_bar.browse_workshop_action.triggered.connect(
            EventBus().do_browse_workshop
        )

        self.menu_bar.update_workshop_mods_action.triggered.connect(
            EventBus().do_check_for_workshop_updates
        )

        # Instances menu
        self.menu_bar.backup_instance_action.triggered.connect(
            self._on_do_backup_current_instance
        )
        self.menu_bar.restore_instance_action.triggered.connect(
            EventBus().do_restore_instance_from_archive.emit
        )
        self.menu_bar.clone_instance_action.triggered.connect(
            self._on_do_clone_current_instance
        )
        self.menu_bar.create_instance_action.triggered.connect(
            EventBus().do_create_new_instance.emit
        )
        self.menu_bar.delete_instance_action.triggered.connect(
            EventBus().do_delete_current_instance.emit
        )

        # Textures menu

        self.menu_bar.optimize_textures_action.triggered.connect(
            EventBus().do_optimize_textures
        )

        self.menu_bar.delete_dds_textures_action.triggered.connect(
            EventBus().do_delete_dds_textures
        )

        # Help menu

        self.menu_bar.wiki_action.triggered.connect(self._on_menu_bar_wiki_triggered)
        self.menu_bar.validate_steam_client_action.triggered.connect(
            EventBus().do_validate_steam_client
        )

        # External signals

        EventBus().refresh_started.connect(self._on_refresh_started)
        EventBus().refresh_finished.connect(self._on_refresh_finished)

    def _on_do_backup_current_instance(self) -> None:
        EventBus().do_backup_existing_instance.emit(
            self.settings_controller.settings.current_instance
        )

    def _on_do_clone_current_instance(self) -> None:
        EventBus().do_clone_existing_instance.emit(
            self.settings_controller.settings.current_instance
        )

    def _on_instances_submenu_population(self, instance_names: list[str]) -> None:
        self.menu_bar.instances_submenu.clear()
        actions = [QAction(name, self) for name in instance_names]
        for action in actions:
            action.triggered.connect(
                partial(
                    self._on_set_current_instance,
                    current_instance=action.text(),
                    initialize=True,
                )
            )
        self.menu_bar.instances_submenu.addActions(actions)

    def _on_set_current_instance(
        self, current_instance: str, initialize: bool = False
    ) -> None:
        self.menu_bar.instances_submenu.setTitle(f"Current: {current_instance}")
        self.menu_bar.instances_submenu.setActiveAction(
            next(
                (
                    action
                    for action in self.menu_bar.instances_submenu.actions()
                    if action.text() == current_instance
                )
            )
        )
        if initialize:
            EventBus().do_activate_current_instance.emit(current_instance)

    @Slot()
    def _on_menu_bar_check_for_updates_on_startup_triggered(self) -> None:
        is_checked = self.menu_bar.check_for_updates_on_startup_action.isChecked()
        self.settings_controller.settings.check_for_update_startup = is_checked
        self.settings_controller.settings.save()

    @Slot()
    def _on_menu_bar_cut_triggered(self) -> None:
        app_instance = QApplication.instance()
        if isinstance(app_instance, QApplication):
            focused_widget = app_instance.focusWidget()
            if isinstance(focused_widget, (QLineEdit, QTextEdit, QPlainTextEdit)):
                focused_widget.cut()

    @Slot()
    def _on_menu_bar_copy_triggered(self) -> None:
        app_instance = QApplication.instance()
        if isinstance(app_instance, QApplication):
            focused_widget = app_instance.focusWidget()
            if isinstance(focused_widget, (QLineEdit, QTextEdit, QPlainTextEdit)):
                focused_widget.copy()

    @Slot()
    def _on_menu_bar_paste_triggered(self) -> None:
        app_instance = QApplication.instance()
        if isinstance(app_instance, QApplication):
            focused_widget = app_instance.focusWidget()
            if isinstance(focused_widget, (QLineEdit, QTextEdit, QPlainTextEdit)):
                focused_widget.paste()

    @Slot()
    def _on_menu_bar_wiki_triggered(self) -> None:
        open_url_browser("https://github.com/RimSort/RimSort/wiki")

    @Slot()
    def _on_refresh_started(self) -> None:
        """
        Disable all menus in the menu bar.
        """
        for action in self.menu_bar.menu_bar.actions():
            action.setEnabled(False)

    @Slot()
    def _on_refresh_finished(self) -> None:
        """
        Enable all menus in the menu bar.
        """
        for action in self.menu_bar.menu_bar.actions():
            action.setEnabled(True)

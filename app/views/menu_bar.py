from PySide6.QtCore import QObject
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QMenuBar, QMenu

from app.utils.system_info import SystemInfo


class MenuBar(QObject):
    def __init__(self, menu_bar: QMenuBar) -> None:
        super().__init__()

        self.menu_bar = menu_bar

        # Menu bars are different on macOS
        if SystemInfo().operating_system == SystemInfo.OperatingSystem.MACOS:
            self._do_menu_bar_macos()
        else:
            self._do_menu_bar_non_macos()

    def _do_menu_bar_macos(self) -> None:
        # Application menu (macOS only)
        self.app_menu = self.menu_bar.addMenu(
            "AppName"
        )  # This title is ignored on macOS
        self.check_for_updates_action = QAction("Check for Updates…", self)
        self.check_for_updates_action.setMenuRole(
            QAction.MenuRole.ApplicationSpecificRole
        )
        self.app_menu.addAction(self.check_for_updates_action)
        self.check_for_updates_on_startup_action = QAction(
            "Check for Updates on Startup", self
        )
        self.check_for_updates_on_startup_action.setCheckable(True)
        self.check_for_updates_on_startup_action.setMenuRole(
            QAction.MenuRole.ApplicationSpecificRole
        )
        self.app_menu.addAction(self.check_for_updates_on_startup_action)
        separator = QAction(self)
        separator.setSeparator(True)
        separator.setMenuRole(QAction.MenuRole.ApplicationSpecificRole)
        self.app_menu.addAction(separator)
        self.settings_action = QAction("Settings…", self)
        self.settings_action.setMenuRole(QAction.MenuRole.ApplicationSpecificRole)
        self.settings_action.setShortcut(QKeySequence("Ctrl+,"))
        self.app_menu.addAction(self.settings_action)
        self.app_menu.addSeparator()
        self.quit_action = QAction("Quit", self)
        self.app_menu.addAction(self.quit_action)
        # File menu
        self.file_menu = self.menu_bar.addMenu("File")
        self.open_mod_list_action = QAction("Open Mod List…", self)
        self.open_mod_list_action.setShortcut(QKeySequence("Ctrl+O"))
        self.file_menu.addAction(self.open_mod_list_action)
        self.file_menu.addSeparator()
        self.save_mod_list_action = QAction("Save Mod List As…", self)
        self.save_mod_list_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
        self.file_menu.addAction(self.save_mod_list_action)
        self.file_menu.addSeparator()
        self.import_submenu = QMenu("Import")
        self.file_menu.addMenu(self.import_submenu)
        self.import_from_rentry_action = QAction("From Rentry.co", self)
        self.import_submenu.addAction(self.import_from_rentry_action)
        self.import_from_workshop_collection_action = QAction(
            "From Workshop collection", self
        )
        self.import_submenu.addAction(self.import_from_workshop_collection_action)
        self.file_menu.addSeparator()
        self.export_submenu = QMenu("Export")
        self.file_menu.addMenu(self.export_submenu)
        self.export_to_clipboard_action = QAction("To Clipboard…", self)
        self.export_submenu.addAction(self.export_to_clipboard_action)
        self.export_to_rentry_action = QAction("To Rentry.co…", self)
        self.export_submenu.addAction(self.export_to_rentry_action)
        self.file_menu.addSeparator()
        self.upload_submenu = QMenu("Upload Log")
        self.file_menu.addMenu(self.upload_submenu)
        self.upload_rimsort_log_action = QAction("RimSort.log", self)
        self.upload_submenu.addAction(self.upload_rimsort_log_action)
        self.upload_rimsort_old_log_action = QAction("RimSort.old.log", self)
        self.upload_submenu.addAction(self.upload_rimsort_old_log_action)
        self.upload_rimworld_log_action = QAction("RimWorld.log", self)
        self.upload_submenu.addAction(self.upload_rimworld_log_action)
        # Edit menu
        self.edit_menu = self.menu_bar.addMenu("Edit")
        self.cut_action = QAction("Cut", self)
        self.cut_action.setShortcut(QKeySequence("Ctrl+X"))
        self.edit_menu.addAction(self.cut_action)
        self.copy_action = QAction("Copy", self)
        self.copy_action.setShortcut(QKeySequence("Ctrl+C"))
        self.edit_menu.addAction(self.copy_action)
        self.paste_action = QAction("Paste", self)
        self.paste_action.setShortcut(QKeySequence("Ctrl+V"))
        self.edit_menu.addAction(self.paste_action)
        self.edit_menu.addSeparator()
        self.rule_editor_action = QAction("Rule Editor…", self)
        self.edit_menu.addAction(self.rule_editor_action)
        # Download menu
        self.download_menu = self.menu_bar.addMenu("Download")
        self.add_git_mod_action = QAction("Add Git Mod", self)
        self.download_menu.addAction(self.add_git_mod_action)
        self.download_menu.addSeparator()
        self.browse_workshop_action = QAction("Browse Workshop", self)
        self.download_menu.addAction(self.browse_workshop_action)
        self.update_workshop_mods_action = QAction("Update Workshop Mods", self)
        self.download_menu.addAction(self.update_workshop_mods_action)
        # Textures menu
        self.texture_menu = self.menu_bar.addMenu("Textures")
        self.optimize_textures_action = QAction("Optimize Textures", self)
        self.texture_menu.addAction(self.optimize_textures_action)
        self.texture_menu.addSeparator()
        self.delete_dds_textures_action = QAction("Delete .dds Textures", self)
        self.texture_menu.addAction(self.delete_dds_textures_action)
        # Help menu
        self.help_menu = self.menu_bar.addMenu("Help")
        self.wiki_action = QAction(f"RimSort Wiki…", self)
        self.help_menu.addAction(self.wiki_action)
        self.help_menu.addSeparator()
        self.validate_steam_client_action = QAction("Validate Steam Client mods", self)
        self.help_menu.addAction(self.validate_steam_client_action)

    def _do_menu_bar_non_macos(self) -> None:
        # File menu
        self.file_menu = self.menu_bar.addMenu("File")
        self.open_mod_list_action = QAction("Open Mod List…", self)
        self.open_mod_list_action.setShortcut(QKeySequence("Ctrl+O"))
        self.file_menu.addAction(self.open_mod_list_action)
        self.file_menu.addSeparator()
        self.save_mod_list_action = QAction("Save Mod List As…", self)
        self.save_mod_list_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
        self.file_menu.addAction(self.save_mod_list_action)
        self.file_menu.addSeparator()
        self.import_submenu = QMenu("Import")
        self.file_menu.addMenu(self.import_submenu)
        self.import_from_rentry_action = QAction("From Rentry.co", self)
        self.import_submenu.addAction(self.import_from_rentry_action)
        self.import_from_workshop_collection_action = QAction(
            "From Workshop collection", self
        )
        self.import_submenu.addAction(self.import_from_workshop_collection_action)
        self.file_menu.addSeparator()
        self.export_submenu = QMenu("Export")
        self.file_menu.addMenu(self.export_submenu)
        self.export_to_clipboard_action = QAction("To Clipboard…", self)
        self.export_submenu.addAction(self.export_to_clipboard_action)
        self.export_to_rentry_action = QAction("To Rentry.co…", self)
        self.export_submenu.addAction(self.export_to_rentry_action)
        self.file_menu.addSeparator()
        self.upload_submenu = QMenu("Upload Log")
        self.file_menu.addMenu(self.upload_submenu)
        self.upload_rimsort_log_action = QAction("RimSort.log", self)
        self.upload_submenu.addAction(self.upload_rimsort_log_action)
        self.upload_rimsort_old_log_action = QAction("RimSort.old.log", self)
        self.upload_submenu.addAction(self.upload_rimsort_old_log_action)
        self.upload_rimworld_log_action = QAction("RimWorld Player.log", self)
        self.upload_submenu.addAction(self.upload_rimworld_log_action)
        self.file_menu.addSeparator()
        self.settings_action = QAction("Settings…", self)
        self.settings_action.setShortcut(QKeySequence("Ctrl+,"))
        self.file_menu.addAction(self.settings_action)
        self.file_menu.addSeparator()
        self.quit_action = QAction("Exit", self)
        self.quit_action.setShortcut(QKeySequence("Ctrl+Q"))
        self.file_menu.addAction(self.quit_action)
        # Edit menu
        self.edit_menu = self.menu_bar.addMenu("Edit")
        self.cut_action = QAction("Cut", self)
        self.cut_action.setShortcut(QKeySequence("Ctrl+X"))
        self.edit_menu.addAction(self.cut_action)
        self.copy_action = QAction("Copy", self)
        self.copy_action.setShortcut(QKeySequence("Ctrl+C"))
        self.edit_menu.addAction(self.copy_action)
        self.paste_action = QAction("Paste", self)
        self.paste_action.setShortcut(QKeySequence("Ctrl+V"))
        self.edit_menu.addAction(self.paste_action)
        self.edit_menu.addSeparator()
        self.rule_editor_action = QAction("Rule Editor…", self)
        self.edit_menu.addAction(self.rule_editor_action)
        # Download menu
        self.file_menu = self.menu_bar.addMenu("Download")
        self.add_git_mod_action = QAction("Add Git Mod", self)
        self.file_menu.addAction(self.add_git_mod_action)
        self.file_menu.addSeparator()
        self.browse_workshop_action = QAction("Browse Workshop", self)
        self.file_menu.addAction(self.browse_workshop_action)
        self.update_workshop_mods_action = QAction("Update Workshop Mods", self)
        self.file_menu.addAction(self.update_workshop_mods_action)
        # Textures menu
        self.file_menu = self.menu_bar.addMenu("Textures")
        self.optimize_textures_action = QAction("Optimize Textures", self)
        self.file_menu.addAction(self.optimize_textures_action)
        self.file_menu.addSeparator()
        self.delete_dds_textures_action = QAction("Delete .dds Textures", self)
        self.file_menu.addAction(self.delete_dds_textures_action)
        # Help menu
        self.help_menu = self.menu_bar.addMenu("Help")
        self.wiki_action = QAction(f"RimSort Wiki…", self)
        self.help_menu.addAction(self.wiki_action)
        self.help_menu.addSeparator()
        self.check_for_updates_action = QAction("Check for Updates…", self)
        self.help_menu.addAction(self.check_for_updates_action)
        self.check_for_updates_on_startup_action = QAction(
            "Check for Updates on Startup", self
        )
        self.check_for_updates_on_startup_action.setCheckable(True)
        self.help_menu.addAction(self.check_for_updates_on_startup_action)
        self.help_menu.addSeparator()
        self.validate_steam_client_action = QAction("Validate Steam Client mods", self)
        self.help_menu.addAction(self.validate_steam_client_action)

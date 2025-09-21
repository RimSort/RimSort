from functools import partial
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QMenu, QMenuBar

from app.controllers.settings_controller import SettingsController
from app.utils.app_info import AppInfo
from app.utils.system_info import SystemInfo


class MenuBar(QObject):
    def __init__(
        self, menu_bar: QMenuBar, settings_controller: SettingsController
    ) -> None:
        """
        Initialize the MenuBar object.

        Args:
            menu_bar (QMenuBar): The menu bar to which the menus and actions will be added.
        """
        super().__init__()

        self.menu_bar: QMenuBar = menu_bar
        self.settings_controller: SettingsController = settings_controller

        # Declare actions and submenus as class variables
        # to be used by menu_bar_controller
        self.settings_action: QAction
        self.quit_action: QAction
        self.open_mod_list_action: QAction
        self.save_mod_list_action: QAction
        self.import_from_rentry_action: QAction
        self.import_from_workshop_collection_action: QAction
        self.import_from_save_file_action: QAction
        self.export_to_clipboard_action: QAction
        self.export_to_rentry_action: QAction
        self.upload_log_actions: list[QAction] = []
        self.default_open_log_actions: list[QAction] = []
        self.upload_rimsort_log_action: QAction
        self.upload_rimsort_old_log_action: QAction
        self.upload_rimworld_log_action: QAction
        self.open_app_directory_action: QAction
        self.open_settings_directory_action: QAction
        self.open_rimsort_logs_directory_action: QAction
        self.open_rimworld_directory_action: QAction
        self.open_rimworld_config_directory_action: QAction
        self.open_rimworld_logs_directory_action: QAction
        self.open_local_mods_directory_action: QAction
        self.open_steam_mods_directory_action: QAction
        self.cut_action: QAction
        self.copy_action: QAction
        self.paste_action: QAction
        self.rule_editor_action: QAction
        self.reset_all_warnings_action: QAction
        self.reset_all_mod_colors_action: QAction
        self.add_git_mod_action: QAction
        self.add_zip_mod_action: QAction
        self.browse_workshop_action: QAction
        self.update_workshop_mods_action: QAction
        self.backup_instance_action: QAction
        self.restore_instance_action: QAction
        self.clone_instance_action: QAction
        self.create_instance_action: QAction
        self.delete_instance_action: QAction
        self.optimize_textures_action: QAction
        self.delete_dds_textures_action: QAction
        self.wiki_action: QAction
        self.github_action: QAction
        self.check_for_updates_action: QAction
        self.check_for_updates_on_startup_action: QAction

        self.import_submenu: QMenu
        self.export_submenu: QMenu
        self.upload_submenu: QMenu
        self.default_open_logs_submenu: QMenu
        self.shortcuts_submenu: QMenu
        self.instances_submenu: QMenu

        self._create_menu_bar()

    def _add_action(
        self,
        menu: QMenu,
        title: str,
        shortcut: str | None = None,
        checkable: bool = False,
        role: QAction.MenuRole | None = None,
    ) -> QAction:
        """
        Add an action to a menu.

        Args:
            menu (QMenu): The menu to which the action will be added.
            title (str): The title of the action.
            shortcut (str | None = None): The keyboard shortcut for the action.
            checkable (bool = False): Whether the action is checkable.
            role (QAction.MenuRole | None, optional): The menu role of the action. Defaults to None.
        Returns:
            QAction: The created action.
        """
        action = QAction(title, self)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        if checkable:
            action.setCheckable(True)
        if role:
            action.setMenuRole(role)
        menu.addAction(action)
        return action

    def _create_file_menu(self) -> QMenu:
        """
        Create the "File" menu and add its actions and submenus.

        Returns:
            QMenu: The created "File" menu.
        """
        file_menu = self.menu_bar.addMenu(self.tr("File"))
        self.open_mod_list_action = self._add_action(
            file_menu, self.tr("Open Mod List…"), "Ctrl+O"
        )
        file_menu.addSeparator()
        self.save_mod_list_action = self._add_action(
            file_menu, self.tr("Save Mod List As…"), "Ctrl+Shift+S"
        )
        file_menu.addSeparator()
        self.import_submenu = QMenu(self.tr("Import"))
        file_menu.addMenu(self.import_submenu)
        self.import_from_rentry_action = self._add_action(
            self.import_submenu, self.tr("From Rentry.co")
        )
        self.import_from_workshop_collection_action = self._add_action(
            self.import_submenu, self.tr("From Workshop collection")
        )
        self.import_from_save_file_action = self._add_action(
            self.import_submenu, self.tr("From Save file…")
        )
        self.export_submenu = QMenu(self.tr("Export"))
        file_menu.addMenu(self.export_submenu)
        self.export_to_clipboard_action = self._add_action(
            self.export_submenu, self.tr("To Clipboard…")
        )
        self.export_to_rentry_action = self._add_action(
            self.export_submenu, self.tr("To Rentry.co…")
        )
        file_menu.addSeparator()

        self.upload_submenu = self._create_logfile_submenu(
            "Upload Log", self.upload_log_actions
        )
        file_menu.addMenu(self.upload_submenu)

        if self.settings_controller.settings.text_editor_location:
            file_menu.addSeparator()

            self.default_open_logs_submenu = self._create_logfile_submenu(
                "Open Log in Default Editor", self.default_open_log_actions
            )
            file_menu.addMenu(self.default_open_logs_submenu)
        file_menu.addSeparator()
        self.shortcuts_submenu = QMenu(self.tr("Open..."))
        file_menu.addMenu(self.shortcuts_submenu)
        # Add submenu under Shortcuts
        self.rimsort_shortcuts_submenu = QMenu(self.tr("RimSort"))
        self.shortcuts_submenu.addMenu(self.rimsort_shortcuts_submenu)
        self.rimworld_shortcuts_submenu = QMenu(self.tr("RimWorld"))
        self.shortcuts_submenu.addMenu(self.rimworld_shortcuts_submenu)
        # Add actions to RimSort submenu
        self.open_app_directory_action = self._add_action(
            self.rimsort_shortcuts_submenu, self.tr("Root Directory")
        )
        self.open_settings_directory_action = self._add_action(
            self.rimsort_shortcuts_submenu, self.tr("Config Directory")
        )
        self.open_rimsort_logs_directory_action = self._add_action(
            self.rimsort_shortcuts_submenu, self.tr("Logs Directory")
        )
        # Add action to RimWorld submenu
        self.open_rimworld_directory_action = self._add_action(
            self.rimworld_shortcuts_submenu, self.tr("Root Directory")
        )
        self.open_rimworld_config_directory_action = self._add_action(
            self.rimworld_shortcuts_submenu, self.tr("Config Directory")
        )
        self.open_rimworld_logs_directory_action = self._add_action(
            self.rimworld_shortcuts_submenu, self.tr("Logs Directory")
        )
        self.open_local_mods_directory_action = self._add_action(
            self.rimworld_shortcuts_submenu, self.tr("Local Mods Directory")
        )
        self.open_steam_mods_directory_action = self._add_action(
            self.rimworld_shortcuts_submenu, self.tr("Steam Mods Directory")
        )

        if SystemInfo().operating_system != SystemInfo.OperatingSystem.MACOS:
            file_menu.addSeparator()
            self.settings_action = self._add_action(
                file_menu, self.tr("Settings…"), "Ctrl+,"
            )
            file_menu.addSeparator()
            self.quit_action = self._add_action(file_menu, self.tr("Exit"), "Ctrl+Q")
        return file_menu

    def _create_logfile_submenu(
        self,
        menu_name: str,
        action_list: list[QAction],
    ) -> QMenu:
        def create_entry(
            name: str, path_accessor: Callable[[], Path | None]
        ) -> QAction:
            action = self._add_action(logfile_submenu, name)
            action.setData(path_accessor)
            action_list.append(action)
            return action

        def rimworld_log_path(suffix: str) -> Path | None:
            config_str = self.settings_controller.settings.instances[
                self.settings_controller.settings.current_instance
            ].config_folder
            if config_str:
                return Path(config_str).parent / suffix
            return None

        logfile_submenu = QMenu(self.tr(menu_name))
        create_entry("RimSort.log", lambda: AppInfo().user_log_folder / "RimSort.log")
        create_entry(
            "RimSort.old.log", lambda: AppInfo().user_log_folder / "RimSort.old.log"
        )
        create_entry(
            "RimWorld Player.log",
            partial(rimworld_log_path, "Player.log"),
        )
        create_entry(
            "RimWorld Player-prev.log",
            partial(rimworld_log_path, "Player-prev.log"),
        )

        return logfile_submenu

    def _create_edit_menu(self) -> QMenu:
        """
        Create the "Edit" menu and add its actions.

        Returns:
            QMenu: The created "Edit" menu.
        """
        edit_menu = self.menu_bar.addMenu(self.tr("Edit"))
        self.cut_action = self._add_action(edit_menu, self.tr("Cut"), "Ctrl+X")
        self.copy_action = self._add_action(edit_menu, self.tr("Copy"), "Ctrl+C")
        self.paste_action = self._add_action(edit_menu, self.tr("Paste"), "Ctrl+V")
        edit_menu.addSeparator()
        self.rule_editor_action = self._add_action(edit_menu, self.tr("Rule Editor…"))
        self.reset_all_warnings_action = self._add_action(
            edit_menu, self.tr("Reset Warning Toggles")
        )
        self.reset_all_mod_colors_action = self._add_action(
            edit_menu, self.tr("Reset Mod Colors")
        )
        return edit_menu

    def _create_download_menu(self) -> QMenu:
        """
        Create the "Download" menu and add its actions.

        Returns:
            QMenu: The created "Download" menu.
        """
        download_menu = self.menu_bar.addMenu(self.tr("Download"))
        self.add_git_mod_action = self._add_action(
            download_menu, self.tr("Add Git Mod")
        )
        self.add_zip_mod_action = self._add_action(
            download_menu, self.tr("Add Zip Mod")
        )
        download_menu.addSeparator()
        self.browse_workshop_action = self._add_action(
            download_menu, self.tr("Browse Workshop")
        )
        self.update_workshop_mods_action = self._add_action(
            download_menu, self.tr("Update Workshop Mods")
        )
        return download_menu

    def _create_instances_menu(self) -> QMenu:
        """
        Create the "Instances" menu and add its actions and submenus.

        Returns:
            QMenu: The created "Instances" menu.
        """
        instances_menu = self.menu_bar.addMenu(self.tr("Instances"))
        self.instances_submenu = QMenu(self.tr('Current: "Default"'))
        instances_menu.addMenu(self.instances_submenu)
        instances_menu.addSeparator()
        self.backup_instance_action = self._add_action(
            instances_menu, self.tr("Backup Instance…")
        )
        self.restore_instance_action = self._add_action(
            instances_menu, self.tr("Restore Instance…")
        )
        instances_menu.addSeparator()
        self.clone_instance_action = self._add_action(
            instances_menu, self.tr("Clone Instance…")
        )
        self.create_instance_action = self._add_action(
            instances_menu, self.tr("Create Instance…")
        )
        self.delete_instance_action = self._add_action(
            instances_menu, self.tr("Delete Instance…")
        )
        return instances_menu

    def _create_texture_menu(self) -> QMenu:
        """
        Create the "Textures" menu and add its actions.

        Returns:
            QMenu: The created "Textures" menu.
        """
        texture_menu = self.menu_bar.addMenu(self.tr("Textures"))
        self.optimize_textures_action = self._add_action(
            texture_menu, self.tr("Optimize Textures")
        )
        texture_menu.addSeparator()
        self.delete_dds_textures_action = self._add_action(
            texture_menu, self.tr("Delete .dds Textures")
        )
        return texture_menu

    def _create_update_menu(self) -> QMenu:
        update_menu = self.menu_bar.addMenu(self.tr("Update"))
        self.check_for_updates_action = self._add_action(
            update_menu, self.tr("Check for Updates…")
        )
        self.check_for_updates_on_startup_action = self._add_action(
            update_menu, self.tr("Check for Updates on Startup"), checkable=True
        )
        update_menu.addSeparator()
        return update_menu

    def _create_help_menu(self) -> QMenu:
        """
        Create the "Help" menu and add its actions.

        Returns:
            QMenu: The created "Help" menu.
        """
        help_menu = self.menu_bar.addMenu(self.tr("Help"))
        self.wiki_action = self._add_action(help_menu, self.tr("RimSort Wiki…"))
        self.github_action = self._add_action(help_menu, self.tr("RimSort GitHub…"))
        help_menu.addSeparator()
        return help_menu

    def _create_menu_bar(self) -> None:
        """
        Create the menu bar. On macOS, include the app menu.
        """
        if SystemInfo().operating_system == SystemInfo.OperatingSystem.MACOS:
            app_menu = self.menu_bar.addMenu("AppName")
            app_menu.addSeparator()
            self.settings_action = self._add_action(
                app_menu,
                "Settings...",
                shortcut="Ctrl+,",
                role=QAction.MenuRole.ApplicationSpecificRole,
            )
            app_menu.addSeparator()
            self.quit_action = self._add_action(app_menu, "Quit")
        self._create_file_menu()
        self._create_edit_menu()
        self._create_download_menu()
        self._create_instances_menu()
        self._create_texture_menu()
        self._create_update_menu()
        self._create_help_menu()

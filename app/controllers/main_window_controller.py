from loguru import logger
from PySide6.QtCore import QObject, Slot
from PySide6.QtWidgets import QPushButton

from app.controllers.metadata_controller import MetadataController
from app.models.divider import is_divider_uuid
from app.services.dependency_resolver import build_dependencies_dialog_context
from app.utils.event_bus import EventBus
from app.views.main_window import MainWindow
from app.windows.missing_dependencies_dialog import MissingDependenciesDialog


class MainWindowController(QObject):
    def __init__(self, view: MainWindow) -> None:
        super().__init__()

        self.main_window = view
        self.metadata_controller = MetadataController.instance()

        # Create a list of buttons
        self.buttons = [
            self.main_window.refresh_button,
            self.main_window.clear_button,
            self.main_window.restore_button,
            self.main_window.sort_button,
            self.main_window.save_button,
            self.main_window.run_button,
        ]

        # Connect signals to slots
        self.connect_signals()

    def connect_signals(self) -> None:
        # Connect buttons to EventBus signals
        for button, signal in zip(
            self.buttons,
            [
                EventBus().do_refresh_mods_lists,
                EventBus().do_clear_active_mods_list,
                EventBus().do_restore_active_mods_list,
                EventBus().do_sort_active_mods_list,
                EventBus().do_save_active_mods_list,
                EventBus().do_run_game,
            ],
        ):
            button.clicked.connect(signal.emit)

        # Connect check dependencies signal from mods panel
        self.main_window.main_content_panel.mods_panel.check_dependencies_signal.connect(
            self.check_dependencies
        )

        # Connect EventBus signals to slots
        EventBus().do_button_animation.connect(self.on_button_animation)
        EventBus().do_save_button_animation_stop.connect(
            self.on_save_button_animation_stop
        )
        EventBus().list_updated_signal.connect(
            self.on_save_button_animation_start
        )  # Save btn animation
        EventBus().refresh_started.connect(self.on_refresh_started)
        EventBus().refresh_finished.connect(self.on_refresh_finished)

    def check_dependencies(self) -> None:
        # Get the active mods list (exclude dividers)
        active_mods = {
            u
            for u in self.main_window.main_content_panel.mods_panel.active_mods_list.paths
            if not is_divider_uuid(u)
        }

        deps_summary, missing_deps, dep_resolve = build_dependencies_dialog_context(
            self.metadata_controller, active_mods
        )

        dialog = MissingDependenciesDialog(
            metadata_controller=self.metadata_controller, parent=self.main_window
        )
        dialog.download_requested.connect(
            self.main_window.main_content_panel._download_single_workshop_mod
        )
        dialog.download_selected_requested.connect(
            self.main_window.main_content_panel._download_selected_workshop_mods
        )
        selected_deps = dialog.show_dialog(deps_summary, missing_deps, dep_resolve)

        if not missing_deps:
            # No missing deps at all - user was shown an informational dialog
            logger.info("No missing dependencies found.")
            return

        if selected_deps:
            # Create lists to track local mods and mods that need to be downloaded
            local_mods = []
            mods_to_download = []

            # Check each selected dependency
            for dep_id in selected_deps:
                paths = self.metadata_controller.packageid_to_paths.get(dep_id.lower())
                if paths:
                    local_mods.append(dep_id)
                    continue

                resolved = dep_resolve.get(dep_id)
                if resolved is not None and resolved.workshop_id:
                    mods_to_download.append(resolved.workshop_id)

            # First add any local mods to the active list
            if local_mods:
                for mod_id in local_mods:
                    # Find the path for this package ID
                    paths = self.metadata_controller.packageid_to_paths.get(
                        mod_id.lower()
                    )
                    if paths:
                        active_mods.add(next(iter(paths)))

                # Update the active mods list with local mods
                self.main_window.main_content_panel.mods_panel.active_mods_list.paths = list(
                    active_mods
                )

            # If there are mods to download, check SteamCMD setup first
            if mods_to_download:
                # Check if SteamCMD is set up
                steamcmd_wrapper = self.main_window.main_content_panel.steamcmd_wrapper

                if not steamcmd_wrapper.setup:
                    # Set up SteamCMD first
                    self.main_window.main_content_panel._do_setup_steamcmd()
                    # After setup, try downloading again if setup was successful
                    if steamcmd_wrapper.setup:
                        self.main_window.main_content_panel._do_download_mods_with_steamcmd(
                            mods_to_download
                        )
                        # Don't sort yet - let the download completion handler do it
                        return
                    else:
                        # Sort what we have so far
                        self.main_window.main_content_panel._do_sort(check_deps=False)
                else:
                    # SteamCMD is already set up, proceed with download
                    self.main_window.main_content_panel._do_download_mods_with_steamcmd(
                        mods_to_download
                    )
                    # Don't sort yet - let the download completion handler do it
                    return
            else:
                # Only local mods were selected, sort them now
                self.main_window.main_content_panel._do_sort(check_deps=False)
        else:
            # User clicked "Sort Without Adding", sort without checking dependencies again
            self.main_window.main_content_panel._do_sort(check_deps=False)

    # @Slot() # TODO: fix @slot() related MYPY errors once bug is fixed in https://bugreports.qt.io/browse/PYSIDE-2942
    def on_button_animation(self, button: QPushButton) -> None:
        button.setObjectName(
            "%s" % ("" if button.objectName() == "indicator" else "indicator")
        )
        button.style().unpolish(button)
        button.style().polish(button)

    @Slot()
    def on_refresh_started(self) -> None:
        self.set_buttons_enabled(False)

    @Slot()
    def on_refresh_finished(self) -> None:
        self.set_buttons_enabled(True)
        self.main_window.game_version_label.setText(
            "RimWorld version " + self.metadata_controller.game_version
        )

    @Slot()
    def on_save_button_animation_start(self) -> None:
        logger.debug(
            "Active mods list has been updated. Managing save button animation state."
        )
        current_mod_uuids = [
            u
            for u in self.main_window.main_content_panel.mods_panel.active_mods_list.paths
            if not is_divider_uuid(u)
        ]
        if (
            current_mod_uuids
            != self.main_window.main_content_panel.active_mods_uuids_last_save
        ):
            if not self.main_window.save_button_flashing_animation.isActive():
                logger.debug("Starting save button animation")
                self.main_window.save_button_flashing_animation.start(
                    500
                )  # Blink every 500 milliseconds
        else:
            self.on_save_button_animation_stop()

    @Slot()
    def on_save_button_animation_stop(self) -> None:
        # Stop the save button from blinking if it is blinking
        if self.main_window.save_button_flashing_animation.isActive():
            self.main_window.save_button_flashing_animation.stop()
            self.main_window.save_button.setObjectName("")
            self.main_window.save_button.style().unpolish(self.main_window.save_button)
            self.main_window.save_button.style().polish(self.main_window.save_button)

    def set_buttons_enabled(self, enabled: bool) -> None:
        for btn in self.buttons:
            btn.setEnabled(enabled)

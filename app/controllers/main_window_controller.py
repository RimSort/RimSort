import os

from loguru import logger
from PySide6.QtCore import QObject, Slot
from PySide6.QtWidgets import QPushButton

from app.utils.event_bus import EventBus
from app.utils.metadata import MetadataManager
from app.views.main_window import MainWindow
from app.windows.missing_dependencies_dialog import MissingDependenciesDialog


class MainWindowController(QObject):
    def __init__(self, view: MainWindow) -> None:
        super().__init__()

        self.main_window = view
        self.metadata_manager = MetadataManager.instance()

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
        EventBus().reset_use_this_instead_cache.connect(
            self.on_reset_use_this_instead_cache
        )

    def check_dependencies(self) -> None:
        # Get the active mods list
        active_mods = set(
            self.main_window.main_content_panel.mods_panel.active_mods_list.uuids
        )

        # Create a dictionary to store missing dependencies
        missing_deps: dict[str, set[str]] = {}

        # Check each active mod's dependencies
        for uuid in active_mods:
            mod_data = self.metadata_manager.internal_local_metadata[uuid]
            mod_id = mod_data.get("packageid", "")
            if not mod_id:
                continue

            # Get the mod's dependencies
            dependencies = mod_data.get("dependencies", [])
            if not dependencies:
                continue

            # Check each dependency
            missing = set()
            for dep in dependencies:
                # Check if the dependency is in the active mods list
                found = False
                for active_uuid in active_mods:
                    active_mod_data = self.metadata_manager.internal_local_metadata[
                        active_uuid
                    ]
                    if active_mod_data.get("packageid") == dep:
                        found = True
                        break
                if not found:
                    missing.add(dep)

            if missing:
                missing_deps[mod_id] = missing

        if missing_deps:
            # Show the missing dependencies dialog
            dialog = MissingDependenciesDialog(self.main_window)
            selected_deps = dialog.show_dialog(missing_deps)

            if selected_deps:
                # Create lists to track local mods and mods that need to be downloaded
                local_mods = []
                mods_to_download = []

                # Check each selected dependency
                for dep_id in selected_deps:
                    # First check if it exists locally
                    found_locally = False
                    for (
                        mod_data
                    ) in self.metadata_manager.internal_local_metadata.values():
                        if mod_data.get("packageid") == dep_id:
                            local_mods.append(dep_id)
                            found_locally = True
                            break

                    if not found_locally:
                        # If not found locally, we need to find its Workshop ID
                        # First check if we have it in our Steam metadata
                        workshop_id = None
                        if self.metadata_manager.external_steam_metadata:
                            for (
                                pfid,
                                metadata,
                            ) in self.metadata_manager.external_steam_metadata.items():
                                if (
                                    metadata.get("packageId", "").lower()
                                    == dep_id.lower()
                                ):
                                    workshop_id = pfid
                                    break

                        if workshop_id:
                            mods_to_download.append(workshop_id)
                        else:
                            # If not in Steam metadata, try to find it in the mod's About.xml
                            # search through all active mods' About.xml files
                            for active_uuid in active_mods:
                                active_mod_data = (
                                    self.metadata_manager.internal_local_metadata[
                                        active_uuid
                                    ]
                                )
                                mod_path = active_mod_data.get("path")
                                if not mod_path:
                                    continue

                                about_path = os.path.join(
                                    mod_path, "About", "About.xml"
                                )
                                if os.path.exists(about_path):
                                    try:
                                        import xml.etree.ElementTree as ET

                                        tree = ET.parse(about_path)
                                        root = tree.getroot()

                                        # Look for modDependencies
                                        deps = root.find("modDependencies")
                                        if deps is None:
                                            continue

                                        for dep in deps.findall("li"):
                                            package_id = dep.find("packageId")
                                            if package_id is not None:
                                                if (
                                                    package_id is not None
                                                    and package_id.text is not None
                                                    and package_id.text.lower()
                                                    == dep_id.lower()
                                                ):
                                                    workshop_url = dep.find(
                                                        "steamWorkshopUrl"
                                                    )
                                                    if (
                                                        workshop_url is not None
                                                        and workshop_url.text
                                                        is not None
                                                    ):
                                                        url = workshop_url.text
                                                        # Extract workshop ID from URL
                                                        if "?id=" in url:
                                                            workshop_id = url.split(
                                                                "?id="
                                                            )[1]
                                                        elif (
                                                            "CommunityFilePage/" in url
                                                        ):
                                                            workshop_id = url.split(
                                                                "CommunityFilePage/"
                                                            )[1]

                                                        if workshop_id:
                                                            # Clean up workshop ID
                                                            if "?" in workshop_id:
                                                                workshop_id = (
                                                                    workshop_id.split(
                                                                        "?"
                                                                    )[0]
                                                                )
                                                            if "/" in workshop_id:
                                                                workshop_id = (
                                                                    workshop_id.split(
                                                                        "/"
                                                                    )[0]
                                                                )
                                                            mods_to_download.append(
                                                                workshop_id
                                                            )
                                                            break
                                        if workshop_id:
                                            break  # Found the workshop ID, no need to check other mods
                                    except Exception:
                                        continue

                # First add any local mods to the active list
                if local_mods:
                    for mod_id in local_mods:
                        # Find the UUID for this package ID
                        for (
                            uuid,
                            mod_data,
                        ) in self.metadata_manager.internal_local_metadata.items():
                            if mod_data.get("packageid") == mod_id:
                                active_mods.add(uuid)
                                break

                    # Update the active mods list with local mods
                    self.main_window.main_content_panel.mods_panel.active_mods_list.uuids = list(
                        active_mods
                    )
                    # Trigger list updated signal to refresh UI
                    self.main_window.main_content_panel.mods_panel.list_updated_signal.emit()

                # If there are mods to download, check SteamCMD setup first
                if mods_to_download:
                    # Check if SteamCMD is set up
                    steamcmd_wrapper = (
                        self.main_window.main_content_panel.steamcmd_wrapper
                    )

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
                            self.main_window.main_content_panel._do_sort(
                                check_deps=False
                            )
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
        else:
            # No missing dependencies, sort without checking dependencies again
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
            "RimWorld version " + MetadataManager.instance().game_version
        )

    @Slot()
    def on_save_button_animation_start(self) -> None:
        logger.debug(
            "Active mods list has been updated. Managing save button animation state."
        )
        if (
            # Compare current active list with last save to see if the list has changed
            self.main_window.main_content_panel.mods_panel.active_mods_list.uuids
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

    @Slot()
    def on_reset_use_this_instead_cache(self) -> None:
        logger.warning(
            'Resetting "Use This Instead" cache - performance may be impacted until xml is re-cached'
        )
        MetadataManager.instance().has_alternative_mod.cache_clear()

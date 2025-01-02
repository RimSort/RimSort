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
            self.main_window.check_deps_button,
            self.main_window.sort_button,
            self.main_window.save_button,
            self.main_window.run_button,
        ]

        # Connect signals to slots
        self.connect_signals()

    def connect_signals(self) -> None:
        # Connect buttons to EventBus signals
        for button, signal in zip(
            [b for b in self.buttons if b != self.main_window.check_deps_button],
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

        # Connect check dependencies button
        self.main_window.check_deps_button.clicked.connect(self.check_dependencies)

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
        """Check for missing dependencies and show dialog if needed"""
        # Get active mods from the mods panel
        active_mods = set(
            self.main_window.main_content_panel.mods_panel.active_mods_list.uuids
        )

        # Check for missing dependencies
        missing_deps = self.metadata_manager.get_missing_dependencies(active_mods)

        # Show dialog if there are missing dependencies
        if missing_deps:
            dialog = MissingDependenciesDialog(self.main_window)
            dialog.show_missing_dependencies(missing_deps)

            result = dialog.exec()
            if result:  # Dialog accepted
                # User clicked "Add Selected & Sort"
                selected_mods = dialog.get_selected_mods()
                if selected_mods:
                    print("\nselected mods to add:")
                    # Track which mods need to be downloaded
                    mods_to_download = []
                    # Track which mods are local
                    local_mods = []

                    for mod_id in selected_mods:
                        mod_name = self.metadata_manager.get_mod_name_from_package_id(
                            mod_id
                        )

                        # Check if mod exists locally
                        exists_locally = False
                        for (
                            mod_data
                        ) in self.metadata_manager.internal_local_metadata.values():
                            if mod_data.get("packageid") == mod_id:
                                exists_locally = True
                                break

                        if exists_locally:
                            print(f"- {mod_name} (id: {mod_id}) [local]")
                            local_mods.append(mod_id)
                        else:
                            print(f"- {mod_name} (id: {mod_id}) [needs download]")
                            # Get the list of mods that list this as a dependency
                            requiring_mods = []
                            # Look in active mods first
                            for (
                                uuid,
                                mod_data,
                            ) in self.metadata_manager.internal_local_metadata.items():
                                if uuid in active_mods:
                                    requiring_mods.append(mod_data["path"])
                            print(
                                f"checking {len(requiring_mods)} active mods for {mod_id}"
                            )

                            # Try each mod's About.xml until we find the workshop ID
                            workshop_id = None
                            for mod_path in requiring_mods:
                                about_path = os.path.join(
                                    mod_path, "About", "About.xml"
                                )
                                print(f"checking About.xml at: {about_path}")
                                if os.path.exists(about_path):
                                    try:
                                        import xml.etree.ElementTree as ET

                                        tree = ET.parse(about_path)
                                        root = tree.getroot()
                                        deps = root.find("modDependencies")
                                        if deps is not None:
                                            print(
                                                f"found modDependencies in {about_path}"
                                            )
                                            for dep in deps.findall("li"):
                                                package_id = dep.find("packageId")
                                                if package_id is not None:
                                                    print(
                                                        f"checking dependency: {package_id.text}"
                                                    )
                                                if (
                                                    package_id is not None
                                                    and package_id.text.lower()
                                                    == mod_id.lower()
                                                ):
                                                    print(
                                                        f"found matching dependency: {package_id.text}"
                                                    )
                                                    workshop_url = dep.find(
                                                        "steamWorkshopUrl"
                                                    )
                                                    if workshop_url is not None:
                                                        url = workshop_url.text
                                                        print(
                                                            f"found workshop url: {url}"
                                                        )
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
                                                            print(
                                                                f"found workshop id: {workshop_id}"
                                                            )
                                                            mods_to_download.append(
                                                                workshop_id
                                                            )
                                                            # Update the needs download message with the workshop ID
                                                            print(
                                                                f"- {mod_name} (id: {mod_id}, workshop id: {workshop_id}) [needs download]"
                                                            )
                                                            break
                                            if workshop_id:
                                                break  # Found the workshop ID, no need to check other mods
                                        else:
                                            print(
                                                f"no modDependencies found in {about_path}"
                                            )
                                    except Exception as e:
                                        print(f"warning: error reading About.xml: {e}")
                                        continue
                                else:
                                    print(f"About.xml not found at: {about_path}")

                    print()  # empty line for readability

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
                        print("downloading mods:", mods_to_download)
                        # Check if SteamCMD is set up
                        steamcmd_wrapper = (
                            self.main_window.main_content_panel.steamcmd_wrapper
                        )
                        print("steamcmd wrapper:", steamcmd_wrapper)
                        print("steamcmd setup:", steamcmd_wrapper.setup)

                        if not steamcmd_wrapper.setup:
                            # Set up SteamCMD first
                            print("steamcmd not set up, setting up now...")
                            self.main_window.main_content_panel._do_setup_steamcmd()
                            print(
                                "steamcmd setup complete, setup status:",
                                steamcmd_wrapper.setup,
                            )
                            # After setup, try downloading again if setup was successful
                            if steamcmd_wrapper.setup:
                                print("starting download with steamcmd...")
                                self.main_window.main_content_panel._do_download_mods_with_steamcmd(
                                    mods_to_download
                                )
                                # Don't sort yet - let the download completion handler do it
                                return
                            else:
                                print(
                                    "warning: steamcmd setup failed, cannot download mods"
                                )
                                print(
                                    "please use the Workshop Browser to download mods instead"
                                )
                                # Sort what we have so far
                                self.main_window.main_content_panel._do_sort(
                                    check_deps=False
                                )
                        else:
                            # SteamCMD is already set up, proceed with download
                            print("steamcmd already set up, starting download...")
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

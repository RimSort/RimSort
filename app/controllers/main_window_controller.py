import os
from xml.etree.ElementTree import Element

from loguru import logger
from PySide6.QtCore import QObject, Slot
from PySide6.QtWidgets import QPushButton

from app.controllers.metadata_controller import MetadataController
from app.models.divider import is_divider_uuid
from app.models.metadata.metadata_structure import AboutXmlMod
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

    def _parse_workshop_id(self, url: str) -> str | None:
        """Extract a Steam Workshop ID from a dependency URL."""
        workshop_id: str | None = None
        if "?id=" in url:
            workshop_id = url.split("?id=")[1]
        elif "CommunityFilePage/" in url:
            workshop_id = url.split("CommunityFilePage/")[1]
        else:
            return None
        # Clean up trailing query or path
        if "?" in workshop_id:
            workshop_id = workshop_id.split("?")[0]
        if "/" in workshop_id:
            workshop_id = workshop_id.split("/")[0]
        return workshop_id

    def _find_workshop_id_in_deps(
        self, deps_node: Element, target_pkg_id: str
    ) -> str | None:
        """Search a <modDependencies> or versioned child node for a matching packageId and return its Workshop ID."""
        target = target_pkg_id.lower()
        for dep in deps_node.findall("li"):
            package_id = dep.find("packageId")
            if (
                package_id is not None
                and package_id.text is not None
                and package_id.text.lower() == target
            ):
                workshop_url = dep.find("steamWorkshopUrl")
                if workshop_url is not None and workshop_url.text is not None:
                    return self._parse_workshop_id(workshop_url.text)
        return None

    def check_dependencies(self) -> None:
        # Get the active mods list (exclude dividers)
        active_mods = {
            u
            for u in self.main_window.main_content_panel.mods_panel.active_mods_list.paths
            if not is_divider_uuid(u)
        }

        mods_metadata = self.metadata_controller.mods_metadata

        # Precompute active package IDs for quick lookup
        active_ids: set[str] = set()
        for u in active_mods:
            mod = mods_metadata.get(u)
            if mod and isinstance(mod, AboutXmlMod):
                active_ids.add(str(mod.package_id))

        # Build a full deps summary and missing deps dict
        deps_summary: dict[str, dict[str, set[str]]] = {}
        missing_deps: dict[str, set[str]] = {}

        # Precompute all local package IDs (for "local" classification)
        all_local_package_ids: set[str] = set()
        for mod in mods_metadata.values():
            if isinstance(mod, AboutXmlMod):
                all_local_package_ids.add(str(mod.package_id))

        consider_alternatives = self.metadata_controller.settings.use_alternative_package_ids_as_satisfying_dependencies

        # Check each active mod's dependencies
        for path in active_mods:
            mod = mods_metadata.get(path)
            if not isinstance(mod, AboutXmlMod):
                continue
            mod_id = str(mod.package_id)
            if not mod_id:
                continue

            # Get the mod's dependencies (dict[CaseInsensitiveStr, DependencyMod])
            dependencies = mod.overall_rules.dependencies
            if not dependencies:
                continue

            satisfied: set[str] = set()
            local: set[str] = set()
            download: set[str] = set()

            # Check each dependency, honoring alternativePackageIds
            for dep_id_key, dep_mod in dependencies.items():
                dep_id = str(dep_id_key)
                alt_ids = {str(a) for a in dep_mod.alternative_package_ids}

                # Check if the dependency is satisfied (in active mods)
                is_satisfied = dep_id in active_ids
                if not is_satisfied and consider_alternatives:
                    is_satisfied = any(alt in active_ids for alt in alt_ids)

                if is_satisfied:
                    satisfied.add(dep_id)
                else:
                    # Classify missing deps: local vs download
                    is_local = dep_id in all_local_package_ids or (
                        consider_alternatives
                        and any(alt in all_local_package_ids for alt in alt_ids)
                    )
                    if is_local:
                        local.add(dep_id)
                    else:
                        download.add(dep_id)

            deps_summary[mod_id] = {
                "satisfied": satisfied,
                "local": local,
                "download": download,
            }

            if local or download:
                missing_deps[mod_id] = local | download

        # Always show the dialog (even if no missing deps)
        dialog = MissingDependenciesDialog(
            metadata_controller=self.metadata_controller, parent=self.main_window
        )
        selected_deps = dialog.show_dialog(deps_summary, missing_deps)

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
                # First check if it exists locally via packageid_to_paths
                paths = self.metadata_controller.packageid_to_paths.get(dep_id.lower())
                if paths:
                    local_mods.append(dep_id)
                    continue

                # If not found locally, we need to find its Workshop ID
                # First check if we have it in our Steam metadata
                workshop_id = None
                steam_db = self.metadata_controller.steam_db
                if steam_db is not None:
                    for pfid, entry in steam_db.database.items():
                        if entry.packageId.lower() == dep_id.lower():
                            workshop_id = pfid
                            break

                if workshop_id:
                    mods_to_download.append(workshop_id)
                else:
                    # If not in Steam metadata, try to find it in the mod's About.xml
                    # search through all active mods' About.xml files
                    for active_path in active_mods:
                        active_mod = mods_metadata.get(active_path)
                        if not active_mod or not active_mod.mod_path:
                            continue

                        mod_path = active_mod.mod_path
                        about_path = os.path.join(str(mod_path), "About", "About.xml")
                        if os.path.exists(about_path):
                            try:
                                import xml.etree.ElementTree as ET

                                tree = ET.parse(about_path)
                                root = tree.getroot()

                                prefer_versioned = False
                                try:
                                    prefer_versioned = self.metadata_controller.settings.prefer_versioned_about_tags
                                except Exception:
                                    prefer_versioned = False

                                # First check versioned deps if preference enabled
                                # ByVersion precedence here mirrors CompiledDependencyData.build():
                                # - If ON and matching version key exists:
                                #   * empty -> suppress base (no fallback)
                                #   * non-empty -> use versioned only (no additive merge)
                                # - If ON and no matching key -> fall back to base
                                # - If OFF -> skip ByVersion entirely and use base only
                                used_versioned = False
                                if prefer_versioned:
                                    try:
                                        major, minor = (
                                            self.metadata_controller.game_version.split(
                                                "."
                                            )[:2]
                                        )
                                        target_keys = [
                                            f"v{major}.{minor}",
                                            f"{major}.{minor}",
                                        ]
                                    except Exception:
                                        target_keys = []

                                    deps_by_version = root.find(
                                        "modDependenciesByVersion"
                                    )
                                    if deps_by_version is not None and target_keys:
                                        # Try exact matches, then prefix matches
                                        candidate = None
                                        for child in list(deps_by_version):
                                            if child.tag in target_keys:
                                                candidate = child
                                                break
                                        if candidate is None:
                                            for child in list(deps_by_version):
                                                if any(
                                                    child.tag.startswith(k)
                                                    for k in target_keys
                                                    if k
                                                ):
                                                    candidate = child
                                                    break

                                        if candidate is not None:
                                            used_versioned = True
                                            lis = candidate.findall("li")
                                            if not lis:
                                                logger.debug(
                                                    f"Prefer versioned tags: {candidate.tag} is present but empty; suppressing base modDependencies for {about_path}"
                                                )
                                            else:
                                                logger.debug(
                                                    f"Prefer versioned tags: using dependencies from {candidate.tag} in {about_path}"
                                                )
                                                workshop_id = (
                                                    self._find_workshop_id_in_deps(
                                                        candidate, dep_id
                                                    )
                                                )
                                                if workshop_id:
                                                    mods_to_download.append(workshop_id)
                                                    break

                                if used_versioned:
                                    # If versioned key existed (even if empty), don't fall back to base
                                    pass
                                else:
                                    # Fall back to base modDependencies
                                    deps = root.find("modDependencies")
                                    if deps is None:
                                        continue

                                    workshop_id = self._find_workshop_id_in_deps(
                                        deps, dep_id
                                    )
                                    if workshop_id:
                                        mods_to_download.append(workshop_id)
                                        break
                                if workshop_id:
                                    break  # Found the workshop ID, no need to check other mods
                            except Exception:
                                continue

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

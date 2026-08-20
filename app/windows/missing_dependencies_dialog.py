from functools import partial

from PySide6.QtCore import QEventLoop, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.controllers.metadata_controller import MetadataController
from app.services.dependency_resolver import DepResolveResult
from app.utils.button_factory import ButtonFactory
from app.utils.event_bus import EventBus
from app.utils.steam.workshop_urls import build_workshop_text_search_url

_DEPS_SUMMARY_ARGS_DOC = (
    "deps_summary: dict mapping each mod package ID to a dict with keys:\n"
    '    - "satisfied": set of dep package IDs already active\n'
    '    - "local": set of dep package IDs available locally but not active\n'
    '    - "download": set of dep package IDs that need to be downloaded'
)


class MissingDependenciesDialog(QDialog):
    """
    Dialog to display all mod dependencies and allow user to select
    which missing ones (local/download) to add.
    """

    download_requested = Signal(str)
    download_selected_requested = Signal(list)
    download_selected_steam_requested = Signal(list)

    def __init__(
        self,
        metadata_controller: MetadataController,
        parent: QWidget | None = None,
        steam_client_integration_enabled: bool = False,
    ) -> None:
        """
        Initialize the MissingDependenciesDialog.
        """
        super().__init__(parent)
        self.setObjectName("missingDependenciesDialog")
        self.metadata_controller = metadata_controller
        self.steam_client_integration_enabled = steam_client_integration_enabled
        self.selected_mods: set[str] = set()
        self.checkboxes: dict[str, QCheckBox] = {}
        self._dep_resolve: dict[str, DepResolveResult] = {}
        self._setup_ui()

    def _setup_ui(self) -> None:
        """
        Set up the UI components of the dialog.
        """
        self.setWindowTitle(self.tr("Dependency Manager"))

        main_layout = QVBoxLayout(self)

        description = QLabel(
            self.tr(
                "Showing dependencies of your active mods.\n"
                "Select which missing dependencies to add to your active mods list."
            )
        )
        description.setWordWrap(True)
        description.setObjectName("missingDepsDescription")
        main_layout.addWidget(description)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_content.setObjectName("missingDepsContent")
        self.scroll_layout = QVBoxLayout(scroll_content)
        self.scroll_area.setWidget(scroll_content)
        main_layout.addWidget(self.scroll_area)

        button_layout = QHBoxLayout()

        select_all_button = QPushButton(self.tr("Select All"))
        select_all_button.setObjectName("primaryButton")
        select_all_button.clicked.connect(self.select_all)
        button_layout.addWidget(select_all_button)

        button_layout.addStretch()

        download_menu_items = [
            (self.tr("Download with SteamCMD"), self._download_selected_steamcmd),
        ]
        if self.steam_client_integration_enabled:
            download_menu_items.append(
                (
                    self.tr("Download with Steam client"),
                    self._download_selected_steam,
                )
            )
        download_selected_button = ButtonFactory(self).create_dropdown_button(
            self.tr("Download Selected"), "dangerButton", download_menu_items
        )
        button_layout.addWidget(download_selected_button)

        add_button = QPushButton(self.tr("Add Selected && Sort"))
        add_button.setObjectName("actionButton")
        add_button.clicked.connect(self.accept)
        add_button.setDefault(True)
        add_button.setShortcut("Return")  # Enter key
        button_layout.addWidget(add_button)

        ignore_button = QPushButton(self.tr("Sort Without Adding"))
        ignore_button.setObjectName("primaryButton")
        ignore_button.clicked.connect(self.reject)
        ignore_button.setShortcut("Escape")  # Esc key
        button_layout.addWidget(ignore_button)

        main_layout.addLayout(button_layout)

        # Set the window size
        self.resize(900, 600)

    def show_dialog(
        self,
        deps_summary: dict[str, dict[str, set[str]]],
        missing_deps: dict[str, set[str]],
        dep_resolve: dict[str, DepResolveResult] | None = None,
    ) -> set[str]:
        """
        Show the dialog with all dependencies (satisfied + missing) for each mod.

        Args:
            deps_summary: See module constant ``_DEPS_SUMMARY_ARGS_DOC``.
            missing_deps: dict mapping mod package IDs to sets of missing
                          dependency package IDs (same as before, used to
                          determine if there are any missing deps at all)
            dep_resolve: optional map of download dep package IDs to workshop resolve results

        Returns:
            Set of selected mod package IDs if user accepted, empty set otherwise.
        """
        self._dep_resolve = dep_resolve or {}
        self._populate_dependencies(deps_summary)

        self.setWindowModality(Qt.WindowModality.NonModal)
        loop = QEventLoop()
        self.finished.connect(loop.quit)
        self.show()
        self.raise_()
        self.activateWindow()
        loop.exec()

        if self.result() == QDialog.DialogCode.Accepted:
            return self.get_selected_mods()
        return set()

    def _populate_dependencies(
        self, deps_summary: dict[str, dict[str, set[str]]]
    ) -> None:
        """
        Populate the dialog with all dependencies grouped by mod.
        Each mod shows: satisfied, local, and download dependencies.

        See ``_DEPS_SUMMARY_ARGS_DOC`` for the ``deps_summary`` shape.
        """
        self.clear_dependencies()

        if not deps_summary:
            label = QLabel(self.tr("No dependencies found for any active mod."))
            label.setWordWrap(True)
            self.scroll_layout.addWidget(label)
            return

        # --- Compute summary stats ---
        total_satisfied = 0
        total_local = 0
        total_download = 0
        total_missing_per_mod = 0  # number of mods that have at least one missing dep
        mods_with_deps = 0

        for mod_id, deps in deps_summary.items():
            satisfied = deps.get("satisfied", set())
            local = deps.get("local", set())
            download = deps.get("download", set())

            total_satisfied += len(satisfied)
            total_local += len(local)
            total_download += len(download)

            if satisfied or local or download:
                mods_with_deps += 1

            if local or download:
                total_missing_per_mod += 1

        total_deps = total_satisfied + total_local + total_download
        total_missing = total_local + total_download
        has_missing = total_missing > 0

        # --- Summary header ---
        if has_missing:
            summary_text = self.tr(
                "<b>Summary:</b> {total_deps} total dependencies across {mods_with_deps} mods — "
                "✅ {total_satisfied} fulfilled, "
                "⚠️ {total_missing} missing ({total_local} local, {total_download} download) across {total_missing_per_mod} mod(s)"
            ).format(
                total_deps=total_deps,
                mods_with_deps=mods_with_deps,
                total_satisfied=total_satisfied,
                total_missing=total_missing,
                total_local=total_local,
                total_download=total_download,
                total_missing_per_mod=total_missing_per_mod,
            )
        else:
            summary_text = self.tr(
                "<b>Summary:</b> {total_deps} total dependencies across {mods_with_deps} mods — "
                "✅ All {total_satisfied} dependencies fulfilled"
            ).format(
                total_deps=total_deps,
                mods_with_deps=mods_with_deps,
                total_satisfied=total_satisfied,
            )

        summary_label = QLabel(summary_text)
        summary_label.setWordWrap(True)
        summary_label.setTextFormat(Qt.TextFormat.RichText)
        summary_label.setObjectName("missingDepsHeader")
        self.scroll_layout.addWidget(summary_label)
        self.scroll_layout.addSpacing(5)

        # Sort mods alphabetically for consistent display
        for mod_id in sorted(deps_summary.keys()):
            deps = deps_summary[mod_id]
            satisfied = deps.get("satisfied", set())
            local = deps.get("local", set())
            download = deps.get("download", set())

            mod_name = self.metadata_controller.get_mod_name_from_package_id(mod_id)

            # --- Mod header with per-mod badge ---
            mod_header_parts = [f"<b>{mod_name}</b>  ({mod_id})"]
            if local or download:
                dep_count = len(satisfied)
                missing_count = len(local) + len(download)
                mod_header_parts.append(
                    f"<span style='color:#cc8800;'>  [{dep_count} fulfilled, {missing_count} missing]</span>"
                )
            else:
                dep_count = len(satisfied)
                mod_header_parts.append(
                    f"<span style='color:green;'>  [{dep_count} fulfilled]</span>"
                )

            header_label = QLabel("".join(mod_header_parts))
            header_label.setWordWrap(True)
            header_label.setTextFormat(Qt.TextFormat.RichText)
            header_label.setObjectName("modHeaderLabel")
            self.scroll_layout.addWidget(header_label)

            # --- Satisfied deps (read-only) ---
            if satisfied:
                satisfied_label = QLabel(
                    self.tr("  ✅ Satisfied: ") + ", ".join(sorted(satisfied))
                )
                satisfied_label.setObjectName("satisfiedDepLabel")
                satisfied_label.setWordWrap(True)
                self.scroll_layout.addWidget(satisfied_label)

            # --- Local deps (checkable) ---
            if local:
                for dep_id in sorted(local):
                    dep_name = self.metadata_controller.get_mod_name_from_package_id(
                        dep_id
                    )
                    checkbox = QCheckBox(f"  📦 {dep_name}  ({dep_id})")
                    checkbox.setToolTip(
                        self.tr("Available locally - add to active list")
                    )
                    checkbox.stateChanged.connect(
                        partial(self._toggle_mod_selection, mod_id=dep_id)
                    )
                    self.scroll_layout.addWidget(checkbox)
                    self.checkboxes[dep_id] = checkbox

            # --- Download deps (checkable) ---
            if download:
                for dep_id in sorted(download):
                    dep_name = self.metadata_controller.get_mod_name_from_package_id(
                        dep_id
                    )
                    row = QWidget()
                    row_layout = QHBoxLayout(row)
                    row_layout.setContentsMargins(0, 0, 0, 0)
                    checkbox = QCheckBox(f"  🌐 {dep_name}  ({dep_id})")
                    checkbox.setToolTip(
                        self.tr("Needs to be downloaded - requires SteamCMD")
                    )
                    checkbox.stateChanged.connect(
                        partial(self._toggle_mod_selection, mod_id=dep_id)
                    )
                    row_layout.addWidget(checkbox, stretch=1)
                    self.checkboxes[dep_id] = checkbox

                    resolve = self._dep_resolve.get(dep_id)
                    open_btn = QPushButton(self.tr("Open Workshop"))
                    open_btn.clicked.connect(
                        partial(self._open_workshop, dep_id=dep_id, resolve=resolve)
                    )
                    row_layout.addWidget(open_btn)

                    download_btn = QPushButton(self.tr("Download"))
                    has_workshop_id = resolve is not None and resolve.workshop_id
                    download_btn.setEnabled(bool(has_workshop_id))
                    if has_workshop_id and resolve is not None:
                        pfid = str(resolve.workshop_id)

                        def _emit_download(
                            _checked: bool = False, workshop_pfid: str = pfid
                        ) -> None:
                            self.download_requested.emit(workshop_pfid)

                        download_btn.clicked.connect(_emit_download)
                    row_layout.addWidget(download_btn)
                    self.scroll_layout.addWidget(row)

                    if not has_workshop_id:
                        hint = QLabel(
                            self.tr(
                                "Workshop ID not found — open Workshop to find manually"
                            )
                        )
                        hint.setObjectName("missingWorkshopHint")
                        hint.setWordWrap(True)
                        self.scroll_layout.addWidget(hint)

            # Add a separator between mods
            self.scroll_layout.addSpacing(10)

        if not has_missing:
            no_missing_label = QLabel(
                self.tr(
                    "\nAll dependencies are satisfied. No missing dependencies found."
                )
            )
            no_missing_label.setObjectName("noMissingDepsLabel")
            no_missing_label.setWordWrap(True)
            self.scroll_layout.addWidget(no_missing_label)
            # Hide the add/sort buttons since there's nothing to add
            self._set_action_buttons_visible(False)

        self.scroll_layout.addStretch()

    def _set_action_buttons_visible(self, visible: bool) -> None:
        """Show or hide the action buttons in the button layout."""
        # The button layout is the last item in the main layout
        layout = self.layout()
        if layout is None:
            return
        item = layout.itemAt(layout.count() - 1)
        if item is None:
            return
        btn_layout = item.layout()
        if btn_layout is None:
            return
        for i in range(btn_layout.count()):
            item = btn_layout.itemAt(i)
            if item is not None:
                w = item.widget()
                if w is not None:
                    w.setVisible(visible)

    def clear_dependencies(self) -> None:
        """
        Clear all dependency widgets and reset selections.
        """
        while self.scroll_layout.count():
            child = self.scroll_layout.takeAt(0)
            if child is None:
                continue
            widget = child.widget()
            if widget is not None:
                widget.deleteLater()
        self.checkboxes.clear()
        self.selected_mods.clear()

    def select_all(self) -> None:
        """
        Select all dependency checkboxes.
        """
        for checkbox in self.checkboxes.values():
            checkbox.setChecked(True)

    def _toggle_mod_selection(self, state: int, mod_id: str) -> None:
        """
        Toggle a mod's selection state.

        Args:
            state: The state of the checkbox.
            mod_id: The package ID of the mod.
        """
        if state == Qt.CheckState.Checked.value:
            self.selected_mods.add(mod_id)
        else:
            self.selected_mods.discard(mod_id)

    def _selected_pfids(self) -> list[str]:
        """
        Return the workshop IDs of all currently checked "download"
        dependencies that have a resolved publishedfileid.
        """
        return [
            str(self._dep_resolve[mod_id].workshop_id)
            for mod_id in self.selected_mods
            if mod_id in self._dep_resolve and self._dep_resolve[mod_id].workshop_id
        ]

    def _download_selected_steamcmd(self) -> None:
        """Emit download_selected_requested (SteamCMD) for selected pfids."""
        pfids = self._selected_pfids()
        if pfids:
            self.download_selected_requested.emit(pfids)

    def _download_selected_steam(self) -> None:
        """Emit download_selected_steam_requested (Steam client) for selected pfids."""
        pfids = self._selected_pfids()
        if pfids:
            self.download_selected_steam_requested.emit(pfids)

    def get_selected_mods(self) -> set[str]:
        """
        Return the set of selected mod IDs.

        Returns:
            Set of selected mod package IDs.
        """
        return self.selected_mods

    def _open_workshop(
        self,
        dep_id: str,
        resolve: DepResolveResult | None,
    ) -> None:
        if resolve and resolve.workshop_url:
            url = resolve.workshop_url
        else:
            mod_name = self.metadata_controller.get_mod_name_from_package_id(dep_id)
            url = build_workshop_text_search_url(mod_name)
        EventBus().workshop_restore_target = self
        self.hide()
        EventBus().do_browse_workshop_url.emit(url)

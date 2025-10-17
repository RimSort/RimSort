from functools import partial

from PySide6.QtCore import Qt
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

from app.utils.metadata import MetadataManager


class MissingDependenciesDialog(QDialog):
    """
    Dialog to display missing mod dependencies and allow user to select which to add.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """
        Initialize the MissingDependenciesDialog.
        """
        super().__init__(parent)
        self.setObjectName("missingDependenciesDialog")
        self.metadata_manager = MetadataManager.instance()
        self.selected_mods: set[str] = set()
        self.checkboxes: dict[str, QCheckBox] = {}
        self._setup_ui()

    def _setup_ui(self) -> None:
        """
        Set up the UI components of the dialog.
        """
        self.setWindowTitle(self.tr("Dependency Manager"))

        main_layout = QVBoxLayout(self)

        description = QLabel(
            self.tr(
                "Some mods in your active list require other mods to work properly.\n"
                "Select which missing dependencies to add to your active mods list."
            )
        )
        description.setWordWrap(True)
        main_layout.addWidget(description)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(scroll_content)
        self.scroll_area.setWidget(scroll_content)
        main_layout.addWidget(self.scroll_area)

        button_layout = QHBoxLayout()

        select_all_button = QPushButton(self.tr("Select All"))
        select_all_button.clicked.connect(self.select_all)
        button_layout.addWidget(select_all_button)

        button_layout.addStretch()

        add_button = QPushButton(self.tr("Add Selected && Sort"))
        add_button.clicked.connect(self.accept)
        add_button.setDefault(True)
        add_button.setShortcut("Return")  # Enter key
        button_layout.addWidget(add_button)

        ignore_button = QPushButton(self.tr("Sort Without Adding"))
        ignore_button.clicked.connect(self.reject)
        ignore_button.setShortcut("Escape")  # Esc key
        button_layout.addWidget(ignore_button)

        main_layout.addLayout(button_layout)

        # Set the window size
        self.resize(900, 600)

    def show_dialog(self, missing_deps: dict[str, set[str]]) -> set[str]:
        """
        Show the dialog with missing dependencies and return selected mods.

        Args:
            missing_deps: dict mapping mod package IDs to sets of missing dependency package IDs

        Returns:
            Set of selected mod package IDs if user accepted, empty set otherwise.
        """
        if not missing_deps:
            return set()

        self._populate_dependencies(missing_deps)

        result = self.exec()
        if result == QDialog.DialogCode.Accepted:
            return self.get_selected_mods()
        else:
            return set()

    def _populate_dependencies(self, missing_deps: dict[str, set[str]]) -> None:
        """
        Populate the dialog with missing dependencies grouped by local and download.

        Args:
            missing_deps: dict mapping mod package IDs to sets of missing dependency package IDs
        """
        self.clear_dependencies()

        local_deps, download_deps = self._classify_dependencies(missing_deps)

        if local_deps:
            local_label = QLabel(self.tr("Local mods (available but not active):"))
            local_label.setObjectName("localDepsLabel")
            self.scroll_layout.addWidget(local_label)

            for dep_id, requiring_mods in local_deps.items():
                self._add_dependency_group(dep_id, requiring_mods)

            self.scroll_layout.addSpacing(20)

        if download_deps:
            download_label = QLabel(self.tr("Mods that need to be downloaded:"))
            download_label.setObjectName("downloadDepsLabel")
            self.scroll_layout.addWidget(download_label)

            for dep_id, requiring_mods in download_deps.items():
                self._add_dependency_group(dep_id, requiring_mods)

        self.scroll_layout.addStretch()

    def _classify_dependencies(
        self, missing_deps: dict[str, set[str]]
    ) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
        """
        Classify missing dependencies into local and download groups.

        Args:
            missing_deps: dict mapping mod package IDs to sets of missing dependency package IDs

        Returns:
            Tuple of two dicts:
            - local_deps: dependencies that exist locally but aren't active
            - download_deps: dependencies that need to be downloaded
        """
        local_deps: dict[str, list[str]] = {}
        download_deps: dict[str, list[str]] = {}

        for mod_id, deps in missing_deps.items():
            mod_name = self.metadata_manager.get_mod_name_from_package_id(mod_id)
            for dep_id in deps:
                exists_locally = any(
                    mod_data.get("packageid") == dep_id
                    for mod_data in self.metadata_manager.internal_local_metadata.values()
                )
                target_dict = local_deps if exists_locally else download_deps
                if dep_id not in target_dict:
                    target_dict[dep_id] = []
                target_dict[dep_id].append(mod_name)

        return local_deps, download_deps

    def clear_dependencies(self) -> None:
        """
        Clear all dependency widgets and reset selections.
        """
        while self.scroll_layout.count():
            child = self.scroll_layout.takeAt(0)
            widget = child.widget()
            if widget is not None:
                widget.deleteLater()
        self.checkboxes.clear()
        self.selected_mods.clear()

    def _add_dependency_group(self, dep_id: str, requiring_mods: list[str]) -> None:
        """
        Add a dependency group widget to the dialog.

        Args:
            dep_id: The package ID of the dependency.
            requiring_mods: List of mod names that require this dependency.
        """
        group_widget = QWidget()
        group_widget.setObjectName("dependencyGroupWidget")
        group_layout = QVBoxLayout(group_widget)

        dep_name = self.metadata_manager.get_mod_name_from_package_id(dep_id)
        checkbox = QCheckBox(dep_name)
        checkbox.setToolTip(self.tr("Package ID: {dep_id}").format(dep_id=dep_id))
        checkbox.stateChanged.connect(
            partial(self._toggle_mod_selection, mod_id=dep_id)
        )
        group_layout.addWidget(checkbox)
        self.checkboxes[dep_id] = checkbox

        requiring_label = QLabel(
            self.tr("Required by:\n  • ") + "\n  • ".join(requiring_mods)
        )
        requiring_label.setStyleSheet("color: gray; margin-left: 20px;")
        requiring_label.setWordWrap(True)
        group_layout.addWidget(requiring_label)

        group_layout.addSpacing(10)

        self.scroll_layout.addWidget(group_widget)

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

    def get_selected_mods(self) -> set[str]:
        """
        Return the set of selected mod IDs.

        Returns:
            Set of selected mod package IDs.
        """
        return self.selected_mods

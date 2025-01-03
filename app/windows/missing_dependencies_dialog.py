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
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.metadata_manager = MetadataManager.instance()
        self.selected_mods: set[str] = set()
        self.init_ui()

    def init_ui(self) -> None:
        # set window title and size
        self.setWindowTitle("Dependency Manager")
        self.resize(700, 500)

        # create main layout
        layout = QVBoxLayout()

        # add description
        description = QLabel(
            "Some mods in your active list require other mods to work properly.\n"
            "You can select which missing dependencies to add to your active mods list."
        )
        description.setWordWrap(True)
        description.setStyleSheet("font-size: 10pt; margin-bottom: 10px;")
        layout.addWidget(description)

        # create scroll area for dependencies
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(scroll_content)
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)

        # create buttons
        button_layout = QHBoxLayout()

        # add select all button
        select_all_button = QPushButton("Select All")
        select_all_button.clicked.connect(self.select_all)
        button_layout.addWidget(select_all_button)

        # add spacer
        button_layout.addStretch()

        # add main action buttons
        apply_button = QPushButton("Add Selected && Sort")
        apply_button.clicked.connect(self.accept)
        apply_button.setDefault(True)

        ignore_button = QPushButton("Sort Without Adding")
        ignore_button.clicked.connect(self.reject)

        button_layout.addWidget(apply_button)
        button_layout.addWidget(ignore_button)

        layout.addLayout(button_layout)
        self.setLayout(layout)

    def show_missing_dependencies(self, missing_deps: dict[str, set[str]]) -> None:
        """
        Display missing dependencies in the dialog
        missing_deps: dict mapping mod package IDs to sets of missing dependency package IDs
        """
        # clear previous content
        while self.scroll_layout.count():
            child = self.scroll_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        if not missing_deps:
            label = QLabel("All dependencies are satisfied!")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.scroll_layout.addWidget(label)
            return

        # Group dependencies by their package ID
        local_deps: dict[
            str, list[str]
        ] = {}  # deps that exist locally but aren't active
        download_deps: dict[str, list[str]] = {}  # deps that need to be downloaded

        for mod_id, deps in missing_deps.items():
            mod_name = self.metadata_manager.get_mod_name_from_package_id(mod_id)
            for dep_id in deps:
                # Check if the mod exists locally but isn't active
                exists_locally = False
                for mod_data in self.metadata_manager.internal_local_metadata.values():
                    if mod_data.get("packageid") == dep_id:
                        exists_locally = True
                        break

                target_dict = local_deps if exists_locally else download_deps
                if dep_id not in target_dict:
                    target_dict[dep_id] = []
                target_dict[dep_id].append(mod_name)

        # log the mod IDs
        if local_deps:
            for dep_id in local_deps.keys():
                mod_name = self.metadata_manager.get_mod_name_from_package_id(dep_id)

        if download_deps:
            for dep_id in download_deps.keys():
                mod_name = self.metadata_manager.get_mod_name_from_package_id(dep_id)

        # add section for local mods
        if local_deps:
            section_label = QLabel("Local mods (available but not active):")
            section_label.setStyleSheet("font-weight: bold; color: green;")
            self.scroll_layout.addWidget(section_label)

            for dep_id, requiring_mods in local_deps.items():
                self._add_dependency_group(dep_id, requiring_mods)

            # add spacing between sections
            self.scroll_layout.addSpacing(20)

        # add section for mods that need downloading
        if download_deps:
            section_label = QLabel("Mods that need to be downloaded:")
            section_label.setStyleSheet("font-weight: bold; color: orange;")
            self.scroll_layout.addWidget(section_label)

            for dep_id, requiring_mods in download_deps.items():
                self._add_dependency_group(dep_id, requiring_mods)

        # add spacer at the bottom
        self.scroll_layout.addStretch()

    def _add_dependency_group(self, dep_id: str, requiring_mods: list[str]) -> None:
        """Helper method to add a dependency group to the dialog"""
        # create group for this dependency
        dep_group = QWidget()
        dep_layout = QVBoxLayout(dep_group)

        # add dependency checkbox and name
        dep_name = self.metadata_manager.get_mod_name_from_package_id(dep_id)
        checkbox = QCheckBox(f"{dep_name}")
        checkbox.setToolTip(f"Package ID: {dep_id}")
        checkbox.stateChanged.connect(
            lambda state, d=dep_id: self.toggle_mod_selection(state, d)
        )
        dep_layout.addWidget(checkbox)

        # add indented list of mods that require this dependency
        mods_label = QLabel("Required by:\n  • " + "\n  • ".join(requiring_mods))
        mods_label.setStyleSheet("color: gray; margin-left: 20px;")
        mods_label.setWordWrap(True)
        dep_layout.addWidget(mods_label)

        # add some spacing between dependency groups
        dep_layout.addSpacing(10)

        self.scroll_layout.addWidget(dep_group)

    def select_all(self) -> None:
        """Select all dependency checkboxes"""
        for i in range(self.scroll_layout.count()):
            item = self.scroll_layout.itemAt(i)
            if item and item.widget():
                mod_group = item.widget()
                for child in mod_group.findChildren(QCheckBox):  # type: QCheckBox
                    child.setChecked(True)

    def toggle_mod_selection(self, state: int, mod_id: str) -> None:
        """Toggle a mod's selection state"""
        if state == Qt.CheckState.Checked.value:
            self.selected_mods.add(mod_id)
        else:
            self.selected_mods.discard(mod_id)

    def get_selected_mods(self) -> set[str]:
        """Return the set of selected mod IDs"""
        return self.selected_mods

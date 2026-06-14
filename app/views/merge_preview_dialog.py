from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.utils.metadata import MetadataManager


class ModListSection(QWidget):
    """A labeled QListWidget section for the merge preview dialog."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        section_layout = QVBoxLayout(self)
        section_layout.setContentsMargins(0, 0, 0, 0)
        section_layout.setSpacing(2)

        self.header_label = QLabel(f"<b>{title}</b>")
        section_layout.addWidget(self.header_label)

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.list_widget.setMaximumHeight(200)
        section_layout.addWidget(self.list_widget)

        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

    def add_item(self, text: str) -> None:
        """Add a text item to the list widget."""
        self.list_widget.addItem(text)


class MergePreviewDialog(QDialog):
    """
    Modal dialog previewing the result of merging an external modlist
    into the current active list.

    Shows three sections:
    - New mods to add
    - Already active
    - Missing / not installed (hidden if empty)
    """

    def __init__(
        self,
        new_mods: list[str],
        already_present: list[str],
        missing_packageids: list[str],
        source_filename: str = "",
        total_imported: int = 0,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("mergePreviewDialog")
        self.metadata_manager = MetadataManager.instance()

        self._new_mods = new_mods
        self._already_present = already_present
        self._missing_packageids = missing_packageids

        self._setup_ui(source_filename, total_imported)

    @property
    def new_mod_count(self) -> int:
        """Number of new mods to add."""
        return len(self._new_mods)

    @property
    def already_present_count(self) -> int:
        """Number of mods already in the active list."""
        return len(self._already_present)

    @property
    def missing_count(self) -> int:
        """Number of missing / not-installed package IDs."""
        return len(self._missing_packageids)

    def _setup_ui(self, source_filename: str, total_imported: int) -> None:
        """Build and lay out all UI components."""
        self.setWindowTitle(self.tr("Merge Modlist Preview"))
        self.resize(700, 500)

        outer_layout = QVBoxLayout(self)

        if source_filename:
            source_label = QLabel(
                self.tr("Source: {filename}").format(filename=source_filename)
            )
            outer_layout.addWidget(source_label)
        if total_imported > 0:
            count_label = QLabel(
                self.tr("Mods in imported list: {count}").format(count=total_imported)
            )
            outer_layout.addWidget(count_label)

        # Scrollable content area for sections
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll_content = QWidget()
        content_layout = QVBoxLayout(scroll_content)
        content_layout.setContentsMargins(0, 0, 0, 0)

        # -- New mods section --
        self.new_section = ModListSection(
            self.tr("✚ New mods to add ({count})").format(count=self.new_mod_count)
        )
        self._populate_uuid_section(self.new_section, self._new_mods)
        content_layout.addWidget(self.new_section)

        # -- Already present section --
        self.already_present_section = ModListSection(
            self.tr("✓ Already active ({count})").format(
                count=self.already_present_count
            )
        )
        self._populate_uuid_section(self.already_present_section, self._already_present)
        content_layout.addWidget(self.already_present_section)

        # -- Missing section (hidden if empty) --
        self.missing_section = ModListSection(
            self.tr("⚠ Missing / not installed ({count})").format(
                count=self.missing_count
            )
        )
        for pkg_id in self._missing_packageids:
            self.missing_section.add_item(pkg_id)
        if not self._missing_packageids:
            self.missing_section.setVisible(False)
        content_layout.addWidget(self.missing_section)

        content_layout.addStretch()
        scroll_area.setWidget(scroll_content)
        outer_layout.addWidget(scroll_area)

        # -- Footer --
        footer_label = QLabel(
            self.tr("After merging, the active list will be automatically sorted.")
        )
        footer_label.setWordWrap(True)
        outer_layout.addWidget(footer_label)

        # -- Buttons --
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_button = QPushButton(self.tr("Cancel"))
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)

        self.merge_button = QPushButton(self.tr("Merge && Sort"))
        self.merge_button.setDefault(True)
        self.merge_button.clicked.connect(self.accept)
        button_layout.addWidget(self.merge_button)

        if self.new_mod_count == 0:
            self.merge_button.setEnabled(False)
            self.merge_button.setToolTip(self.tr("No new mods to add."))

        outer_layout.addLayout(button_layout)

    def _populate_uuid_section(self, section: ModListSection, uuids: list[str]) -> None:
        """Add mod entries to a section, displaying 'Name  (packageid)' per uuid."""
        for uuid in uuids:
            mod_data = self.metadata_manager.internal_local_metadata.get(uuid, {})
            name = mod_data.get("name", self.tr("Unknown"))
            package_id = mod_data.get("packageid", "???")
            section.add_item(f"{name}  ({package_id})")

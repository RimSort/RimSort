from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.utils.metadata import MetadataManager


class CollapsibleSection(QGroupBox):
    """A QGroupBox with a clickable title that toggles visibility of a QListWidget."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(title, parent)
        self.setCheckable(False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        section_layout = QVBoxLayout(self)
        section_layout.setContentsMargins(4, 4, 4, 4)

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        section_layout.addWidget(self.list_widget)

    def mousePressEvent(self, _event: object) -> None:
        """Toggle section visibility on click."""
        self._toggle()

    def _toggle(self) -> None:
        self.list_widget.setVisible(not self.list_widget.isVisible())

    def set_expanded(self, expanded: bool) -> None:
        """Set whether the list widget is visible."""
        self.list_widget.setVisible(expanded)

    def add_item(self, text: str) -> None:
        """Add a text item to the list widget."""
        self.list_widget.addItem(text)


class MergePreviewDialog(QDialog):
    """
    Modal dialog previewing the result of merging an external modlist
    into the current active list.

    Shows three collapsible sections:

    - New mods to add (expanded by default)
    - Already active (collapsed by default)
    - Missing / not installed (expanded if non-empty, hidden if empty)
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

        main_layout = QVBoxLayout(self)

        if source_filename:
            source_label = QLabel(
                self.tr("Source: {filename}").format(filename=source_filename)
            )
            main_layout.addWidget(source_label)
        if total_imported > 0:
            count_label = QLabel(
                self.tr("Mods in imported list: {count}").format(count=total_imported)
            )
            main_layout.addWidget(count_label)

        # -- New mods section (expanded) --
        self.new_section = CollapsibleSection(
            self.tr("✚ New mods to add ({count})").format(count=self.new_mod_count)
        )
        self._populate_uuid_section(self.new_section, self._new_mods)
        self.new_section.set_expanded(True)
        main_layout.addWidget(self.new_section)

        # -- Already present section (collapsed) --
        self.already_present_section = CollapsibleSection(
            self.tr("✓ Already active ({count})").format(
                count=self.already_present_count
            )
        )
        self._populate_uuid_section(self.already_present_section, self._already_present)
        self.already_present_section.set_expanded(False)
        main_layout.addWidget(self.already_present_section)

        # -- Missing section (expanded if non-empty, hidden if empty) --
        self.missing_section = CollapsibleSection(
            self.tr("⚠ Missing / not installed ({count})").format(
                count=self.missing_count
            )
        )
        for pkg_id in self._missing_packageids:
            self.missing_section.add_item(pkg_id)
        if self._missing_packageids:
            self.missing_section.set_expanded(True)
        else:
            self.missing_section.setVisible(False)
        main_layout.addWidget(self.missing_section)

        # -- Footer --
        footer_label = QLabel(
            self.tr("After merging, the active list will be automatically sorted.")
        )
        footer_label.setWordWrap(True)
        main_layout.addWidget(footer_label)

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

        main_layout.addLayout(button_layout)

    def _populate_uuid_section(
        self, section: CollapsibleSection, uuids: list[str]
    ) -> None:
        """Add mod entries to a section, displaying 'Name  (packageid)' per uuid."""
        for uuid in uuids:
            mod_data = self.metadata_manager.internal_local_metadata.get(uuid, {})
            name = mod_data.get("name", self.tr("Unknown"))
            package_id = mod_data.get("packageid", "???")
            section.add_item(f"{name}  ({package_id})")

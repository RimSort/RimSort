"""The Modern UI profile's left panel.

ModInfoPanel is SHARED - the classic profile mounts it unchanged. All
Modern-only left panel work (card sections, collapsible headers, row
separators, the scroll area, the Incompatibilities / Quick Actions
sections) lives in this subclass so classic is never touched.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.views.mod_info_panel import ModInfoPanel


class ModernModInfoPanel(ModInfoPanel):
    """ModInfoPanel restyled for the Modern UI: the same metadata,
    arranged as collapsible cards under a full-width cover image, with
    separator lines under each metadata row (the Modern UI mock)."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._row_separators: list[tuple[QFrame, QWidget | None]] = []
        self._modernize_layout()

    def _modernize_layout(self) -> None:
        """Transform the freshly built classic panel into the modern
        card layout - everything here is Modern-only."""
        # Detach the four classic sections from the base layout
        sections: list[QLayout] = []
        while self.info_layout.count():
            item = self.info_layout.takeAt(0)
            if item is None:
                break
            row_layout = item.layout()
            if row_layout is not None:
                sections.append(row_layout)
        if not sections:
            return

        # Natural sizes, the scroll area handles small monitors. Small
        # edge space only: the cover art fills the panel width
        self.info_layout.setContentsMargins(4, 4, 4, 4)
        self.info_layout.addLayout(self.image_layout)

        # Mod Information section (collapsible mini container under the
        # image, holding the metadata rows)
        self._make_card_section(self.tr("Mod Information"), self.mod_info_layout)

        # Notes section (collapsible card)
        self._make_card_section(self.tr("Notes"), self.notes_layout)

        # Description section (collapsible card)
        self._make_card_section(self.tr("Description"), self.description_layout)

        # Incompatibilities section (renamed from Conflicts)
        incompat_layout = QVBoxLayout()
        incompat_layout.setContentsMargins(0, 0, 0, 0)
        self.incompatibilities_label = QLabel(self.tr("No incompatibilities detected"))
        self.incompatibilities_label.setWordWrap(True)
        self.incompatibilities_label.setObjectName("summaryValue")
        incompat_layout.addWidget(self.incompatibilities_label)
        self._make_card_section(self.tr("Incompatibilities"), incompat_layout)

        # Quick Actions section (placeholder for a later round)
        quick_layout = QVBoxLayout()
        quick_layout.setContentsMargins(0, 0, 0, 0)
        self.quick_actions_placeholder = QLabel(self.tr("Placeholder"))
        self.quick_actions_placeholder.setObjectName("summaryValue")
        quick_layout.addWidget(self.quick_actions_placeholder)
        self._make_card_section(self.tr("Quick Actions"), quick_layout)

        # Separator line under every metadata row, inside the card
        self._add_row_separators()

        # The whole left panel scrolls on small monitors: swap the
        # classic direct frame mount for a scroll area
        while self.panel.count():
            item = self.panel.takeAt(0)
            if item is None:
                break
            if item.widget() is not None:
                break
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setWidget(self.info_panel_frame)
        self.panel.addWidget(scroll_area)

    def _add_row_separators(self) -> None:
        """Insert a separator after each row layout in the Mod
        Information card, walking the built layout in order."""
        index = 0
        while index < self.mod_info_layout.count():
            item = self.mod_info_layout.itemAt(index)
            row_layout = item.layout() if item is not None else None
            if isinstance(row_layout, QHBoxLayout):
                self._add_row_separator(row_layout, index + 1)
                index += 2  # skip the separator just inserted
            else:
                index += 1

    def _add_row_separator(self, row_layout: QHBoxLayout, insert_at: int) -> None:
        """A thin line under a metadata row - the text sits on lines
        (the mock's Mod Information card). The line follows the row's
        own visibility: hidden rows (GitHub, Summary) stop leaving
        orphan lines behind. QWidget has no visibility signal, so the
        sync runs through _sync_row_separators at each display update."""
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setStyleSheet("background: #23324a; border: none; max-height: 1px;")
        first = row_layout.itemAt(0)
        first_widget = first.widget() if first is not None else None
        self._row_separators.append((separator, first_widget))
        self.mod_info_layout.insertWidget(insert_at, separator)

    def _sync_row_separators(self) -> None:
        """Show each separator only while its row's labels are visible -
        hidden rows (GitHub, Summary on non-matching mods) leave no
        orphan lines."""
        for separator, first_widget in self._row_separators:
            if first_widget is None:
                separator.setVisible(False)
                continue
            parent = first_widget.parentWidget()
            separator.setVisible(
                parent is not None and first_widget.isVisibleTo(parent)
            )

    def _make_card_section(
        self, title: str, content_layout: QLayout
    ) -> tuple[QToolButton, QFrame]:
        """A styled card holding the collapsible header AND the content:
        expanding shows the section, collapsing folds the content while
        the header bar stays as the neat rectangle (her fix)."""
        card = QFrame()
        card.setObjectName("sectionCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)
        header = self._make_section_header(title)
        content = QWidget()
        content.setLayout(content_layout)
        card_layout.addWidget(header)
        card_layout.addWidget(content)

        def _toggle(checked: bool) -> None:
            # Fold the CONTENT only - the header bar stays visible
            content.setVisible(checked)
            header.setArrowType(
                Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow
            )

        header.toggled.connect(_toggle)
        self.info_layout.addWidget(card)
        return header, card

    def _make_section_header(self, title: str) -> QToolButton:
        """A flat section header with a collapse arrow. No toggle wiring -
        the caller folds its own content, so the header bar always stays
        visible as the collapsed rectangle (her fix)."""
        header = QToolButton()
        header.setText(title)
        header.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        header.setArrowType(Qt.ArrowType.DownArrow)
        header.setCheckable(True)
        header.setChecked(True)
        header.setStyleSheet("text-align: left; font-weight: 600; border: none;")
        return header

    def display_mod_info(self, uuid: str) -> None:
        super().display_mod_info(uuid)
        self._sync_row_separators()

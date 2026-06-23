from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QIcon, QMouseEvent, QResizeEvent, QShowEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLayoutItem,
    QRadioButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.models.filter_state import FilterState
from app.utils.app_info import AppInfo


class FlowLayout(QLayout):
    """Layout that arranges widgets in a flow, wrapping to the next line."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._items: list[QLayoutItem] = []
        self._spacing = 6

    def addItem(self, item: QLayoutItem) -> None:
        """
        Add an item to the layout.

        :param item: Layout item to add
        """
        self._items.append(item)

    def count(self) -> int:
        """
        Return the number of items in the layout.

        :return: Item count
        """
        return len(self._items)

    def itemAt(self, index: int) -> QLayoutItem | None:
        """
        Return the item at the given index.

        :param index: Index of the item
        :return: Layout item or None if out of range
        """
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int) -> QLayoutItem | None:
        """
        Remove and return the item at the given index.

        :param index: Index of the item to remove
        :return: Removed layout item or None if out of range
        """
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def setSpacing(self, spacing: int) -> None:
        """
        Set the spacing between items.

        :param spacing: Spacing in pixels
        """
        self._spacing = spacing

    def spacing(self) -> int:
        """
        Return the spacing between items.

        :return: Spacing in pixels
        """
        return self._spacing

    def sizeHint(self) -> QSize:
        """
        Return the preferred size for this layout.

        :return: Size hint
        """
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        """
        Return the minimum size for this layout.

        :return: Minimum size
        """
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(
            margins.left() + margins.right(), margins.top() + margins.bottom()
        )
        return size

    def setGeometry(self, rect: QRect) -> None:
        """
        Set the geometry of all items in the layout.

        :param rect: Rectangle to lay out within
        """
        super().setGeometry(rect)
        self._do_layout(rect)

    def _do_layout(self, rect: QRect) -> int:
        """
        Perform the actual layout of items within the given rectangle.

        :param rect: Rectangle to lay out within
        :return: The bottom Y coordinate of the last row
        """
        margins = self.contentsMargins()
        effective = rect.adjusted(
            margins.left(), margins.top(), -margins.right(), -margins.bottom()
        )
        x = effective.x()
        y = effective.y()
        line_height = 0
        for item in self._items:
            size = item.sizeHint()
            next_x = x + size.width() + self._spacing
            if next_x - self._spacing > effective.right() and line_height > 0:
                x = effective.x()
                y = y + line_height + self._spacing
                next_x = x + size.width() + self._spacing
                line_height = 0
            item.setGeometry(QRect(QPoint(x, y), size))
            x = next_x
            line_height = max(line_height, size.height())
        return y + line_height

    def hasHeightForWidth(self) -> bool:
        """
        Return whether this layout supports height-for-width.

        :return: Always True
        """
        return True

    def heightForWidth(self, width: int) -> int:
        """
        Return the preferred height for the given width.

        :param width: Available width
        :return: Required height
        """
        return self._do_layout(QRect(0, 0, width, 0))


class FlowLayoutContainer(QWidget):
    """Widget wrapper that keeps a FlowLayout height in sync with its width."""

    def __init__(self, layout: FlowLayout, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setLayout(layout)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._sync_height()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._sync_height()

    def _sync_height(self) -> None:
        layout = self.layout()
        if not isinstance(layout, FlowLayout):
            return
        width = max(1, self.contentsRect().width())
        layout.invalidate()
        self.setMinimumHeight(layout.heightForWidth(width))


class TagChip(QFrame):
    """
    A small clickable chip widget representing a single tag filter.

    Displays a tag name with an active/inactive toggle state. When active,
    shows a dismiss indicator (cross mark). The "no tags" variant uses
    italic text to visually distinguish it.

    :param tag_name: Display name for the tag
    :param is_no_tags: Whether this chip represents the "no tags" filter
    :param parent: Parent widget
    """

    toggled = Signal()

    def __init__(
        self,
        tag_name: str,
        is_no_tags: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._tag_name = tag_name
        self._is_no_tags = is_no_tags
        self._active = False

        self.setObjectName("TagChip")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setProperty("active", False)

        layout = QHBoxLayout()
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setSpacing(0)
        self.setLayout(layout)

        self._label = QLabel(tag_name)
        if is_no_tags:
            font = self._label.font()
            font.setItalic(True)
            self._label.setFont(font)
        layout.addWidget(self._label)

    @property
    def tag_name(self) -> str:
        """
        Return the tag name for this chip.

        :return: Tag name string
        """
        return self._tag_name

    @property
    def is_no_tags(self) -> bool:
        """
        Return whether this chip represents the "no tags" filter.

        :return: True if this is the "no tags" chip
        """
        return self._is_no_tags

    @property
    def active(self) -> bool:
        """
        Return whether this chip is currently active (selected).

        :return: True if active
        """
        return self._active

    def set_active(self, active: bool) -> None:
        """
        Programmatically set the active state of this chip.

        Updates the label text and the ``active`` dynamic property
        for QSS styling.

        :param active: New active state
        """
        self._active = active
        self.setProperty("active", active)
        self.style().unpolish(self)
        self.style().polish(self)
        if active:
            self._label.setText(f"{self._tag_name} ✕")
        else:
            self._label.setText(self._tag_name)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """
        Handle mouse press to toggle the chip state.

        :param event: Mouse event
        """
        self.set_active(not self._active)
        self.toggled.emit()


class FilterPanel(QFrame):
    """
    Popup panel for filtering mods by source, type, and tags.

    Displays checkboxes for mod sources, radio buttons for mod types,
    and tag chips for tag-based filtering. Uses ``Qt.Popup`` window flag
    so it auto-dismisses when the user clicks outside.

    :param parent: Parent widget
    """

    filters_changed = Signal()

    SOURCE_LABELS: dict[str, str] = {
        "workshop": "Workshop",
        "local": "Local",
        "expansion": "Expansion",
        "steamcmd": "SteamCMD",
        "git_repo": "Git",
    }

    TYPE_LABELS: dict[str, str] = {
        "all": "All",
        "csharp": "C# Mods",
        "xml": "XML-only",
    }

    TAG_MATCH_MODE_LABELS: dict[str, str] = {
        "or": "Any",
        "and": "All",
    }

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Popup)
        self.setObjectName("FilterPanel")
        self.setMinimumWidth(320)

        self._source_checkboxes: dict[str, QCheckBox] = {}
        self._type_radios: dict[str, QRadioButton] = {}
        self._tag_match_mode_radios: dict[str, QRadioButton] = {}
        self._tag_chips: dict[str, TagChip] = {}

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(8)
        self.setLayout(main_layout)

        # --- Source and Type sections side by side ---
        top_row = QHBoxLayout()
        top_row.setSpacing(16)

        # Source column
        source_col = QVBoxLayout()
        source_header = QLabel("Mod Source")
        header_font = source_header.font()
        header_font.setBold(True)
        source_header.setFont(header_font)
        source_col.addWidget(source_header)

        for key, label in self.SOURCE_LABELS.items():
            cb = QCheckBox(label)
            cb.setChecked(True)
            cb.toggled.connect(self._on_filter_changed)
            self._source_checkboxes[key] = cb
            source_col.addWidget(cb)

        top_row.addLayout(source_col)

        # Type column
        type_col = QVBoxLayout()
        type_header = QLabel("Mod Type")
        type_header.setFont(header_font)
        type_col.addWidget(type_header)

        self._type_group = QButtonGroup(self)
        for key, label in self.TYPE_LABELS.items():
            rb = QRadioButton(label)
            if key == "all":
                rb.setChecked(True)
            rb.toggled.connect(self._on_filter_changed)
            self._type_radios[key] = rb
            self._type_group.addButton(rb)
            type_col.addWidget(rb)

        top_row.addLayout(type_col)
        top_row.addStretch()
        main_layout.addLayout(top_row)

        # --- Separator ---
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.HLine)
        sep1.setFrameShadow(QFrame.Shadow.Sunken)
        main_layout.addWidget(sep1)

        # --- Tags section ---
        tags_header_row = QHBoxLayout()
        tags_label = QLabel("Tags")
        tags_label.setFont(header_font)
        tags_header_row.addWidget(tags_label)
        self._tag_match_mode_group = QButtonGroup(self)
        for key, label in self.TAG_MATCH_MODE_LABELS.items():
            rb = QRadioButton(label)
            rb.setToolTip(
                "Match any selected tag" if key == "or" else "Match all selected tags"
            )
            if key == "or":
                rb.setChecked(True)
            rb.toggled.connect(self._on_filter_changed)
            self._tag_match_mode_radios[key] = rb
            self._tag_match_mode_group.addButton(rb)
            tags_header_row.addWidget(rb)
        tags_header_row.addStretch()

        self._select_all_label = QLabel("Select All")
        self._select_all_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self._select_all_label.setStyleSheet("color: palette(link);")
        self._select_all_label.mousePressEvent = self._on_select_all_tags  # type: ignore[method-assign]
        tags_header_row.addWidget(self._select_all_label)

        divider_label = QLabel("|")
        tags_header_row.addWidget(divider_label)

        self._select_none_label = QLabel("None")
        self._select_none_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self._select_none_label.setStyleSheet("color: palette(link);")
        self._select_none_label.mousePressEvent = self._on_select_none_tags  # type: ignore[method-assign]
        tags_header_row.addWidget(self._select_none_label)

        main_layout.addLayout(tags_header_row)

        # Flow layout for tag chips
        self._tags_flow = FlowLayout()
        self._tags_flow.setSpacing(4)
        self._tags_container = FlowLayoutContainer(self._tags_flow)

        self._tags_scroll = QScrollArea()
        self._tags_scroll.setWidgetResizable(True)
        self._tags_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._tags_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._tags_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self._tags_scroll.setWidget(self._tags_container)
        self._tags_scroll.setMaximumHeight(200)

        # "No tags" chip is always present
        self._no_tags_chip = TagChip("No tags", is_no_tags=True)
        self._no_tags_chip.toggled.connect(self._on_filter_changed)
        self._tag_chips["__no_tags__"] = self._no_tags_chip
        self._tags_flow.addWidget(self._no_tags_chip)

        main_layout.addWidget(self._tags_scroll)

        # --- Separator ---
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setFrameShadow(QFrame.Shadow.Sunken)
        main_layout.addWidget(sep2)

        # --- Clear All button ---
        clear_row = QHBoxLayout()
        clear_row.addStretch()
        self._clear_label = QLabel("Clear All")
        self._clear_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clear_label.setStyleSheet("color: palette(link);")
        self._clear_label.mousePressEvent = self._on_clear_all  # type: ignore[method-assign]
        clear_row.addWidget(self._clear_label)
        main_layout.addLayout(clear_row)

    def set_available_tags(self, tags: list[str]) -> None:
        """
        Set the available user tags, creating tag chips for each.

        Removes any previously created user tag chips and creates new ones.
        The "no tags" chip is always preserved.

        :param tags: List of tag names to display
        """
        selected_tags = {
            key
            for key, chip in self._tag_chips.items()
            if key != "__no_tags__" and chip.active
        }
        include_no_tags = self._no_tags_chip.active

        # Remove existing user tag chips (not the no_tags chip)
        keys_to_remove = [k for k in self._tag_chips if k != "__no_tags__"]
        for key in keys_to_remove:
            chip = self._tag_chips.pop(key)
            self._tags_flow.removeWidget(chip)
            chip.deleteLater()

        # Remove the no_tags chip from layout temporarily so we can
        # add user chips first, then re-add no_tags at the end
        self._tags_flow.removeWidget(self._no_tags_chip)

        for tag in tags:
            chip = TagChip(tag)
            chip.toggled.connect(self._on_filter_changed)
            chip.set_active(tag in selected_tags)
            self._tag_chips[tag] = chip
            self._tags_flow.addWidget(chip)

        # Re-add no_tags chip at end
        self._tags_flow.addWidget(self._no_tags_chip)
        self._no_tags_chip.set_active(include_no_tags)
        self._tags_container._sync_height()

    @property
    def filter_state(self) -> FilterState:
        """
        Build a FilterState from the current widget state.

        :return: FilterState reflecting current selections
        """
        sources: set[str] = set()
        for key, cb in self._source_checkboxes.items():
            if cb.isChecked():
                sources.add(key)

        mod_type = "all"
        for key, rb in self._type_radios.items():
            if rb.isChecked():
                mod_type = key
                break

        tags: set[str] = set()
        for key, chip in self._tag_chips.items():
            if key != "__no_tags__" and chip.active:
                tags.add(key)

        tag_match_mode = "or"
        for key, rb in self._tag_match_mode_radios.items():
            if rb.isChecked():
                tag_match_mode = key
                break

        include_no_tags = self._no_tags_chip.active

        return FilterState(
            sources=sources,
            mod_type=mod_type,
            tags=tags,
            tag_match_mode=tag_match_mode,
            include_no_tags=include_no_tags,
        )

    def clear(self) -> None:
        """
        Reset all filters to their default state and emit ``filters_changed``.

        Uses ``blockSignals`` to avoid cascading signal emissions during
        the reset process.
        """
        # Block signals while resetting
        for cb in self._source_checkboxes.values():
            cb.blockSignals(True)
            cb.setChecked(True)
            cb.blockSignals(False)

        for key, rb in self._type_radios.items():
            rb.blockSignals(True)
            if key == "all":
                rb.setChecked(True)
            rb.blockSignals(False)

        for key, rb in self._tag_match_mode_radios.items():
            rb.blockSignals(True)
            rb.setChecked(key == "or")
            rb.blockSignals(False)

        for chip in self._tag_chips.values():
            chip.set_active(False)

        self.filters_changed.emit()

    def _on_filter_changed(self) -> None:
        """Emit ``filters_changed`` when any filter widget changes."""
        self.filters_changed.emit()

    def _on_select_all_tags(self, event: QMouseEvent) -> None:
        """
        Activate all tag chips (including "no tags").

        :param event: Mouse event (unused)
        """
        for chip in self._tag_chips.values():
            chip.set_active(True)
        self.filters_changed.emit()

    def _on_select_none_tags(self, event: QMouseEvent) -> None:
        """
        Deactivate all tag chips (including "no tags").

        :param event: Mouse event (unused)
        """
        for chip in self._tag_chips.values():
            chip.set_active(False)
        self.filters_changed.emit()

    def _on_clear_all(self, event: QMouseEvent) -> None:
        """
        Clear all filters via the "Clear All" label click.

        :param event: Mouse event (unused)
        """
        self.clear()


class FilterButton(QToolButton):
    """
    Toolbar button that owns a FilterPanel popup and displays a badge.

    Clicking the button positions the FilterPanel below it and shows it.
    A small badge overlay in the top-right corner shows the number of
    active filter categories when any filters are engaged.

    :param parent: Parent widget
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("FilterButton")

        icon_path = str(AppInfo().theme_data_folder / "default-icons" / "AppIcon_b.png")
        self.setIcon(QIcon(icon_path))
        self.setToolTip("Filter mods")

        # Badge label positioned as a child widget (top-right corner)
        self._badge_label = QLabel(self)
        self._badge_label.setObjectName("FilterBadge")
        self._badge_label.setFixedSize(16, 16)
        self._badge_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._badge_label.hide()

        # Create the filter panel
        self.filter_panel = FilterPanel()
        self.filter_panel.filters_changed.connect(self._update_badge)

        self.clicked.connect(self._show_panel)

    def _show_panel(self) -> None:
        """Position the filter panel below this button and show it."""
        pos = self.mapToGlobal(QPoint(0, self.height()))
        self.filter_panel.move(pos)
        self.filter_panel.show()

    def _update_badge(self) -> None:
        """Update the badge label to reflect the active filter category count."""
        count = self.filter_panel.filter_state.active_category_count()
        if count > 0:
            self._badge_label.setText(str(count))
            self._badge_label.show()
        else:
            self._badge_label.hide()

    def resizeEvent(self, event: object) -> None:
        """
        Reposition the badge when the button is resized.

        :param event: Resize event
        """
        super().resizeEvent(event)  # type: ignore[arg-type]
        # Position badge at top-right corner
        self._badge_label.move(self.width() - 16, 0)

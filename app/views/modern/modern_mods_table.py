from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from datetime import datetime
from typing import TYPE_CHECKING, Any, cast

from loguru import logger
from PySide6.QtCore import (
    QAbstractItemModel,
    QEvent,
    QModelIndex,
    QPersistentModelIndex,
    QPoint,
    QPointF,
    QRect,
    QSize,
    Qt,
    QThread,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QContextMenuEvent,
    QCursor,
    QHelpEvent,
    QIcon,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPixmap,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QColorDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QToolButton,
    QToolTip,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.models.filter_state import FilterState
from app.models.metadata.metadata_structure import ModType
from app.sort.mod_sorting import FolderSizeRequestWorker
from app.utils.aux_db_utils import auxdb_update_all_mod_colors
from app.utils.categories_utils import save_categories
from app.views.filter_panel import FilterButton
from app.views.mods_panel import ModListIcons

if TYPE_CHECKING:
    from app.models.settings import Settings
    from app.utils.custom_list_widget_item_metadata import (
        CustomListWidgetItemMetadata,
    )
    from app.views.mods_panel import CustomListWidgetItem, ModsPanel

UNCATEGORIZED = "Uncategorized"


# Column layout: [checkbox, Name, ...Active Columns slots in slot order
# (None slots skipped)]. "Category" is a slot choice like the data
# columns, not a permanent column. Slot 1 defaults to "Default",
# RimSort's bundled warnings/errors column.
COL_CHECK = 0
COL_NAME = 1

# The real data columns: metadata-driven, sortable by header
# click. Game version sorts FIRST in the Mod/Game Version column.
_DATA_COLUMNS: dict[str, str] = {
    "Mod/Game Version": "modgame",
    "Author": "author",
    "Modified Time/Workshop Updated": "modtime",
    "Folder Size": "size",
    "Version": "version",
    "PackageId": "packageid",
}

# List-level classic menu options that belong to the RIGHT panel only;
# filtered out when the center delegates the classic menu
_BLOCKED_MENU_ACTIONS = frozenset({"Add divider here"})


class GradientColor(QColor):
    """A QColor that carries a full gradient CSS as its name(): RimSort's
    mod-color paths call .name() and feed the result straight into a
    stylesheet, so a centered fade rides every repaint untouched."""

    def __init__(self, css: str) -> None:
        super().__init__(255, 255, 255, 0)  # valid, truthy, paints nothing
        self._gradient_css = css

    def name(self, format: QColor.NameFormat = QColor.NameFormat.HexRgb) -> str:
        return self._gradient_css


class ModernModsTree(QTreeWidget):
    """The center table's tree. SOLID category dividers are painted as a
    post-render overlay in paintEvent: one flat muted block spanning the
    full row width after the normal render, so cell backgrounds and
    selection fills never cover it. Hover/selection thin the block; the
    text follows the configured alignment, centered over the row."""

    def __init__(self, settings: object, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = settings

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        if getattr(self._settings, "modern_ui_category_style", "solid") != "solid":
            return
        painter = QPainter(self.viewport())
        align = getattr(self._settings, "modern_ui_category_text_align", "center")
        hover_index = self.indexAt(self.viewport().mapFromGlobal(QCursor.pos()))
        viewport_width = self.viewport().width()
        for row in range(self.topLevelItemCount()):
            item = self.topLevelItem(row)
            if item is None:
                continue
            index = self.indexFromItem(item, 0)
            # The "group" marker lives on the Name column's roles
            if index.siblingAtColumn(1).data(Qt.ItemDataRole.UserRole) != "group":
                continue
            rect = self.visualRect(index)
            if not rect.isValid():
                continue
            color = index.siblingAtColumn(1).data(Qt.ItemDataRole.UserRole + 4)
            if not isinstance(color, QColor):
                color = QColor("#5e6f88")
            block_color = QColor(muted_category_color(color))
            hovered = hover_index.isValid() and hover_index.siblingAtColumn(0) == index
            selected = self.selectionModel().isSelected(index)
            if hovered or selected:
                # A thinner shade of the block on hover/selection
                block_color.setAlpha(90)
            row_rect = QRect(0, rect.y(), viewport_width, rect.height())
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(block_color)
            painter.drawRoundedRect(row_rect, 3, 3)

            name = index.siblingAtColumn(1).data(Qt.ItemDataRole.UserRole + 1) or ""
            count = self.model().rowCount(index)
            text_rect = row_rect
            text_align = Qt.AlignmentFlag.AlignCenter
            if align == "left":
                text_align = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                text_rect = row_rect.adjusted(12, 0, 0, 0)
            elif align == "right":
                text_align = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                text_rect = row_rect.adjusted(0, 0, -12, 0)
            painter.setPen(QColor("#e6edf6"))
            painter.drawText(text_rect, text_align, f"{name}  ({count})")


class CheckDelegate(QStyledItemDelegate):
    """Column 0's delegate: paints the checkbox indicator naturally,
    centered in its cell."""

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        return super().paint(painter, option, index)


def muted_category_color(color: QColor) -> QColor:
    """Tone a category color down for solid dividers: saturation is
    reduced and brightness steps down slightly, keeping the hue."""
    hue, sat, val, _ = cast(tuple[float, float, float, float], color.getHsvF())
    if hue < 0:
        hue, sat = 0.0, 0.0
    return QColor.fromHsvF(hue, min(sat * 0.75, 0.60), max(min(val * 0.85, 0.60), 0.32))


class ModernNameDelegate(QStyledItemDelegate):
    """Column 1's delegate: group rows paint as category dividers in the
    configured style - "solid" (a flat muted MO2-style block spanning
    the full row, no gradients) or "neon" (the gradient band with the
    diagonal slash) - with the text aligned per the format setting; mod
    rows paint default with per-symbol tooltips through helpEvent."""

    def __init__(
        self,
        parent: QWidget | None = None,
        settings: object | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        if index.data(Qt.ItemDataRole.UserRole) == "group":
            # SOLID: the tree's overlay paints the whole divider (block
            # + aligned text) after the normal render - nothing here
            if getattr(self._settings, "modern_ui_category_style", "solid") == "solid":
                return
            # NEON: the gradient band with the diagonal slash
            shifted = QStyleOptionViewItem(option)
            shifted.rect = option.rect.adjusted(-24, 0, 0, 0)
            self._paint_chip(painter, shifted, index)
            return
        # Mod rows: nudge the icons + name left toward the checkboxes
        # without covering them
        shifted = QStyleOptionViewItem(option)
        shifted.rect = option.rect.adjusted(-2, 0, -2, 0)
        super().paint(painter, shifted, index)

    def _paint_chip(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        name = index.data(Qt.ItemDataRole.UserRole + 1) or ""
        color = index.data(Qt.ItemDataRole.UserRole + 4)
        if not isinstance(color, QColor):
            color = QColor("#5e6f88")
        # Count children through the MODEL: the loading animation
        # rebuilds the tree mid-paint, and internalPointer() can hand back
        # freed memory during that rebuild
        model = index.model()
        count = model.rowCount(index) if model is not None else 0

        style = getattr(self._settings, "modern_ui_category_style", "solid")
        if style == "neon":
            self._paint_neon_chip(painter, option, name, color, count)
            return

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # SOLID: no shader work at all - the row's own BackgroundRole
        # (set in _make_group_row) paints the flat muted block across
        # every cell; this delegate only draws the aligned text on top
        align = {
            "left": Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            "right": Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        }.get(
            getattr(self._settings, "modern_ui_category_text_align", "center"),
            Qt.AlignmentFlag.AlignCenter,
        )
        painter.setPen(QColor("#e6edf6"))
        painter.drawText(option.rect, align, f"{name}  ({count})")
        painter.restore()

    def _paint_neon_chip(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        name: str,
        color: QColor,
        count: int,
    ) -> None:
        """NEON: her original design - a band in the raw category color
        rising from translucent to solid across the name, ending in the
        diagonal slash falling top-right down-left."""
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = option.rect.adjusted(2, 2, -6, -2)
        metrics = option.fontMetrics
        name_width = metrics.horizontalAdvance(name) + 18
        slash = 10
        band_width = max(
            slash + 10, min(name_width, max(10, rect.width() - slash - 12))
        )
        top = rect.top()
        bottom = rect.bottom()
        # One shape: a rectangle whose right end is the diagonal slash,
        # falling from the top-right tip down-left
        band_poly = QPolygonF(
            [
                QPointF(rect.left(), top),
                QPointF(rect.left() + band_width, top),
                QPointF(rect.left() + band_width - slash, bottom),
                QPointF(rect.left(), bottom),
            ]
        )
        # The left edge sits at reduced alpha and the color rises
        # continuously across the band, fully solid at the slash tip
        faded = QColor(color)
        faded.setAlpha(120)
        gradient = QLinearGradient(rect.left(), 0, rect.left() + band_width, 0)
        gradient.setColorAt(0.0, faded)
        gradient.setColorAt(1.0, color)
        painter.setBrush(QBrush(gradient))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPolygon(band_poly)

        text_color = QColor("#0b1320") if color.lightness() > 150 else QColor("#e6edf6")
        painter.setPen(text_color)
        painter.drawText(
            rect.adjusted(10, 0, -8, 0),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            f"{name}  ({count})",
        )
        painter.restore()

    def helpEvent(
        self,
        event: QEvent,
        view: QAbstractItemView,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> bool:
        if event.type() == QEvent.Type.ToolTip and isinstance(event, QHelpEvent):
            tooltips = index.data(Qt.ItemDataRole.UserRole + 3)
            if tooltips:
                icon_rect = QRect(
                    option.rect.x(),
                    option.rect.y(),
                    20 * len(tooltips),
                    option.rect.height(),
                )
                if icon_rect.contains(event.pos()):
                    half = (event.pos().x() - option.rect.x()) // 20
                    half = max(0, min(half, len(tooltips) - 1))
                    QToolTip.showText(event.globalPos(), tooltips[half])
                    return True
        return super().helpEvent(cast("QHelpEvent", event), view, option, index)


class CenteredIconDelegate(QStyledItemDelegate):
    """The Default column: three fixed-width sections huddled under the
    header - latest save (left), last updated (center), warning/error
    (right) - each a muted dash when absent, the RimSort symbol when
    present. Clicking the warning section toggles the warning like the
    classic row icons."""

    def __init__(
        self,
        parent: QWidget | None = None,
        on_warning_click: Callable[..., None] | None = None,
    ) -> None:
        super().__init__(parent)
        self._on_warning_click = on_warning_click

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        # Route the background and text through the style directly with
        # the icon stripped, then paint the three slots
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.icon = QIcon()
        widget = option.widget
        style = widget.style() if widget else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, widget)
        rect = option.rect
        # The Default column's OWN index roles carry uuid + source item
        # (stored in _make_mod_row) - reading them from another column's
        # roles was why every slot painted as a dash
        source_item = index.data(Qt.ItemDataRole.UserRole + 1)
        data = (
            source_item.data(Qt.ItemDataRole.UserRole)
            if source_item is not None
            else None
        )
        # Three fixed 28px sections aligned to the column's left edge
        # under the "Default" header
        slot_w = 28
        first_center = rect.left() + slot_w / 2
        dash_pen = QColor("#4a5a78")

        def _slot(center_x: float, pixmap: QPixmap | None) -> None:
            sub = QRect(
                int(center_x - slot_w / 2),
                rect.top(),
                slot_w,
                rect.height(),
            )
            if pixmap is not None and not pixmap.isNull():
                painter.drawPixmap(
                    sub.center().x() - pixmap.width() // 2,
                    sub.center().y() - pixmap.height() // 2,
                    pixmap,
                )
            else:
                painter.setPen(dash_pen)
                painter.drawText(sub, Qt.AlignmentFlag.AlignCenter, "\u2014")
                painter.setPen(Qt.PenStyle.NoPen)

        # Metadata is read as attributes, exactly like the classic
        # list does - it only shims __getitem__ and is not a dict.
        row_data = data
        has_warnings = (
            bool(row_data.warnings or row_data.mismatch)
            if row_data is not None
            else False
        )
        has_errors = (
            bool(row_data.errors or row_data.invalid) if row_data is not None else False
        )
        in_save = (
            bool(row_data.__dict__.get("in_save", False))
            if row_data is not None
            else False
        )
        is_recently_updated = (
            bool(row_data.__dict__.get("is_recently_updated", False))
            if row_data is not None
            else False
        )
        updated_ts = (
            getattr(row_data, "updated_timestamp", None)
            if row_data is not None
            else None
        )

        updated_pixmap = (
            ModListIcons.updated_icon().pixmap(20, 20)
            if is_recently_updated and updated_ts
            else None
        )
        if has_errors:
            warn_pixmap = ModListIcons.error_icon().pixmap(20, 20)
        elif has_warnings:
            warn_pixmap = ModListIcons.warning_icon().pixmap(20, 20)
        else:
            warn_pixmap = None
        save_pixmap = ModListIcons.clear_icon().pixmap(20, 20) if in_save else None

        # Sections, left to right: in latest save, recently updated,
        # warning/error triangle
        _slot(first_center, save_pixmap)
        _slot(first_center + slot_w, updated_pixmap)
        _slot(first_center + slot_w * 2, warn_pixmap)

    def editorEvent(
        self,
        event: QEvent,
        model: QAbstractItemModel,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> bool:
        """Clicking the warning slot toggles the warning - the classic
        icon-click functionality, restored in the modern column."""
        if (
            self._on_warning_click is not None
            and event.type() == QEvent.Type.MouseButtonRelease
            and isinstance(event, QMouseEvent)
            and event.button() == Qt.MouseButton.LeftButton
        ):
            rect = option.rect
            # The warning section is the third 28px slot (geometry in
            # CenteredIconDelegate.paint)
            slot_w = 28
            first_center = rect.left() + slot_w / 2
            warn_rect = QRect(
                int(first_center + slot_w * 2 - slot_w / 2),
                rect.top(),
                slot_w,
                rect.height(),
            )
            if warn_rect.contains(event.pos()):
                source_item = index.data(Qt.ItemDataRole.UserRole + 1)
                data = (
                    source_item.data(Qt.ItemDataRole.UserRole)
                    if source_item is not None
                    else None
                )
                if data is not None and (
                    data.warnings or data.errors or data.mismatch or data.invalid
                ):
                    self._on_warning_click(index)
                    return True
        return super().editorEvent(event, model, option, index)


class ModernModsTable(QWidget):
    """The Modern UI center panel: all mods in one collapsible table.

    Rows are grouped by category (collapsible, from the shareable
    categories file, "Core" first by default). Each mod row carries a
    checkbox that activates/deactivates the mod through the classic
    ModsPanel lists, so every existing signal path (save, sort, run,
    warnings) keeps working. The table NEVER dictates the right panel's
    load order beyond the initial fill.
    """

    mod_info_signal = Signal(str, object)  # (uuid, CustomListWidgetItem)
    active_count_changed = Signal(int)
    refresh_finished = Signal()

    def __init__(
        self,
        settings: Settings,
        mods_panel: ModsPanel,
        categories: dict[str, Any],
    ) -> None:
        super().__init__()
        self.settings = settings
        self.mods_panel = mods_panel
        self.categories = categories
        self._populating = False
        self._uuid_rows: dict[str, QTreeWidgetItem] = {}
        self._slot_columns: list[str] = []
        self._default_col: int | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        header_row = QHBoxLayout()
        self.title_label = QLabel("All Mods")
        self.title_label.setObjectName("ModernPanelHeader")
        self.count_label = QLabel("")
        self.count_label.setObjectName("ModernCountChip")
        header_row.addWidget(self.title_label)
        header_row.addSpacing(8)
        header_row.addWidget(self.count_label)
        header_row.addStretch()
        layout.addLayout(header_row)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search by...")
        self.search_box.setObjectName("ModernSearchBox")
        self.search_box.setClearButtonEnabled(True)
        self.search_box.setFixedHeight(28)
        self.search_box.textChanged.connect(self._apply_search)
        self._search_field = "Name"
        self.search_options_button = QToolButton()
        self.search_options_button.setText("Name")
        self.search_options_button.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextOnly
        )
        self.search_options_button.setMinimumWidth(96)
        self.search_options_button.setFixedHeight(24)
        self.search_options_button.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup
        )
        self.search_options_button.setToolTip(
            self.tr("Search by which field the pattern matches")
        )
        search_row = QHBoxLayout()
        search_row.addWidget(self.search_box, 1)
        search_row.addWidget(self.search_options_button)
        options_menu = QMenu(self.search_options_button)
        for field in (
            "Name",
            "Tags",
            "PackageId",
            "Author(s)",
            "PublishedFileId",
            "Version",
        ):
            action = options_menu.addAction(field)
            action.setCheckable(True)
            action.setChecked(field == self._search_field)
            if field == self._search_field:
                options_menu.setDefaultAction(action)

        def _pick(field_action: QAction) -> None:
            self._search_field = field_action.text()
            self.search_options_button.setText(field_action.text())
            for act in options_menu.actions():
                act.setChecked(act is field_action)
            self._apply_search(self.search_box.text())

        options_menu.triggered.connect(_pick)
        self.search_options_button.setMenu(options_menu)

        # The spyglass filter button: the FilterPanel choosing which mods to
        # show (sources / tags), driving the table's visibility
        self._sort_descending = False
        self.sort_button = QToolButton()
        self.sort_button.setText("Asc")
        self.sort_button.setCheckable(True)
        self.sort_button.setToolTip(
            self.tr("Toggle ascending / descending order within groups")
        )
        self.sort_button.clicked.connect(self._toggle_sort)
        self.filter_button = FilterButton(self)
        self.filter_button.filter_panel.filters_changed.connect(self._apply_search)
        search_row.addWidget(self.sort_button)
        search_row.addWidget(self.filter_button)
        layout.addLayout(search_row)

        self.tree = ModernModsTree(self.settings)
        # Ctrl-click, shift-click, drag-band: the classic list's
        # ExtendedSelection, mirrored here
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.setRootIsDecorated(True)
        self.tree.setUniformRowHeights(True)
        # Tighter indentation pulls rows closer to the checkboxes
        self.tree.setIndentation(8)
        # Icon size matches the combined indicator pair's native 40x20 so
        # the classic icons render at the same size as the right panel's
        self.tree.setIconSize(QSize(40, 20))
        # Striped or plain rows, chosen in Theme Settings (Modern UI).
        # The QSS ships the alternate color; it shows only when enabled.
        self.tree.setAlternatingRowColors(self.settings.modern_ui_striped_rows)
        self.tree.setAnimated(False)
        self.tree.itemChanged.connect(self._on_item_changed)
        self.tree.currentItemChanged.connect(self._on_current_changed)
        # Any click on a category divider toggles it - not just the arrow
        self.tree.itemClicked.connect(self._on_item_clicked)
        # Classic right-click actions: delegate to the source list's own
        # context menu so upstream's full menu (open folder, rules, tags,
        # Steam actions, warning toggles) arrives without duplication.
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self.tree)

        # Coalesce refresh storms from bulk list operations (sort, import,
        # metadata rebuild) into one rebuild.
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(200)
        self._refresh_timer.timeout.connect(self.refresh)

        # Header-click sorting: which column, and which direction
        self._sort_column = COL_NAME
        self._sort_descending = False
        self.tree.header().sectionClicked.connect(self._on_header_clicked)

        # Folder sizes walk off the GUI thread; rows fill in progressively
        self._folder_sizes: dict[str, int] = {}
        self._folder_size_requested: set[str] = set()
        self._folder_size_seq = 0
        self._folder_size_thread = QThread(self)
        self._folder_size_worker = FolderSizeRequestWorker()
        self._folder_size_worker.moveToThread(self._folder_size_thread)
        self._folder_size_worker.result.connect(self._on_folder_size_result)
        self._folder_size_thread.start()
        # Stop the walk before Qt tears the thread down on app close,
        # or the destroyed-while-running abort kills the exit
        app_instance = QApplication.instance()
        if app_instance is not None:
            app_instance.aboutToQuit.connect(self._stop_folder_size_thread)

        for list_widget in (
            self.mods_panel.active_mods_list,
            self.mods_panel.inactive_mods_list,
        ):
            list_widget.list_update_signal.connect(
                lambda _uuid: self.schedule_refresh()
            )
            list_widget.refresh_signal.connect(self.schedule_refresh)
            # Warning toggles (menu or classic row icons) recalculate
            # without touching the lists - refresh the Default columns
            list_widget.recalculate_warnings_signal.connect(self.schedule_refresh)

        self._setup_columns()
        self.refresh()

    def _on_default_warning_clicked(
        self, index: QModelIndex | QPersistentModelIndex
    ) -> None:
        """A click on a Default column's warning slot toggles that mod's
        warning - the classic icon click, through the owning list."""
        source_item = index.data(Qt.ItemDataRole.UserRole + 1)
        data = (
            source_item.data(Qt.ItemDataRole.UserRole)
            if source_item is not None
            else None
        )
        if data is None:
            return
        uuid = data.path
        mod = self.mods_panel.metadata_controller.get_mod(uuid)
        package_id = str(getattr(mod, "package_id", "") or "")
        if not package_id:
            return
        source_list = (
            self.mods_panel.active_mods_list
            if data.list_type == "Active"
            else self.mods_panel.inactive_mods_list
        )
        source_list.toggle_warning(package_id, uuid)
        self.schedule_refresh()

    def _stop_folder_size_thread(self) -> None:
        self._folder_size_thread.quit()
        # Bounded wait: quit() lands after the current single-folder walk
        # finishes - but a walk over a huge folder can outlive any sane
        # timeout. terminate() here made Qt abort the teardown (exit
        # 2816), and an unbounded wait() left idle processes holding
        # the single-instance lock. The worker owns no unsaved state, so
        # if it is still walking, end the process immediately: the OS
        # releases the lock and reaps everything cleanly.
        if not self._folder_size_thread.wait(3000):
            logger.warning("Folder size thread still walking at exit; ending process")
            os._exit(0)

    # ------------------------------------------------------------------
    # Columns

    def _setup_columns(self) -> None:
        """Build the column set from her six Active Columns slots."""
        slots = [str(s) for s in (self.settings.active_columns or [])[:6]]
        while len(slots) < 6:
            slots.append("None")
        slot_columns = [s for s in slots if s != "None"]

        signature = tuple(slot_columns)
        if signature == getattr(self, "_columns_signature", None):
            return
        self._columns_signature = signature

        self._slot_columns = slot_columns
        self.tree.setColumnCount(2 + len(slot_columns))
        headers = ["", "Name"] + slot_columns
        self.tree.setHeaderLabels(headers)

        header = self.tree.header()
        # Slot columns share the remaining width EQUALLY and the last one
        # reaches the panel's edge. Name stays fixed-but-draggable.
        header.setSectionsClickable(True)
        header.setStretchLastSection(True)
        header.setSectionResizeMode(COL_CHECK, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(COL_CHECK, 34)
        header.setSectionResizeMode(COL_NAME, QHeaderView.ResizeMode.Interactive)
        header.resizeSection(COL_NAME, 340)
        # Fresh delegates per column build; kept referenced so Qt doesn't
        # garbage-collect them mid-paint
        self._delegates: list[CenteredIconDelegate] = []
        self._check_delegate = CheckDelegate(self.tree)
        self.tree.setItemDelegateForColumn(COL_CHECK, self._check_delegate)
        self._default_columns: list[int] = []
        self._name_delegate = ModernNameDelegate(self.tree, settings=self.settings)
        self.tree.setItemDelegateForColumn(COL_NAME, self._name_delegate)
        for offset, name in enumerate(slot_columns):
            column = 2 + offset
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Stretch)
            if name == "Default":
                delegate = CenteredIconDelegate(
                    self.tree,
                    on_warning_click=self._on_default_warning_clicked,
                )
                self.tree.setItemDelegateForColumn(column, delegate)
                self._delegates.append(delegate)
                self.tree.headerItem().setToolTip(
                    column,
                    self.tr(
                        "RimSort's bundled warnings, incompatibilities "
                        "and errors (the Default column)"
                    ),
                )
            else:
                # All data columns are live; no placeholder text needed
                pass
        # EVERY Default slot shows the classic status indicators, even
        # when the same slot name is set more than once
        self._default_columns = [
            2 + offset for offset, name in enumerate(slot_columns) if name == "Default"
        ]
        self._slot_col_index = {
            name: 2 + offset for offset, name in enumerate(slot_columns)
        }

    # ------------------------------------------------------------------
    # Population

    def schedule_refresh(self) -> None:
        self._refresh_timer.start()

    def refresh(self) -> None:
        # Column slots may have changed across a restart; re-check
        self._setup_columns()

        self._populating = True
        try:
            self.tree.clear()
            self._uuid_rows.clear()
            self._cats = self._ordered_categories()

            rows: list[tuple[str, CustomListWidgetItem, bool]] = []
            seen: set[str] = set()
            for source_is_active, list_widget in (
                (True, self.mods_panel.active_mods_list),
                (False, self.mods_panel.inactive_mods_list),
            ):
                for item in list_widget.get_all_mod_list_items():
                    data = item.data(Qt.ItemDataRole.UserRole)
                    if data is None:
                        continue
                    uuid = data.path
                    if uuid in seen:
                        continue
                    seen.add(uuid)
                    rows.append((uuid, item, source_is_active))

            groups: dict[str, QTreeWidgetItem] = {}
            for category in self._cats:
                groups[category["name"]] = self._make_group_row(category)
            self._current_groups = groups
            self._fallback_category = {
                "name": UNCATEGORIZED,
                "color": "#5e6f88",
                "mods": [],
            }
            if UNCATEGORIZED not in groups:
                groups[UNCATEGORIZED] = self._make_group_row(self._fallback_category)

            active_count = 0
            for uuid, source_item, is_active in rows:
                if is_active:
                    active_count += 1
                mod = self.mods_panel.metadata_controller.get_mod(uuid)
                display_name = getattr(mod, "name", None) or uuid
                package_id = str(getattr(mod, "package_id", "") or "")
                category = self._category_for(display_name, package_id)
                row = self._make_mod_row(
                    uuid, source_item, is_active, display_name, category
                )
                self._uuid_rows[uuid] = row

            for name, group in groups.items():
                # Child rows are attached by now; sort within the group
                # (sorting never reorders the right panel) and stamp the
                # live count
                self._apply_group_sort(group)
                group.setText(1, f"{name}    {group.childCount()}")
                self.tree.addTopLevelItem(group)
            self.tree.expandAll()
            self._update_counts(active_count)
            self._queue_folder_sizes()
            self._apply_search(self.search_box.text())
            self.refresh_finished.emit()
        finally:
            self._populating = False

    def _ordered_categories(self) -> list[dict[str, Any]]:
        raw = self.categories.get("categories", [])
        ordered = []
        seen: set[str] = set()
        for category in raw:
            name = str(category.get("name", "")).strip()
            if not name or name in seen:
                continue
            seen.add(name)
            ordered.append(
                {
                    "name": name,
                    "color": str(category.get("color", "") or "#93a4bd"),
                    "mods": [str(m).casefold() for m in category.get("mods", [])],
                }
            )
        return ordered

    def _make_group_row(self, category: dict[str, Any]) -> QTreeWidgetItem:
        group = QTreeWidgetItem()
        group.setText(1, category["name"])
        group.setFlags(Qt.ItemFlag.ItemIsEnabled)
        group.setData(COL_NAME, Qt.ItemDataRole.UserRole, "group")
        group.setData(COL_NAME, Qt.ItemDataRole.UserRole + 1, category["name"])
        group.setData(
            COL_NAME,
            Qt.ItemDataRole.UserRole + 4,
            QColor(category["color"]),
        )
        return group

    def _category_for(self, display_name: str, package_id: str) -> dict[str, Any]:
        key_name = display_name.casefold()
        key_pid = package_id.casefold()
        for category in self._cats:
            if key_name in category["mods"] or (
                key_pid and key_pid in category["mods"]
            ):
                return category
        return self._fallback_category

    def _make_mod_row(
        self,
        uuid: str,
        source_item: CustomListWidgetItem,
        is_active: bool,
        display_name: str,
        category: dict[str, Any],
    ) -> QTreeWidgetItem:
        group = self._current_groups[category["name"]]
        row = QTreeWidgetItem(group)
        row.setFlags(
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsUserCheckable
            | Qt.ItemFlag.ItemIsSelectable
        )
        row.setCheckState(
            COL_CHECK, Qt.CheckState.Checked if is_active else Qt.CheckState.Unchecked
        )
        row.setText(COL_NAME, display_name)
        mod = self.mods_panel.metadata_controller.get_mod(uuid)
        data = source_item.data(Qt.ItemDataRole.UserRole)
        # Source indicators beside the name, mirroring the classic row's
        # order: git / steamcmd first, then the source icon by mod type,
        # then C#/XML last (when the type filter is on)
        type_icons = []
        mod_type = getattr(mod, "mod_type", None)
        if mod_type == ModType.GIT:
            type_icons.append(ModListIcons.git_icon())
        elif mod_type == ModType.STEAM_CMD:
            type_icons.append(ModListIcons.steamcmd_icon())
        elif mod_type == ModType.LUDEON:
            type_icons.append(ModListIcons.ludeon_icon())
        elif mod_type == ModType.LOCAL:
            type_icons.append(ModListIcons.local_icon())
        elif mod_type == ModType.STEAM_WORKSHOP:
            type_icons.append(ModListIcons.steam_icon())
        if self.settings.mod_type_filter:
            if getattr(mod, "c_sharp_mod", False):
                type_icons.append(ModListIcons.csharp_icon())
            else:
                type_icons.append(ModListIcons.xml_icon())
        if type_icons:
            row.setIcon(COL_NAME, self._combine_icons(type_icons))
        # Per-symbol tooltips, aligned with the combine order; the mod
        # tooltip answers for the rest of the column
        icon_tooltips = []
        if mod_type == ModType.GIT:
            icon_tooltips.append("Local mod that contains a git repository")
        elif mod_type == ModType.STEAM_CMD:
            icon_tooltips.append("Local mod that can be used with SteamCMD")
        elif mod_type == ModType.LUDEON:
            icon_tooltips.append("Official RimWorld content by Ludeon Studios")
        elif mod_type == ModType.LOCAL:
            icon_tooltips.append("Installed locally")
        elif mod_type == ModType.STEAM_WORKSHOP:
            icon_tooltips.append("Subscribed via Steam")
        if self.settings.mod_type_filter:
            if getattr(mod, "c_sharp_mod", False):
                icon_tooltips.append("Contains custom C# assemblies (custom code)")
            else:
                icon_tooltips.append("Contains custom content (textures / XML)")
        row.setData(COL_NAME, Qt.ItemDataRole.UserRole + 3, icon_tooltips)
        # The classic row's hover tooltip, composed from real metadata
        row.setToolTip(
            COL_NAME,
            self._build_name_tooltip(uuid, data, mod),
        )
        # Real data columns: each slot renders its metadata field and
        # carries a sort key for header-click sorting
        for column_name in _DATA_COLUMNS:
            column = self._slot_col_index.get(column_name)
            if column is None:
                continue
            text, sort_key = self._column_text(uuid, column_name, data, mod)
            row.setText(column, text)
            row.setData(column, Qt.ItemDataRole.UserRole + 2, sort_key)
        # The Default column's delegate reads uuid + source item from its
        # OWN index roles - they must be stored on EVERY Default column,
        # or every indicator lookup returns empty and only dashes paint
        # ("Default" is not in _DATA_COLUMNS - this can't live in that loop)
        for column in self._default_columns:
            row.setData(column, Qt.ItemDataRole.UserRole, uuid)
            row.setData(column, Qt.ItemDataRole.UserRole + 1, source_item)
        # Category is a SLOT column: plain selectable text
        # fills whichever slot is named "Category", if any - its color
        # plus the dividers are all the middle panel needs
        category_column = self._slot_col_index.get("Category")
        if category_column is not None:
            color = QColor(category["color"])
            row.setText(category_column, category["name"])
            row.setForeground(category_column, color)
            row.setToolTip(
                category_column,
                self.tr(f"Category: {category['name']}"),
            )
        # The ONLY functional slot: Default (RimSort's bundled status).
        # Mirrors the classic row bar's indicator pair - warning for
        # warnings/mismatch, error for errors/invalid - side by side in
        # one cell, with a combined hover tooltip. Fills EVERY Default
        # column when the same slot name is set more than once.
        if self._default_columns:
            data = source_item.data(Qt.ItemDataRole.UserRole)
            if data is not None:
                self._apply_status_icons(row, data)
        row.setData(COL_NAME, Qt.ItemDataRole.UserRole, uuid)
        row.setData(COL_NAME, Qt.ItemDataRole.UserRole + 1, source_item)
        return row

    def _apply_status_icons(
        self, row: QTreeWidgetItem, data: CustomListWidgetItemMetadata
    ) -> None:
        """The Default column's indicator pair for one mod. Respects
        warning_toggled: her Toggle warning(s) hides the warning side
        (error indicators stay - invalid mods shouldn't go silent)."""
        if not self._default_columns:
            return
        if not (
            data.errors_warnings
            or data.errors
            or data.warnings
            or data.invalid
            or data.mismatch
        ):
            return
        icons = []
        tooltip_parts = []
        if data.invalid or data.errors:
            icons.append(ModListIcons.error_icon())
            tooltip_parts.append(data.errors or data.errors_warnings)
        show_warning = (data.mismatch or data.warnings) and not data.warning_toggled
        if show_warning:
            icons.append(ModListIcons.warning_icon())
            tooltip_parts.append(data.warnings or "Version mismatch detected")
        if icons:
            combined = self._combine_icons(icons)
            for column in self._default_columns:
                row.setIcon(column, combined)
                row.setToolTip(column, "\n".join(tooltip_parts))

    def _column_text(
        self, uuid: str, column_name: str, data: object, mod: object
    ) -> tuple[str, int | str]:
        """(display text, sort key) for a data column. Sort keys are
        numeric where the field is numeric (timestamps, bytes)."""
        if column_name == "Mod/Game Version":
            mod_ver = str(
                getattr(mod, "mod_version", "") or getattr(mod, "version", "") or "-"
            )
            supported = getattr(mod, "supported_versions", None) or set()
            game = max(supported) if supported else "-"
            # Game version sorts first
            return f"{mod_ver} / {game}", f"{game}|{mod_ver}".casefold()
        if column_name == "Author":
            authors = getattr(mod, "authors", None) or []
            text = ", ".join(str(a) for a in authors)
            return (text or "-"), text.casefold()
        if column_name == "Modified Time/Workshop Updated":
            ts = getattr(data, "updated_timestamp", None) or getattr(
                mod, "internal_time_touched", -1
            )
            ts = int(ts) if ts else -1
            if ts < 0:
                return "-", -1
            text = datetime.fromtimestamp(ts).strftime(  # noqa: DTZ006
                "%Y-%m-%d %H:%M"
            )
            return text, ts
            return text, ts
        if column_name == "Folder Size":
            size = self._folder_sizes.get(uuid)
            if size is None:
                return "-", -1
            return self._human_size(size), size
        if column_name == "Version":
            text = str(
                getattr(mod, "mod_version", "") or getattr(mod, "version", "") or "-"
            )
            return text, text.casefold()
        if column_name == "PackageId":
            text = str(getattr(mod, "package_id", "") or "-")
            return text, text.casefold()
        return "-", 0

    @staticmethod
    def _human_size(num_bytes: int) -> str:
        value = float(num_bytes)
        for unit in ("B", "KB", "MB", "GB"):
            if value < 1024 or unit == "GB":
                return f"{value:.1f} {unit}"
            value /= 1024
        return f"{value:.1f} GB"

    def _apply_group_sort(self, group: QTreeWidgetItem | None) -> None:
        if group is None:
            return
        """Sort one group's children by the active sort column, within the
        group only (the right panel's order never moves)."""
        column = self._sort_column

        def sort_key(child: QTreeWidgetItem) -> tuple[int, str, float]:
            if column == COL_NAME:
                return (0, child.text(COL_NAME).casefold(), 0.0)
            value = child.data(column, Qt.ItemDataRole.UserRole + 2)
            if isinstance(value, (int, float)):
                return (1, "", float(value))
            if isinstance(value, str) and value:
                return (0, value.casefold(), 0.0)
            return (0, child.text(column).casefold(), 0.0)

        children = group.takeChildren()
        children.sort(key=sort_key, reverse=self._sort_descending)
        group.addChildren(children)

    def _on_header_clicked(self, column: int) -> None:
        header_name = self.tree.headerItem().text(column)
        if column == COL_CHECK or header_name == "Default" or header_name == "Category":
            return
        if column == self._sort_column:
            self._sort_descending = not self._sort_descending
        else:
            self._sort_column = column
            self._sort_descending = False
        self._sync_sort_button()
        for index in range(self.tree.topLevelItemCount()):
            self._apply_group_sort(self.tree.topLevelItem(index))

    def _sync_sort_button(self) -> None:
        self.sort_button.setText("Desc" if self._sort_descending else "Asc")
        self.sort_button.setChecked(self._sort_descending)

    def _queue_folder_sizes(self) -> None:
        if "Folder Size" not in self._slot_col_index:
            return
        for uuid in self._uuid_rows:
            if uuid in self._folder_size_requested:
                continue
            self._folder_size_requested.add(uuid)
            self._folder_size_seq += 1
            self._folder_size_worker.requested.emit(uuid, self._folder_size_seq)

    def _on_folder_size_result(self, uuid: str, _request_id: int, size: object) -> None:
        size = int(cast("int", size) or 0)
        self._folder_sizes[uuid] = size
        row = self._uuid_rows.get(uuid)
        column = self._slot_col_index.get("Folder Size")
        if row is None or column is None:
            return
        row.setText(column, self._human_size(size))
        row.setData(column, Qt.ItemDataRole.UserRole + 2, size)

    def _build_name_tooltip(self, uuid: str, data: object, mod: object) -> str:
        """The classic row's hover text, composed from real metadata
        (mirrors ModListItemInner.get_tool_tip_text without heavy IO)."""
        name = getattr(mod, "name", None) or "Not specified"
        tags = getattr(data, "mod_tags", None) or []
        tags_text = ", ".join(str(t) for t in tags) if tags else "None"
        authors = getattr(mod, "authors", None) or []
        authors_text = (
            ", ".join(str(a) for a in authors) if authors else "Not specified"
        )
        package_id = str(getattr(mod, "package_id", "") or "Not specified")
        mod_version = str(getattr(mod, "mod_version", "") or "Not specified")
        supported = getattr(mod, "supported_versions", None) or set()
        supported_text = (
            ", ".join(sorted(str(s) for s in supported))
            if supported
            else "Not specified"
        )
        mod_path = str(getattr(mod, "mod_path", "") or "Not specified")
        folder_size = self._folder_sizes.get(uuid)
        size_text = (
            self._human_size(folder_size)
            if folder_size is not None
            else "Not available"
        )
        lines = [
            f"Mod: {name}",
            f"Tags: {tags_text}",
            f"Authors: {authors_text}",
            f"PackageID: {package_id}",
            f"Mod Version: {mod_version}",
            f"Supported Versions: {supported_text}",
            f"Path: {mod_path}",
            f"Folder Size: {size_text}",
        ]
        return "\n".join(lines)

    @staticmethod
    def _combine_icons(icons: list[QIcon]) -> QIcon:
        """Paint the classic indicator pair side by side in one cell."""
        size = 20
        pixmap = QPixmap(size * len(icons), size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        for offset, icon in enumerate(icons):
            icon.paint(painter, offset * size, 0, size, size)
        painter.end()
        return QIcon(pixmap)

    def _update_counts(self, active_count: int) -> None:
        total = len(self._uuid_rows)
        self.count_label.setText(f"{active_count} active of {total}")
        self.active_count_changed.emit(active_count)

    # ------------------------------------------------------------------
    # Interaction

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if self._populating or column != COL_CHECK:
            return
        uuid = item.data(COL_NAME, Qt.ItemDataRole.UserRole)
        if not uuid:
            return
        source_item = item.data(COL_NAME, Qt.ItemDataRole.UserRole + 1)
        if source_item is None:
            return
        want_active = item.checkState(COL_CHECK) == Qt.CheckState.Checked
        data = source_item.data(Qt.ItemDataRole.UserRole)
        if data is None:
            return
        is_active = data.list_type == "Active"
        if want_active == is_active:
            return
        # Bulk: the toggled checkbox applies to the WHOLE selection -
        # every ctrl/shift-selected mod moves in the same direction
        # (multi-select must stay functional)
        self._move_mod(uuid, source_item, to_active=want_active)
        for selected_row in self.tree.selectedItems():
            if selected_row is item:
                continue
            row_uuid = selected_row.data(COL_NAME, Qt.ItemDataRole.UserRole)
            if not row_uuid or row_uuid == "group":
                continue
            row_source = selected_row.data(COL_NAME, Qt.ItemDataRole.UserRole + 1)
            if row_source is None or isinstance(row_source, str):
                continue
            row_data = row_source.data(Qt.ItemDataRole.UserRole)
            if row_data is None:
                continue
            if (row_data.list_type == "Active") != want_active:
                selected_row.setCheckState(
                    COL_CHECK,
                    Qt.CheckState.Checked if want_active else Qt.CheckState.Unchecked,
                )
                self._move_mod(row_uuid, row_source, to_active=want_active)

    def _move_mod(self, uuid: str, source_item: object, to_active: bool) -> None:
        active = self.mods_panel.active_mods_list
        inactive = self.mods_panel.inactive_mods_list
        src, dst = (inactive, active) if to_active else (active, inactive)
        if uuid not in src.paths:
            return
        index = src.paths.index(uuid)
        item = src.takeItem(index)
        src.paths.pop(index)
        dst.addItem(item)
        data = item.data(Qt.ItemDataRole.UserRole)
        if data is not None:
            data["list_type"] = "Active" if to_active else "Inactive"
            item.setData(Qt.ItemDataRole.UserRole, data)
        if to_active:
            self.mods_panel.update_count(list_type="Active")
        else:
            self.mods_panel.update_count(list_type="Inactive")
        self._update_counts(len(active.paths))

    def _on_current_changed(
        self, current: QTreeWidgetItem | None, _previous: QTreeWidgetItem | None
    ) -> None:
        if current is None or self._populating:
            return
        uuid = current.data(COL_NAME, Qt.ItemDataRole.UserRole)
        if not uuid or uuid == "group":
            # Group rows carry the category name at the item slot; the
            # info panel only accepts real CustomListWidgetItems
            return
        source_item = current.data(COL_NAME, Qt.ItemDataRole.UserRole + 1)
        if source_item is not None and not isinstance(source_item, str):
            self.mod_info_signal.emit(uuid, source_item)

    def _search_text_for(self, uuid: str, row: QTreeWidgetItem) -> str:
        """The mod's text for the chosen search field, from real metadata."""
        field = getattr(self, "_search_field", "Name")
        if field == "Name":
            return row.text(COL_NAME)
        mod = self.mods_panel.metadata_controller.get_mod(uuid)
        source_item = row.data(COL_NAME, Qt.ItemDataRole.UserRole + 1)
        data = source_item.data(Qt.ItemDataRole.UserRole) if source_item else None
        if field == "Tags":
            tags = getattr(data, "mod_tags", None) or []
            return " ".join(str(t) for t in tags)
        if mod is None:
            return ""
        if field == "PackageId":
            return str(getattr(mod, "package_id", "") or "")
        if field == "Author(s)":
            authors = getattr(mod, "authors", None) or []
            return " ".join(str(a) for a in authors)
        if field == "PublishedFileId":
            return str(getattr(mod, "published_file_id", "") or "")
        if field == "Version":
            return str(getattr(mod, "mod_version", "") or "")
        return ""

    def _toggle_sort(self, checked: bool) -> None:
        self._sort_descending = checked
        self.sort_button.setText("Desc" if checked else "Asc")
        self.refresh()

    def _on_item_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        if item.data(COL_NAME, Qt.ItemDataRole.UserRole) == "group":
            item.setExpanded(not item.isExpanded())

    def _apply_search(self, text: str) -> None:
        needle = text.casefold().strip()
        filter_state = self.filter_button.filter_panel.filter_state
        sources_locked = filter_state.sources != FilterState.ALL_SOURCES
        for uuid, row in self._uuid_rows.items():
            haystack = self._search_text_for(uuid, row)
            hidden = bool(needle) and needle not in haystack.casefold()
            if not hidden and sources_locked:
                hidden = self._fails_source_filter(uuid, filter_state)
            if not hidden:
                source_item = row.data(COL_NAME, Qt.ItemDataRole.UserRole + 1)
                data = (
                    source_item.data(Qt.ItemDataRole.UserRole) if source_item else None
                )
                mod_tags = set(getattr(data, "mod_tags", None) or [])
                hidden = not filter_state.matches_tags(mod_tags)
            row.setHidden(hidden)
        for index in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(index)
            if group is None:
                continue
            any_visible = any(
                (child := group.child(i)) is not None and not child.isHidden()
                for i in range(group.childCount())
            )
            group.setHidden(bool(needle) and not any_visible)

    def _fails_source_filter(self, uuid: str, filter_state: FilterState) -> bool:
        """Mirror the classic source mapping: a mod whose source is not in
        the FilterPanel's enabled set is hidden."""
        mod = self.mods_panel.metadata_controller.get_mod(uuid)
        mod_type = getattr(mod, "mod_type", None)
        _type_to_source = {
            ModType.LUDEON: "expansion",
            ModType.STEAM_WORKSHOP: "workshop",
            ModType.LOCAL: "local",
            ModType.GIT: "local",
            ModType.STEAM_CMD: "local",
            ModType.UNKNOWN: "local",
        }
        source = _type_to_source.get(cast("ModType", mod_type), "local")
        return source not in filter_state.sources

    def _on_context_menu(self, pos: QPoint) -> None:
        """The center's menu = the source list's FULL classic menu (tags,
        open URL, Steam actions, translations, deletion, miscellaneous,
        workshop options...) with the right-panel's list-level options
        filtered out ("Add divider here"), plus the center's own actions
        appended (her menu list + Add mod to category)."""
        item = self.tree.itemAt(pos)
        if item is None:
            return
        uuid = item.data(COL_NAME, Qt.ItemDataRole.UserRole)
        is_group = uuid == "group"
        category_name = item.data(COL_NAME, Qt.ItemDataRole.UserRole + 1)
        # Right-clicking a row OUTSIDE the selection does not select it
        # in Qt - make it the sole selection, so the mirrored actions
        # never target an outdated selection
        if not is_group and item not in self.tree.selectedItems():
            self.tree.clearSelection()
            item.setSelected(True)

        if is_group or not uuid:
            # Group rows: the center-only actions, no delegation
            menu = QMenu()
            add_divider_action = menu.addAction("Add category divider")
            change_color_action = menu.addAction("Change category divider color")
            match_colors_action = menu.addAction("Match colors to categories")
            if category_name == UNCATEGORIZED:
                change_color_action.setEnabled(False)
            chosen = menu.exec(QCursor.pos())
            if chosen == add_divider_action:
                self._add_category_divider()
            elif chosen == change_color_action:
                self._change_category_color(category_name)
            elif chosen == match_colors_action:
                self._match_colors_to_categories()
            return

        source_item = item.data(COL_NAME, Qt.ItemDataRole.UserRole + 1)
        if source_item is None or isinstance(source_item, str):
            return
        data = source_item.data(Qt.ItemDataRole.UserRole)
        if data is None:
            return
        source_list = (
            self.mods_panel.active_mods_list
            if data.list_type == "Active"
            else self.mods_panel.inactive_mods_list
        )
        mod = self.mods_panel.metadata_controller.get_mod(uuid)
        package_id = str(getattr(mod, "package_id", "") or "")

        # Mirror the FULL center selection into the source list: the
        # classic menu handler reads the list's selectedItems(), so
        # every ctrl/shift-selected mod gets the action, not just the
        # clicked one. setCurrentItem FIRST (it resets the selection in
        # ExtendedSelection mode), then add the rest with setSelected.
        source_list.clearSelection()
        source_list.setCurrentItem(source_item)
        for selected_row in self.tree.selectedItems():
            row_uuid = selected_row.data(COL_NAME, Qt.ItemDataRole.UserRole)
            if not row_uuid or row_uuid == "group":
                continue
            row_source = selected_row.data(COL_NAME, Qt.ItemDataRole.UserRole + 1)
            if row_source is not None and not isinstance(row_source, str):
                row_source.setSelected(True)

        captured: dict[str, Any] = {"result": None}
        center_actions: dict[object, tuple[str, str | None]] = {}
        original_exec_ = QMenu.exec_
        original_exec = QMenu.exec

        def patched_exec(menu_self: QMenu, *args: object, **kwargs: object) -> object:
            for act in list(menu_self.actions()):
                if act.text() in _BLOCKED_MENU_ACTIONS:
                    menu_self.removeAction(act)
            menu_self.addSeparator()
            assign_menu = menu_self.addMenu("Add mod to category")
            for category in self.categories.get("categories", []):
                name = str(category.get("name", ""))
                if not name:
                    continue
                center_actions[assign_menu.addAction(name)] = ("assign", name)
            menu_self.addSeparator()
            center_actions[menu_self.addAction("Add category divider")] = (
                "divider",
                None,
            )
            center_actions[menu_self.addAction("Change category divider color")] = (
                "color",
                category_name,
            )
            center_actions[menu_self.addAction("Match colors to categories")] = (
                "match",
                None,
            )
            result = original_exec_(menu_self, *args, **kwargs)
            captured["result"] = result
            return result

        # itemAt is pointed at the source item for the classic handler,
        # which reads the list's selection plus the item under the cursor
        source_list.itemAt = lambda _pos: source_item  # type: ignore[assignment,method-assign]
        QMenu.exec_ = patched_exec  # type: ignore[assignment]
        QMenu.exec = patched_exec  # type: ignore[assignment]
        try:
            event = QContextMenuEvent(
                QContextMenuEvent.Reason.Mouse,
                QPoint(0, 0),
                QCursor.pos(),
            )
            source_list.eventFilter(source_list, event)
        finally:
            del source_list.itemAt
            QMenu.exec_ = original_exec_  # type: ignore[method-assign]
            QMenu.exec = original_exec  # type: ignore[method-assign]

        result = captured.get("result")
        if result is None or result not in center_actions:
            return
        kind, payload = center_actions[result]
        if kind == "assign":
            # Assign EVERY selected mod, not just the clicked one:
            # menu actions work on the selected group
            selected_ids: list[str] = []
            for selected_row in self.tree.selectedItems():
                row_uuid = selected_row.data(COL_NAME, Qt.ItemDataRole.UserRole)
                if not row_uuid or row_uuid == "group":
                    continue
                row_mod = self.mods_panel.metadata_controller.get_mod(row_uuid)
                row_pid = str(getattr(row_mod, "package_id", "") or "")
                if row_pid:
                    selected_ids.append(row_pid)
            if not selected_ids:
                selected_ids = [package_id] if package_id else []
            for pid in selected_ids:
                self._assign_mod_to_category(payload, pid)
        elif kind == "divider":
            self._add_category_divider()
        elif kind == "color":
            self._change_category_color(payload)
        elif kind == "match":
            self._match_colors_to_categories()

    def _assign_mod_to_category(
        self, category_name: str | None, package_id: str
    ) -> None:
        if not category_name or not package_id:
            return
        folded = package_id.casefold()
        for category in self.categories.get("categories", []):
            mods = category.setdefault("mods", [])
            if str(category.get("name", "")) == category_name:
                # A mod belongs to one category: the destination gains it
                if folded not in [str(m).casefold() for m in mods]:
                    mods.append(package_id)
            else:
                # Every other category loses it, or _category_for keeps
                # returning the older first match
                category["mods"] = [m for m in mods if str(m).casefold() != folded]
        if save_categories(self.settings.categories_file, self.categories):
            self.refresh()

    def _add_category_divider(self) -> None:
        name, ok = QInputDialog.getText(self, "Add category divider", "Category name:")
        name = (name or "").strip()
        if not ok or not name:
            return
        existing = {
            str(c.get("name", "")).casefold()
            for c in self.categories.get("categories", [])
        }
        if name.casefold() in existing:
            return
        self.categories.setdefault("categories", []).append(
            {"name": name, "color": "#5e6f88", "mods": []}
        )
        if save_categories(self.settings.categories_file, self.categories):
            self.refresh()

    def _change_category_color(self, category_name: str | None) -> None:
        if not category_name or category_name == UNCATEGORIZED:
            return
        color = QColorDialog.getColor(parent=self)
        if not color.isValid():
            return
        for category in self.categories.get("categories", []):
            if str(category.get("name", "")) == category_name:
                category["color"] = color.name()
                break
        if save_categories(self.settings.categories_file, self.categories):
            self._sweep_category_color(category_name, color)
            self.refresh()

    def _iter_list_mods(
        self,
    ) -> Iterator[tuple[str, CustomListWidgetItemMetadata, dict[str, Any]]]:
        """(uuid, metadata, category) for every mod in both lists,
        with the category resolved from package id and display name."""
        for list_widget in (
            self.mods_panel.active_mods_list,
            self.mods_panel.inactive_mods_list,
        ):
            for item in list_widget.get_all_mod_list_items():
                data = item.data(Qt.ItemDataRole.UserRole)
                if data is None:
                    continue
                uuid = data.path
                yield uuid, data, self.resolve_category(uuid)

    def resolve_category(self, uuid: str) -> dict[str, Any]:
        """The category a mod belongs to, by its metadata lookup."""
        mod = self.mods_panel.metadata_controller.get_mod(uuid)
        display_name = getattr(mod, "name", None) or uuid
        package_id = str(getattr(mod, "package_id", "") or "")
        return self._category_for(display_name, package_id)

    def _sweep_category_color(self, category_name: str, color: QColor) -> None:
        """Recolor every mod in the category, exactly like a manual color
        change: aux db updated, in-memory metadata updated, classic row
        widgets rebuilt so the right panel repaints."""
        matched: dict[str, CustomListWidgetItemMetadata] = {}
        for uuid, data, category in self._iter_list_mods():
            if category["name"] != category_name:
                continue
            data.mod_color = QColor(color)
            matched[uuid] = data

        self._apply_mod_colors({uuid: QColor(color) for uuid in matched}, matched)

    def _match_colors_to_categories(self) -> None:
        """Every mod takes its category's color across both lists;
        Uncategorized mods are cleared back to the default styling."""
        colors: dict[str, QColor | None] = {}
        datas: dict[str, CustomListWidgetItemMetadata] = {}
        for uuid, data, category in self._iter_list_mods():
            if category["name"] == UNCATEGORIZED:
                color = None
            else:
                color = QColor(category["color"])
            data.mod_color = color
            colors[uuid] = color
            datas[uuid] = data

        self._apply_mod_colors(colors, datas)

    def _apply_mod_colors(
        self,
        colors: dict[str, QColor | None],
        datas: dict[str, CustomListWidgetItemMetadata],
    ) -> None:
        """Persist a uuid->color mapping to the aux db and rebuild the
        affected classic row widgets."""
        if not colors:
            return
        auxdb_update_all_mod_colors(self.settings, colors)
        for uuid, data in datas.items():
            if data is None:
                continue
            source_list = (
                self.mods_panel.active_mods_list
                if data.list_type == "Active"
                else self.mods_panel.inactive_mods_list
            )
            source_list.rebuild_item_widget_from_uuid(uuid=uuid)
        self.schedule_refresh()

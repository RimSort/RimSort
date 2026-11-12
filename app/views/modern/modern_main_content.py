from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, cast

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app.utils.categories_utils import load_categories
from app.views.main_content_panel import MainContent
from app.views.modern.modern_mod_info_panel import ModernModInfoPanel
from app.views.modern.modern_mods_table import (
    GradientColor,
    ModernModsTable,
)
from app.views.mods_panel import ModListItemInner

if TYPE_CHECKING:
    from app.controllers.metadata_controller import MetadataController
    from app.models.settings import Settings
    from app.views.settings_dialog import SettingsDialog

_QSS_PATH = Path(__file__).parent / "modern.qss"


class ModernMainContent(MainContent):
    """The "RimSort - Modern UI" profile's main content panel.

    Subclasses the classic MainContent so every signal, controller hook, and
    attribute the main window wires keeps working. The classic pieces are
    re-homed into the modern three-panel layout:

    - LEFT: the existing ModInfoPanel (banner, metadata, notes, conflicts)
    - CENTER: ModernModsTable - all mods, checkbox activation, collapsible
      category groups from the shareable categories file, Default warnings
      column
    - RIGHT: the existing active_mods_list, drag-drop load order intact

    The classic ModsPanel container stays alive but unmounted: the inactive
    list remains the data backbone behind the table's checkboxes. The
    window's footer buttons (Refresh/Sort/Save/Run) act on the same lists
    and are untouched.
    """

    def __init__(
        self,
        settings: Settings,
        metadata_controller: MetadataController,
        show_settings_dialog: Callable[..., None] | None = None,
        settings_dialog: SettingsDialog | None = None,
    ) -> None:
        super().__init__(
            settings=settings,
            metadata_controller=metadata_controller,
            show_settings_dialog=show_settings_dialog,
            settings_dialog=settings_dialog,
        )
        self.categories = load_categories(settings.categories_file)
        self._swap_in_modern_info_panel()
        self._build_modern_shell()

    def _swap_in_modern_info_panel(self) -> None:
        """The left panel is SHARED code - the classic profile mounts
        ModInfoPanel unchanged. The Modern profile swaps in its own
        subclass instance (same attributes, same signals, restyled
        panel), so classic never sees the modern touches."""
        self.mod_info_panel = ModernModInfoPanel(
            settings=self.settings,
            metadata_controller=self.metadata_controller,
        )
        self.mod_info_container = QWidget()
        self.mod_info_container.setLayout(self.mod_info_panel.panel)
        self.mod_info_container.setMinimumWidth(280)

    def _build_modern_shell(self) -> None:
        # Keep the classic frame alive: it is unmounted, but the data
        # backbone still wires against parts of it, so the reference
        # must not drop.
        self._classic_frame = self.main_layout_frame

        shell = QFrame()
        shell.setObjectName("ModernMainPanel")
        # Claim the window's full vertical space - without this the shell
        # hugs its size hint and the bottom half of the window sits empty

        shell.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        if _QSS_PATH.exists():
            shell.setStyleSheet(_QSS_PATH.read_text(encoding="utf-8"))
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(8, 8, 8, 8)
        shell_layout.setSpacing(0)

        # All three sections resize by drag on their shared edges.
        shell_splitter = QSplitter(Qt.Orientation.Horizontal)
        shell_splitter.setChildrenCollapsible(False)
        shell_splitter.setHandleWidth(6)

        # LEFT: mod information panel (existing ModInfoPanel, re-parented)
        left_panel = QFrame()
        left_panel.setObjectName("ModernLeftPanel")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(10, 10, 10, 10)
        left_layout.setSpacing(6)
        left_layout.addWidget(self.mod_info_container, 1)

        # CENTER: the modern all-mods table
        center_panel = QFrame()
        center_panel.setObjectName("ModernCenterPanel")
        center_layout = QVBoxLayout(center_panel)
        center_layout.setContentsMargins(0, 0, 0, 0)
        self.mods_table = ModernModsTable(
            self.settings, self.mods_panel, self.categories
        )
        center_layout.addWidget(self.mods_table)

        # Center lower bar: the Use This Instead + Check Dependencies
        # buttons, pinned to the right half of the width and lifted off
        # the frame edges
        center_footer = QHBoxLayout()
        center_footer.setContentsMargins(0, 0, 6, 6)
        center_footer.setSpacing(4)
        center_footer.addStretch(2)
        for button in (
            self.mods_panel.use_this_instead_button,
            self.mods_panel.check_dependencies_button,
        ):
            button.setMinimumWidth(0)
            policy = button.sizePolicy()
            policy.setHorizontalPolicy(QSizePolicy.Policy.Expanding)
            button.setSizePolicy(policy)
            center_footer.addWidget(button, 1)
            center_footer.setStretchFactor(button, 1)
        center_layout.addLayout(center_footer)

        # RIGHT: the active list, load-order drag-drop intact
        right_panel = QFrame()
        right_panel.setObjectName("ModernRightPanel")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(10, 10, 10, 10)
        right_layout.setSpacing(6)
        right_header_row = QHBoxLayout()
        right_header = QLabel("Active")
        right_header.setObjectName("ModernPanelHeader")
        self.active_count_label = QLabel("")
        self.active_count_label.setObjectName("ModernPanelSublabel")
        right_header_row.addWidget(right_header)
        right_header_row.addSpacing(8)
        right_header_row.addWidget(self.active_count_label)
        right_header_row.addStretch()
        right_layout.addLayout(right_header_row)

        # Search row: the classic active-list search widgets re-homed, so
        # the regular RimSort search functions drive the list unchanged.
        # The tags FilterButton and the hide-filter eye stay unmounted.
        right_search_row = QHBoxLayout()
        right_search_row.setSpacing(4)
        right_search_row.addWidget(self.mods_panel.active_mods_search, 1)
        right_search_row.addWidget(self.mods_panel.active_mods_search_filter)
        # The field list drops the classic "Notes" option
        notes_index = self.mods_panel.active_mods_search_filter.findText("Notes")
        if notes_index >= 0:
            self.mods_panel.active_mods_search_filter.removeItem(notes_index)
        # The spyglass: already wired to the regular Active-list functions
        right_search_row.addWidget(self.mods_panel.active_filter_button)
        right_layout.addLayout(right_search_row)
        right_layout.addWidget(self.mods_panel.active_mods_list, 1)

        # Summary row: the classic Warnings / Errors / New / Updated
        # label pairs with RimSort's own icons, at the panel bottom
        summary_row = QHBoxLayout()
        summary_row.setSpacing(10)
        for icon_name, text_name in (
            ("warnings_icon", "warnings_text"),
            ("errors_icon", "errors_text"),
            ("new_icon", "new_text"),
            ("updated_icon", "updated_text"),
        ):
            icon = getattr(self.mods_panel, icon_name, None)
            text = getattr(self.mods_panel, text_name, None)
            if icon is not None:
                summary_row.addWidget(icon)
            if text is not None:
                summary_row.addWidget(text)
        summary_row.addStretch()
        right_layout.addLayout(summary_row)

        shell_splitter.addWidget(left_panel)
        shell_splitter.addWidget(center_panel)
        shell_splitter.addWidget(right_panel)
        shell_splitter.setSizes([320, 880, 320])
        shell_layout.addWidget(shell_splitter)

        # Wire the table into the same info-panel slot the classic lists use
        self.mods_table.mod_info_signal.connect(
            getattr(self, "_MainContent__mod_list_slot")  # noqa: B009
        )
        self.mods_table.active_count_changed.connect(
            lambda count: self.active_count_label.setText(f"{count}")
        )
        self.mods_table.refresh_finished.connect(self._tint_active_rows)
        self._sync_active_count()

        # The main window mounts main_layout_frame; hand it the shell
        self.main_layout_frame = shell

    def _sync_active_count(self) -> None:
        count = len(self.mods_panel.active_mods_list.paths)
        self.active_count_label.setText(f"{count}")

    def _tint_active_rows(self) -> None:
        """The same technique as the category dividers: the category
        color rides a GradientColor through the row's own mod_color
        state machine, and the styled-background flag lets the
        stylesheet paint the centered fade. Every repolish re-applies
        the gradient because mod_color.name() IS the gradient. Her
        ruling: the neon drains out - the color is muted first (the
        same helper that darkens the category blocks), so the rows
        read as a calm wash, not cyberpunk glow."""
        list_widget = self.mods_panel.active_mods_list
        for row in range(list_widget.count()):
            item = list_widget.item(row)
            if item is None:
                continue
            widget = list_widget.itemWidget(item)
            if not isinstance(widget, ModListItemInner):
                continue
            data = item.data(Qt.ItemDataRole.UserRole)
            if data is None:
                continue
            uuid = data.path
            category = self.mods_table.resolve_category(uuid)
            # Push the row content past the checkbox column, which the
            # widget body otherwise overlaps
            layout = widget.layout()
            if layout is not None:
                margins = layout.contentsMargins()
                layout.setContentsMargins(
                    4, margins.top(), margins.right(), margins.bottom()
                )
            # Slide the whole widget 2px left toward the checkboxes
            widget.move(widget.x() - 2, widget.y())
            widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            # A hand-picked color outranks the category: the row keeps
            # its own color and this pass touches only geometry
            if getattr(data, "mod_color_hand_picked", False):
                continue
            if category["name"] == "Uncategorized":
                data["mod_color"] = None
                widget.mod_color = None
                widget.setStyleSheet("")
                continue
            if self.settings.modern_ui_active_mod_style == "default":
                # DEFAULT: rows take the category color as a plain
                # QColor through RimSort's own mod_color path - gradient
                # CSS in this path rendered as black bars
                color = QColor(category["color"])
                data["mod_color"] = color
                widget.mod_color = color
                if widget.settings.color_background_instead_of_text_toggle:
                    widget.setStyleSheet(f"background: {color.name()};")
                else:
                    widget.setStyleSheet(f"color: {color.name()};")
                data.mod_color_plain = color
                continue
            # Keep the chosen color's own brightness; only drain the
            # excess saturation so bright colors stay bright
            hue, sat, val, _ = cast(
                tuple[float, float, float, float],
                QColor(category["color"]).getHsvF(),
            )
            if hue < 0:
                hue, sat = 0.0, 0.0
            color = QColor.fromHsvF(hue, min(sat * 0.75, 0.60), max(val, 0.45)).lighter(
                110
            )
            # The plain color rides along for the center table's rows
            data.mod_color_plain = color
            # Every style lands the plain color through the native
            # application first; the gradient is layered on top in the
            # same pass, never standing alone
            data["mod_color"] = color
            widget.mod_color = color
            if widget.settings.color_background_instead_of_text_toggle:
                widget.setStyleSheet(f"background: {color.name()};")
            else:
                widget.setStyleSheet(f"color: {color.name()};")
            if self.settings.modern_ui_active_mod_style != "double_gradient":
                continue
            # Centered fade: strongest at the middle of the row,
            # fading to nothing toward both edges
            css = (
                "qlineargradient(x1:0, y1:0, x2:1, y2:0,"
                f" stop:0 rgba({color.red()}, {color.green()}, {color.blue()}, 0),"
                f" stop:0.5 rgba({color.red()}, {color.green()}, {color.blue()}, 60),"
                f" stop:1 rgba({color.red()}, {color.green()}, {color.blue()}, 0))"
            )
            gradient_color = GradientColor(css)
            data["mod_color"] = gradient_color
            widget.mod_color = gradient_color
            widget.setStyleSheet(f"background: {css};")

"""Reusable "add to list / download with SteamCMD" widget.

Extracted from SteamBrowser so the same list + buttons can be embedded
in other panels (e.g. the AI assistant) with independent state.
"""

import re
from collections.abc import Callable
from functools import partial
from typing import Any

from loguru import logger
from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtWidgets import QDialogButtonBox as ButtonBox

DEFAULT_URL_PREFIX_SHAREDFILES = "https://steamcommunity.com/sharedfiles/filedetails/?id="


class ModDownloadListWidget(QWidget):
    """A labeled list of mods queued for download, with add/remove/download controls."""

    mod_added = Signal(str)
    mod_removed = Signal(str)
    download_requested = Signal(list)
    open_mod_requested = Signal(str)  # publishedfileid

    def __init__(
        self,
        *,
        title: str = "",
        show_steamworks_button: bool = False,
        show_add_by_id_button: bool = True,
        url_builder: Callable[[str], str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._url_builder = url_builder or (
            lambda pfid: f"{DEFAULT_URL_PREFIX_SHAREDFILES}{pfid}"
        )

        self.mods_tracking: list[str] = []
        self.dupe_tracking: dict[str, Any] = {}

        layout = QVBoxLayout(self)
        if title:
            self.title_label = QLabel(title)
            layout.addWidget(self.title_label)

        self.list_widget = QListWidget()
        self.list_widget.setFixedWidth(200)
        self.list_widget.setItemAlignment(Qt.AlignmentFlag.AlignCenter)
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(
            self._item_contextmenu_event
        )
        self.list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.list_widget)

        if show_add_by_id_button:
            self.add_by_id_button = QPushButton(self.tr("Add Mods by Workshop ID"))
            self.add_by_id_button.clicked.connect(self._show_add_mods_by_id_dialog)
            layout.addWidget(self.add_by_id_button)

        self.download_steamcmd_button = QPushButton(
            self.tr("Download mod(s) (SteamCMD)")
        )
        self.download_steamcmd_button.clicked.connect(
            lambda: self.download_requested.emit(list(self.mods_tracking))
        )
        layout.addWidget(self.download_steamcmd_button)

        self.download_steamworks_button: QPushButton | None = None
        if show_steamworks_button:
            self.download_steamworks_button = QPushButton(
                self.tr("Download mod(s) (Steam app)")
            )
            layout.addWidget(self.download_steamworks_button)

        self.clear_list_button = QPushButton(self.tr("Clear List"))
        self.clear_list_button.clicked.connect(self.clear_list)
        layout.addWidget(self.clear_list_button)

    def add_mod(
        self, publishedfileid: str, title: str | None = None, tooltip: str | None = None
    ) -> bool:
        """Add a mod to the list. Returns False (and records a dupe) if already present."""
        display_title = title or publishedfileid
        if publishedfileid in self.mods_tracking:
            logger.debug(f"Tried to add duplicate PFID to download list: {publishedfileid}")
            self.dupe_tracking.setdefault(publishedfileid, display_title)
            return False

        self.mods_tracking.append(publishedfileid)
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, publishedfileid)
        label = QLabel(display_title)
        label.setObjectName("ListItemLabel")
        item.setToolTip(
            tooltip or f"{display_title}\n--> {self._url_builder(publishedfileid)}"
        )
        item.setSizeHint(label.sizeHint())
        self.list_widget.addItem(item)
        self.list_widget.setItemWidget(item, label)
        self.mod_added.emit(publishedfileid)
        return True

    def has_mod(self, publishedfileid: str) -> bool:
        return publishedfileid in self.mods_tracking

    def set_item_tooltip(self, publishedfileid: str, tooltip: str) -> None:
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == publishedfileid:
                item.setToolTip(tooltip)
                return

    def set_item_title(self, publishedfileid: str, title: str) -> None:
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == publishedfileid:
                label = self.list_widget.itemWidget(item)
                if isinstance(label, QLabel):
                    label.setText(title)
                    item.setSizeHint(label.sizeHint())
                return

    def remove_mod(self, publishedfileid: str) -> None:
        if publishedfileid not in self.mods_tracking:
            logger.warning(
                f"Mod {publishedfileid} not found in download tracking list, cannot remove."
            )
            return
        self.mods_tracking.remove(publishedfileid)
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == publishedfileid:
                self.list_widget.takeItem(i)
                break
        self.mod_removed.emit(publishedfileid)

    def clear_list(self) -> None:
        cleared = list(self.mods_tracking)
        self.list_widget.clear()
        self.mods_tracking.clear()
        self.dupe_tracking.clear()
        for pfid in cleared:
            self.mod_removed.emit(pfid)

    def pop_dupe_report(self) -> dict[str, Any]:
        """Return and clear the accumulated duplicate-add report."""
        report = self.dupe_tracking
        self.dupe_tracking = {}
        return report

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        publishedfileid = item.data(Qt.ItemDataRole.UserRole)
        if publishedfileid:
            self.open_mod_requested.emit(publishedfileid)

    def _item_contextmenu_event(self, point: QPoint) -> None:
        context_item = self.list_widget.itemAt(point)
        if not context_item:
            return
        publishedfileid = context_item.data(Qt.ItemDataRole.UserRole)
        context_menu = QMenu(self)
        remove_item = context_menu.addAction(self.tr("Remove mod from list"))
        remove_item.triggered.connect(partial(self.remove_mod, publishedfileid))
        context_menu.exec_(self.list_widget.mapToGlobal(point))

    def _show_add_mods_by_id_dialog(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle(self.tr("Add Mods by Workshop ID"))
        layout = QVBoxLayout(dialog)
        label = QLabel(
            self.tr(
                "Enter one or more Workshop IDs (one per line or separated by commas):"
            )
        )
        layout.addWidget(label)
        text_edit = QTextEdit()
        layout.addWidget(text_edit)
        buttons = ButtonBox(
            ButtonBox.StandardButton.Ok | ButtonBox.StandardButton.Cancel
        )
        layout.addWidget(buttons)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            ids_text = text_edit.toPlainText()
            ids = [id_.strip() for id_ in re.split(r"[\s,]+", ids_text.strip()) if id_.strip()]
            for workshop_id in ids:
                self.add_mod(workshop_id)

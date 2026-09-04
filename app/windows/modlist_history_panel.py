"""Dialog for browsing and comparing mod list history snapshots."""

from collections.abc import Callable

from loguru import logger
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.services.modlist_history_service import (
    ModListDiff,
    ModlistHistoryService,
    Snapshot,
    SnapshotEntry,
)
from app.utils.generic import platform_specific_open
from app.views import dialogue


class ModlistHistoryPanel(QDialog):
    """Lists mod list snapshots for the current instance and diffs any two."""

    def __init__(
        self,
        history_service: ModlistHistoryService,
        restore_callback: Callable[[list[str]], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("modlistHistoryPanel")
        self.setWindowTitle(self.tr("Mod List History"))
        self._service = history_service
        self._restore_callback = restore_callback
        self._snapshots: list[Snapshot] = []

        self._setup_ui()
        self.resize(1000, 620)
        self._reload()

    # ------------------------------------------------------------------ setup
    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        description = QLabel(
            self.tr(
                "Every save writes a snapshot of your mod list. Select a snapshot "
                "to compare it with the one before it, or hold Ctrl and select two "
                "snapshots to compare them directly."
            )
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter, stretch=1)

        self.snapshot_list = QListWidget()
        self.snapshot_list.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.snapshot_list.itemSelectionChanged.connect(self._on_selection_changed)
        splitter.addWidget(self.snapshot_list)

        self.diff_tree = QTreeWidget()
        self.diff_tree.setHeaderLabels([self.tr("Change"), self.tr("Mod")])
        self.diff_tree.setColumnWidth(0, 160)
        self.diff_tree.setRootIsDecorated(True)
        splitter.addWidget(self.diff_tree)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        button_row = QHBoxLayout()

        self.restore_button = QPushButton(self.tr("Restore Selected"))
        self.restore_button.setObjectName("actionButton")
        self.restore_button.clicked.connect(self._on_restore)
        button_row.addWidget(self.restore_button)

        self.export_button = QPushButton(self.tr("Export Selected…"))
        self.export_button.clicked.connect(self._on_export)
        button_row.addWidget(self.export_button)

        self.note_button = QPushButton(self.tr("Edit Note…"))
        self.note_button.clicked.connect(self._on_edit_note)
        button_row.addWidget(self.note_button)

        button_row.addStretch()

        open_folder_button = QPushButton(self.tr("Open History Folder"))
        open_folder_button.clicked.connect(self._on_open_folder)
        button_row.addWidget(open_folder_button)

        close_button = QPushButton(self.tr("Close"))
        close_button.clicked.connect(self.close)
        button_row.addWidget(close_button)

        layout.addLayout(button_row)

    # ------------------------------------------------------------------ data
    def _reload(self) -> None:
        self._snapshots = self._service.list_snapshots()
        self.snapshot_list.clear()
        for index, snap in enumerate(self._snapshots):
            note = f"  —  {snap.note}" if snap.note else ""
            text = (
                f"{snap.display_timestamp}   "
                f"{len(snap.active)} active / {len(snap.inactive)} inactive   "
                f"[{snap.short_id}]{note}"
            )
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, index)
            self.snapshot_list.addItem(item)

        self._update_buttons()
        if self._snapshots:
            self.snapshot_list.setCurrentRow(0)
        else:
            self.diff_tree.clear()
            placeholder = QTreeWidgetItem(
                [
                    self.tr("No snapshots yet"),
                    self.tr("Save your mod list to create one"),
                ]
            )
            self.diff_tree.addTopLevelItem(placeholder)

    def _selected_indices(self) -> list[int]:
        indices = [
            item.data(Qt.ItemDataRole.UserRole)
            for item in self.snapshot_list.selectedItems()
        ]
        return sorted(int(i) for i in indices)

    def _selected_pair(self) -> tuple[Snapshot, Snapshot] | None:
        """Return (older, newer) snapshots to diff, or None."""
        indices = self._selected_indices()
        if len(indices) >= 2:
            older = self._snapshots[indices[-1]]
            newer = self._snapshots[indices[0]]
            return older, newer
        if len(indices) == 1:
            newer = self._snapshots[indices[0]]
            if indices[0] + 1 < len(self._snapshots):
                older = self._snapshots[indices[0] + 1]
                return older, newer
        return None

    # --------------------------------------------------------------- events
    def _on_selection_changed(self) -> None:
        self._update_buttons()
        self.diff_tree.clear()

        pair = self._selected_pair()
        if pair is None:
            indices = self._selected_indices()
            if len(indices) == 1:
                self.diff_tree.addTopLevelItem(
                    QTreeWidgetItem(
                        [
                            self.tr("Oldest snapshot"),
                            self.tr("Nothing to compare against"),
                        ]
                    )
                )
            return

        older, newer = pair
        try:
            diff = self._service.diff(older, newer)
        except Exception:
            logger.exception("Failed to diff mod list snapshots")
            return
        self._render_diff(older, newer, diff)

    def _render_diff(self, older: Snapshot, newer: Snapshot, diff: ModListDiff) -> None:
        header = QTreeWidgetItem(
            [
                self.tr("Comparing"),
                self.tr("{old} → {new}").format(
                    old=older.display_timestamp, new=newer.display_timestamp
                ),
            ]
        )
        self.diff_tree.addTopLevelItem(header)

        if diff.is_empty:
            self.diff_tree.addTopLevelItem(
                QTreeWidgetItem([self.tr("No differences"), ""])
            )
            return

        self._add_diff_group(self.tr("Added to active ({n})"), diff.active_added, "+")
        self._add_diff_group(
            self.tr("Removed from active ({n})"), diff.active_removed, "−"
        )
        self._add_diff_group(self.tr("Reordered ({n})"), diff.active_reordered, "~")
        self._add_diff_group(
            self.tr("Newly installed / disabled ({n})"), diff.inactive_added, "+"
        )
        self._add_diff_group(
            self.tr("No longer installed ({n})"), diff.inactive_removed, "−"
        )
        self.diff_tree.expandAll()

    def _add_diff_group(
        self, title_template: str, entries: list[SnapshotEntry], marker: str
    ) -> None:
        if not entries:
            return
        group = QTreeWidgetItem([title_template.format(n=len(entries)), ""])
        self.diff_tree.addTopLevelItem(group)
        for entry in entries:
            child = QTreeWidgetItem([marker, entry.label])
            if entry.source and entry.source != "unknown":
                child.setToolTip(1, self.tr("Source: {src}").format(src=entry.source))
            group.addChild(child)

    def _update_buttons(self) -> None:
        one_selected = len(self._selected_indices()) == 1
        self.restore_button.setEnabled(one_selected)
        self.export_button.setEnabled(one_selected)
        self.note_button.setEnabled(one_selected)

    def _current_snapshot(self) -> Snapshot | None:
        indices = self._selected_indices()
        if len(indices) != 1:
            return None
        return self._snapshots[indices[0]]

    # --------------------------------------------------------------- actions
    def _on_restore(self) -> None:
        snap = self._current_snapshot()
        if snap is None:
            return
        confirmed = dialogue.show_dialogue_conditional(
            title=self.tr("Restore Mod List"),
            text=self.tr("Load the active mod list from this snapshot ({ts})?").format(
                ts=snap.display_timestamp
            ),
            information=self.tr(
                "This replaces the mods currently loaded in RimSort. Nothing is "
                "written to disk until you press Save."
            ),
            button_text_override=[self.tr("Restore")],
        )
        if confirmed != self.tr("Restore"):
            return
        try:
            self._restore_callback(list(snap.active_package_ids))
        except Exception:
            logger.exception("Failed to restore mod list snapshot")
            dialogue.show_warning(
                title=self.tr("Restore failed"),
                text=self.tr("Could not restore the selected snapshot."),
            )
            return
        self.close()

    def _on_export(self) -> None:
        snap = self._current_snapshot()
        if snap is None:
            return
        target = dialogue.show_dialogue_file(
            mode="save",
            caption=self.tr("Export snapshot"),
            _dir=f"{snap.timestamp}__{snap.short_id}.json",
            _filter="JSON (*.json)",
        )
        if not target:
            return
        try:
            destination = target if target.endswith(".json") else target + ".json"
            with (
                open(snap.path, "r", encoding="utf-8-sig") as src,
                open(destination, "w", encoding="utf-8") as dst,
            ):
                dst.write(src.read())
        except OSError:
            logger.exception("Failed to export mod list snapshot")
            dialogue.show_warning(
                title=self.tr("Export failed"),
                text=self.tr("Could not write the snapshot file."),
            )

    def _on_edit_note(self) -> None:
        snap = self._current_snapshot()
        if snap is None:
            return
        note, ok = QInputDialog.getMultiLineText(
            self,
            self.tr("Snapshot Note"),
            self.tr("Note for {ts}:").format(ts=snap.display_timestamp),
            snap.note,
        )
        if not ok:
            return
        try:
            self._service.set_note(snap.path, note.strip())
        except (OSError, ValueError):
            logger.exception("Failed to write snapshot note")
            dialogue.show_warning(
                title=self.tr("Could not save note"),
                text=self.tr("The snapshot note could not be written."),
            )
            return
        self._reload()

    def _on_open_folder(self) -> None:
        platform_specific_open(str(self._service.history_dir()))

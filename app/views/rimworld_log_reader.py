import re
from pathlib import Path
from typing import Optional, TypedDict

import requests
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.views import dialogue
from app.views.rimworld_log_parser import LogTreeNode, parse_rimworld_timing_log


class HarmonyPatchEntry(TypedDict):
    method: str
    patches: list[tuple[str, str]]


class RimWorldLogReader(QDialog):
    tree: QTreeWidget

    def __init__(self, log_path: Optional[str] = None) -> None:
        super().__init__()
        self.setWindowTitle("RimWorld Log Reader")
        self.log_path: Optional[str] = log_path
        self._setup_ui()
        if log_path:
            self.load_log(log_path)

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        top_controls = QHBoxLayout()
        self.game_info_label = QLabel()
        top_controls.addStretch()
        top_controls.addWidget(self.game_info_label)
        main_layout.addLayout(top_controls)
        self.summary_label = QLabel()
        main_layout.addWidget(self.summary_label)
        splitter = QSplitter()
        sidebar_tabs = QTabWidget()
        mods_tab = QWidget()
        mods_layout = QVBoxLayout()
        mods_tab.setLayout(mods_layout)
        mods_layout.addWidget(QLabel("Mods"))
        self.mod_list = QListWidget()
        self.mod_list.itemSelectionChanged.connect(self.filter_by_mod)
        mods_layout.addWidget(self.mod_list)
        self.mod_search_edit = QLineEdit()
        self.mod_search_edit.setPlaceholderText("Search mods...")
        self.mod_search_edit.textChanged.connect(self._filter_mod_list)
        mods_layout.addWidget(self.mod_search_edit)
        self.clear_mod_filter_btn = QPushButton("Clear Mod Filter")
        self.clear_mod_filter_btn.clicked.connect(self.clear_mod_filter)
        mods_layout.addWidget(self.clear_mod_filter_btn)
        sidebar_tabs.addTab(mods_tab, "Mods")
        harmony_tab = QWidget()
        harmony_layout = QVBoxLayout()
        harmony_tab.setLayout(harmony_layout)
        harmony_layout.addWidget(QLabel("Harmony patches"))
        self.harmony_tree = QTreeWidget()
        self.harmony_tree.setHeaderLabels(
            ["Patching Class/Mod", "Method Patched", "Patch Type"]
        )
        harmony_layout.addWidget(self.harmony_tree)
        sidebar_tabs.addTab(harmony_tab, "Harmony patches")
        splitter.addWidget(sidebar_tabs)
        # --- Main Content ---
        content = QWidget()
        content_layout = QVBoxLayout()
        content.setLayout(content_layout)
        # Controls row (open, filter, refresh)
        controls = QHBoxLayout()
        self.open_btn = QPushButton("Open Log File")
        self.open_btn.clicked.connect(self.open_log_file)
        self.open_url_btn = QPushButton("Open Log from URL")
        self.open_url_btn.clicked.connect(self.open_log_from_url)
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filter (error, warning, info, text...)")
        self.filter_edit.textChanged.connect(self.apply_filter)
        controls.addWidget(self.open_btn)
        controls.addWidget(self.open_url_btn)
        controls.addWidget(QLabel("Filter:"))
        controls.addWidget(self.filter_edit)
        # --- Refresh Button ---
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh_log)
        controls.addWidget(self.refresh_btn)
        content_layout.addLayout(controls)
        # --- Issue Details Panel ---
        self.issue_details = QTextEdit()
        self.issue_details.setReadOnly(True)
        content_layout.addWidget(QLabel("Issue Details"))
        content_layout.addWidget(self.issue_details)
        # --- Full Log Viewer ---
        self.log_viewer = QTextEdit()
        self.log_viewer.setReadOnly(True)
        self.log_viewer.cursorPositionChanged.connect(self._on_log_cursor_changed)
        content_layout.addWidget(QLabel("Full Log"))
        content_layout.addWidget(self.log_viewer)
        # --- Log navigation ---
        nav_controls = QHBoxLayout()
        self.jump_prev_btn = QPushButton("Jump to previous issue")
        self.jump_prev_btn.clicked.connect(lambda: self._jump_to_issue_in_log("prev"))
        self.jump_next_btn = QPushButton("Jump to next issue")
        self.jump_next_btn.clicked.connect(lambda: self._jump_to_issue_in_log("next"))
        nav_controls.addWidget(self.jump_prev_btn)
        nav_controls.addWidget(self.jump_next_btn)
        content_layout.addLayout(nav_controls)
        # --- Timing Tree ---
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Section", "Duration (ms)", "%", "Self (ms)", "Mod"])
        self.tree.itemSelectionChanged.connect(self.show_tree_details)
        content_layout.addWidget(self.tree)
        tree_controls = QHBoxLayout()
        self.expand_all_btn = QPushButton("Expand All")
        self.expand_all_btn.clicked.connect(lambda: self.tree.expandAll())
        self.collapse_all_btn = QPushButton("Collapse All")
        self.collapse_all_btn.clicked.connect(lambda: self.tree.collapseAll())
        tree_controls.addWidget(self.expand_all_btn)
        tree_controls.addWidget(self.collapse_all_btn)
        content_layout.addLayout(tree_controls)
        self.tree_details = QLabel()
        self.tree_details.setWordWrap(True)
        content_layout.addWidget(self.tree_details)
        self.status_bar = QStatusBar()
        content_layout.addWidget(self.status_bar)
        splitter.addWidget(content)
        splitter.setStretchFactor(1, 3)
        main_layout.addWidget(splitter)
        self.setLayout(main_layout)

    def open_log_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open RimWorld.log",
            str(Path.home()),
            "Log Files (*.log);;All Files (*)",
        )
        if file_path:
            self.load_log(file_path)

    def open_log_from_url(self) -> None:
        url, ok = QInputDialog.getText(self, "Open Log from URL", "Paste log URL:")
        if not ok or not url:
            return
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            content = resp.text
            if url and not url.endswith("/raw"):
                raw_url = f"{url}/raw"
                raw_resp = requests.get(raw_url, timeout=10)
                raw_resp.raise_for_status()
                content = raw_resp.text
            lines = content.splitlines()
            self.log_path = url
            self._update_log_ui(lines, url)
        except Exception as e:
            dialogue.show_fatal_error(
                title="Failed to load log from URL",
                text=f"Could not load log from URL: {e}",
            )

    def load_log(self, path: str) -> None:
        self.log_path = path
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        self._update_log_ui([line.rstrip("\n") for line in lines], path)

    def _update_log_ui(self, lines: list[str], source: str) -> None:
        # Add line numbers to each log line
        numbered_lines = [f"{i + 1:>5}: {line}" for i, line in enumerate(lines)]
        self.log_viewer.setPlainText(
            "\n".join(numbered_lines) if isinstance(lines, list) else lines
        )
        mods = self.extract_mods_from_log(lines)
        self.mod_list.clear()
        for mod in sorted(mods):
            self.mod_list.addItem(mod)
        root = parse_rimworld_timing_log(lines)
        self.tree.clear()
        if root:
            self._add_tree_node(self.tree, root)
            self.expand_all_btn.setEnabled(True)
            self.collapse_all_btn.setEnabled(True)
            self.tree_details.setText("")
        else:
            self.expand_all_btn.setEnabled(False)
            self.collapse_all_btn.setEnabled(False)
            self.tree_details.setText(
                "<i>No timing data found in log.<br>"
                "If you want to see performance breakdowns, run RimWorld in developer mode with verbose logging enabled.</i>"
            )
        self._update_harmony_tree(lines)
        self.status_bar.showMessage(f"Loaded log from {source}")

    def _update_harmony_tree(self, lines: list[str]) -> None:
        """Parse the 'Active Harmony patches' section from the log lines."""
        self.harmony_tree.clear()
        patches = self._parse_harmony_patches(lines)
        mod_identifiers = self._extract_mod_identifiers(lines)

        def normalize(s: str) -> str:
            return re.sub(r"[_\-]", "", s).lower()

        def split_segments(s: str) -> set[str]:
            return set(re.split(r"[._+]", s))

        def find_mod_for_patcher(patcher: str) -> str:
            patcher_norm = normalize(patcher)
            patcher_segments = split_segments(patcher_norm)
            best_mod = "<Unknown mod>"
            best_len = 0
            for mod, identifiers in mod_identifiers.items():
                for ident in identifiers:
                    ident_norm = normalize(ident)
                    # Match if identifier is in patcher, or any segment matches
                    if ident_norm and (
                        ident_norm in patcher_norm or ident_norm in patcher_segments
                    ):
                        if len(ident_norm) > best_len:
                            best_mod = mod
                            best_len = len(ident_norm)
            return best_mod

        grouped: dict[str, dict[str, list[tuple[str, str]]]] = {}
        for patch in patches:
            for patch_type, patcher in patch["patches"]:
                mod = find_mod_for_patcher(patcher)
                if mod not in grouped:
                    grouped[mod] = {}
                if patcher not in grouped[mod]:
                    grouped[mod][patcher] = []
                grouped[mod][patcher].append((patch["method"], patch_type))
        for mod, patchers in sorted(grouped.items()):
            mod_item = QTreeWidgetItem([mod])
            for patcher, methods in sorted(patchers.items()):
                patcher_item = QTreeWidgetItem([patcher])
                for method, patch_type in methods:
                    child = QTreeWidgetItem(["", method, patch_type])
                    patcher_item.addChild(child)
                mod_item.addChild(patcher_item)
            self.harmony_tree.addTopLevelItem(mod_item)
        # self.harmony_tree.expandAll()  # do not auto-expand keep disabled for performance

    def _extract_mod_identifiers(self, lines: list[str]) -> dict[str, set[str]]:
        """
        Parse the 'Loaded mods:' section and return a dict of mod name -> set of identifiers (namespace, assemblies, prefixes, mod name, mod name without spaces).
        """
        mod_identifiers: dict[str, set[str]] = {}
        in_mod_section = False
        for line in lines:
            if line.strip().startswith("Loaded mods:"):
                in_mod_section = True
                continue
            if in_mod_section:
                if not line.strip() or line.strip().startswith("---"):
                    break
                # Example: Harmony(brrainz.harmony)[mv:2.3.1.0]: ...
                if "(" in line and ")" in line and ":" in line:
                    mod_name = line.split("(")[0].strip()
                    ns_part = line.split("(")[1].split(")")[0]
                    identifiers = set()
                    # Add namespace(s)
                    for ns in ns_part.split(","):
                        ns = ns.strip()
                        if ns:
                            identifiers.add(ns.lower())
                            identifiers.add(ns.split(".")[0].lower())
                    # Add mod name
                    if mod_name:
                        identifiers.add(mod_name.lower())
                        identifiers.add(mod_name.replace(" ", "").lower())
                    # Add assemblies (after colon)
                    after_colon = line.split(":", 1)[1] if ":" in line else ""
                    for asm in after_colon.split(","):
                        asm = asm.strip().split("(")[0].split("[")[0].strip()
                        if asm:
                            identifiers.add(asm.lower())
                            identifiers.add(asm.replace(" ", "").lower())
                            identifiers.add(asm.split(".")[0].lower())
                            identifiers.add(asm.split(".")[0].replace(" ", "").lower())
                    mod_identifiers[mod_name] = identifiers
        return mod_identifiers

    def _parse_harmony_patches(self, lines: list[str]) -> list[HarmonyPatchEntry]:
        """
        Parse the 'Active Harmony patches' section from the log lines.
        Returns a list of dicts: { 'method': str, 'patches': list[(patch_type, patcher)] }
        """
        patches: list[HarmonyPatchEntry] = []
        in_section = False
        for line in lines:
            if not in_section:
                if line.strip() == "Active Harmony patches:":
                    in_section = True
                continue
            if not line.strip() or line.strip().startswith("Loaded mods:"):
                break
            if ":" not in line:
                continue
            method, rest = line.split(":", 1)
            method = method.strip()
            patch_entries: list[tuple[str, str]] = []
            patch_type = None
            for entry in rest.strip().split():
                if entry in ("PRE:", "post:", "TRANS:"):
                    patch_type = entry.rstrip(":")
                elif entry in ("(no", "patches)", "(no patches)"):
                    continue
                elif patch_type:
                    patch_entries.append((patch_type, entry))
            if patch_entries:
                patches.append({"method": method, "patches": patch_entries})
        return patches

    def _add_tree_node(
        self, parent: QTreeWidget | QTreeWidgetItem, node: LogTreeNode
    ) -> None:
        item = QTreeWidgetItem(
            [
                node.label,
                f"{node.duration:.3f}",
                f"{node.percent:.1f}" if node.percent is not None else "",
                f"{node.self_time:.3f}" if node.self_time is not None else "",
                node.mod or "",
            ]
        )
        parent.addTopLevelItem(item) if isinstance(
            parent, QTreeWidget
        ) else parent.addChild(item)
        for child in node.children:
            self._add_tree_node(item, child)

    def _jump_to_issue_in_log(self, direction: str) -> None:
        cursor = self.log_viewer.textCursor()
        current_line = cursor.blockNumber()
        lines = self.log_viewer.toPlainText().splitlines()
        issue_lines = [
            i for i, line in enumerate(lines) if line.strip().startswith("[")
        ]
        if not issue_lines:
            dialogue.show_information(
                title="No issues found",
                text="No error/warning/info lines found in log.",
            )
            return
        if direction == "prev":
            prev = [i for i in issue_lines if i < current_line]
            target = prev[-1] if prev else issue_lines[-1]
        else:
            nexts = [i for i in issue_lines if i > current_line]
            target = nexts[0] if nexts else issue_lines[0]
        self._highlight_log_line(target + 1)
        self._show_issue_details_for_line(target)

    def _on_log_cursor_changed(self) -> None:
        cursor = self.log_viewer.textCursor()
        line = cursor.blockNumber()
        self._show_issue_details_for_line(line)

    def _show_issue_details_for_line(self, line: int) -> None:
        lines = self.log_viewer.toPlainText().splitlines()
        if 0 <= line < len(lines):
            text = lines[line]
            if text.strip().startswith("["):
                self.issue_details.setHtml(f"<b>Line {line + 1}:</b> {text}")
            else:
                self.issue_details.clear()
        else:
            self.issue_details.clear()

    def _highlight_log_line(self, lineno: int) -> None:
        cursor = self.log_viewer.textCursor()
        doc = self.log_viewer.document()
        block = doc.findBlockByLineNumber(lineno - 1)
        cursor.setPosition(block.position())
        self.log_viewer.setTextCursor(cursor)
        self.log_viewer.ensureCursorVisible()

    def extract_mods_from_log(self, log_lines: list[str]) -> list[str]:
        mods: list[str] = []
        in_mod_section = False
        for line in log_lines:
            if line.strip().startswith("Loaded mods:"):
                in_mod_section = True
                continue
            if in_mod_section:
                if not line.strip() or line.strip().startswith("---"):
                    break
                if "(" in line and ")" in line and ":" in line:
                    mod_name = line.split("(")[0].strip()
                    if mod_name and mod_name not in mods:
                        mods.append(mod_name)
        return mods

    def filter_by_mod(self) -> None:
        # Optionally implement mod-based filtering for the log viewer
        pass

    def clear_mod_filter(self) -> None:
        self.mod_list.clearSelection()
        # Optionally reset any mod-based filtering
        pass

    def _filter_mod_list(self) -> None:
        text = self.mod_search_edit.text().lower()
        for i in range(self.mod_list.count()):
            item = self.mod_list.item(i)
            item.setHidden(text not in item.text().lower())

    def refresh_log(self) -> None:
        if not self.log_path:
            dialogue.show_information(
                title="No log loaded",
                text="Please open a log file or URL first.",
            )
            return
        if self.log_path.startswith("http"):
            self.open_log_from_url()
        else:
            self.load_log(self.log_path)

    def apply_filter(self) -> None:
        # Optionally implement text filtering for the log viewer
        pass

    def show_tree_details(self) -> None:
        items = self.tree.selectedItems()
        if not items:
            self.tree_details.setText("")
            return
        item = items[0]
        details = []
        for i in range(item.columnCount()):
            header = self.tree.headerItem().text(i)
            value = item.text(i)
            if value:
                details.append(f"<b>{header}:</b> {value}")
        self.tree_details.setText("<br>".join(details))

    def extract_mod_from_line(self, line: str) -> str:
        # Optionally implement mod extraction from a log line
        return ""

import logging
import os
from typing import Any, Dict, List, Optional, Set

from PySide6.QtCore import QObject, QThread, Signal

from app.models.search_result import SearchResult
from app.models.settings import Settings
from app.utils.file_search import FileSearch
from app.views.file_search_dialog import FileSearchDialog

logger = logging.getLogger(__name__)


class SearchWorker(QThread):
    """worker thread for file searching"""

    result_found = Signal(str, str, str, str)  # mod_name, file_name, path, preview
    progress = Signal(int, int)  # current, total
    stats = Signal(str)  # statistics text
    finished = Signal()
    error = Signal(str)

    def __init__(
        self,
        root_paths: List[str],
        pattern: str,
        options: Dict[str, Any],
        active_mod_ids: Optional[Set[str]] = None,
        scope: str = "all mods",
    ) -> None:
        super().__init__()
        self.root_paths = root_paths
        self.pattern = pattern
        self.options = options
        self.active_mod_ids = active_mod_ids
        self.scope = scope
        self.searcher = FileSearch()
        if active_mod_ids is not None:
            self.searcher.set_active_mods(active_mod_ids, scope)
        self.total_files = 0
        self.processed_files = 0
        self.found_files = 0
        self.total_size = 0

    def _get_file_preview(self, file_path: str, content: str = "") -> str:
        """get preview of the matched content"""
        try:
            # if content wasn't provided, read it from file
            if not content:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()

            # find the position of the search term
            search_term = (
                self.pattern.lower()
                if not self.options.get("case_sensitive")
                else self.pattern
            )
            content_to_search = (
                content.lower() if not self.options.get("case_sensitive") else content
            )
            pos = content_to_search.find(search_term)
            if pos == -1:
                return ""

            # get some context around the match
            start = max(0, pos - 50)
            end = min(len(content), pos + len(search_term) + 50)

            # add ellipsis if needed
            prefix = "..." if start > 0 else ""
            suffix = "..." if end < len(content) else ""

            return f"{prefix}{content[start:end]}{suffix}"
        except Exception as e:
            logger.warning(f"Failed to get preview for {file_path}: {e}")
            return ""

    def _should_process_mod(self, mod_path: str) -> bool:
        """check if mod should be processed based on active/inactive filter"""
        scope = self.options.get("scope", "all mods")
        if scope == "all mods":
            return True

        # get mod ID from folder name
        mod_id = os.path.basename(mod_path)
        if self.active_mod_ids is None:
            return False
        is_active = mod_id in self.active_mod_ids

        return (scope == "active mods" and is_active) or (
            scope == "not active mods" and not is_active
        )

    def run(self) -> None:
        try:
            logger.info(f"Starting search with text: {self.pattern}")
            logger.info(f"Search options: {self.options}")
            logger.info(f"Search paths: {self.root_paths}")

            # count total files first
            self.total_files = 0
            self.total_size = 0
            for root_path in self.root_paths:
                try:
                    logger.debug(f"Scanning path: {root_path}")
                    for root, _, files in os.walk(root_path):
                        # check if this is a mod folder we should process
                        if not self._should_process_mod(root):
                            logger.debug(f"Skipping mod folder: {root}")
                            continue

                        for file in files:
                            file_path = os.path.join(root, file)
                            if self.searcher._should_process_file(
                                file_path, self.options
                            ):
                                try:
                                    self.total_files += 1
                                    self.total_size += os.path.getsize(file_path)
                                except (OSError, IOError) as e:
                                    logger.warning(
                                        f"Cannot access file {file_path}: {e}"
                                    )
                                    continue
                except Exception as e:
                    logger.error(f"Error accessing path {root_path}: {e}")
                    self.error.emit(f"Error accessing path {root_path}: {str(e)}")
                    return

            logger.info(f"Found {self.total_files} files to search")
            self.stats.emit(
                f"Found {self.total_files} files to search (total size: {self.total_size / 1024 / 1024:.1f} MB)"
            )

            # get search method based on selected algorithm
            algorithm = self.options.get("algorithm", "simple search")
            try:
                search_method = getattr(self.searcher, f"{algorithm.replace(' ', '_')}")
                logger.info(f"Using search method: {algorithm}")
            except AttributeError:
                logger.error(f"Invalid search algorithm: {algorithm}")
                self.error.emit(f"Invalid search algorithm: {algorithm}")
                return

            def progress_callback(
                mod_name: str, file_name: str, path: str, content: str = ""
            ) -> None:
                self.processed_files += 1
                self.progress.emit(self.processed_files, self.total_files)

                # only emit result if there was a match
                if path:
                    self.found_files += 1
                    preview = self._get_file_preview(path, content)
                    self.result_found.emit(mod_name, file_name, path, preview)
                    logger.debug(f"Found match in {path}")

                # update stats periodically
                if (
                    self.processed_files % 10 == 0
                    or self.processed_files == self.total_files
                ):
                    self.stats.emit(
                        f"Processed: {self.processed_files}/{self.total_files} files, Found: {self.found_files} matches"
                    )

            # perform search
            try:
                for mod_name, file_name, path in search_method(
                    self.pattern,
                    self.root_paths,
                    self.options,
                    lambda *args: progress_callback(*args),
                ):
                    pass  # results are emitted via callback
            except Exception as e:
                logger.error(f"Search error: {e}")
                self.error.emit(f"Search error: {str(e)}")
                return

            logger.info("Search completed successfully")
            self.finished.emit()
        except Exception as e:
            import traceback

            error_details = f"Error: {str(e)}\n\nDetails:\n{traceback.format_exc()}"
            logger.error(f"Unexpected error: {error_details}")
            self.error.emit(error_details)
            self.finished.emit()


class FileSearchController(QObject):
    """controller for file search functionality"""

    # define signals
    search_results_updated = Signal()

    def __init__(
        self,
        settings: Settings,
        dialog: FileSearchDialog,
        active_mod_ids: Optional[Set[str]] = None,
    ) -> None:
        """initialize controller"""
        super().__init__()
        self.settings = settings
        self.dialog = dialog
        self.active_mod_ids = active_mod_ids or set()
        self.search_results: List[SearchResult] = []
        self.search_worker: Optional[SearchWorker] = None
        self.searcher = FileSearch()

        # connect signals
        self.dialog.search_button.clicked.connect(self._on_search_clicked)
        self.dialog.stop_button.clicked.connect(self._on_stop_clicked)
        self.dialog.search_input.returnPressed.connect(self._on_search_clicked)
        self.dialog.filter_input.textChanged.connect(self._on_filter_changed)

        # set initial paths
        instance = self.settings.instances[self.settings.current_instance]
        if instance.local_folder:
            self.dialog.set_search_paths([instance.local_folder])

    def set_active_mod_ids(self, active_mod_ids: Set[str]) -> None:
        """update the list of active mod IDs"""
        self.active_mod_ids = active_mod_ids

    def get_search_paths(self) -> List[str]:
        """get search paths from dialog"""
        return self.dialog.get_search_options().get("paths", [])

    def get_search_text(self) -> str:
        """get search text from dialog"""
        return self.dialog.search_input.text()

    def clear_results(self) -> None:
        """clear search results"""
        self.search_results.clear()
        self.search_results_updated.emit()

    def update_results(self) -> None:
        """notify that results have been updated"""
        self.search_results_updated.emit()

    def _setup_search_worker(
        self,
        root_paths: List[str],
        pattern: str,
        options: Dict[str, Any],
        active_mod_ids: Optional[Set[str]] = None,
        scope: str = "all mods",
    ) -> SearchWorker:
        """Set up and configure a new search worker"""
        if self.search_worker is not None:
            self.search_worker.quit()
            self.search_worker.wait()

        worker = SearchWorker(root_paths, pattern, options, active_mod_ids, scope)
        worker.result_found.connect(self.dialog.add_result)
        worker.progress.connect(self.dialog.update_progress)
        worker.stats.connect(self.dialog.update_stats)
        worker.finished.connect(self._on_search_finished)
        worker.error.connect(self._on_search_error)
        return worker

    def _start_search_worker(
        self,
        root_paths: List[str],
        search_text: str,
        options: Dict[str, Any],
        active_mod_ids: Optional[Set[str]] = None,
        scope: str = "all mods",
    ) -> None:
        """Start a new search worker"""
        self.searcher = FileSearch()
        if active_mod_ids is not None:
            self.searcher.set_active_mods(active_mod_ids, scope)

        self.dialog.clear_results()

        worker = self._setup_search_worker(
            root_paths, search_text, options, active_mod_ids, scope
        )
        worker.start()
        self.search_worker = worker

    def _on_search_clicked(self) -> None:
        """handle search button click"""
        self.dialog.search_button.setEnabled(False)
        self.dialog.stop_button.setEnabled(True)

        options = self.dialog.get_search_options()
        root_paths = options.get("paths", [])
        search_text = self.dialog.search_input.text()

        self._start_search_worker(root_paths, search_text, options, self.active_mod_ids)

    def _on_stop_clicked(self) -> None:
        """handle stop button click"""
        if self.search_worker and self.search_worker.isRunning():
            self.searcher.stop_search()
            self.search_worker.wait()
        self._on_search_finished()

    def _on_search_finished(self) -> None:
        """handle search completion"""
        self.dialog.search_button.setEnabled(True)
        self.dialog.stop_button.setEnabled(False)

    def _on_search_error(self, error_msg: str) -> None:
        """handle search errors"""
        from app.utils.gui_info import show_dialogue_conditional

        show_dialogue_conditional(
            "Search Error", error_msg, "Please check your settings and try again."
        )
        self._on_search_finished()

    def _on_filter_changed(self, text: str) -> None:
        """handle filter text changes"""
        # hide rows that don't match the filter
        filter_text = text.lower()
        print("\n=== Filtering results ===")
        print(f"Filter text: {filter_text}")
        print(f"Total rows: {self.dialog.results_table.rowCount()}")

        visible_rows = 0
        for row in range(self.dialog.results_table.rowCount()):
            show_row = False
            row_content = []
            for col in range(self.dialog.results_table.columnCount()):
                item = self.dialog.results_table.item(row, col)
                if item is not None:
                    item_text = item.text().lower()
                    row_content.append(f"col {col}: {item_text}")
                    if filter_text in item_text:
                        show_row = True
                        print(f"Match found in row {row}, column {col}: {item_text}")
                        break

            print(f"\nRow {row} content: {', '.join(row_content)}")
            print(f"Row {row} visible: {show_row}")

            self.dialog.results_table.setRowHidden(row, not show_row)
            if show_row:
                visible_rows += 1

        print(
            f"\nFilter complete - Visible rows: {visible_rows}/{self.dialog.results_table.rowCount()}"
        )

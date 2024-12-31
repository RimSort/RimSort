import logging
import os

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import QMessageBox

from app.models.settings import Settings
from app.utils.file_search import FileSearch
from app.utils.gui_info import show_dialogue_conditional
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
        searcher: FileSearch,
        search_text: str,
        root_paths: list[str],
        options: dict,
        active_mod_ids: set[str] = None,
    ):
        super().__init__()
        self.searcher = searcher
        self.search_text = search_text
        self.root_paths = root_paths
        self.options = options
        self.active_mod_ids = active_mod_ids or set()  # set of active mod IDs
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
                self.search_text.lower()
                if not self.options.get("case_sensitive")
                else self.search_text
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
        is_active = mod_id in self.active_mod_ids

        return (scope == "active mods" and is_active) or (
            scope == "not active mods" and not is_active
        )

    def run(self):
        try:
            logger.info(f"Starting search with text: {self.search_text}")
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
            ):
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
                    self.search_text,
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
    """controller for file search dialog"""

    def __init__(
        self,
        settings: Settings,
        dialog: FileSearchDialog,
        active_mod_ids: set[str] = None,
    ) -> None:
        super().__init__()
        self.settings = settings
        self.dialog = dialog
        self.active_mod_ids = active_mod_ids or set()
        self.search_worker = None
        self.searcher = FileSearch()

        # connect signals
        self.dialog.search_button.clicked.connect(self._on_search_clicked)
        self.dialog.stop_button.clicked.connect(self._on_stop_clicked)
        self.dialog.search_input.returnPressed.connect(self._on_search_clicked)
        self.dialog.filter_input.textChanged.connect(self._on_filter_changed)

    def _get_search_paths(self) -> list[str]:
        """get paths to search based on selected scope"""
        scope = self.dialog.search_scope.currentText()
        instance = self.settings.instances[self.settings.current_instance]

        # check if both local and steam mods are available
        local_mods = instance.local_folder
        steam_mods = instance.workshop_folder

        paths = []
        if scope in ["active mods", "not active mods", "all mods"]:
            if local_mods and steam_mods:
                # ask user which locations to search
                msg = QMessageBox()
                msg.setWindowTitle("Select Search Location")
                msg.setText("Where would you like to search?")
                msg.addButton("Local Mods", QMessageBox.ButtonRole.AcceptRole)
                msg.addButton("Steam Mods", QMessageBox.ButtonRole.AcceptRole)
                msg.addButton("Both", QMessageBox.ButtonRole.AcceptRole)
                msg.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)

                choice = msg.exec()
                if choice == 3:  # Cancel
                    return []
                elif choice == 0:  # Local Mods
                    paths.append(local_mods)
                elif choice == 1:  # Steam Mods
                    paths.append(steam_mods)
                else:  # Both
                    paths.extend([local_mods, steam_mods])
            else:
                # use whichever is available
                if local_mods:
                    paths.append(local_mods)
                if steam_mods:
                    paths.append(steam_mods)
        elif scope == "configs folder":
            if instance.config_folder:
                paths.append(instance.config_folder)

        logger.info(f"Search paths: {paths}")
        return paths

    def _on_search_clicked(self) -> None:
        """handle search button click"""
        # get search parameters
        search_text = self.dialog.search_input.text()
        if not search_text:
            return

        # prepare for new search
        self.dialog.clear_results()
        self.dialog.search_button.setEnabled(False)
        self.dialog.stop_button.setEnabled(True)
        self.searcher.reset()

        # get search paths and options
        root_paths = self._get_search_paths()
        if not root_paths:
            show_dialogue_conditional(
                "No Search Paths",
                "No valid paths to search in were found.",
                "Please check your settings and try again.",
            )
            self._on_search_finished()
            return

        # get search options and add active mod IDs
        options = self.dialog.get_search_options()
        options["active_mod_ids"] = self.active_mod_ids
        options["scope"] = self.dialog.search_scope.currentText().lower()

        # create and start search worker
        self.search_worker = SearchWorker(
            self.searcher, search_text, root_paths, options
        )
        self.search_worker.result_found.connect(self.dialog.add_result)
        self.search_worker.progress.connect(self.dialog.update_progress)
        self.search_worker.stats.connect(self.dialog.update_stats)
        self.search_worker.finished.connect(self._on_search_finished)
        self.search_worker.error.connect(self._on_search_error)
        self.search_worker.start()

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
        show_dialogue_conditional(
            "Search Error", error_msg, "Please check your settings and try again."
        )
        self._on_search_finished()

    def _on_filter_changed(self, text: str) -> None:
        """handle filter text changes"""
        # hide rows that don't match the filter
        filter_text = text.lower()
        for row in range(self.dialog.results_table.rowCount()):
            show_row = any(
                filter_text in self.dialog.results_table.item(row, col).text().lower()
                for col in range(self.dialog.results_table.columnCount())
            )
            self.dialog.results_table.setRowHidden(row, not show_row)

    def set_active_mod_ids(self, active_mod_ids: set[str]) -> None:
        """update the list of active mod IDs"""
        self.active_mod_ids = active_mod_ids

import os
import re
import xml.etree.ElementTree as ET
from typing import Any, Optional, Union
from xml.dom import minidom

import chardet
from loguru import logger
from psutil import Process
from PySide6.QtCore import QObject, QThread, QTimer, Signal

import app.utils.metadata as metadata
from app.controllers.settings_controller import SettingsController
from app.models.search_result import SearchResult
from app.models.settings import Settings
from app.utils.file_search import FileSearch
from app.utils.ignore_extensions import IGNORE_EXTENSIONS
from app.utils.metadata import MetadataManager
from app.utils.mod_utils import get_mod_paths_from_uuids
from app.views.dialogue import show_warning
from app.views.file_search_dialog import FileSearchDialog
from app.views.mods_panel import ModsPanel


class SearchWorker(QThread):
    """worker thread for file searching"""

    result_found = Signal(str, str, str, str)  # mod_name, file_name, path, preview
    progress = Signal(int, int)  # current, total
    stats = Signal(str)  # statistics text
    finished = Signal()
    error = Signal(str)

    def __init__(
        self,
        root_paths: list[str],
        pattern: str,
        options: dict[str, Any],
        active_mod_ids: Optional[set[str]] = None,
        scope: str = "all mods",
    ) -> None:
        """
        Initialize search worker

        Parameters:
        - root_paths: List of paths to search in
        - pattern: Text to search for
        - options: Search options
        - mod_ids: Set of mod IDs to use for filtering
          For active mods search, this should be active mod IDs
          For inactive mods search, this should be inactive mod IDs
        - scope: Search scope ("active mods", "inactive mods", "all mods", etc.)
        """
        super().__init__()
        self.root_paths = root_paths
        self.pattern = pattern
        self.options = options
        self.active_mod_ids = active_mod_ids
        self.scope = scope
        self.searcher = FileSearch()
        self.processed_files = 0
        self.found_files = 0

        # Pass ignore extensions to the search options
        if self.options.get("file_type", "All Files") == "All Files":
            self.options["ignore_extensions"] = IGNORE_EXTENSIONS

        # Memory monitoring
        self.memory_check_interval = 100  # Check memory usage every 100 files
        self.memory_warning_threshold = 0.85  # 85% of available memory
        self.last_memory_check = 0
        self.memory_warning_shown = False

        # Set thread priority to lower to avoid UI freezing
        if not self.isRunning():
            logger.warning("Thread is not running. Skipping priority setting.")
            return
        self.setPriority(QThread.Priority.LowPriority)

        # Validate regex pattern if using regex
        if options.get("use_regex", False):
            try:
                re.compile(pattern)
            except re.error as e:
                logger.error(f"Invalid regex pattern: {e}")
                self.error.emit(f"Invalid regex pattern: {e}")
                # Force simple search if regex is invalid
                self.options["algorithm"] = "simple search"

        # Automatically select the best search algorithm based on the collection size
        if "algorithm" in self.options and self.options["algorithm"] == "auto":
            self._select_optimal_algorithm()

    def _select_optimal_algorithm(self) -> None:
        """
        Automatically select the best search algorithm based on the file type and search parameters
        """
        # Check if we're searching for XML files specifically
        file_type = self.options.get("file_type", "All Files")

        # Select algorithm based on file type and search parameters
        if self.options.get("use_regex", False):
            # Always use pattern search for regex
            self.options["algorithm"] = "pattern search"
        elif file_type == "XML Files":
            # For XML files, use the optimized XML search
            self.options["algorithm"] = "xml search"
        else:
            # For all other file types, use standard search
            self.options["algorithm"] = "standard search"

        logger.info(
            f"Auto-selected search algorithm: {self.options['algorithm']} for {file_type}"
        )

    def _check_memory_usage(self) -> bool:
        """
        Check current memory usage and emit a warning if it's too high.
        Returns True if memory usage is acceptable, False if it's too high.
        """
        try:
            process = Process()
            memory_info = process.memory_info()
            memory_percent = process.memory_percent()

            logger.debug(
                f"Memory usage: {memory_info.rss / (1024 * 1024):.1f} MB ({memory_percent:.1f}%)"
            )

            if (
                memory_percent > self.memory_warning_threshold
                and not self.memory_warning_shown
            ):
                logger.warning(
                    f"High memory usage detected: {memory_percent:.1f}%. Consider optimizing the search."
                )
                self.memory_warning_shown = True

            return memory_percent <= self.memory_warning_threshold
        except Exception as e:
            logger.error(f"Error checking memory usage: {e}")
            return True

    def _read_file_with_fallback(self, file_path: str) -> str:
        """
        Read file content with multiple encoding attempts and improved error handling.

        Args:
            file_path: Path to the file to read.

        Returns:
            The file content as a string, or empty string on failure.
        """
        # Check if file exists and is accessible
        if not os.path.exists(file_path):
            logger.warning(f"File does not exist: {file_path}")
            return ""

        # Check file size before attempting to read
        try:
            file_size = os.path.getsize(file_path)
            if file_size == 0:
                logger.debug(f"Skipping empty file: {file_path}")
                return ""

            # Skip very large files to prevent memory issues
            max_size = 20 * 1024 * 1024  # 20MB
            if file_size > max_size:
                logger.warning(
                    f"File too large to read fully: {file_path} ({file_size} bytes)"
                )
                # For large files, read only the first part
                try:
                    with open(file_path, "rb") as f:
                        binary_content = f.read(1024 * 1024)  # Read first 1MB
                        return (
                            binary_content.decode("utf-8", errors="replace")
                            + "\n\n[File truncated due to size...]"
                        )
                except Exception as e:
                    logger.warning(f"Failed to read large file {file_path}: {e}")
                    return ""
        except OSError as e:
            logger.warning(f"Error checking file size for {file_path}: {e}")
            return ""

        try:  # Try to detect encoding with chardet for better accuracy
            with open(file_path, "rb") as f:
                raw_data = f.read(min(4096, file_size))
                result = chardet.detect(raw_data)
                if result["confidence"] > 0.7 and result["encoding"]:
                    detected_encoding = result["encoding"]
                    try:
                        # Use explicit text mode with detected encoding
                        content = ""
                        with open(
                            file_path, "r", encoding=detected_encoding
                        ) as text_file:
                            content = text_file.read()
                            return content
                    except UnicodeDecodeError:
                        # If detected encoding fails, continue with fallbacks
                        pass
        except ImportError:
            # chardet not available, continue with fallbacks
            pass
        except Exception as e:
            logger.debug(f"Error detecting encoding: {e}")

        # Try common encodings
        encodings = ["utf-8", "utf-8-sig", "latin-1", "cp1252", "iso-8859-1"]

        for encoding in encodings:
            try:
                with open(file_path, "r", encoding=encoding) as f:
                    content = f.read()
                    logger.debug(f"Successfully read file with encoding: {encoding}")
                    return content
            except UnicodeDecodeError:
                # Try the next encoding
                continue
            except IOError as e:
                logger.warning(f"Error reading file {file_path}: {e}")
                return ""

        # If all encodings fail, try binary mode and decode with errors='replace'
        try:
            with open(file_path, "rb") as f:
                binary_content = f.read()
                # Try to decode with 'replace' option to substitute invalid chars
                return binary_content.decode("utf-8", errors="replace")
        except Exception as e:
            logger.warning(f"Failed to read file {file_path} after all attempts: {e}")
            return ""

    def _get_file_preview(self, file_path: str, content: str = "") -> str:
        """Get preview of the matched content with improved context and highlighting"""
        try:
            # If content wasn't provided, read it from file
            if not content:
                content = self._read_file_with_fallback(file_path)

            # If content is still empty, return early
            if not content:
                return "Error: Could not read file content"

            # Check file type for special handling
            _, ext = os.path.splitext(file_path.lower())

            # Special handling for XML files
            if ext == ".xml" and not self.options.get("use_regex", False):
                xml_preview = self._get_xml_preview(file_path, content)
                if xml_preview:
                    return xml_preview

            # Find the position of the search term
            search_term = (
                self.pattern.lower()
                if not self.options.get("case_sensitive")
                else self.pattern
            )
            content_to_search = (
                content.lower() if not self.options.get("case_sensitive") else content
            )

            # For regex patterns, we need to find all matches
            if self.options.get("use_regex", False):
                try:
                    # Compile the regex pattern
                    flags = 0 if self.options.get("case_sensitive") else re.IGNORECASE
                    regex = re.compile(self.pattern, flags)

                    # Find all matches in the content
                    matches = list(regex.finditer(content))
                    if not matches:
                        return ""

                    # Use the first match for preview
                    match = matches[0]
                    pos = match.start()
                    # We can calculate match length directly when needed using match.end() - match.start()
                except re.error as e:
                    logger.warning(f"Invalid regex pattern: {e}")
                    return f"Error: Invalid regex pattern: {e}"
            else:
                # For simple text search
                pos = content_to_search.find(search_term)
                if pos == -1:
                    return ""
                # We don't need to store the match length for simple text search
                # as we can use len(search_term) directly when needed

            # Split content into lines for better context
            lines = content.split("\n")

            # Find which line contains the match
            current_pos = 0
            match_line_index = 0
            for i, line in enumerate(lines):
                line_length = len(line) + 1  # +1 for the newline character
                if current_pos <= pos < current_pos + line_length:
                    match_line_index = i
                    # Calculate position within the line (useful for debugging)
                    # line_pos = pos - current_pos
                    break
                current_pos += line_length

            # Get context lines (3 lines before and after the match)
            start_line = max(0, match_line_index - 3)
            end_line = min(len(lines), match_line_index + 4)

            # Format the preview with line numbers and highlight the match
            preview_lines = []
            for i in range(start_line, end_line):
                # Highlight the matched line with a different prefix and formatting
                if i == match_line_index:
                    line_prefix = f"→ {i + 1}: "

                    # Try to highlight the matched text within the line
                    line = lines[i]
                    if self.options.get("use_regex", False):
                        # For regex search, we need to find the match in this specific line
                        try:
                            flags = (
                                0
                                if self.options.get("case_sensitive")
                                else re.IGNORECASE
                            )
                            regex = re.compile(self.pattern, flags)
                            line_match = regex.search(line)
                            if line_match:
                                match_pos = line_match.start()
                                match_end = line_match.end()
                                # Highlight with ** around the match
                                line = (
                                    line[:match_pos]
                                    + "**"
                                    + line[match_pos:match_end]
                                    + "**"
                                    + line[match_end:]
                                )
                        except re.error:
                            # If regex fails, just show the line without highlighting
                            pass
                    else:
                        # For simple text search, we can highlight the exact match
                        if self.options.get("case_sensitive"):
                            # Case-sensitive: find exact match
                            match_pos = line.find(self.pattern)
                            if match_pos >= 0:
                                # Highlight with ** around the match
                                line = (
                                    line[:match_pos]
                                    + "**"
                                    + line[match_pos : match_pos + len(self.pattern)]
                                    + "**"
                                    + line[match_pos + len(self.pattern) :]
                                )
                        else:
                            # Case-insensitive: find match ignoring case
                            match_pos = line.lower().find(self.pattern.lower())
                            if match_pos >= 0:
                                # Highlight with ** around the match
                                line = (
                                    line[:match_pos]
                                    + "**"
                                    + line[match_pos : match_pos + len(self.pattern)]
                                    + "**"
                                    + line[match_pos + len(self.pattern) :]
                                )
                else:
                    line_prefix = f"  {i + 1}  "
                    line = lines[i]

                preview_lines.append(f"{line_prefix}{line}")

            # Add ellipsis if needed
            prefix = "...\n" if start_line > 0 else ""
            suffix = "\n..." if end_line < len(lines) else ""

            # Add a header with file info
            file_size = os.path.getsize(file_path)
            file_size_str = self._format_file_size(file_size)

            header = f"File: {os.path.basename(file_path)} ({file_size_str})\n"
            header += f"Path: {os.path.dirname(file_path)}\n"
            header += f"Match at line {match_line_index + 1}:\n"

            return f"{header}\n{prefix}{'\n'.join(preview_lines)}{suffix}"
        except Exception as e:
            logger.warning(f"Failed to get preview for {file_path}: {e}")
            return f"Error generating preview: {e}"

    def _get_xml_preview(self, file_path: str, content: str) -> str:
        """Generate a more structured preview for XML files with better formatting"""
        try:  # Find the position of the search term
            search_term = (
                self.pattern.lower()
                if not self.options.get("case_sensitive")
                else self.pattern
            )

            # Try to parse the XML
            try:
                # Parse the XML
                root = ET.fromstring(content)

                def find_element_with_text(
                    element: "ET.Element", search_text: str, case_sensitive: bool = True
                ) -> Optional["ET.Element"]:
                    # Check element text
                    element_text = element.text or ""
                    if not case_sensitive:
                        element_text = element_text.lower()
                        search_text = search_text.lower()

                    if search_text in element_text:
                        return element

                    # Check attributes
                    for attr, value in element.attrib.items():
                        if not case_sensitive:
                            value = value.lower()
                        if search_text in value:
                            return element

                    # Check children
                    for child in element:
                        result = find_element_with_text(
                            child, search_text, case_sensitive
                        )
                        if result is not None:
                            return result

                    return None

                # Find the element containing the search term
                element = find_element_with_text(
                    root, search_term, self.options.get("case_sensitive", False)
                )

                if element is not None:
                    # Convert element to string with nice formatting
                    element_str = ET.tostring(element, encoding="unicode")

                    # Pretty print the XML
                    pretty_xml = minidom.parseString(element_str).toprettyxml(
                        indent="  "
                    )

                    # Remove XML declaration
                    if pretty_xml.startswith("<?xml"):
                        pretty_xml = pretty_xml.split("\n", 1)[1]

                    # Highlight the search term
                    if not self.options.get("case_sensitive"):
                        pattern = re.compile(re.escape(search_term), re.IGNORECASE)
                        pretty_xml = pattern.sub("**\\g<0>**", pretty_xml)
                    else:
                        pretty_xml = pretty_xml.replace(
                            search_term, f"**{search_term}**"
                        )

                    # Create the preview
                    file_name = os.path.basename(file_path)
                    preview = [
                        f"File: {file_name} (XML)",
                        "─" * 40,  # Separator line
                        "Matched XML Element:",
                        pretty_xml,
                    ]

                    return "\n".join(preview)

            except ET.ParseError:
                # If XML parsing fails, return empty string to fall back to standard preview
                return ""

            # If element not found, return empty string to fall back to standard preview
            return ""

        except Exception as e:
            logger.warning(f"Error generating XML preview for {file_path}: {e}")
            # Return empty string to fall back to standard preview
            return ""

    def _format_file_size(self, size_in_bytes: int) -> str:
        """Format file size in human-readable format"""
        if size_in_bytes < 1024:
            return f"{size_in_bytes} B"
        elif size_in_bytes < 1024 * 1024:
            return f"{size_in_bytes / 1024:.1f} KB"
        else:
            return f"{size_in_bytes / (1024 * 1024):.1f} MB"

    def _should_process_mod(self, mod_path: str) -> bool:
        """
        Check if mod should be processed based on active/inactive filter

        Parameters:
        - mod_path: Path to the mod folder

        Returns:
        - True if the mod should be processed, False otherwise
        """
        scope = self.options.get("scope", "all mods")
        if scope == "all mods":
            return True

        # If we're directly searching in specific mod folders and no mod_ids provided,
        # we can skip the filtering since the paths are already filtered
        if self.active_mod_ids is None:
            return True

        # get mod ID from folder name
        mod_id = os.path.basename(mod_path)
        if self.active_mod_ids is None:
            return False
        is_active = mod_id in self.active_mod_ids

        return (scope == "active mods" and is_active) or (
            scope == "inactive mods" and not is_active
        )

    def get_mod_name_from_pfid(self, pfid: Union[str, int, None]) -> str:
        """
        Get a mod's name from its PublishedFileID.

        Args:
            pfid: The PublishedFileID to lookup (str, int or None)

        Returns:
            str: The mod name or "Unknown Mod" if not found
        """
        if not pfid:
            return f"{pfid}"

        pfid_str = str(pfid)
        if not pfid_str.isdigit():
            return f"{pfid_str}"

        metadata = self._get_mod_metadata(pfid_str)
        if not isinstance(metadata, dict):
            return f"{pfid_str}"

        name = metadata.get("name") or metadata.get("steamName")
        return repr(name) if name else f"{pfid_str}"

    def _get_mod_metadata(self, pfid: str) -> dict[str, Any]:
        """
        Helper method to get metadata for a mod by PublishedFileID.
        Checks both internal and external metadata sources.

        Args:
            pfid: The PublishedFileID to lookup
        Returns:
            Dictionary containing metadata or empty dict if not found
        """
        try:
            if not hasattr(self, "metadata_manager"):
                self.metadata_manager = MetadataManager.instance()

            # First check internal local metadata
            if hasattr(self.metadata_manager, "internal_local_metadata"):
                for (
                    uuid,
                    metadata,
                ) in self.metadata_manager.internal_local_metadata.items():
                    if (
                        metadata
                        and isinstance(metadata, dict)
                        and metadata.get("publishedfileid") == pfid
                    ):
                        return metadata

            # Then check external steam metadata if available
            if hasattr(self.metadata_manager, "external_steam_metadata"):
                steam_metadata = getattr(
                    self.metadata_manager, "external_steam_metadata", {}
                )
                if isinstance(steam_metadata, dict):
                    return steam_metadata.get(pfid, {})

            return {}
        except Exception as e:
            logger.error(f"Metadata lookup failed: {str(e)}")
            return {}

    def _should_exclude(self, file_path: str) -> bool:
        """Check if a file or directory should be excluded based on exclude_options."""
        exclude_options = self.options.get("exclude_options", {})

        # Skip translations
        if exclude_options.get("skip_translations") and "Languages" in file_path:
            return True

        # Skip .git folders
        if exclude_options.get("skip_git") and ".git" in file_path:
            return True

        # Skip Source folders
        if exclude_options.get("skip_source") and "Source" in file_path:
            return True

        # Skip Textures folders
        if exclude_options.get("skip_textures") and "Textures" in file_path:
            return True

        return False

    def run(self) -> None:
        try:
            logger.info(f"Starting search with text: {self.pattern}")
            logger.info(f"Search options: {self.options}")
            logger.info(f"Search paths: {self.root_paths}")

            # Initialize counters
            self.processed_files = 0
            self.found_files = 0

            # Start with an estimate and reset timer
            logger.info("Starting search...")
            self.stats.emit("Starting search...")

            # Get search method based on selected algorithm
            algorithm = self.options.get("algorithm", "simple search")

            # If using regex, force pattern search
            if self.options.get("use_regex", False) and algorithm != "pattern search":
                algorithm = "pattern search"
                logger.info("Using regex pattern - switching to pattern search")

            # Map algorithm display names to method names
            algorithm_map = {
                "xml search": "xml_search",
                "standard search": "standard_search",
                "pattern search": "pattern_search",
            }

            # Get method name from the map or convert from display name
            method_name = algorithm_map.get(algorithm, algorithm.replace(" ", "_"))

            # Check if the method exists
            if not hasattr(self.searcher, method_name):
                logger.warning(
                    f"Search method {method_name} not found, falling back to simple_search"
                )
                method_name = "simple_search"

            search_method = getattr(self.searcher, method_name)
            logger.info(f"Using search method: {algorithm} ({method_name})")

            # Perform the search
            for root_path in self.root_paths:
                self.stats.emit(f"Searching in: {root_path}")
                for result in search_method(self.pattern, [root_path], self.options):
                    mod_name, file_name, path = result
                    preview = self._get_file_preview(path)
                    self.result_found.emit(mod_name, file_name, path, preview)

            self.finished.emit()
            self.stats.emit("Search complete")

        except Exception as e:
            logger.error(f"Unexpected error during search: {e}")
            self.error.emit(str(e))


class FileSearchController(QObject):
    """
    Controller class for managing file search functionality.

    This class handles user interactions from the file search dialog,
    manages the search worker thread, and updates the UI with search results.

    Signals:
        search_results_updated (): Emitted when the search results are updated.
    """

    # define signals
    search_results_updated = Signal()

    def __init__(
        self,
        settings: Settings,
        settings_controller: SettingsController,
        dialog: FileSearchDialog,
        active_mod_ids: Optional[set[str]] = None,
    ) -> None:
        """
        Initialize the FileSearchController.

        Args:
            settings (Settings): Application settings instance.
            settings_controller (SettingsController): Controller for settings management.
            dialog (FileSearchDialog): The file search dialog UI component.
            active_mod_ids (Optional[Set[str]]): Set of active mod IDs for filtering.
        """
        super().__init__()
        self.settings = settings
        self.dialog = dialog
        self.settings_controller = settings_controller
        self.mods_panel = ModsPanel(
            settings_controller=self.settings_controller,
        )
        self.active_mod_ids = (
            active_mod_ids or set()
        )  # This is used for the controller, not the worker
        self.search_results: list[SearchResult] = []
        self.search_worker: Optional[SearchWorker] = None
        self.searcher = FileSearch()
        # Initialize MetadataManager
        self.metadata_manager = metadata.MetadataManager.instance()

        # connect signals
        self.dialog.search_button.clicked.connect(self._on_search_clicked)
        self.dialog.stop_button.clicked.connect(self._on_stop_clicked)
        self.dialog.search_input.returnPressed.connect(self._on_search_clicked)
        self.dialog.filter_input.textChanged.connect(self._on_filter_changed)

    def set_active_mod_ids(self, active_mod_ids: set[str]) -> None:
        """
        Update the list of active mod IDs used for filtering searches.

        Args:
            active_mod_ids (Set[str]): Set of active mod IDs.
        """
        self.active_mod_ids = active_mod_ids

    def get_search_paths(self) -> list[str]:
        """
        Get the list of search paths from the dialog's search options.

        Returns:
            List[str]: List of directory paths to search.
        """
        return self.dialog.get_search_options().get("paths", [])

    def get_search_text(self) -> str:
        """
        Get the current search text from the dialog input.

        Returns:
            str: The search text entered by the user.
        """
        return self.dialog.search_input.text()

    def clear_results(self) -> None:
        """
        Clear the current search results and notify listeners.
        """
        self.search_results.clear()
        self.search_results_updated.emit()

    def update_results(self) -> None:
        """
        Notify listeners that the search results have been updated.
        """
        self.search_results_updated.emit()

    def _setup_search_worker(
        self,
        root_paths: list[str],
        pattern: str,
        options: dict[str, Any],
        active_mod_ids: Optional[set[str]] = None,
        scope: str = "all mods",
    ) -> SearchWorker:
        """
        Set up and configure a new SearchWorker thread.

        Args:
            root_paths (List[str]): List of directory paths to search.
            pattern (str): The search pattern.
            options (Dict[str, Any]): Search options and flags.
            active_mod_ids (Optional[Set[str]]): Set of mod IDs for filtering.
            scope (str): Search scope ("active mods", "inactive mods", "all mods", etc.).

        Returns:
            SearchWorker: Configured search worker instance.
        """
        if self.search_worker is not None:
            # Properly clean up the previous worker
            try:
                self.search_worker.quit()
                if not self.search_worker.wait(1000):  # Wait up to 1 second
                    self.search_worker.terminate()
            except Exception as e:
                logger.warning(f"Error cleaning up previous search worker: {e}")

        # Log search parameters
        logger.info(f"Setting up search worker with pattern: {pattern}")
        logger.info(f"Search options: {options}")
        logger.info(f"Search scope: {scope}")

        # Create and configure the worker
        worker = SearchWorker(root_paths, pattern, options, active_mod_ids, scope)

        # Connect signals
        worker.result_found.connect(self.dialog.add_result)
        worker.progress.connect(self.dialog.update_progress)
        worker.stats.connect(self.dialog.update_stats)
        worker.finished.connect(self._on_search_finished)
        worker.error.connect(self._on_search_error)

        # Update UI to show search is starting
        self.dialog.update_stats("Preparing search...")

        return worker

    def _on_search_start(self) -> None:
        """Clear filter and reset UI when a new search starts."""
        self.dialog.filter_input.clear()  # Clear the filter input
        self.dialog.clear_results()  # Clear previous results
        self.dialog.update_stats("Starting new search...")

    def _on_search_clicked(self) -> None:
        """
        Handle the search button click event.

        Disables the search button, enables the stop button, collects search options,
        determines search scope and paths, and starts the search worker.
        """
        self._on_search_start()
        self.dialog.search_button.setEnabled(False)
        self.dialog.search_button.setStyleSheet(
            "font-weight: bold; background-color: nornal;"
        )
        self.dialog.stop_button.setEnabled(True)
        self.dialog.stop_button.setStyleSheet(
            "font-weight: bold; background-color: red;"
        )

        options = self.dialog.get_search_options()
        search_text = self.dialog.search_input.text()

        # Add to recent searches
        self.dialog.add_recent_search(search_text)

        scope = options.get("scope", "all mods")

        # Set search paths based on the active scope
        root_paths = []
        instance = self.settings.instances[self.settings.current_instance]
        mod_ids_for_search = set()

        # For active mods, we'll use get_active_mods_paths() directly
        # This is just for collecting mod IDs for other purposes
        if scope == "active mods":
            # Get active mod IDs by extracting folder names from active mod paths
            active_paths = self.get_active_mods_paths()
            for path in active_paths:
                mod_id = os.path.basename(path)
                mod_ids_for_search.add(mod_id)

        if scope == "inactive mods":
            # Get inactive mod IDs by extracting folder names from inactive mod paths
            inactive_paths = self.get_inactive_mods_paths()
            for path in inactive_paths:
                mod_id = os.path.basename(path)
                mod_ids_for_search.add(mod_id)

        if scope == "all mods":
            # Get all mod IDs by combining active and inactive mods
            all_uuids = set(self.mods_panel.active_mods_list.uuids) | set(
                self.mods_panel.inactive_mods_list.uuids
            )
            # Use our helper method to get paths and extract IDs
            all_paths = self._get_mod_paths_from_uuids(list(all_uuids))
            for path in all_paths:
                mod_id = os.path.basename(path)
                mod_ids_for_search.add(mod_id)

        if scope == "all mods":
            root_paths = self.all_mods_path()
        elif scope == "active mods":
            # Get direct paths to active mod folders
            logger.info("Searching in active mods")
            root_paths = self.get_active_mods_paths()
            logger.info(f"Found {len(root_paths)} active mod paths")
            if not root_paths:
                # Show error if no active mods found
                show_warning(
                    title="Active Mods Error",
                    text="No active mods found",
                )
                return self._on_search_finished()
        elif scope == "inactive mods":
            # Get direct paths to inactive mod folders
            logger.info("Searching in inactive mods")
            root_paths = self.get_inactive_mods_paths()
            logger.info(f"Found {len(root_paths)} inactive mod paths")
            if not root_paths:
                # Show error if no inactive mods found
                show_warning(
                    title="Inactive Mods Error",
                    text="No inactive mods found",
                )
                return self._on_search_finished()
        elif scope == "configs folder" and instance.config_folder:
            root_paths = [instance.config_folder]

        # Update the options with the new paths
        options["paths"] = root_paths

        if not root_paths:
            self.location_not_set()
            return
        # For active/inactive mods, we're already searching in specific mod folders
        # so we don't need to filter by mod ID
        root_paths_list = (
            list(root_paths) if not isinstance(root_paths, list) else root_paths
        )

        # Log the search paths
        logger.info(f"Searching in {len(root_paths_list)} paths: {root_paths_list}")

        # Start the search worker
        # Pass mod_ids_for_search for active/inactive mods to enable filtering
        if scope in ("active mods", "inactive mods"):
            self._start_search_worker(
                root_paths_list, search_text, options, mod_ids_for_search, scope
            )
        else:
            self._start_search_worker(
                root_paths_list, search_text, options, None, scope
            )

    def _start_search_worker(
        self,
        root_paths: list[str],
        search_text: str,
        options: dict[str, Any],
        mod_ids: Optional[set[str]] = None,
        scope: str = "all mods",
    ) -> None:
        """
        Start a new search worker thread to perform the search.

        Args:
            root_paths (List[str]): List of directory paths to search.
            search_text (str): The search text or pattern.
            options (Dict[str, Any]): Search options and flags.
            mod_ids (Optional[Set[str]]): Set of mod IDs for filtering.
            scope (str): Search scope ("active mods", "inactive mods", "all mods", etc.).
        """
        self.searcher = FileSearch()

        # Update the dialog's search paths
        self.dialog.set_search_paths(root_paths)
        self.dialog.clear_results()

        worker = self._setup_search_worker(
            root_paths, search_text, options, mod_ids, scope
        )
        worker.start()
        self.search_worker = worker

    def all_mods_path(self) -> list[str]:
        """
        Get paths to all mod folders (local and workshop).

        Returns:
            List[str]: List of absolute paths to mod folders.
        """
        active_mods = self.get_active_mods_paths()
        inactive_mods = self.get_inactive_mods_paths()

        # Combine active and inactive mod paths
        root_paths = active_mods + inactive_mods

        # Log the combined paths for debugging
        logger.info(
            f"All mods paths: {len(root_paths)} paths found (active + inactive)"
        )

        return root_paths

    def _get_mod_paths_from_uuids(self, uuids: list[str]) -> list[str]:
        """
        Helper method to get mod paths from a list of UUIDs.

        Args:
            uuids (List[str]): List of mod UUID strings.

        Returns:
            List[str]: List of mod folder paths corresponding to the UUIDs.
        """
        # Get direct paths to the mods instead of just mod IDs
        mod_paths = []

        for uuid in uuids:
            # Check if the mod is in local metadata
            if uuid in self.metadata_manager.internal_local_metadata:
                mod_path = self.metadata_manager.internal_local_metadata[uuid]["path"]
                if os.path.isdir(mod_path):
                    mod_paths.append(mod_path)
                    logger.debug(f"Added mod path: {mod_path}")

        logger.info(f"Found {len(mod_paths)} mod paths from {len(uuids)} UUIDs")
        return mod_paths

    def get_specific_mod_paths(self, mod_ids: set[str]) -> list[str]:
        """
        Get direct paths to specific mods based on their IDs.

        Args:
            mod_ids (set[str]): Set of mod IDs.

        Returns:
            List[str]: List of mod folder paths for the specified mod IDs.
        """
        if not mod_ids:
            return []

        instance = self.settings.instances[self.settings.current_instance]
        specific_paths = []

        # Check local folder
        if instance.local_folder and instance.local_folder != "":
            local_folder = os.path.abspath(instance.local_folder)
            for mod_id in mod_ids:
                mod_path = os.path.join(local_folder, mod_id)
                if os.path.isdir(mod_path):
                    specific_paths.append(mod_path)

        # Check workshop folder
        if instance.workshop_folder and instance.workshop_folder != "":
            workshop_folder = os.path.abspath(instance.workshop_folder)
            for mod_id in mod_ids:
                mod_path = os.path.join(workshop_folder, mod_id)
                if os.path.isdir(mod_path):
                    specific_paths.append(mod_path)

        return specific_paths

    def get_active_mods_paths(self) -> list[str]:
        """
        Get direct paths to active mod folders only.

        Returns:
            List[str]: List of active mod folder paths.
        """
        # Use metadata.get_mods_from_list to get active mod UUIDs
        instance = self.settings.instances[self.settings.current_instance]
        mod_list_path = os.path.join(instance.config_folder, "ModsConfig.xml")
        active_uuids, _, _, _ = metadata.get_mods_from_list(mod_list_path)
        logger.info(f"Getting paths for {len(active_uuids)} active mods from mod list")
        return get_mod_paths_from_uuids(active_uuids)

    def get_inactive_mods_paths(self) -> list[str]:
        """
        Get direct paths to inactive mod folders only.

        Returns:
            List[str]: List of inactive mod folder paths.
        """
        # Use metadata.get_mods_from_list to get inactive mod UUIDs
        instance = self.settings.instances[self.settings.current_instance]
        mod_list_path = os.path.join(instance.config_folder, "ModsConfig.xml")
        _, inactive_uuids, _, _ = metadata.get_mods_from_list(mod_list_path)
        logger.info(
            f"Getting paths for {len(inactive_uuids)} inactive mods from mod list"
        )
        return get_mod_paths_from_uuids(inactive_uuids)

    def _on_stop_clicked(self) -> None:
        """
        Handle the stop button click event.

        Stops the search worker thread if it is running, updates the UI accordingly,
        and resets the UI state.
        """
        if self.search_worker and self.search_worker.isRunning():
            # Disable the stop button to prevent multiple clicks
            self.dialog.stop_button.setEnabled(False)

            # Update the UI to show search is stopping
            self.dialog.update_stats("Stopping search...")

            # Set the stop flag in the searcher
            self.searcher.stop_search()

            # Terminate the worker thread immediately
            self.search_worker.terminate()

            # Update the UI to show search has stopped
            self.dialog.update_stats("Search stopped by user")

        # Reset the UI
        self._on_search_finished()

    def _on_search_finished(self) -> None:
        """
        Handle completion of the search.

        Resets the UI buttons to their default enabled/disabled states.
        """
        # Reset buttons
        self.dialog.search_button.setEnabled(True)
        self.dialog.search_button.setStyleSheet(
            "font-weight: bold; background-color: green;"
        )
        self.dialog.stop_button.setEnabled(False)
        self.dialog.stop_button.setStyleSheet(
            "font-weight: bold; background-color: normal;"
        )

    def _on_search_error(self, error_msg: str) -> None:
        """
        Handle errors that occur during the search.

        Displays a warning dialog with the error message and resets the UI.
        Provides more detailed error information and potential solutions.

        Args:
            error_msg (str): The error message to display.
        """
        # Check for common error patterns and provide helpful messages
        if "regex" in error_msg.lower():
            show_warning(
                title="Regular Expression Error",
                text="There was an error with your regular expression pattern.",
                information=f"{error_msg}\n\nTry simplifying your pattern or check for syntax errors.",
            )
        elif "permission" in error_msg.lower() or "access" in error_msg.lower():
            show_warning(
                title="File Access Error",
                text="RimSort doesn't have permission to access some files.",
                information=f"{error_msg}\n\nTry running RimSort with administrator privileges or check folder permissions.",
            )
        elif "memory" in error_msg.lower():
            show_warning(
                title="Memory Error",
                text="RimSort ran out of memory while searching.",
                information=f"{error_msg}\n\nTry searching in smaller batches or use the 'streaming search' method for very large files.",
            )
        else:
            show_warning(
                title="Search Error",
                text="An error occurred during the search.",
                information=f"{error_msg}\n\nPlease check your settings and try again.",
            )

        # Update the stats label to show the error
        self.dialog.update_stats(f"Search failed: {error_msg[:100]}...")

        # Reset the UI
        self._on_search_finished()

    def _on_filter_changed(self, text: str) -> None:
        """
        Handle changes to the filter text input with debounce.

        Args:
            text (str): The current filter text.
        """
        if not hasattr(self, "_filter_timer"):
            self._filter_timer = QTimer()
            self._filter_timer.setSingleShot(True)
            self._filter_timer.timeout.connect(self._apply_filter)

        self._filter_text = text.lower()
        self._filter_timer.start(
            200
        )  # Reduced debounce to 200 ms for more responsiveness

    def _apply_filter(self) -> None:
        """
        Apply the current filter text to the results table.

        Hides rows that do not match the filter text and updates the stats label.
        """
        filter_text = self._filter_text
        logger.debug(f"Applying filter with text: '{filter_text}'")
        logger.debug(f"Total rows: {self.dialog.results_table.rowCount()}")

        visible_rows = 0
        for row in range(self.dialog.results_table.rowCount()):
            show_row = False
            for col in range(self.dialog.results_table.columnCount()):
                item = self.dialog.results_table.item(row, col)
                if item is not None:
                    item_text = item.text().lower()
                    if filter_text in item_text:
                        show_row = True
                        break

            self.dialog.results_table.setRowHidden(row, not show_row)
            if show_row:
                visible_rows += 1

        # Update the stats label to show filter results
        self.dialog.update_stats(
            f"Filter: {visible_rows} of {self.dialog.results_table.rowCount()} results visible"
        )

        logger.debug(
            f"Filter complete - Visible rows: {visible_rows}/{self.dialog.results_table.rowCount()}"
        )

    def location_not_set(self) -> None:
        """
        Handle the case when no valid search location is set.

        Displays a warning dialog informing the user to configure game folders in settings.
        """
        show_warning(
            title="Location Not Set",
            text="No valid search location is available for the selected scope. Please configure your game folders in the settings.",
        )

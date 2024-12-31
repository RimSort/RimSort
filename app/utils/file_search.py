import os
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, Generator, List, Optional, Tuple


class FileSearch:
    """utility class for file searching"""

    def __init__(self) -> None:
        """initialize file search"""
        self.active_mod_ids: set[str] = set()
        self.search_scope: str = ""
        self.stop_requested: bool = False

    def stop_search(self) -> None:
        """stop current search operation"""
        self.stop_requested = True

    def reset(self) -> None:
        """reset searcher state"""
        self.stop_requested = False
        self.active_mod_ids = set()
        self.search_scope = ""

    def set_active_mods(self, active_mod_ids: set[str], scope: str) -> None:
        """set active mod IDs and search scope"""
        self.active_mod_ids = active_mod_ids
        self.search_scope = scope

    def _get_mod_name(self, file_path: str) -> str:
        """extract mod name from file path"""
        path_parts = os.path.normpath(file_path).split(os.sep)
        try:
            # find the Mods folder in the path and get the next folder name
            mods_index = path_parts.index("Mods")
            if mods_index + 1 < len(path_parts):
                return path_parts[mods_index + 1]
        except ValueError:
            pass
        return os.path.basename(os.path.dirname(file_path))

    def _should_process_file(self, file_path: str, options: Dict[str, Any]) -> bool:
        """check if file should be processed based on options"""
        if self.stop_requested:
            return False

        # get file extension
        _, ext = os.path.splitext(file_path.lower())

        # list of text file extensions we want to search
        text_extensions = {
            ".xml",
            ".txt",
            ".json",
            ".md",
            ".cfg",
            ".config",
            ".patch",
            ".cs",
            ".py",
            ".lua",
            ".sh",
            ".bat",
            ".ini",
            ".yaml",
            ".yml",
            ".html",
            ".css",
            ".js",
            ".log",
            ".def",
            ".properties",
        }

        # list of binary/non-text extensions to skip
        skip_extensions = {
            ".dll",
            ".exe",
            ".pdb",
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".bmp",
            ".ico",
            ".zip",
            ".rar",
            ".7z",
            ".pdf",
            ".doc",
            ".docx",
            ".xls",
            ".xlsx",
            ".mp3",
            ".wav",
            ".ogg",
            ".mp4",
            ".avi",
            ".mov",
            ".ttf",
            ".otf",
            ".woff",
            ".woff2",
            ".eot",
        }

        # if it's a known binary format, skip it
        if ext in skip_extensions:
            print(f"Skipping binary file: {file_path}")
            return False

        # if xml_only is set, only process .xml files
        if options.get("xml_only") and ext != ".xml":
            return False

        # if it's not a known text format, try to detect if it's text
        if ext not in text_extensions:
            try:
                # try to read first few bytes to check if it's text
                with open(file_path, "rb") as f:
                    chunk = f.read(1024)
                    # if it contains null bytes, it's probably binary
                    if b"\x00" in chunk:
                        print(f"Skipping likely binary file: {file_path}")
                        return False
            except Exception:
                return False

        # normalize path for consistent comparison
        norm_path = os.path.normpath(file_path)
        if (
            options.get("skip_translations")
            and os.path.join("Languages", "") in norm_path
        ):
            return False

        # check active/inactive status if searching in specific scope
        if self.search_scope in ["active mods", "not active mods"]:
            mod_name = self._get_mod_name(file_path)
            is_active = mod_name in self.active_mod_ids

            # For debugging
            print(
                f"Checking mod {mod_name} - active: {is_active}, scope: {self.search_scope}"
            )

            if self.search_scope == "active mods":
                return is_active
            elif self.search_scope == "not active mods":
                return not is_active

        return True

    def _build_file_index(
        self,
        root_paths: List[str],
        result_callback: Optional[Callable[[str, str, str, str], None]] = None,
    ) -> None:
        """build index of files for faster searching"""
        self._file_index = {}
        total_files = 0

        # first count total files
        for root_path in root_paths:
            for root, _, files in os.walk(root_path):
                if self.stop_requested:
                    return
                total_files += len(files)

        processed = 0
        for root_path in root_paths:
            for root, _, files in os.walk(root_path):
                if self.stop_requested:
                    return
                for file in files:
                    processed += 1
                    full_path = os.path.join(root, file)
                    if result_callback:
                        result_callback(
                            self._get_mod_name(full_path), file, "", ""
                        )  # indexing progress
                    try:
                        with open(full_path, "r", encoding="utf-8") as f:
                            content = f.read()
                        self._file_index[full_path] = (
                            content.lower()
                        )  # store lowercase for case-insensitive search
                    except (UnicodeDecodeError, IOError):
                        continue

    def simple_search(
        self,
        search_text: str,
        root_paths: List[str],
        options: Dict[str, Any],
        result_callback: Optional[Callable[[str, str, str, str], None]] = None,
    ) -> Generator[Tuple[str, str, str], None, None]:
        """simple linear search through files"""
        # Set active mods and scope before starting search
        active_mod_ids = options.get("active_mod_ids", set())
        scope = options.get("scope", "all mods")
        self.set_active_mods(active_mod_ids, scope)

        print(f"Starting simple search with scope: {scope}")
        print(f"Active mods: {len(active_mod_ids)}")
        print(f"Search paths: {root_paths}")

        for root_path in root_paths:
            for root, _, files in os.walk(root_path):
                if self.stop_requested:
                    return

                for file in files:
                    full_path = os.path.join(root, file)
                    if not self._should_process_file(full_path, options):
                        continue

                    try:
                        with open(full_path, "r", encoding="utf-8") as f:
                            content = f.read()

                        found_match = False
                        if options.get("case_sensitive"):
                            found_match = search_text in content
                        else:
                            found_match = search_text.lower() in content.lower()

                        if found_match:
                            mod_name = self._get_mod_name(full_path)
                            result = (mod_name, file, full_path)
                            if result_callback:
                                result_callback(*result, content)
                            yield result
                        elif result_callback:
                            result_callback(self._get_mod_name(full_path), file, "", "")
                    except (UnicodeDecodeError, IOError):
                        if result_callback:
                            result_callback(self._get_mod_name(full_path), file, "", "")
                        continue

    def pattern_search(
        self,
        search_text: str,
        root_paths: List[str],
        options: Dict[str, Any],
        result_callback: Optional[Callable[[str, str, str, str], None]] = None,
    ) -> Generator[Tuple[str, str, str], None, None]:
        """search using regex pattern matching"""
        # Set active mods and scope before starting search
        active_mod_ids = options.get("active_mod_ids", set())
        scope = options.get("scope", "all mods")
        self.set_active_mods(active_mod_ids, scope)

        try:
            flags = 0 if options.get("case_sensitive") else re.IGNORECASE
            pattern = re.compile(search_text, flags)

            for root_path in root_paths:
                mod_name = os.path.basename(root_path)
                for root, _, files in os.walk(root_path):
                    if self.stop_requested:
                        return

                    for file in files:
                        if not self._should_process_file(file, options):
                            continue

                        full_path = os.path.join(root, file)
                        try:
                            with open(full_path, "r", encoding="utf-8") as f:
                                content = f.read()

                            if pattern.search(content):
                                result = (mod_name, file, full_path)
                                if result_callback:
                                    result_callback(*result, content)
                                yield result
                            elif result_callback:
                                result_callback(mod_name, file, "", "")  # no match
                        except (UnicodeDecodeError, IOError):
                            if result_callback:
                                result_callback(mod_name, file, "", "")  # failed file
                            continue
        except re.error:
            # if regex is invalid, fall back to simple search
            yield from self.simple_search(
                search_text, root_paths, options, result_callback
            )

    def parallel_search(
        self,
        search_text: str,
        root_paths: List[str],
        options: Dict[str, Any],
        result_callback: Optional[Callable[[str, str, str, str], None]] = None,
    ) -> Generator[Tuple[str, str, str], None, None]:
        """search files in parallel using thread pool"""
        # Set active mods and scope before starting search
        active_mod_ids = options.get("active_mod_ids", set())
        scope = options.get("scope", "all mods")
        self.set_active_mods(active_mod_ids, scope)

        def search_file(args: Tuple[str, str]) -> Optional[Tuple[str, str, str, str]]:
            full_path, _ = args  # ignore the passed mod_name, calculate it from path
            file_name = os.path.basename(full_path)
            mod_name = self._get_mod_name(full_path)

            if not self._should_process_file(full_path, options):
                if result_callback:
                    result_callback(mod_name, file_name, "", "")  # skipped file
                return None

            try:
                with open(full_path, "r", encoding="utf-8") as f:
                    content = f.read()

                found_match = False
                if options.get("case_sensitive"):
                    found_match = search_text in content
                else:
                    found_match = search_text.lower() in content.lower()

                if found_match:
                    return (mod_name, file_name, full_path, content)
                else:
                    if result_callback:
                        result_callback(mod_name, file_name, "", "")  # no match
            except (UnicodeDecodeError, IOError):
                if result_callback:
                    result_callback(mod_name, file_name, "", "")  # failed file
                pass
            return None

        # collect all files first
        all_files = []
        for root_path in root_paths:
            for root, _, files in os.walk(root_path):
                for file in files:
                    full_path = os.path.join(root, file)
                    all_files.append(
                        (full_path, "")
                    )  # empty mod_name, will be calculated in search_file

        # search in parallel
        with ThreadPoolExecutor() as executor:
            for result in executor.map(search_file, all_files):
                if self.stop_requested:
                    return
                if result:
                    mod_name, file_name, path, content = result
                    if result_callback:
                        result_callback(mod_name, file_name, path, content)
                    yield (mod_name, file_name, path)

import os
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import wraps
from pathlib import Path
from typing import (
    Any,
    Callable,
    Dict,
    Generator,
    List,
    Optional,
    Tuple,
    TypeAlias,
    cast,
)


@dataclass
class SearchParams:
    """common parameters for all search operations"""

    search_text: str
    root_paths: List[str]
    options: Dict[str, Any]
    result_callback: Optional[Callable[[str, str, str, str], None]] = None
    is_pattern_search: bool = False
    search_type: str = "text"


SearchResult: TypeAlias = Generator[Tuple[str, str, str], None, None]
SearchCallback: TypeAlias = Optional[Callable[[str, str, str, str], None]]
SearchMethod: TypeAlias = Callable[
    ["FileSearch", str, List[str], Dict[str, Any], SearchCallback], SearchResult
]


def search_method(
    is_pattern: bool = False, search_type: str = "text", parallel: bool = False
) -> Callable[[SearchMethod], SearchMethod]:
    """decorator for search methods to handle common parameters"""

    def decorator(func: SearchMethod) -> SearchMethod:
        @wraps(func)
        def wrapper(
            self: "FileSearch",
            text: str,
            paths: List[str],
            opts: Dict[str, Any],
            callback: SearchCallback = None,
        ) -> SearchResult:
            params = SearchParams(
                text,
                paths,
                opts,
                callback,
                is_pattern_search=is_pattern,
                search_type=search_type,
            )
            yield from self._search_files(params, parallel)

        return cast(SearchMethod, wrapper)

    return decorator


class FileSearch:
    """utility class for file searching"""

    # maximum file size to process (10MB)
    MAX_FILE_SIZE: int = 10 * 1024 * 1024

    def __init__(self) -> None:
        """initialize file search"""
        self.active_mod_ids: set[str] = set()
        self.search_scope: str = ""
        self.stop_requested: bool = False
        self._file_index: Dict[str, str] = {}
        self.file_paths: List[Path] = []

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
            print(f"Search stopped, skipping: {file_path}")
            return False

        # get file extension
        _, ext = os.path.splitext(file_path.lower())
        print(f"\nChecking if should process: {file_path}")
        print(f"File extension: {ext}")

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
            print(f"Skipping known binary extension: {ext}")
            return False

        # if xml_only is set, only process .xml files
        if options.get("xml_only") and ext != ".xml":
            print(f"XML only mode and not XML file, skipping: {file_path}")
            return False

        # if it's not a known text format, try to detect if it's text
        if ext not in text_extensions:
            print(f"Unknown extension {ext}, checking content type")
            try:
                # try to read first few bytes to check if it's text
                with open(file_path, "rb") as f:
                    chunk = f.read(1024)
                    # if it contains null bytes, it's probably binary
                    if b"\x00" in chunk:
                        print(f"Found null bytes, likely binary file: {file_path}")
                        return False
            except Exception as e:
                print(f"Error checking file type: {e}")
                return False

        # normalize path for consistent comparison
        norm_path = os.path.normpath(file_path)
        print(f"Normalized path: {norm_path}")

        if (
            options.get("skip_translations")
            and os.path.join("Languages", "") in norm_path
        ):
            print(f"Skipping translation file: {norm_path}")
            return False

        # check active/inactive status if searching in specific scope
        if self.search_scope in ["active mods", "not active mods"]:
            mod_name = self._get_mod_name(file_path)
            is_active = mod_name in self.active_mod_ids

            print(
                f"Checking mod status - Name: {mod_name}, Active: {is_active}, Scope: {self.search_scope}"
            )

            if self.search_scope == "active mods" and not is_active:
                print(f"Skipping inactive mod in active mods scope: {mod_name}")
                return False
            elif self.search_scope == "not active mods" and is_active:
                print(f"Skipping active mod in inactive mods scope: {mod_name}")
                return False

        print(f"File will be processed: {file_path}")
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

    def _init_search(
        self, search_text: str, root_paths: List[str], options: Dict[str, Any]
    ) -> List[Tuple[str, str]]:
        """initialize search parameters and logging"""
        active_mod_ids = options.get("active_mod_ids", set())
        scope = options.get("scope", "all mods")
        self.set_active_mods(active_mod_ids, scope)

        print("\n=== Starting search ===")
        print(f"Search text: {search_text}")
        print(f"Search scope: {scope}")
        print(f"Active mods: {active_mod_ids}")
        print(f"Options: {options}")
        print(f"Root paths: {root_paths}")

        # collect all files first
        all_files = []
        for root_path in root_paths:
            for root, _, files in os.walk(root_path):
                for file in files:
                    full_path = os.path.join(root, file)
                    all_files.append(
                        (full_path, "")
                    )  # empty mod_name, will be calculated in search_file

        return all_files

    def _process_search_result(
        self,
        mod_name: str,
        file_name: str,
        full_path: str,
        content: str,
        result_callback: Optional[Callable[[str, str, str, str], None]],
        matched: bool = True,
    ) -> Optional[Tuple[str, str, str]]:
        """process search result and handle callback"""
        if matched:
            if result_callback:
                result_callback(mod_name, file_name, full_path, content)
            return (mod_name, file_name, full_path)
        else:
            if result_callback:
                result_callback(mod_name, file_name, "", "")
            return None

    def _check_content_match(
        self, search_text: str, content: str, case_sensitive: bool
    ) -> bool:
        """check if content matches search text"""
        if case_sensitive:
            return search_text in content
        return search_text.lower() in content.lower()

    def _read_file_content(self, file_path: str) -> Optional[str]:
        """Read file content with error handling"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()
        except (UnicodeDecodeError, IOError) as e:
            print(f"Error reading file {file_path}: {e}")
            return None

    def _handle_file_check(
        self,
        full_path: str,
        mod_name: str,
        file_name: str,
        options: Dict[str, Any],
        result_callback: Optional[Callable[[str, str, str, str], None]] = None,
    ) -> Optional[str]:
        """Handle common file checking logic"""
        if not self._should_process_file(full_path, options):
            self._process_search_result(
                mod_name, file_name, "", "", result_callback, False
            )
            return None

        content = self._read_file_content(full_path)
        if content is None:
            self._process_search_result(
                mod_name, file_name, "", "", result_callback, False
            )
            return None

        return content

    def _handle_match_result(
        self,
        mod_name: str,
        file_name: str,
        full_path: str,
        content: str,
        result_callback: Optional[Callable[[str, str, str, str], None]] = None,
    ) -> Optional[Tuple[str, str, str]]:
        """Handle common result processing logic"""
        result = self._process_search_result(
            mod_name, file_name, full_path, content, result_callback
        )
        return result

    def _process_single_file(
        self,
        full_path: str,
        search_text: str,
        options: Dict[str, Any],
        result_callback: Optional[Callable[[str, str, str, str], None]] = None,
        is_pattern_search: bool = False,
    ) -> Optional[Tuple[str, str, str, str]]:
        """Process a single file for searching"""
        file_name = os.path.basename(full_path)
        mod_name = self._get_mod_name(full_path)

        content = self._handle_file_check(
            full_path, mod_name, file_name, options, result_callback
        )
        if content is None:
            return None

        # check for match based on search type
        if is_pattern_search:
            if re.search(
                search_text,
                content,
                re.IGNORECASE if not options.get("case_sensitive") else 0,
            ):
                return (mod_name, file_name, full_path, content)
        else:
            if self._check_content_match(
                search_text, content, options.get("case_sensitive", False)
            ):
                return (mod_name, file_name, full_path, content)

        self._process_search_result(mod_name, file_name, "", "", result_callback, False)
        return None

    def _handle_search_result(
        self,
        result: Optional[Tuple[str, str, str, str]],
        result_callback: Optional[Callable[[str, str, str, str], None]] = None,
    ) -> Optional[Tuple[str, str, str]]:
        """Handle search result processing"""
        if result:
            processed = self._handle_match_result(*result, result_callback)
            if processed:
                return processed
        return None

    def _process_files(
        self, params: SearchParams, files: List[Tuple[str, str]], parallel: bool = False
    ) -> Generator[Tuple[str, str, str], None, None]:
        """process files either sequentially or in parallel"""
        if parallel:

            def search_file(
                args: Tuple[str, str],
            ) -> Optional[Tuple[str, str, str, str]]:
                full_path, _ = args
                return self._process_single_file(
                    full_path,
                    params.search_text,
                    params.options,
                    params.result_callback,
                    params.is_pattern_search,
                )

            with ThreadPoolExecutor() as executor:
                for result in executor.map(search_file, files):
                    if self.stop_requested:
                        return
                    processed = self._handle_search_result(
                        result, params.result_callback
                    )
                    if processed:
                        yield processed
        else:
            for full_path, _ in files:
                if self.stop_requested:
                    return
                result = self._process_single_file(
                    full_path,
                    params.search_text,
                    params.options,
                    params.result_callback,
                    params.is_pattern_search,
                )
                processed = self._handle_search_result(result, params.result_callback)
                if processed:
                    yield processed

    def _search_files(
        self, params: SearchParams, parallel: bool = False
    ) -> Generator[Tuple[str, str, str], None, None]:
        """common search logic for all search types"""
        print(f"searching for {params.search_type}: {params.search_text}")
        all_files = self._init_search(
            params.search_text, params.root_paths, params.options
        )
        yield from self._process_files(params, all_files, parallel)

    @search_method()
    def simple_search(
        self,
        text: str,
        paths: List[str],
        opts: Dict[str, Any],
        callback: SearchCallback = None,
    ) -> SearchResult:
        """search for files containing text"""
        yield from ()  # implementation provided by decorator

    @search_method(is_pattern=True, search_type="pattern")
    def pattern_search(
        self,
        text: str,
        paths: List[str],
        opts: Dict[str, Any],
        callback: SearchCallback = None,
    ) -> SearchResult:
        """search for files matching regex pattern"""
        yield from ()  # implementation provided by decorator

    @search_method(parallel=True)
    def parallel_search(
        self,
        text: str,
        paths: List[str],
        opts: Dict[str, Any],
        callback: SearchCallback = None,
    ) -> SearchResult:
        """search files in parallel using thread pool"""
        yield from ()  # implementation provided by decorator

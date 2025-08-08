import os
import re
from typing import Any, Callable, Generator, Optional, Tuple

import chardet
from loguru import logger

from app.utils.metadata import MetadataManager
from app.utils.mod_utils import get_mod_name_from_pfid


class FileSearch:
    """Utility class for performing file searches with advanced features."""

    def __init__(self, metadata_manager: Optional[MetadataManager] = None) -> None:
        self.stop_requested = False
        self.metadata_manager = metadata_manager or MetadataManager.instance()

    def stop_search(self) -> None:
        """Stop the current search operation."""
        self.stop_requested = True

    def reset(self) -> None:
        """Reset the search state."""
        self.stop_requested = False

    def search(
        self,
        search_text: str,
        root_paths: list[str],
        options: dict[str, Any],
        result_callback: Optional[Callable[[str, str, str], None]] = None,
    ) -> Generator[dict[str, str], None, None]:
        """
        Perform a search for files containing the specified text.

        Args:
            search_text (str): The text to search for.
            root_paths (List[str]): List of root directories to search in.
            options (Dict[str, Any]): Search options (e.g., case sensitivity, file types).
            result_callback (Optional[Callable[[str, str, str], None]]): Callback for each result.

        Yields:
            Dict[str, str]: A dictionary containing file path and preview of the match.
        """
        # Set default options for the search method
        search_options = options.copy()
        search_options["preview"] = True
        search_options["return_dict"] = True

        for result in self._generic_search(
            search_text, root_paths, search_options, result_callback
        ):
            if isinstance(result, dict):
                yield result

    def _generic_search(
        self,
        search_text: str,
        root_paths: list[str],
        options: dict[str, Any],
        result_callback: Optional[Callable[..., None]] = None,
    ) -> Generator[dict[str, str] | Tuple[str, str, str], None, None]:
        """
        Generic search method that handles all search types.

        Args:
            search_text (str): The text to search for.
            root_paths (List[str]): List of root directories to search in.
            options (Dict[str, Any]): Search options including:
                - file_extensions (List[str]): File extensions to include
                - ignore_extensions (List[str]): File extensions to ignore
                - case_sensitive (bool): Whether the search is case-sensitive
                - use_regex (bool): Whether to use regex for matching
                - preview (bool): Whether to include a preview of the match
                - return_dict (bool): Whether to return a dictionary or tuple
            result_callback (Optional[Callable]): Callback for each result.

        Yields:
            Dict or Tuple depending on return_dict flag.
        """
        file_extensions = options.get("file_extensions", [])
        ignore_extensions = options.get("ignore_extensions", [])
        case_sensitive = options.get("case_sensitive", False)
        use_regex = options.get("use_regex", False)
        preview = options.get("preview", False)
        return_dict = options.get("return_dict", False)

        for root_path in root_paths:
            for dirpath, _, filenames in os.walk(root_path):
                if self.stop_requested:
                    logger.info("Search stopped by user.")
                    return

                for filename in filenames:
                    # Skip files with ignored extensions
                    if any(filename.endswith(ext) for ext in ignore_extensions):
                        continue

                    # Only process files with specified extensions if provided
                    if file_extensions and not any(
                        filename.lower().endswith(ext.lower())
                        for ext in file_extensions
                    ):
                        continue

                    file_path = os.path.join(dirpath, filename)
                    try:
                        for content_chunk in self._read_file_in_chunks(file_path):
                            if self._matches(
                                content_chunk, search_text, case_sensitive, use_regex
                            ):
                                if return_dict:
                                    result: dict[str, str] | Tuple[str, str, str] = {
                                        "file_path": file_path,
                                        "preview": self._get_preview(
                                            content_chunk, search_text, case_sensitive
                                        )
                                        if preview
                                        else "",
                                    }
                                else:
                                    # Extract pfid (publishedfileid) from file_path or root_path
                                    pfid = os.path.basename(root_path)
                                    mod_name = get_mod_name_from_pfid(pfid)
                                    result = (
                                        mod_name,
                                        filename,
                                        file_path,
                                    )
                                if result_callback:
                                    if isinstance(result, dict):
                                        result_callback(*result.values())
                                    elif isinstance(result, tuple):
                                        result_callback(*result)
                                    else:
                                        result_callback(result)
                                yield result
                                break
                    except Exception as e:
                        logger.error(f"Error reading file {file_path}: {e}")

    def _read_file_in_chunks(
        self, file_path: str, chunk_size: int = 1024 * 1024
    ) -> Generator[str, None, None]:
        """
        Read a file in chunks to handle large files efficiently.

        Args:
            file_path (str): Path to the file to read.
            chunk_size (int): Size of each chunk in bytes.

        Yields:
            str: A chunk of the file content.
        """
        if not os.path.exists(file_path):
            logger.warning(f"File does not exist: {file_path}")
            return

        try:
            with open(file_path, "rb") as f:
                while chunk := f.read(chunk_size):
                    yield chunk.decode("utf-8", errors="ignore")
        except Exception as e:
            logger.error(f"Failed to read file {file_path} in chunks: {e}")

    def _create_search_method(
        self, search_type: str
    ) -> Callable[
        [str, list[str], dict[str, Any], Optional[Callable[[str, str, str], None]]],
        Generator[Tuple[str, str, str], None, None],
    ]:
        """
        Factory method to create specialized search methods.

        Args:
            search_type (str): Type of search to create ("standard", "xml", "pattern")

        Returns:
            A method that performs the specified type of search
        """

        def search_method(
            search_text: str,
            root_paths: list[str],
            options: dict[str, Any],
            result_callback: Optional[Callable[[str, str, str], None]] = None,
        ) -> Generator[Tuple[str, str, str], None, None]:
            # Apply search-type specific options
            search_options = options.copy()
            search_options["return_dict"] = False

            if search_type == "xml":
                search_options["file_extensions"] = [".xml"]
            elif search_type == "pattern":
                search_options["use_regex"] = True

            # Use a generator expression to ensure we only yield tuples
            for result in self._generic_search(
                search_text, root_paths, search_options, result_callback
            ):
                if isinstance(result, tuple):
                    yield result

        return search_method

    # Create specialized search methods using the factory
    xml_search = property(lambda self: self._create_search_method("xml"))
    standard_search = property(lambda self: self._create_search_method("standard"))
    pattern_search = property(lambda self: self._create_search_method("pattern"))

    def _matches(
        self, content: str, search_text: str, case_sensitive: bool, use_regex: bool
    ) -> bool:
        """Check if the content matches the search criteria."""
        if use_regex:
            flags = 0 if case_sensitive else re.IGNORECASE
            return re.search(search_text, content, flags) is not None
        else:
            if not case_sensitive:
                content = content.lower()
                search_text = search_text.lower()
            return search_text in content

    def _get_preview(self, content: str, search_text: str, case_sensitive: bool) -> str:
        """Generate a preview of the match in the content."""
        lines = content.splitlines()
        for i, line in enumerate(lines):
            if search_text in (line if case_sensitive else line.lower()):
                start = max(0, i - 2)
                end = min(len(lines), i + 3)
                return "\n".join(lines[start:end])
        return ""

    def _read_file_with_encodings(self, file_path: str, encodings: list[str]) -> str:
        """
        Attempt to read a file using a list of encodings.

        Args:
            file_path (str): Path to the file to read.
            encodings (List[str]): List of encodings to try.

        Returns:
            str: The file content as a string, or an empty string on failure.
        """
        for encoding in encodings:
            try:
                with open(file_path, "r", encoding=encoding, errors="ignore") as f:
                    return f.read()
            except Exception:
                continue
        return ""

    def _read_file_with_fallback(self, file_path: str) -> str:
        """
        Read file content with multiple encoding attempts and improved error handling.

        Args:
            file_path: Path to the file to read.

        Returns:
            The file content as a string, or empty string on failure.
        """
        if not os.path.exists(file_path):
            logger.warning(f"File does not exist: {file_path}")
            return ""

        try:
            with open(file_path, "rb") as f:
                raw_data = f.read()
                result = chardet.detect(raw_data)
                encoding = result["encoding"]
                if encoding:
                    return raw_data.decode(encoding, errors="ignore")
        except Exception as e:
            logger.error(f"Failed to read file {file_path} with chardet: {e}")

        encodings = ["utf-8", "utf-8-sig", "latin-1", "cp1252", "iso-8859-1"]
        return self._read_file_with_encodings(file_path, encodings)

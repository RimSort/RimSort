import os
from dataclasses import dataclass
from datetime import datetime
from mimetypes import guess_type
from pathlib import Path
from typing import Optional, Union


@dataclass
class SearchResult:
    """Class representing a search result with enhanced metadata"""

    file_path: Path
    mod_name: str
    content: str
    match_line: int = 0
    match_context: str = ""
    file_size: int = 0
    file_type: str = ""
    visible: bool = True
    preview: Optional[str] = None
    match_count: int = 1
    last_modified: Optional[datetime] = None

    def __post_init__(self) -> None:
        """Initialize additional properties after creation"""
        # Get file stats if the file exists
        if os.path.exists(self.file_path):
            if not self.file_size:
                self.file_size = os.path.getsize(self.file_path)
            if not self.last_modified:
                self.last_modified = datetime.fromtimestamp(
                    os.path.getmtime(self.file_path)
                )

        # Set file_type based on extension if not provided
        if not self.file_type:
            self.file_type = self._determine_file_type()

    @property
    def file_name(self) -> str:
        """Get the file name from the path"""
        return self.file_path.name

    @property
    def directory(self) -> str:
        """Get the directory containing the file"""
        return str(self.file_path.parent)

    @property
    def extension(self) -> str:
        """Get the file extension"""
        return self.file_path.suffix.lower()

    @property
    def formatted_size(self) -> str:
        """Get the file size in a human-readable format"""
        if self.file_size < 1024:
            return f"{self.file_size} B"
        elif self.file_size < 1024 * 1024:
            return f"{self.file_size / 1024:.1f} KB"
        else:
            return f"{self.file_size / (1024 * 1024):.1f} MB"

    @property
    def formatted_date(self) -> str:
        """Get the last modified date in a readable format"""
        if self.last_modified:
            return self.last_modified.strftime("%Y-%m-%d %H:%M:%S")
        return "Unknown"

    def to_dict(self) -> dict[str, Union[str, int, bool]]:
        """Convert the search result to a dictionary for serialization"""
        return {
            "file_path": str(self.file_path),
            "mod_name": self.mod_name,
            "file_name": self.file_name,
            "directory": self.directory,
            "extension": self.extension,
            "match_line": self.match_line,
            "match_context": self.match_context,
            "file_size": self.file_size,
            "formatted_size": self.formatted_size,
            "file_type": self.file_type,
            "match_count": self.match_count,
            "last_modified": self.formatted_date,
            "visible": self.visible,
        }

    def _determine_file_type(self) -> str:
        """Determine the file type based on extension or MIME type."""
        mime_type, _ = guess_type(self.file_path)
        if mime_type:
            if "xml" in mime_type:
                return "XML"
            elif "text" in mime_type:
                return "Text"
            elif "image" in mime_type:
                return "Image"
            elif "application/json" in mime_type:
                return "JSON"
        return "Other"

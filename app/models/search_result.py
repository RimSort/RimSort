from dataclasses import dataclass
from pathlib import Path


@dataclass
class SearchResult:
    """class representing a search result"""

    file_path: Path
    mod_name: str
    content: str
    visible: bool = True

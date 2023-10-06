import os
from pathlib import Path

from PySide6.QtGui import QIcon


class ModListIcons:

    _ludeon_icon_path: str = str(Path(os.path.join(os.path.dirname(__file__), "../data/ludeon_icon.png")).resolve())
    _local_icon_path: str = str(Path(os.path.join(os.path.dirname(__file__), "../data/local_icon.png")).resolve())
    _steam_icon_path: str = str(Path(os.path.join(os.path.dirname(__file__), "../data/steam_icon.png")).resolve())

    _ludeon_icon: QIcon = None
    _local_icon: QIcon = None
    _steam_icon: QIcon = None

    @classmethod
    def ludeon_icon(cls) -> QIcon:
        if cls._ludeon_icon is None:
            cls._ludeon_icon = QIcon(cls._ludeon_icon_path)
        return cls._ludeon_icon

    @classmethod
    def local_icon(cls) -> QIcon:
        if cls._local_icon is None:
            cls._local_icon = QIcon(cls._local_icon_path)
        return cls._local_icon

    @classmethod
    def steam_icon(cls) -> QIcon:
        if cls._steam_icon is None:
            cls._steam_icon = QIcon(cls._steam_icon_path)
        return cls._steam_icon

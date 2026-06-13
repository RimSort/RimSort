"""Service for tracking and managing MainContent child windows."""

from typing import Any

from PySide6.QtWidgets import QWidget

import app.utils.constants as app_constants
from app.utils.ignore_manager import IgnoreManager
from app.utils.metadata import MetadataManager


class WindowManager:
    """Tracks child windows owned by MainContent and provides cleanup.

    Handles both instance-attribute windows (e.g. ``self.rule_editor``)
    and list-tracked windows (created as local variables). Also owns
    query helpers for identifying mods with missing properties.
    """

    def __init__(self, metadata_manager: MetadataManager) -> None:
        self._metadata_manager = metadata_manager
        self._child_windows: list[QWidget] = []
        self._tracked_attrs: list[tuple[Any, str]] = []

    def register(self, window: QWidget) -> None:
        """Track a window that was created as a local variable."""
        self._child_windows.append(window)

    def register_attr(self, instance: Any, attr_name: str) -> None:
        """Track an instance attribute that holds a window reference."""
        self._tracked_attrs.append((instance, attr_name))

    def close_all(self) -> None:
        """Close all tracked windows and clear tracking lists."""
        for instance, attr_name in self._tracked_attrs:
            window = getattr(instance, attr_name, None)
            if window is not None:
                try:
                    window.close()
                except Exception:
                    # Avoid RuntimeError: libshiboken: Internal C++ object (Panel) already deleted.
                    pass
        for window in self._child_windows:
            if window is not None:
                try:
                    window.close()
                except Exception:
                    # Avoid RuntimeError: libshiboken: Internal C++ object (Panel) already deleted.
                    pass
        self._child_windows.clear()
        self._tracked_attrs.clear()

    def get_missing_packageid_uuids(self) -> list[str]:
        """Identify mods lacking a valid Package ID in their About.xml."""
        return [
            uuid
            for uuid, mod_metadata in self._metadata_manager.internal_local_metadata.items()
            if mod_metadata.get("packageid") == app_constants.DEFAULT_MISSING_PACKAGEID
        ]

    def get_missing_publishfieldid_uuids(self) -> list[str]:
        """Identify mods lacking a Publish Field ID (Steam Workshop ID)."""
        ignored_mods = IgnoreManager.load_ignored_mods()
        return [
            uuid
            for uuid, mod_metadata in self._metadata_manager.internal_local_metadata.items()
            if mod_metadata.get("publishedfileid") is None
            and mod_metadata.get("packageid") not in app_constants.RIMWORLD_PACKAGE_IDS
            and mod_metadata.get("packageid") not in ignored_mods
        ]

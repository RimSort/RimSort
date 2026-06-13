"""Service for tracking and managing MainContent child windows."""

from typing import Any

from PySide6.QtWidgets import QWidget

import app.utils.constants as app_constants
from app.controllers.metadata_controller import MetadataController
from app.models.metadata.metadata_structure import AboutXmlMod
from app.utils.ignore_manager import IgnoreManager


class WindowManager:
    """Tracks child windows owned by MainContent and provides cleanup.

    Handles both instance-attribute windows (e.g. ``self.rule_editor``)
    and list-tracked windows (created as local variables). Also owns
    query helpers for identifying mods with missing properties.
    """

    def __init__(self, metadata_controller: MetadataController) -> None:
        self._metadata_controller = metadata_controller
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

    def get_missing_packageid_paths(self) -> list[str]:
        """Identify mods lacking a valid Package ID in their About.xml.

        Mods without an About.xml (non-AboutXmlMod) are considered to have
        a missing package ID. AboutXmlMod instances are checked against the
        default missing package ID constant.
        """
        result: list[str] = []
        for path, mod in self._metadata_controller.mods_metadata.items():
            if not isinstance(mod, AboutXmlMod):
                # Non-AboutXmlMod mods inherently lack a package ID
                result.append(path)
            elif str(mod.package_id) == app_constants.DEFAULT_MISSING_PACKAGEID:
                result.append(path)
        return result

    def get_missing_publishfieldid_paths(self) -> list[str]:
        """Identify mods lacking a Publish Field ID (Steam Workshop ID)."""
        ignored_mods = IgnoreManager.load_ignored_mods()
        result: list[str] = []
        for path, mod in self._metadata_controller.mods_metadata.items():
            if mod.published_file_id is not None:
                continue
            if isinstance(mod, AboutXmlMod):
                pid = str(mod.package_id)
                if pid in app_constants.RIMWORLD_PACKAGE_IDS:
                    continue
                if pid in ignored_mods:
                    continue
            result.append(path)
        return result

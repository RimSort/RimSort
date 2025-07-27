from typing import Any, Optional

from loguru import logger
from PySide6.QtGui import QColor

from app.controllers.metadata_db_controller import AuxMetadataController
from app.utils.metadata import MetadataManager


class CustomListWidgetItemMetadata:
    """
    A class to store metadata for CustomListWidgetItem.

    """

    def __init__(
        self,
        uuid: str,
        errors_warnings: str = "",
        errors: str = "",
        warnings: str = "",
        warning_toggled: bool = False,
        filtered: bool = False,
        hidden_by_filter: bool = False,
        invalid: bool | None = None,
        mismatch: bool | None = None,
        mod_color: QColor | None = None,
        alternative: Optional[str] = None,

    ) -> None:
        """
        Must provide a uuid, the rest is optional.

        Unless explicitly provided, invalid and mismatch are automatically set based on the uuid using metadata manager.

        :param uuid: str, the uuid of the mod which corresponds to a mod's metadata
        :param errors_warnings: a string of errors and warnings
        :param errors: a string of errors for the notification tooltip
        :param warnings: a string of warnings for the notification tooltip
        :param warning_toggled: a bool representing if the warning/error icons are toggled off
        :param filtered: a bool representing whether the widget's item is filtered
        :param hidden_by_filter: a bool representing whether the widget's item is hidden because of a filter (Search, or Mod Type (C#, Xml, Local Mod, Steam Mod etc.)
        :param invalid: a bool representing whether the widget's item is an invalid mod
        :param mismatch: a bool representing whether the widget's item has a version mismatch
        :param mod_color: QColor, the color of the mod's text/background in the modlist
        :param alternative: a bool representing whether the widget's item has an alternative mod in the "Use This Instead" database
        """
        # Do not cache the metadata manager, it will cause freezes/crashes when dragging mods.
        # self.metatadata_manager = MetadataManager.instance()
        self.aux_metadata_controller = AuxMetadataController()
        self.aux_metadata_session = self.aux_metadata_controller.Session()

        # Metadata attributes
        self.uuid = uuid
        self.errors_warnings = errors_warnings
        self.errors = errors
        self.warnings = warnings
        self.filtered = filtered
        self.hidden_by_filter = hidden_by_filter
        self.warning_toggled = warning_toggled
        self.invalid = (
            invalid if invalid is not None else self.get_invalid_by_uuid(uuid)
        )
        self.mismatch = (
            mismatch if mismatch is not None else self.get_mismatch_by_uuid(uuid)
        )
        if mod_color is None:
            self.mod_color = self.get_mod_color(uuid)
        else:
            self.mod_color = mod_color
        self.alternative = (
            alternative
            if alternative is not None
            else self.get_alternative_by_uuid(uuid)
        )

        logger.debug(
            f"Finished initializing CustomListWidgetItemMetadata for uuid: {uuid}"
        )

    def get_mod_color(self, uuid: str) -> QColor | None:
        """
        Get the mod color from DB.

        :param uuid: str, the uuid of the mod
        :return: QColor | None, Color of hte mod, or None if no color
        """
        metadata_manager = MetadataManager.instance()
        entry = self.aux_metadata_controller.get(
            self.aux_metadata_session,
            metadata_manager.internal_local_metadata[uuid]["path"],
        )

        mod_color = None
        if entry:
            color_text = entry.color_hex
            if color_text is not None:
                mod_color = QColor(color_text)

        return mod_color

    def get_invalid_by_uuid(self, uuid: str) -> bool:
        """
        Get the invalid status of the mod by its uuid.

        :param uuid: str, the uuid of the mod
        :return: bool, the invalid status of the mod
        """
        metadata_manager = MetadataManager.instance()
        try:
            return metadata_manager.internal_local_metadata[uuid].get("invalid", False)
        except KeyError:
            logger.error(f"UUID {uuid} not found in metadata")
            return False

    def get_mismatch_by_uuid(self, uuid: str) -> bool:
        """
        Get the version mismatch status of the mod by its uuid.

        :param uuid: str, the uuid of the mod
        :return: bool, the version mismatch status of the mod
        """
        metadata_manager = MetadataManager.instance()
        try:
            return metadata_manager.is_version_mismatch(uuid)
        except KeyError:
            logger.error(f"UUID {uuid} not found in metadata")
            return False

    def get_alternative_by_uuid(self, uuid: str) -> str | None:
        """
        Get the "has alternative" status of the mod by its uuid.

        :param uuid: str, the uuid of the mod
        :return: None if there is no mismatch, otherwise the replacement string.
        """
        metadata_manager = MetadataManager.instance()
        try:
            mr = metadata_manager.has_alternative_mod(uuid)
            if mr is None:
                return None
            return f"{mr.name} ({mr.pfid}) by {mr.author}"

        except KeyError:
            logger.info(f"UUID {uuid} not found in metadata - probably non-steam mod")
            return None

    def __getitem__(self, key: str) -> Any:
        """
        Get the value of the attribute by key.

        :param key: str, the attribute name
        :return: Any, the value of the attribute
        """
        return getattr(self, key)

    def __setitem__(self, key: str, value: Any) -> None:
        """
        Set the value of the attribute by key.

        :param key: str, the attribute name
        :param value: Any, the value to set
        """
        setattr(self, key, value)

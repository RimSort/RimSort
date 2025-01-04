from typing import Any, Optional

from loguru import logger

from app.utils.metadata import MetadataManager


class CustomListWidgetItemMetadata:
    """
    A class to store metadata for CustomListWidgetItem.

    Attributes:
        uuid: str, the uuid of the mod which corresponds to a mod's metadata
        errors_warnings: str, a string of errors and warnings
        errors: str, a string of errors for the notification tooltip
        warnings: str, a string of warnings for the notification tooltip
        warning_toggled: bool, representing if the warning/error icons are toggled off
        filtered: bool, representing whether the widget's item is filtered
        invalid: bool, representing whether the widget's item is an invalid mod
        mismatch: bool, representing whether the widget's item has a version mismatch
    """

    def __init__(
        self,
        uuid: str,
        errors_warnings: str = "",
        errors: str = "",
        warnings: str = "",
        warning_toggled: bool = False,
        filtered: bool = False,
        invalid: Optional[bool] = None,
        mismatch: Optional[bool] = None,
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
        :param invalid: a bool representing whether the widget's item is an invalid mod
        """
        # Do not cache the metadata manager, it will cause freezes/crashes when dragging mods.
        # self.metatadata_manager = MetadataManager.instance()

        # Metadata attributes
        self.uuid = uuid
        self.errors_warnings = errors_warnings
        self.errors = errors
        self.warnings = warnings
        self.filtered = filtered
        self.warning_toggled = warning_toggled
        self.invalid = (
            invalid if invalid is not None else self.get_invalid_by_uuid(uuid)
        )
        self.mismatch = (
            mismatch if mismatch is not None else self.get_mismatch_by_uuid(uuid)
        )
        logger.debug(
            f"Finished initializing CustomListWidgetItemMetadata for uuid: {uuid}"
        )

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

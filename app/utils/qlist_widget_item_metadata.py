from loguru import logger

from app.utils.metadata import MetadataManager


class QListWidgetItemMetadata():
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
        invalid: bool = None,
        mismatch: bool = None,
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
        
        self.uuid = uuid
        self.errors_warnings = errors_warnings
        self.errors = errors
        self.warnings = warnings
        self.filtered = filtered
        self.warning_toggled = warning_toggled
        self.invalid = invalid if invalid is not None else self.get_invalid_by_uuid(uuid)
        self.mismatch = mismatch if mismatch is not None else self.get_mismatch_by_uuid(uuid)
        
        logger.debug(f"Finished initializing QListWidgetItemMetadata for {uuid}")

    def get_invalid_by_uuid(self, uuid: str) -> bool:
        metadata_manager = MetadataManager.instance()
        return metadata_manager.internal_local_metadata[uuid].get("invalid")

    def get_mismatch_by_uuid(self, uuid: str) -> bool:
        metadata_manager = MetadataManager.instance()
        return metadata_manager.is_version_mismatch(uuid)

    def toggle_warning(self) -> None:
        if self.warning_toggled:
            self.warning_toggled = False
        else:
            self.warning_toggled = True

    def __getitem__(self, key: str) -> any:
        return getattr(self, key)

    def __setitem__(self, key: str, value: any) -> None:
        setattr(self, key, value)
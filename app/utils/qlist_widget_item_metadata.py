from app.utils.metadata import MetadataManager

class QListWidgetItemMetadata():
    """
    
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

    def __getitem__(self, key) -> any:
        return getattr(self, key)

    def __setitem__(self, key, value) -> None:
        setattr(self, key, value)
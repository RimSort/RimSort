from PySide6.QtCore import Signal

class QListWidgetItemMetadata():
    """
    
    """
    
    def __init__(
        self,
        errors_warnings: str,
        errors: str,
        warnings: str,
        filtered: bool,
        invalid: bool,
        mismatch: bool,
        uuid: str,
    ) -> None:
        
        self.errors_warnings = errors_warnings
        self.errors = errors
        self.warnings = warnings
        self.filtered = filtered
        self.invalid = invalid
        self.mismatch = mismatch
        self.uuid = uuid
        
        self.warning_toggled = False
        self.test_var = None
        
    def toggle_warning(self) -> None:
        if self.warning_toggled:
            self.warning_toggled = False
        else:
            self.warning_toggled = True
        
    def __getitem__(self, key) -> any:
        return getattr(self, key)

    def __setitem__(self, key, value) -> None:
        setattr(self, key, value)
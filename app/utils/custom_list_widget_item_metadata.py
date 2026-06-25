from typing import Any

from loguru import logger
from PySide6.QtGui import QColor
from sqlalchemy.orm.session import Session

from app.controllers.metadata_controller import MetadataController
from app.controllers.metadata_db_controller import AuxMetadataController
from app.models.metadata.metadata_structure import AboutXmlMod
from app.models.settings import Settings
from app.utils.aux_db_utils import (
    auxdb_get_mod_color,
    auxdb_get_mod_tags,
    auxdb_get_mod_user_notes,
    auxdb_get_mod_warning_toggled,
)


class CustomListWidgetItemMetadata:
    """
    A class to store metadata for CustomListWidgetItem.
    """

    def __init__(
        self,
        path: str,
        settings: Settings,
        errors_warnings: str = "",
        errors: str = "",
        warnings: str = "",
        warning_toggled: bool = False,
        filtered: bool = False,
        hidden_by_filter: bool = False,
        user_notes: str = "",
        invalid: bool | None = None,
        mismatch: bool | None = None,
        mod_color: QColor | None = None,
        mod_tags: list[str] | None = None,
        alternative: str | None = None,
        list_type: str | None = None,
        aux_metadata_controller: AuxMetadataController | None = None,
        aux_metadata_session: Session | None = None,
    ) -> None:
        """
        Must provide a path, the rest is optional.

        Unless explicitly provided, invalid and mismatch are automatically set based on the path using metadata controller.

        :param path: str, the path of the mod which corresponds to a mod's metadata key
        :param settings: Settings, settings model instance
        :param errors_warnings: a string of errors and warnings
        :param errors: a string of errors for the notification tooltip
        :param warnings: a string of warnings for the notification tooltip
        :param warning_toggled: a bool representing if the warning/error icons are toggled off
        :param filtered: a bool representing whether the widget's item is filtered
        :param hidden_by_filter: a bool representing whether the widget's item is hidden because of a filter
        :param invalid: a bool representing whether the widget's item is an invalid mod
        :param user_notes: str, representing the users own notes for this mod
        :param mismatch: a bool representing whether the widget's item has a version mismatch
        :param mod_color: QColor, the color of the mod's text/background in the modlist
        :param alternative: a string representing whether the widget's item has an alternative mod
        :param aux_metadata_controller: AuxMetadataController, an instance of the controller used for fetching mod color
        :param aux_metadata_session: Session, an instance of the session used for fetching mod color
        """
        # Do not cache the metadata controller, aux metadata controller or settings controller
        # They will cause freezes/crashes when dragging mods from inactive->active or vice versa

        # Metadata attributes
        self.path = path
        self.errors_warnings = errors_warnings
        self.errors = errors
        self.warnings = warnings
        self.filtered = filtered
        self.hidden_by_filter = hidden_by_filter
        if not warning_toggled:
            self.warning_toggled = auxdb_get_mod_warning_toggled(
                settings, path, aux_metadata_controller, aux_metadata_session
            )
        else:
            self.warning_toggled = warning_toggled
        self.invalid = (
            invalid if invalid is not None else self.get_invalid_by_path(path)
        )
        self.mismatch = (
            mismatch if mismatch is not None else self.get_mismatch_by_path(path)
        )
        if mod_color is None:
            self.mod_color = auxdb_get_mod_color(
                settings, path, aux_metadata_controller, aux_metadata_session
            )
        else:
            self.mod_color = mod_color
        self.alternative = (
            alternative
            if alternative is not None
            else self.get_alternative_by_path(path)
        )
        self.mod_tags = (
            auxdb_get_mod_tags(
                settings, path, aux_metadata_controller, aux_metadata_session
            )
            if mod_tags is None
            else mod_tags
        )
        # Persist list type for UI logic that depends on which list the item is in (Active/Inactive)
        self.list_type = list_type

        logger.debug(
            f"Finished initializing CustomListWidgetItemMetadata for path: {path}"
        )
        if user_notes == "":
            self.user_notes = auxdb_get_mod_user_notes(
                settings, path, aux_metadata_controller, aux_metadata_session
            )
        else:
            self.user_notes = user_notes

    def get_invalid_by_path(self, path: str) -> bool:
        """
        Get the invalid status of the mod by its path.

        :param path: str, the path of the mod
        :return: bool, the invalid status of the mod
        """
        metadata_controller = MetadataController.instance()
        try:
            mod = metadata_controller.get_mod(path)
            if mod is None:
                return False
            return not isinstance(mod, AboutXmlMod)
        except KeyError:
            logger.error(f"Path {path} not found in metadata")
            return False

    def get_mismatch_by_path(self, path: str) -> bool:
        """
        Get the version mismatch status of the mod by its path.

        :param path: str, the path of the mod
        :return: bool, the version mismatch status of the mod
        """
        metadata_controller = MetadataController.instance()
        try:
            return metadata_controller.is_version_mismatch(path)
        except KeyError:
            logger.error(f"Path {path} not found in metadata")
            return False

    def get_alternative_by_path(self, path: str) -> str | None:
        """
        Get the "has alternative" status of the mod by its path.

        :param path: str, the path of the mod
        :return: None if there is no alternative, otherwise the replacement string.
        """
        metadata_controller = MetadataController.instance()
        try:
            mr = metadata_controller.has_alternative_mod(path)
            if mr is None:
                return None
            return f"{mr.name} ({mr.pfid}) by {mr.author}"

        except KeyError:
            logger.info(f"Path {path} not found in metadata - probably non-steam mod")
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

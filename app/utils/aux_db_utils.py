from pathlib import Path

from PySide6.QtGui import QColor
from sqlalchemy.orm.session import Session

from app.controllers.metadata_db_controller import AuxMetadataController
from app.controllers.settings_controller import SettingsController
from app.models.metadata.metadata_db import AuxMetadataEntry
from app.utils.metadata import MetadataManager


def get_aux_db_entry(
    settings_controller: SettingsController,
    uuid: str,
    aux_db_controller: AuxMetadataController | None,
    session: Session | None,
) -> AuxMetadataEntry | None:
    """
    Get the AuxMetadataEntry for a given UUID from the Aux Metadata DB.
    """
    metadata_manager = MetadataManager.instance()
    instance_path = Path(settings_controller.settings.current_instance_path)
    local_controller = (
        aux_db_controller
        or AuxMetadataController.get_or_create_cached_instance(
            instance_path / "aux_metadata.db"
        )
    )
    with session or local_controller.Session() as local_session:
        entry = local_controller.get(
            local_session,
            metadata_manager.internal_local_metadata[uuid]["path"],
        )

    return entry
def get_mod_color(
    settings_controller: SettingsController,
    uuid: str,
    aux_db_controller: AuxMetadataController | None,
    session: Session | None,
) -> QColor | None:
    """
    Get the mod color from Aux Metadata DB.

    :param settings_controller: SettingsController, settings controller instance
    :param uuid: str, the uuid of the mod
    :param aux_db_controller: AuxMetadataController | None, optional aux metadata controller instance
    :return: QColor | None, Color of the mod, or None if no color
    """
    entry = get_aux_db_entry(
        settings_controller, uuid, aux_db_controller, session
    )
    mod_color = None
    if entry:
        color_text = entry.color_hex
        if color_text is not None:
            mod_color = QColor(color_text)

    return mod_color


def get_mod_user_notes(
    settings_controller: SettingsController,
    uuid: str,
    aux_db_controller: AuxMetadataController | None,
    session: Session | None,
) -> str:
    """
    Get the user notes for a mod from Aux Metadata DB.

    :param settings_controller: SettingsController, settings controller instance
    :param uuid: str, the uuid of the mod
    :param aux_db_controller: AuxMetadataController | None, optional aux metadata controller instance
    :return: str, User notes for the mod, or empty string if no notes
    """
    entry = get_aux_db_entry(
        settings_controller, uuid, aux_db_controller, session
    )
    user_notes = ""
    if entry:
        user_notes = entry.user_notes

    return user_notes


def get_mod_warning_toggled(
    settings_controller: SettingsController,
    uuid: str,
    aux_db_controller: AuxMetadataController | None,
    session: Session | None,
) -> bool:
    """
    Get the warning_toggled status for a mod from Aux Metadata DB.

    :param settings_controller: SettingsController, settings controller instance
    :param uuid: str, the uuid of the mod
    :param aux_db_controller: AuxMetadataController | None, optional aux metadata controller instance
    :return: bool, Warning toggled status for the mod
    """
    entry = get_aux_db_entry(
        settings_controller, uuid, aux_db_controller, session
    )
    warning_toggled = False
    if entry:
        warning_toggled = entry.ignore_warnings

    return warning_toggled
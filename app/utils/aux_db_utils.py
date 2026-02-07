from PySide6.QtGui import QColor
from sqlalchemy.orm.session import Session

from app.controllers.metadata_db_controller import AuxMetadataController
from app.controllers.settings_controller import SettingsController
from app.models.metadata.metadata_db import AuxMetadataEntry
from app.utils.metadata import MetadataManager


def auxdb_get_aux_db_entry(
    settings_controller: SettingsController,
    uuid: str,
    aux_db_controller: AuxMetadataController | None = None,
    session: Session | None = None,
) -> AuxMetadataEntry | None:
    """
    Get the AuxMetadataEntry for a given UUID from the Aux Metadata DB.

    :param settings_controller: SettingsController, settings controller instance
    :param uuid: str, the uuid of the mod
    :param aux_db_controller: AuxMetadataController | None, optional aux metadata controller instance
    :param session: Session | None, optional SQLAlchemy session to use for the query; if None, a new session will be created and closed within this function
    :return: AuxMetadataEntry | None, the AuxMetadataEntry for the given UUID, or None if no entry exists
    """
    metadata_manager = MetadataManager.instance()
    local_controller = (
        aux_db_controller
        or AuxMetadataController.get_or_create_cached_instance(
            settings_controller.settings.aux_db_path
        )
    )
    local_session = session or local_controller.Session()
    try:
        entry = local_controller.get(
            local_session,
            metadata_manager.internal_local_metadata[uuid]["path"],
        )
        return entry
    finally:
        if not session:
            local_session.close()


def auxdb_get_mod_color(
    settings_controller: SettingsController,
    uuid: str,
    aux_db_controller: AuxMetadataController | None = None,
    session: Session | None = None,
) -> QColor | None:
    """
    Get the mod color from Aux Metadata DB.

    :param settings_controller: SettingsController, settings controller instance
    :param uuid: str, the uuid of the mod
    :param aux_db_controller: AuxMetadataController | None, optional aux metadata controller instance
    :param session: Session | None, optional SQLAlchemy session to use for the query; if None, a new session will be created and closed within this function
    :return: QColor | None, Color of the mod, or None if no color
    """
    entry = auxdb_get_aux_db_entry(settings_controller, uuid, aux_db_controller, session)
    mod_color = None
    if entry:
        color_text = entry.color_hex
        if color_text is not None:
            mod_color = QColor(color_text)

    return mod_color


def auxdb_get_mod_user_notes(
    settings_controller: SettingsController,
    uuid: str,
    aux_db_controller: AuxMetadataController | None = None,
    session: Session | None = None,
) -> str:
    """
    Get the user notes for a mod from Aux Metadata DB.

    :param settings_controller: SettingsController, settings controller instance
    :param uuid: str, the uuid of the mod
    :param aux_db_controller: AuxMetadataController | None, optional aux metadata controller instance
    :param session: Session | None, optional SQLAlchemy session to use for the query; if None, a new session will be created and closed within this function
    :return: str, User notes for the mod, or empty string if no notes
    """
    entry = auxdb_get_aux_db_entry(settings_controller, uuid, aux_db_controller, session)
    user_notes = ""
    if entry:
        user_notes = entry.user_notes

    return user_notes


def auxdb_get_mod_warning_toggled(
    settings_controller: SettingsController,
    uuid: str,
    aux_db_controller: AuxMetadataController | None = None,
    session: Session | None = None,
) -> bool:
    """
    Get the warning_toggled status for a mod from Aux Metadata DB.

    :param settings_controller: SettingsController, settings controller instance
    :param uuid: str, the uuid of the mod
    :param aux_db_controller: AuxMetadataController | None, optional aux metadata controller instance
    :param session: Session | None, optional SQLAlchemy session to use for the query; if None, a new session will be created and closed within this function
    :return: bool, Warning toggled status for the mod
    """
    entry = auxdb_get_aux_db_entry(settings_controller, uuid, aux_db_controller, session)
    warning_toggled = False
    if entry:
        warning_toggled = entry.ignore_warnings

    return warning_toggled


def auxdb_update_mod_color(
    settings_controller: SettingsController,
    uuid: str,
    color: QColor | None,
    aux_db_controller: AuxMetadataController | None = None,
    session: Session | None = None,
) -> None:
    """
    Update the mod color in the Aux Metadata DB.

    :param settings_controller: SettingsController, settings controller instance
    :param uuid: str, the uuid of the mod
    :param color: QColor | None, the new color to set for the mod, or None to clear the color
    :param aux_db_controller: AuxMetadataController, the aux metadata controller instance to use for the update
    :param session: Session | None, optional SQLAlchemy session to use for the update; if None, a new session will be created and closed within this function
    """
    metadata_manager = MetadataManager.instance()
    local_controller = (
        aux_db_controller
        or AuxMetadataController.get_or_create_cached_instance(
            settings_controller.settings.aux_db_path
        )
    )

    local_session = session or local_controller.Session()
    try:
        mod_path = metadata_manager.internal_local_metadata[uuid]["path"]
        local_controller.update(
            local_session,
            mod_path,
            color_hex=color.name() if color else None,
        )
    finally:
        if not session:
            local_session.close()


def auxdb_update_all_mod_colors(
    settings_controller: SettingsController,
    uuid_color_mapping: dict[str, QColor | None],
    aux_db_controller: AuxMetadataController | None = None,
    session: Session | None = None,
) -> None:
    """
    Update the mod colors in the Aux Metadata DB for multiple mods.

    :param settings_controller: SettingsController, settings controller instance
    :param uuid_color_mapping: dict[str, QColor | None], a mapping of mod UUIDs to their new colors (or None to clear the color)
    :param aux_db_controller: AuxMetadataController, the aux metadata controller instance to use for the update
    :param session: Session | None, optional SQLAlchemy session to use for the update; if None, a new session will be created and closed within this function
    """
    metadata_manager = MetadataManager.instance()
    local_controller = (
        aux_db_controller
        or AuxMetadataController.get_or_create_cached_instance(
            settings_controller.settings.aux_db_path
        )
    )

    local_session = session or local_controller.Session()
    try:
        updates = [
            {
                "path": metadata_manager.internal_local_metadata[uuid]["path"],
                "color_hex": color.name() if color else None,
            }
            for uuid, color in uuid_color_mapping.items()
        ]
        local_session.bulk_update_mappings(AuxMetadataEntry.__mapper__, updates)
        local_session.commit()
    finally:
        if not session:
            local_session.close()
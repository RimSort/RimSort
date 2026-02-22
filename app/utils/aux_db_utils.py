from typing import Any

from PySide6.QtGui import QColor
from sqlalchemy.orm.session import Session

from app.controllers.metadata_db_controller import AuxMetadataController
from app.controllers.settings_controller import SettingsController
from app.models.metadata.metadata_db import AuxMetadataEntry
from app.utils.metadata import MetadataManager


def _get_controller_and_session(
    settings_controller: SettingsController,
    aux_db_controller: AuxMetadataController | None,
    session: Session | None,
) -> tuple[AuxMetadataController, Session, bool]:
    """Resolve controller and session, returning (controller, session, should_close)."""
    controller = (
        aux_db_controller
        or AuxMetadataController.get_or_create_cached_instance(
            settings_controller.settings.aux_db_path
        )
    )
    local_session = session or controller.Session()
    return controller, local_session, session is None


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
    controller, local_session, should_close = _get_controller_and_session(
        settings_controller, aux_db_controller, session
    )
    try:
        return controller.get(
            local_session,
            metadata_manager.internal_local_metadata[uuid]["path"],
        )
    finally:
        if should_close:
            local_session.close()


def _get_entry_color_field(
    settings_controller: SettingsController,
    uuid: str,
    field: str,
    aux_db_controller: AuxMetadataController | None = None,
    session: Session | None = None,
) -> QColor | None:
    """Get a color field from Aux Metadata DB entry."""
    entry = auxdb_get_aux_db_entry(settings_controller, uuid, aux_db_controller, session)
    if entry:
        color_text = getattr(entry, field, None)
        if color_text is not None:
            return QColor(color_text)
    return None


def auxdb_get_mod_color(
    settings_controller: SettingsController,
    uuid: str,
    aux_db_controller: AuxMetadataController | None = None,
    session: Session | None = None,
) -> QColor | None:
    """Get the mod background color from Aux Metadata DB."""
    return _get_entry_color_field(
        settings_controller, uuid, "color_hex", aux_db_controller, session
    )


def auxdb_get_mod_font_color(
    settings_controller: SettingsController,
    uuid: str,
    aux_db_controller: AuxMetadataController | None = None,
    session: Session | None = None,
) -> QColor | None:
    """Get the mod font color from Aux Metadata DB."""
    return _get_entry_color_field(
        settings_controller, uuid, "font_color_hex", aux_db_controller, session
    )


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


def _update_single_mod_field(
    settings_controller: SettingsController,
    uuid: str,
    aux_db_controller: AuxMetadataController | None,
    session: Session | None,
    **kwargs: Any,
) -> None:
    """Update a single field on a mod's aux metadata entry."""
    metadata_manager = MetadataManager.instance()
    controller, local_session, should_close = _get_controller_and_session(
        settings_controller, aux_db_controller, session
    )
    try:
        mod_path = metadata_manager.internal_local_metadata[uuid]["path"]
        controller.update(local_session, mod_path, **kwargs)
    finally:
        if should_close:
            local_session.close()


def _update_bulk_mod_field(
    settings_controller: SettingsController,
    uuid_color_mapping: dict[str, QColor | None],
    field: str,
    aux_db_controller: AuxMetadataController | None,
    session: Session | None,
) -> None:
    """Update a color field for multiple mods in the Aux Metadata DB."""
    metadata_manager = MetadataManager.instance()
    controller, local_session, should_close = _get_controller_and_session(
        settings_controller, aux_db_controller, session
    )
    try:
        updates = [
            {
                "path": metadata_manager.internal_local_metadata[uuid]["path"],
                field: color.name() if color else None,
            }
            for uuid, color in uuid_color_mapping.items()
        ]
        local_session.bulk_update_mappings(AuxMetadataEntry.__mapper__, updates)
        local_session.commit()
    finally:
        if should_close:
            local_session.close()


def auxdb_update_mod_color(
    settings_controller: SettingsController,
    uuid: str,
    color: QColor | None,
    aux_db_controller: AuxMetadataController | None = None,
    session: Session | None = None,
) -> None:
    """Update the mod background color in the Aux Metadata DB."""
    _update_single_mod_field(
        settings_controller, uuid, aux_db_controller, session,
        color_hex=color.name() if color else None,
    )


def auxdb_update_mod_font_color(
    settings_controller: SettingsController,
    uuid: str,
    color: QColor | None,
    aux_db_controller: AuxMetadataController | None = None,
    session: Session | None = None,
) -> None:
    """Update the mod font color in the Aux Metadata DB."""
    _update_single_mod_field(
        settings_controller, uuid, aux_db_controller, session,
        font_color_hex=color.name() if color else None,
    )


def auxdb_update_all_mod_colors(
    settings_controller: SettingsController,
    uuid_color_mapping: dict[str, QColor | None],
    aux_db_controller: AuxMetadataController | None = None,
    session: Session | None = None,
) -> None:
    """Update the mod background colors in the Aux Metadata DB for multiple mods."""
    _update_bulk_mod_field(
        settings_controller, uuid_color_mapping, "color_hex",
        aux_db_controller, session,
    )


def auxdb_update_all_mod_font_colors(
    settings_controller: SettingsController,
    uuid_color_mapping: dict[str, QColor | None],
    aux_db_controller: AuxMetadataController | None = None,
    session: Session | None = None,
) -> None:
    """Update the mod font colors in the Aux Metadata DB for multiple mods."""
    _update_bulk_mod_field(
        settings_controller, uuid_color_mapping, "font_color_hex",
        aux_db_controller, session,
    )

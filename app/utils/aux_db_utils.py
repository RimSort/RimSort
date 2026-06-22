from typing import Literal

from PySide6.QtGui import QColor
from sqlalchemy.orm.session import Session

from app.controllers.metadata_db_controller import AuxMetadataController
from app.models.metadata.metadata_db import AuxMetadataEntry, TagsEntry
from app.models.settings import Settings


def auxdb_get_aux_db_entry(
    settings: Settings,
    path: str,
    aux_db_controller: AuxMetadataController | None = None,
    session: Session | None = None,
) -> AuxMetadataEntry | None:
    """
    Get the AuxMetadataEntry for a given mod path from the Aux Metadata DB.

    :param settings: Settings, settings controller instance
    :param path: str, the filesystem path of the mod
    :param aux_db_controller: AuxMetadataController | None, optional aux metadata controller instance
    :param session: Session | None, optional SQLAlchemy session to use for the query; if None, a new session will be created and closed within this function
    :return: AuxMetadataEntry | None, the AuxMetadataEntry for the given path, or None if no entry exists
    """
    local_controller = (
        aux_db_controller
        or AuxMetadataController.get_or_create_cached_instance(settings.aux_db_path)
    )
    local_session = session or local_controller.Session()
    try:
        entry = local_controller.get(
            local_session,
            path,
        )
        return entry
    finally:
        if not session:
            local_session.close()


def auxdb_get_mod_color(
    settings: Settings,
    path: str,
    aux_db_controller: AuxMetadataController | None = None,
    session: Session | None = None,
) -> QColor | None:
    """
    Get the mod color from Aux Metadata DB.

    :param settings: Settings, settings controller instance
    :param path: str, the filesystem path of the mod
    :param aux_db_controller: AuxMetadataController | None, optional aux metadata controller instance
    :param session: Session | None, optional SQLAlchemy session to use for the query; if None, a new session will be created and closed within this function
    :return: QColor | None, Color of the mod, or None if no color
    """
    entry = auxdb_get_aux_db_entry(settings, path, aux_db_controller, session)
    mod_color = None
    if entry:
        color_text = entry.color_hex
        if color_text is not None:
            mod_color = QColor(color_text)

    return mod_color


def auxdb_get_mod_user_notes(
    settings: Settings,
    path: str,
    aux_db_controller: AuxMetadataController | None = None,
    session: Session | None = None,
) -> str:
    """
    Get the user notes for a mod from Aux Metadata DB.

    :param settings: Settings, settings controller instance
    :param path: str, the filesystem path of the mod
    :param aux_db_controller: AuxMetadataController | None, optional aux metadata controller instance
    :param session: Session | None, optional SQLAlchemy session to use for the query; if None, a new session will be created and closed within this function
    :return: str, User notes for the mod, or empty string if no notes
    """
    entry = auxdb_get_aux_db_entry(settings, path, aux_db_controller, session)
    user_notes = ""
    if entry:
        user_notes = entry.user_notes

    return user_notes


def auxdb_get_mod_warning_toggled(
    settings: Settings,
    path: str,
    aux_db_controller: AuxMetadataController | None = None,
    session: Session | None = None,
) -> bool:
    """
    Get the warning_toggled status for a mod from Aux Metadata DB.

    :param settings: Settings, settings controller instance
    :param path: str, the filesystem path of the mod
    :param aux_db_controller: AuxMetadataController | None, optional aux metadata controller instance
    :param session: Session | None, optional SQLAlchemy session to use for the query; if None, a new session will be created and closed within this function
    :return: bool, Warning toggled status for the mod
    """
    entry = auxdb_get_aux_db_entry(settings, path, aux_db_controller, session)
    warning_toggled = False
    if entry:
        warning_toggled = entry.ignore_warnings

    return warning_toggled


def auxdb_update_mod_color(
    settings: Settings,
    path: str,
    color: QColor | None,
    aux_db_controller: AuxMetadataController | None = None,
    session: Session | None = None,
) -> None:
    """
    Update the mod color in the Aux Metadata DB.

    :param settings: Settings, settings controller instance
    :param path: str, the filesystem path of the mod
    :param color: QColor | None, the new color to set for the mod, or None to clear the color
    :param aux_db_controller: AuxMetadataController, the aux metadata controller instance to use for the update
    :param session: Session | None, optional SQLAlchemy session to use for the update; if None, a new session will be created and closed within this function
    """
    local_controller = (
        aux_db_controller
        or AuxMetadataController.get_or_create_cached_instance(settings.aux_db_path)
    )

    local_session = session or local_controller.Session()
    try:
        local_controller.update(
            local_session,
            path,
            color_hex=color.name() if color else None,
        )
    finally:
        if not session:
            local_session.close()


def auxdb_update_all_mod_colors(
    settings: Settings,
    path_color_mapping: dict[str, QColor | None],
    aux_db_controller: AuxMetadataController | None = None,
    session: Session | None = None,
) -> None:
    """
    Update the mod colors in the Aux Metadata DB for multiple mods.

    :param settings: Settings, settings controller instance
    :param path_color_mapping: dict[str, QColor | None], a mapping of mod paths to their new colors (or None to clear the color)
    :param aux_db_controller: AuxMetadataController, the aux metadata controller instance to use for the update
    :param session: Session | None, optional SQLAlchemy session to use for the update; if None, a new session will be created and closed within this function
    """
    local_controller = (
        aux_db_controller
        or AuxMetadataController.get_or_create_cached_instance(settings.aux_db_path)
    )

    local_session = session or local_controller.Session()
    try:
        updates = [
            {
                "path": path,
                "color_hex": color.name() if color else None,
            }
            for path, color in path_color_mapping.items()
        ]
        local_session.bulk_update_mappings(AuxMetadataEntry.__mapper__, updates)
        local_session.commit()
    finally:
        if not session:
            local_session.close()


def auxdb_get_mod_tags(
    settings: Settings,
    path: str,
    aux_db_controller: AuxMetadataController | None = None,
    session: Session | None = None,
) -> list[str]:
    """
    Get user-defined tags for a mod from Aux Metadata DB.
    """
    local_controller = (
        aux_db_controller
        or AuxMetadataController.get_or_create_cached_instance(settings.aux_db_path)
    )
    local_session = session or local_controller.Session()
    try:
        entry = local_controller.get(local_session, path)
        if not entry:
            return []

        return sorted(tag.tag for tag in entry.tags)
    finally:
        if not session:
            local_session.close()


def auxdb_get_all_tags(
    settings: Settings,
    aux_db_controller: AuxMetadataController | None = None,
    session: Session | None = None,
) -> list[str]:
    """
    Get all user-defined mod tags from Aux Metadata DB.
    """
    if aux_db_controller is None and not hasattr(settings, "aux_db_path"):
        return []

    local_controller = (
        aux_db_controller
        or AuxMetadataController.get_or_create_cached_instance(settings.aux_db_path)
    )
    local_session = session or local_controller.Session()
    try:
        tags = local_session.query(TagsEntry).order_by(TagsEntry.tag.asc()).all()
        return [tag.tag for tag in tags]
    finally:
        if not session:
            local_session.close()


def _normalize_tags(tags: list[str]) -> list[str]:
    return sorted({tag.strip().lower() for tag in tags if tag.strip()})


def _get_aux_controller(
    settings: Settings,
    aux_db_controller: AuxMetadataController | None = None,
) -> AuxMetadataController:
    return aux_db_controller or AuxMetadataController.get_or_create_cached_instance(
        settings.aux_db_path
    )


def _get_or_create_tag_entry(session: Session, tag_text: str) -> TagsEntry:
    tag_entry = session.query(TagsEntry).filter(TagsEntry.tag == tag_text).first()
    if tag_entry is None:
        tag_entry = TagsEntry(tag=tag_text)
        session.add(tag_entry)
        session.flush()
    return tag_entry


def _update_mod_tags(
    settings: Settings,
    path: str,
    tags: list[str] | None,
    mode: Literal["add", "replace", "remove"],
    aux_db_controller: AuxMetadataController | None = None,
    session: Session | None = None,
) -> None:
    local_controller = _get_aux_controller(settings, aux_db_controller)
    local_session = session or local_controller.Session()

    try:
        entry = local_controller.get_or_create(local_session, path)

        if mode in {"replace", "remove"}:
            entry.tags.clear()
            local_session.flush()

        if mode != "remove" and tags is not None:
            existing_tags = {tag.tag for tag in entry.tags}

            for tag_text in _normalize_tags(tags):
                if tag_text in existing_tags:
                    continue

                entry.tags.append(_get_or_create_tag_entry(local_session, tag_text))

        local_session.commit()
    finally:
        if not session:
            local_session.close()


def auxdb_add_mod_tags(
    settings: Settings,
    path: str,
    tags: list[str],
    aux_db_controller: AuxMetadataController | None = None,
    session: Session | None = None,
) -> None:
    """
    Add tags to a mod without removing existing tags.
    """
    _update_mod_tags(
        settings=settings,
        path=path,
        tags=tags,
        mode="add",
        aux_db_controller=aux_db_controller,
        session=session,
    )


def auxdb_replace_mod_tags(
    settings: Settings,
    path: str,
    tags: list[str],
    aux_db_controller: AuxMetadataController | None = None,
    session: Session | None = None,
) -> None:
    """
    Replace all tags for a mod.
    """
    _update_mod_tags(
        settings=settings,
        path=path,
        tags=tags,
        mode="replace",
        aux_db_controller=aux_db_controller,
        session=session,
    )


def auxdb_remove_mod_tags(
    settings: Settings,
    path: str,
    aux_db_controller: AuxMetadataController | None = None,
    session: Session | None = None,
) -> None:
    """
    Remove all tags from a mod.
    """
    _update_mod_tags(
        settings=settings,
        path=path,
        tags=None,
        mode="remove",
        aux_db_controller=aux_db_controller,
        session=session,
    )


def auxdb_update_all_mod_tags(
    settings: Settings,
    paths: list[str],
    tags: list[str],
    replace: bool,
) -> None:
    """
    Update tags for multiple mods.
    """
    aux_db_controller = AuxMetadataController.get_or_create_cached_instance(
        settings.aux_db_path
    )
    with aux_db_controller.Session() as aux_metadata_session:
        for path in paths:
            if replace:
                auxdb_replace_mod_tags(
                    settings,
                    path,
                    tags,
                    aux_db_controller,
                    aux_metadata_session,
                )
            else:
                auxdb_add_mod_tags(
                    settings,
                    path,
                    tags,
                    aux_db_controller,
                    aux_metadata_session,
                )


def auxdb_cleanup_unused_tags(
    settings: Settings,
    aux_db_controller: AuxMetadataController | None = None,
    session: Session | None = None,
) -> None:
    """
    Delete tags that are no longer assigned to any mod.
    """
    local_controller = _get_aux_controller(settings, aux_db_controller)
    local_session = session or local_controller.Session()

    try:
        unused_tags = local_session.query(TagsEntry).filter(~TagsEntry.mods.any()).all()
        for tag in unused_tags:
            local_session.delete(tag)
        local_session.commit()
    finally:
        if not session:
            local_session.close()

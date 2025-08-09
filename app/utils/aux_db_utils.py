from pathlib import Path

from PySide6.QtGui import QColor
from sqlalchemy.orm.session import Session

from app.controllers.metadata_db_controller import AuxMetadataController
from app.controllers.settings_controller import SettingsController
from app.utils.app_info import AppInfo
from app.utils.metadata import MetadataManager


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
    :return: QColor | None, Color of hte mod, or None if no color
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

    mod_color = None
    if entry:
        color_text = entry.color_hex
        if color_text is not None:
            mod_color = QColor(color_text)

    return mod_color

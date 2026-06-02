import os
from pathlib import Path
from tempfile import gettempdir

from loguru import logger

from app.controllers.settings_controller import SettingsController
from app.models.divider import is_divider_uuid


class ToddsController:
    """Controller for todds texture optimization operations."""

    def __init__(
        self,
        settings_controller: SettingsController,
        metadata_manager: object,
    ) -> None:
        self.settings_controller = settings_controller
        self.metadata_manager = metadata_manager

    def generate_todds_txt(
        self,
        active_mod_uuids: list[str] | None = None,
    ) -> tuple[str, int]:
        """
        Generate the todds.txt path-list file that todds uses as input.

        When ``settings.todds_active_mods_target`` is False, writes the
        configured local and workshop mod folders.  When True, writes the
        path for each mod UUID in *active_mod_uuids*.

        :param active_mod_uuids: UUIDs of active mods (required when
            todds_active_mods_target is True).
        :return: (path_to_todds_txt, number_of_paths_written)
        """
        logger.info("Generating todds.txt...")
        todds_txt_path = str(Path(gettempdir()) / "todds.txt")
        if os.path.exists(todds_txt_path):
            os.remove(todds_txt_path)

        paths_written = 0
        settings = self.settings_controller.settings

        if not settings.todds_active_mods_target:
            instance = settings.instances[settings.current_instance]

            for folder in (instance.local_folder, instance.workshop_folder):
                if folder and folder != "":
                    abs_path = os.path.abspath(folder)
                    if os.path.isdir(abs_path):
                        with open(todds_txt_path, "a", encoding="utf-8") as f:
                            f.write(abs_path + "\n")
                        paths_written += 1
                    else:
                        logger.warning(
                            f"Folder does not exist, skipping for todds: {abs_path}"
                        )
        else:
            if active_mod_uuids is None:
                logger.error(
                    "active_mod_uuids required when todds_active_mods_target is True"
                )
                return todds_txt_path, 0

            with open(todds_txt_path, "a", encoding="utf-8") as f:
                for uuid in active_mod_uuids:
                    if is_divider_uuid(uuid):
                        continue
                    mod_path = os.path.abspath(
                        self.metadata_manager.internal_local_metadata[uuid]["path"]  # type: ignore[attr-defined]
                    )
                    if os.path.isdir(mod_path):
                        f.write(mod_path + "\n")
                        paths_written += 1
                    else:
                        logger.warning(
                            f"Mod path does not exist, skipping for todds: {mod_path}"
                        )

        logger.info(
            f"Generated todds.txt at: {todds_txt_path} ({paths_written} path(s) written)"
        )
        return todds_txt_path, paths_written

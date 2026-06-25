import os
from pathlib import Path
from tempfile import gettempdir

from loguru import logger

from app.controllers.metadata_controller import MetadataController
from app.models.divider import is_divider_uuid
from app.models.settings import Settings
from app.utils.todds.wrapper import ToddsInterface, ToddsRunner


class ToddsController:
    """Controller for todds texture optimization operations."""

    def __init__(
        self,
        settings: Settings,
        metadata_controller: MetadataController,
    ) -> None:
        self.settings = settings
        self.metadata_controller = metadata_controller

    def generate_todds_txt(
        self,
        active_mod_paths: list[str] | None = None,
    ) -> tuple[str, int]:
        """
        Generate the todds.txt path-list file that todds uses as input.

        When ``settings.todds_active_mods_target`` is False, writes the
        configured local and workshop mod folders.  When True, writes the
        path for each mod in *active_mod_paths*.

        :param active_mod_paths: Paths of active mods (required when
            todds_active_mods_target is True).
        :return: (path_to_todds_txt, number_of_paths_written)
        """
        logger.info("Generating todds.txt...")
        todds_txt_path = str(Path(gettempdir()) / "todds.txt")
        if os.path.exists(todds_txt_path):
            os.remove(todds_txt_path)

        paths_written = 0
        settings = self.settings

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
            if active_mod_paths is None:
                logger.error(
                    "active_mod_paths required when todds_active_mods_target is True"
                )
                return todds_txt_path, 0

            with open(todds_txt_path, "a", encoding="utf-8") as f:
                for path in active_mod_paths:
                    if is_divider_uuid(path):
                        continue
                    abs_mod_path = os.path.abspath(path)
                    if os.path.isdir(abs_mod_path):
                        f.write(abs_mod_path + "\n")
                        paths_written += 1
                    else:
                        logger.warning(
                            f"Mod path does not exist, skipping for todds: {abs_mod_path}"
                        )

        logger.info(
            f"Generated todds.txt at: {todds_txt_path} ({paths_written} path(s) written)"
        )
        return todds_txt_path, paths_written

    def optimize_textures(
        self,
        runner: ToddsRunner,
        active_mod_paths: list[str] | None = None,
    ) -> bool:
        """
        Run todds texture optimization.

        :param runner: Process runner that satisfies the ToddsRunner protocol.
        :param active_mod_paths: Paths of active mods (used when
            todds_active_mods_target is True).
        :return: True if todds was executed (paths found), False otherwise.
        """
        settings = self.settings

        todds_interface = ToddsInterface(
            preset=settings.todds_preset,
            dry_run=settings.todds_dry_run,
            overwrite=settings.todds_overwrite,
            custom_command=settings.todds_custom_command,
        )

        todds_txt_path, paths_written = self.generate_todds_txt(active_mod_paths)
        if paths_written == 0:
            return False

        todds_interface.execute_todds_cmd(todds_txt_path, runner)
        return True

    def delete_dds_textures(
        self,
        runner: ToddsRunner,
        active_mod_paths: list[str] | None = None,
    ) -> bool:
        """
        Delete .dds textures using todds clean preset.

        :param runner: Process runner that satisfies the ToddsRunner protocol.
        :param active_mod_paths: Paths of active mods (used when
            todds_active_mods_target is True).
        :return: True if todds was executed (paths found), False otherwise.
        """
        settings = self.settings

        todds_interface = ToddsInterface(
            preset="clean",
            dry_run=settings.todds_dry_run,
        )

        todds_txt_path, paths_written = self.generate_todds_txt(active_mod_paths)
        if paths_written == 0:
            return False

        todds_interface.execute_todds_cmd(todds_txt_path, runner)
        return True

import os
from glob import glob
from pathlib import Path

from loguru import logger

from app.controllers.settings_controller import SettingsController


class DDSUtility:
    """
    Utility class for handling DDS files in the application.
    """

    def __init__(self, settings_controller: SettingsController) -> None:
        self.settings_controller = settings_controller
        logger.info("DDSUtility initialized.")

    def delete_dds_files_without_png(self) -> None:
        """Deletes all DDS files that do not have a corresponding PNG file."""
        logger.info(
            "Running checks for deleting DDS files without corresponding PNG files..."
        )
        local_mods_target = self.settings_controller.settings.instances[
            self.settings_controller.settings.current_instance
        ].local_folder
        workshop_mods_target = self.settings_controller.settings.instances[
            self.settings_controller.settings.current_instance
        ].workshop_folder

        # Combine both paths to search for DDS files
        combined_paths = [local_mods_target, workshop_mods_target]
        combined_paths = [
            path for path in combined_paths if path and os.path.exists(path)
        ]

        dds_files = []
        for path in combined_paths:
            dds_files.extend(glob(os.path.join(path, "**", "*.dds"), recursive=True))

        # Check for corresponding PNG files
        deleted_count = 0
        for dds_file in dds_files:
            dds_path = Path(dds_file)
            png_path = dds_path.with_suffix(".png")
            if not png_path.exists():
                logger.warning(f"Deleting DDS file without PNG: {dds_file}")
                try:
                    dds_path.unlink()
                    deleted_count += 1
                except OSError as e:
                    logger.error(f"Failed to delete {dds_file}: {e}")

        logger.info(
            f"Deleted {deleted_count} DDS files without corresponding PNG files"
        )

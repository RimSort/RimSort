import os
import shutil
from pathlib import Path
from traceback import format_exc
from typing import Any, Callable, Self
from zipfile import ZipFile

import msgspec
from loguru import logger
from PySide6.QtCore import QCoreApplication, QObject

from app.models.instance import Instance
from app.utils.app_info import AppInfo
from app.views.dialogue import (
    show_fatal_error,
    show_warning,
)


class InvalidArchivePathError(ValueError):
    """Raised when provided archive path is invalid or not a valid ZIP file."""

    def __init__(self, archive_path: str) -> None:
        super().__init__(f"Invalid archive path: {archive_path}")


class InstanceController(QObject):
    """Controller for managing Instance operations and serialization."""

    def __init__(self, instance: Instance) -> None:
        """Initialize controller with an Instance."""
        super().__init__()
        self.instance = instance

    @classmethod
    def from_archive(cls, archive_path: str) -> Self:
        """Load an Instance from a ZIP archive containing instance.json."""
        if not cls._validate_archive_path(archive_path):
            logger.error(f"Invalid archive path: {archive_path}")
            show_warning(
                title=QCoreApplication.translate(
                    "InstanceController", "Invalid archive path"
                ),
                text=QCoreApplication.translate(
                    "InstanceController", "The provided archive path is invalid."
                ),
                information=QCoreApplication.translate(
                    "InstanceController", "Please provide a valid archive path."
                ),
            )
            raise InvalidArchivePathError(archive_path)

        try:
            with ZipFile(archive_path, "r") as archive:
                instance_bytes = archive.read("instance.json")
                instance = msgspec.json.decode(instance_bytes, type=Instance)
                return cls(instance)
        except Exception as e:
            logger.error(f"An error occurred while reading instance archive: {e}")
            show_fatal_error(
                title=QCoreApplication.translate(
                    "InstanceController", "Error restoring instance"
                ),
                text=QCoreApplication.translate(
                    "InstanceController",
                    "An error occurred while reading instance archive: {e}",
                ).format(e=e),
                details=format_exc(),
            )
            raise

    @classmethod
    def _validate_archive_path(cls, archive_path: str) -> bool:
        """Validate archive path exists and has .zip extension."""
        return Path(archive_path).exists() and archive_path.endswith(".zip")

    @property
    def instance_folder_path(self) -> Path:
        """Get the instance folder path."""
        return AppInfo().app_storage_folder / "instances" / self.instance.name

    @staticmethod
    def get_instance_folder_path(instance_name: str) -> Path:
        """Get instance folder path for a given instance name."""
        return AppInfo().app_storage_folder / "instances" / instance_name

    @staticmethod
    def get_game_data_path(instance: Instance) -> Path | None:
        """Get game data folder path or None if not configured."""
        if not instance.game_folder:
            return None
        return Path(instance.game_folder) / "Data"

    @staticmethod
    def get_local_mods_path(instance: Instance) -> Path | None:
        """Get local mods folder path or None if not configured."""
        if not instance.local_folder:
            return None
        return Path(instance.local_folder)

    @staticmethod
    def get_workshop_mods_path(instance: Instance) -> Path | None:
        """Get workshop mods folder path or None if not configured."""
        if not instance.workshop_folder:
            return None
        return Path(instance.workshop_folder)

    @staticmethod
    def get_config_folder_path(instance: Instance) -> Path | None:
        """Get config folder path or None if not configured."""
        if not instance.config_folder:
            return None
        return Path(instance.config_folder)

    def create_instance(
        self,
        instance_name: str,
        game_folder: str = "",
        config_folder: str = "",
        local_folder: str = "",
        workshop_folder: str = "",
        run_args: list[str] | None = None,
        steamcmd_install_path: str = "",
        steam_client_integration: bool = False,
    ) -> Instance:
        """
        Create a new Instance with the provided parameters.

        :param instance_name: Name of the instance
        :param game_folder: Path to game folder
        :param config_folder: Path to config folder
        :param local_folder: Path to local mods folder
        :param workshop_folder: Path to workshop folder
        :param run_args: Run arguments list
        :param steamcmd_install_path: Path to SteamCMD installation
        :param steam_client_integration: Enable Steam client integration
        :return: Created Instance
        :rtype: Instance
        """
        if run_args is None:
            run_args = []
        return Instance(
            name=instance_name,
            game_folder=game_folder,
            config_folder=config_folder,
            local_folder=local_folder,
            workshop_folder=workshop_folder,
            run_args=run_args,
            steamcmd_install_path=steamcmd_install_path,
            steam_client_integration=steam_client_integration,
        )

    def compress_to_archive(self, output_path: str) -> None:
        """Compress instance folder to ZIP archive, skipping symlinks and junctions."""
        if not output_path.endswith(".zip"):
            output_path += ".zip"

        try:
            logger.info(f"Compressing instance folder to archive: {output_path}")
            with ZipFile(output_path, "w") as archive:
                self._add_instance_folder_to_archive(archive)
                archive.writestr("instance.json", self.to_bytes())
                logger.debug(f"Added instance data to archive: {self.instance}")
        except Exception as e:
            logger.error(f"An error occurred while compressing instance folder: {e}")
            raise

    def _add_instance_folder_to_archive(self, archive: ZipFile) -> None:
        """Add instance folder contents to archive, skipping symlinks and junctions."""
        for root, dirs, files in os.walk(
            self.instance_folder_path, topdown=True, followlinks=False
        ):
            # Detect and skip symlinks by comparing resolved vs absolute paths
            if Path(root).absolute() != Path(root).resolve():
                logger.debug(f"Skipping symlinked directory: {root}")
                dirs.clear()
                files.clear()
                continue

            for _dir in dirs:
                dir_path = os.path.join(root, _dir)
                archive.write(
                    dir_path,
                    os.path.relpath(dir_path, self.instance_folder_path),
                )
                logger.debug(f"Added directory to archive: {dir_path}")

            for file in files:
                file_path = os.path.join(root, file)
                archive.write(
                    file_path,
                    os.path.relpath(file_path, self.instance_folder_path),
                )
                logger.debug(f"Added file to archive: {file_path}")

    def extract_from_archive(self, archive_path: str, delete_old: bool = True) -> None:
        """Extract instance folder from ZIP archive, optionally deleting existing folder."""
        logger.info(f"Extracting instance folder from archive: {archive_path}")

        if os.path.exists(self.instance_folder_path) and delete_old:
            self._delete_instance_folder()

        try:
            logger.info(f"Extracting to: {self.instance_folder_path}")
            with ZipFile(archive_path, "r") as archive:
                for info in archive.infolist():
                    if info.filename == "instance.json":
                        continue
                    logger.debug(f"Extracting file: {info.filename}")
                    archive.extract(info, path=self.instance_folder_path)
        except Exception as e:
            logger.error(f"An error occurred while extracting instance folder: {e}")
            raise

    def _delete_instance_folder(self) -> None:
        """Safely delete instance folder, handling read-only files on Windows."""
        logger.info(f"Deleting existing instance folder: {self.instance_folder_path}")

        def ignore_extended_attributes(
            func: Callable[[Any], Any], filename: str, exc_info: Any
        ) -> None:
            """Ignore macOS extended attribute files (._*) that may be read-only."""
            is_meta_file = os.path.basename(filename).startswith("._")
            if not (func is os.unlink and is_meta_file):
                raise

        try:
            shutil.rmtree(self.instance_folder_path, onerror=ignore_extended_attributes)
        except Exception as e:
            logger.error(f"An error occurred while deleting instance folder: {e}")
            raise

    def validate_paths(self, clear: bool = True) -> list[str]:
        """Validate instance paths exist and optionally clear invalid ones."""
        invalid_paths = []
        path_fields = [
            "game_folder",
            "config_folder",
            "local_folder",
            "workshop_folder",
            "steamcmd_install_path",
        ]

        # Check each path and optionally clear those that don't exist
        for path_name in path_fields:
            path_value = getattr(self.instance, path_name, "")
            if path_value and not Path(path_value).exists():
                invalid_paths.append(path_name)
                if clear:
                    object.__setattr__(self.instance, path_name, "")

        # Auto-recover steamcmd path if folder exists in instance directory
        if "steamcmd_install_path" in invalid_paths:
            default_path = self.instance_folder_path / "steamcmd"
            if default_path.exists():
                object.__setattr__(
                    self.instance,
                    "steamcmd_install_path",
                    str(self.instance_folder_path),
                )
                invalid_paths.remove("steamcmd_install_path")

        return invalid_paths

    def to_bytes(self) -> bytes:
        """Encode the instance to JSON bytes."""
        return msgspec.json.encode(self.instance)

    def from_bytes(self, instance_bytes: bytes) -> Instance:
        """Decode JSON bytes to Instance and update internal state."""
        self.instance = msgspec.json.decode(instance_bytes, type=Instance)
        return self.instance

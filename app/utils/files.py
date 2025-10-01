import datetime
import fnmatch
import os
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from loguru import logger

from app.models.settings import Settings
from app.utils.app_info import AppInfo


def subfolder_contains_candidate_path(
    subfolder: Path | None,
    candidate_directory: Path | str | None,
    glob_pattern: str,
    case_sensitive: bool = False,
) -> bool:
    """
    Check if the given subfolder or its immediate subfolders contain the candidate directory
    with files matching the glob pattern.

    :param subfolder: The base subfolder to check
    :param candidate_directory: The candidate directory name or path relative to subfolder
    :param glob_pattern: The glob pattern to match files (e.g., '*.dll')
    :param case_sensitive: Whether the glob matching should be case-sensitive (not supported by pathlib.glob)
    :return: True if matching files are found, False otherwise
    """
    if subfolder is None:
        return False

    if candidate_directory is None:
        candidate_directory = ""

    subfolder_paths = [subfolder]
    try:
        subfolder_paths.extend(
            [subfolder / folder for folder in subfolder.iterdir() if folder.is_dir()]
        )
    except Exception:
        # Could not list subdirectories, return False
        return False

    def check_subfolder(subfolder_path: Path) -> bool:
        candidate_path = subfolder_path / candidate_directory
        if candidate_path.exists() and candidate_path.is_dir():
            if case_sensitive:
                return any(candidate_path.glob(glob_pattern))
            else:
                for file_path in candidate_path.glob(glob_pattern):
                    if fnmatch.fnmatch(file_path.name.lower(), glob_pattern.lower()):
                        return True
        return False

    with ThreadPoolExecutor(max_workers=4) as executor:  # Limit to 4 threads
        results = executor.map(check_subfolder, subfolder_paths)
        return any(results)


def cleanup_old_backups(backup_dir: Path, keep: int) -> None:
    """
    Deletes old backups, keeping only the specified number of recent ones.
    """
    if keep == -1:
        logger.info(
            "Skipping backup cleanup because retention count is set to -1 (keep all)."
        )
        return
    try:
        logger.info(
            f"Cleaning up old backups in {backup_dir}. Keeping the most recent {keep}."
        )
        backups = sorted(
            [p for p in backup_dir.glob("Saves_*.zip")],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        if keep == 0:
            logger.info("Deleting all backups because retention count is set to 0.")
            for backup in backups:
                logger.info(f"Deleting backup: {backup}")
                os.remove(backup)
            return

        if len(backups) > keep:
            for old_backup in backups[keep:]:
                logger.info(f"Deleting old backup: {old_backup}")
                os.remove(old_backup)
    except Exception as e:
        logger.error(f"An error occurred during backup cleanup: {e}")


def create_saves_backup(
    saves_path: Path, backup_dir: Path, settings: Settings
) -> str | None:
    """
    Creates a compressed backup of the specified number of recent save files and cleans up old backups.
    """
    logger.info(f"Target saves folder identified: {saves_path}")
    if not saves_path.exists() or not saves_path.is_dir():
        logger.error(f"Saves directory not found at expected location: {saves_path}")
        return None

    try:
        # Get all files in the saves folder, sort by modification time
        all_files = [p for p in saves_path.rglob("*") if p.is_file()]
        all_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)

        compression_count = settings.auto_backup_compression_count
        if compression_count == -1:
            recent_files = all_files
        elif compression_count == 0:
            logger.info(
                "No save files will be backed up because compression count is set to 0."
            )
            return None
        else:
            recent_files = all_files[:compression_count]

        if not recent_files:
            logger.info("No save files found to back up.")
            return None

        backup_dir.mkdir(exist_ok=True)
        logger.info(f"Backup directory is: {backup_dir.resolve()}")

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        backup_filename = f"Saves_{timestamp}.zip"
        backup_archive_path = backup_dir / backup_filename

        logger.info(
            f"Compressing {len(recent_files)} most recent save(s) to {backup_archive_path} using DEFLATED..."
        )
        with zipfile.ZipFile(
            backup_archive_path, "w", compression=zipfile.ZIP_DEFLATED
        ) as zf:
            for file_path in recent_files:
                arc_name = file_path.relative_to(saves_path)
                zf.write(file_path, arc_name)

        logger.info(f"Successfully created backup: {backup_archive_path}")

        # Clean up old backups
        cleanup_old_backups(backup_dir, keep=settings.auto_backup_retention_count)

        return str(backup_archive_path)

    except Exception as e:
        logger.error(f"An error occurred during save backup: {e}")
        return None


def create_backup_in_thread(settings: Settings) -> None:
    """
    Launches the backup process in a background thread to avoid blocking the UI.
    """
    if not settings.backup_saves_on_launch:
        return

    today = datetime.date.today().isoformat()
    if settings.last_backup_date == today:
        logger.info(f"A backup has already been created today ({today}). Skipping.")
        return

    logger.info("Starting daily save backup in a background thread...")

    current_instance = settings.instances.get(settings.current_instance)
    if not current_instance or not current_instance.config_folder:
        logger.warning(
            "No active instance or config folder path found. Cannot perform backup."
        )
        return

    config_path = Path(current_instance.config_folder)
    saves_path = config_path.parent / "Saves"
    backup_dir = Path(AppInfo().app_storage_folder) / "backups"

    def backup_task() -> None:
        backup_path = create_saves_backup(saves_path, backup_dir, settings)
        if backup_path:
            # Update the last backup date in settings upon successful backup
            settings.last_backup_date = today
            settings.save()

    executor = ThreadPoolExecutor(max_workers=1)

    executor.submit(backup_task)

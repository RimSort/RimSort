import os
from functools import partial
from pathlib import Path
from shutil import copytree, rmtree
from traceback import format_exc
from typing import Any

from loguru import logger
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QInputDialog, QMessageBox

from app.controllers.instance_controller import (
    InstanceController,
    InvalidArchivePathError,
)
from app.controllers.metadata_db_controller import AuxMetadataController
from app.models.settings import Settings
from app.utils.app_info import AppInfo
from app.utils.constants import (
    DEFAULT_INSTANCE_NAME,
    INSTANCE_FOLDER_NAME,
    STEAM_FOLDER_NAME,
    STEAMCMD_FOLDER_NAME,
)
from app.utils.event_bus import EventBus
from app.utils.generic import handle_remove_read_only
from app.utils.steam.steamcmd.wrapper import SteamcmdInterface
from app.views.dialogue import (
    BinaryChoiceDialog,
    show_dialogue_conditional,
    show_dialogue_file,
    show_fatal_error,
    show_warning,
)


class InstanceService:
    """Orchestrates instance lifecycle operations (clone, backup, restore, create, delete).

    Keeps pure filesystem operations as static methods; orchestration methods
    take dependencies via constructor injection.
    """

    def __init__(
        self,
        settings: Settings,
        steamcmd_wrapper: SteamcmdInterface,
    ) -> None:
        self.settings = settings
        self.steamcmd_wrapper = steamcmd_wrapper
        self._subscribe_to_eventbus()

    # --- Pure filesystem helpers (static) ---

    @staticmethod
    def copy_game_folder(
        existing_instance_game_folder: str, target_game_folder: str
    ) -> None:
        try:
            if os.path.exists(target_game_folder) and os.path.isdir(target_game_folder):
                logger.info(f"Replacing existing game folder at {target_game_folder}")
                rmtree(
                    target_game_folder,
                    ignore_errors=False,
                    onerror=handle_remove_read_only,
                )
            logger.info(
                f"Copying game folder from {existing_instance_game_folder} to {target_game_folder}"
            )
            copytree(existing_instance_game_folder, target_game_folder, symlinks=True)
        except Exception as e:
            logger.error(f"An error occurred while copying game folder: {e}")

    @staticmethod
    def copy_config_folder(
        existing_instance_config_folder: str, target_config_folder: str
    ) -> None:
        try:
            if os.path.exists(target_config_folder) and os.path.isdir(
                target_config_folder
            ):
                logger.info(
                    f"Replacing existing config folder at {target_config_folder}"
                )
                rmtree(
                    target_config_folder,
                    ignore_errors=False,
                    onerror=handle_remove_read_only,
                )
            logger.info(
                f"Copying config folder from {existing_instance_config_folder} to {target_config_folder}"
            )
            copytree(
                existing_instance_config_folder,
                target_config_folder,
                symlinks=True,
            )
        except Exception as e:
            logger.error(f"An error occurred while copying config folder: {e}")

    @staticmethod
    def copy_local_folder(
        existing_instance_local_folder: str, target_local_folder: str
    ) -> None:
        try:
            if os.path.exists(target_local_folder) and os.path.isdir(
                target_local_folder
            ):
                logger.info(f"Replacing existing local folder at {target_local_folder}")
                rmtree(
                    target_local_folder,
                    ignore_errors=False,
                    onerror=handle_remove_read_only,
                )
            logger.info(
                f"Copying local folder from {existing_instance_local_folder} to {target_local_folder}"
            )
            copytree(
                existing_instance_local_folder,
                target_local_folder,
                symlinks=True,
            )
        except Exception as e:
            logger.error(f"An error occurred while copying local folder: {e}")

    @staticmethod
    def copy_workshop_mods_to_local(
        existing_instance_workshop_folder: str, target_local_folder: str
    ) -> None:
        try:
            if not os.path.exists(target_local_folder):
                os.mkdir(target_local_folder)
            logger.info(
                f"Cloning Workshop mods from {existing_instance_workshop_folder} to {target_local_folder}"
            )
            for subdir in os.listdir(existing_instance_workshop_folder):
                if os.path.isdir(
                    os.path.join(existing_instance_workshop_folder, subdir)
                ):
                    logger.debug(f"Cloning Workshop mod: {subdir}")
                    copytree(
                        os.path.join(existing_instance_workshop_folder, subdir),
                        os.path.join(target_local_folder, subdir),
                        symlinks=True,
                    )
        except Exception as e:
            logger.error(f"An error occurred while cloning Workshop mods: {e}")

    @staticmethod
    def clone_essential_paths(
        existing_instance_game_folder: str,
        target_game_folder: str,
        existing_instance_config_folder: str,
        target_config_folder: str,
    ) -> None:
        if os.path.exists(existing_instance_game_folder) and os.path.isdir(
            existing_instance_game_folder
        ):
            InstanceService.copy_game_folder(
                existing_instance_game_folder, target_game_folder
            )
        if os.path.exists(existing_instance_config_folder) and os.path.isdir(
            existing_instance_config_folder
        ):
            InstanceService.copy_config_folder(
                existing_instance_config_folder, target_config_folder
            )

    def _check_essential_paths_are_set(self, prompt: bool = True) -> bool:
        current_instance = self.settings.current_instance
        inst = self.settings.instances[current_instance]
        game_folder_path = inst.game_folder
        config_folder_path = inst.config_folder
        local_mods_folder_path = inst.local_folder
        logger.info(f"Game folder: {game_folder_path}")
        logger.info(f"Config folder: {config_folder_path}")
        logger.info(f"Local mods folder: {local_mods_folder_path}")
        if (
            game_folder_path
            and config_folder_path
            and local_mods_folder_path
            and os.path.exists(game_folder_path)
            and os.path.exists(config_folder_path)
            and os.path.exists(local_mods_folder_path)
        ):
            logger.info("Essential paths set!")
            return True
        else:
            logger.warning("Essential path(s) are invalid or not set!")
            answer = show_dialogue_conditional(
                title=QCoreApplication.translate(
                    "InstanceService", "Essential path(s)"
                ),
                text=QCoreApplication.translate(
                    "InstanceService", "Essential path(s) are invalid or not set!"
                ),
                information=QCoreApplication.translate(
                    "InstanceService",
                    "RimSort requires the below paths to be set.<br/><br/>"
                    "1) Game folder (Folder where RimWorld is installed).<br/><br/>"
                    "2) Config folder (Folder where ModsConfig.xml is located)<br/><br/>"
                    "3) Local mods folder (Mods folder inside the RimWorld installation).<br/><br/>"
                    "4) Steam mods folder (Only set if you use Steam user also enable Steam Client Integration)<br/><br/>"
                    "Try Using the autodetect functionality to set all paths automatically.<br/><br/>"
                    "Would you like to open the settings to configure them now?",
                ),
                button_text_override=[
                    QCoreApplication.translate("InstanceService", "Yes"),
                    QCoreApplication.translate("InstanceService", "No"),
                ],
            )
            if not prompt:
                return False
            return answer == QCoreApplication.translate("InstanceService", "Yes")

    def _subscribe_to_eventbus(self) -> None:
        EventBus().do_backup_existing_instance.connect(self.backup_existing_instance)
        EventBus().do_clone_existing_instance.connect(self.clone_existing_instance)
        EventBus().do_create_new_instance.connect(self.create_new_instance)
        EventBus().do_delete_current_instance.connect(self.delete_current_instance)
        EventBus().do_restore_instance_from_archive.connect(
            self.restore_instance_from_archive
        )

    # --- Instance lifecycle operations ---

    def backup_existing_instance(self, instance_name: str) -> None:
        """Backup an instance to a ZIP archive."""
        instance = self.settings.instances.get(instance_name)

        if instance_name == DEFAULT_INSTANCE_NAME:
            while True:
                new_instance_name, ok = QInputDialog.getText(
                    None,
                    QCoreApplication.translate(
                        "InstanceService", "Provide instance name"
                    ),
                    QCoreApplication.translate(
                        "InstanceService",
                        "Input a unique name for the backed up instance"
                        ' that is not "{name}"',
                    ).format(name=DEFAULT_INSTANCE_NAME),
                )
                if ok and new_instance_name.lower() != DEFAULT_INSTANCE_NAME.lower():
                    new_instance_name = (
                        new_instance_name.strip() if new_instance_name else ""
                    )
                    break
                else:
                    new_instance_name = ""
                    break
            if not new_instance_name.strip():
                logger.info("User cancelled operation")
                return
            instance_name = new_instance_name

        if instance is None:
            logger.error(f"Instance [{instance_name}] not found in Settings")
            return

        instance_controller = InstanceController(instance)
        output_path = show_dialogue_file(
            mode="save",
            caption="Select output path for instance archive",
            _dir=str(AppInfo().app_storage_folder),
            _filter="Zip files (*.zip)",
        )
        logger.info(f"Selected path: {output_path}")
        if output_path:
            try:
                EventBus().do_threaded_loading_animation.emit(
                    str(AppInfo().theme_data_folder / "default-icons" / "rimsort.gif"),
                    partial(
                        instance_controller.compress_to_archive,
                        output_path,
                    ),
                    QCoreApplication.translate(
                        "InstanceService",
                        "Compressing [{instance_name}] instance folder to archive...",
                    ).format(instance_name=instance_name),
                )
            except Exception as e:
                show_fatal_error(
                    title=QCoreApplication.translate(
                        "InstanceService", "Error compressing instance"
                    ),
                    text=QCoreApplication.translate(
                        "InstanceService",
                        "An error occurred while compressing instance folder: {e}",
                    ).format(e=e),
                    information=QCoreApplication.translate(
                        "InstanceService",
                        "Please check the logs for more information.",
                    ),
                    details=format_exc(),
                )
        else:
            logger.warning("Backup cancelled: User cancelled selection...")
            return

    def restore_instance_from_archive(self) -> None:
        """Restore an instance from a ZIP archive."""
        input_path = show_dialogue_file(
            mode="open",
            caption="Select input path for instance archive",
            _dir=str(AppInfo().app_storage_folder),
            _filter="Zip files (*.zip)",
        )

        if input_path is None:
            logger.info("User cancelled operation. Input path was None")
            return
        logger.info(f"Selected path: {input_path}")

        if not os.path.exists(input_path):
            logger.error(f"Archive not found at path: {input_path}")
            show_warning(
                title=QCoreApplication.translate(
                    "InstanceService", "Error restoring instance"
                ),
                text=QCoreApplication.translate(
                    "InstanceService",
                    "Archive not found at path: {input_path}",
                ).format(input_path=input_path),
            )
            return

        try:
            instance_controller = InstanceController.from_archive(input_path)
        except InvalidArchivePathError:
            return
        except Exception as e:
            logger.error(f"An error occurred while reading instance archive: {e}")
            show_fatal_error(
                title=QCoreApplication.translate(
                    "InstanceService", "Error restoring instance"
                ),
                text=QCoreApplication.translate(
                    "InstanceService",
                    "An error occurred while reading instance archive: {e}",
                ),
                details=format_exc(),
            )
            return

        if os.path.exists(instance_controller.instance_folder_path):
            answer = show_dialogue_conditional(
                title=QCoreApplication.translate(
                    "InstanceService", "Instance folder exists"
                ),
                text=QCoreApplication.translate(
                    "InstanceService",
                    "Instance folder already exists: {instance_folder_path}",
                ).format(instance_folder_path=instance_controller.instance_folder_path),
                information=QCoreApplication.translate(
                    "InstanceService",
                    "Do you want to continue and replace the existing instance folder?",
                ),
                button_text_override=[
                    QCoreApplication.translate("InstanceService", "Replace"),
                ],
            )

            if answer != QCoreApplication.translate("InstanceService", "Replace"):
                logger.info("User cancelled instance extraction.")
                return

        EventBus().do_threaded_loading_animation.emit(
            str(AppInfo().theme_data_folder / "default-icons" / "rimsort.gif"),
            partial(
                instance_controller.extract_from_archive,
                input_path,
            ),
            QCoreApplication.translate(
                "InstanceService", "Restoring instance [{name}] from archive..."
            ).format(name=instance_controller.instance.name),
        )

        if os.path.exists(instance_controller.instance_folder_path):
            cleared_paths = instance_controller.validate_paths()
            if cleared_paths:
                logger.warning(
                    f"Instance folder paths not found: {', '.join(cleared_paths)}"
                )
                show_warning(
                    title=QCoreApplication.translate(
                        "InstanceService", "Invalid instance folder paths"
                    ),
                    text=QCoreApplication.translate(
                        "InstanceService", "Invalid instance folder paths"
                    ),
                    information=QCoreApplication.translate(
                        "InstanceService",
                        "Some folder paths from the restored instance are invalid and were cleared."
                        " Please reconfigure them in the settings",
                    ),
                    details=QCoreApplication.translate(
                        "InstanceService", "Invalid paths: {path}"
                    ).format(path=", ".join(cleared_paths)),
                )

            steamcmd_link_path = str(
                Path(instance_controller.instance.steamcmd_install_path)
                / "steam"
                / "steamapps"
                / "workshop"
                / "content"
                / "294100"
            )

            if (
                os.path.exists(steamcmd_link_path)
                and instance_controller.instance.local_folder != ""
            ):
                logger.info("Restoring steamcmd symlink...")
                self.steamcmd_wrapper.create_symlink(
                    instance_controller.instance.local_folder,
                    steamcmd_link_path,
                    show_dialogues=False,
                    force=True,
                )
            elif not os.path.exists(steamcmd_link_path):
                logger.info("Skipping steamcmd symlink restoration")
            else:
                show_warning(
                    title=QCoreApplication.translate(
                        "InstanceService",
                        "Couldn't restore steamcmd symlink/junction",
                    ),
                    text=QCoreApplication.translate(
                        "InstanceService",
                        "Couldn't restore steamcmd symlink/junction",
                    ),
                    information=QCoreApplication.translate(
                        "InstanceService",
                        "The steamcmd symlink/junction could not be restored as the local folder"
                        " is not set or invalid. The symlink/junction will need to be manually"
                        " recreated.",
                    ),
                )
                logger.warning(
                    "Skipping steamcmd symlink restoration: Local folder not set."
                    " The symlink will need to be manually updated."
                )

            self.settings.instances[instance_controller.instance.name] = (
                instance_controller.instance
            )
            EventBus().do_activate_current_instance.emit(
                instance_controller.instance.name
            )
        else:
            show_warning(
                title=QCoreApplication.translate(
                    "InstanceService", "Error restoring instance"
                ),
                text=QCoreApplication.translate(
                    "InstanceService",
                    "An error occurred while restoring instance [{name}].",
                ).format(name=instance_controller.instance.name),
                information=QCoreApplication.translate(
                    "InstanceService",
                    "The instance folder was not found after extracting the archive."
                    " Perhaps the archive is corrupt or the instance name is invalid.",
                ),
            )

            logger.warning(
                "Restore cancelled: Instance folder not found after extraction..."
            )

    def clone_existing_instance(self, existing_instance_name: str) -> None:
        """Clone an existing instance to create a new one with copied data."""
        if not self._check_essential_paths_are_set(prompt=True):
            return

        current_instances = list(self.settings.instances.keys())
        existing_instance = self.settings.instances[existing_instance_name]

        existing_instance_game_folder = existing_instance.game_folder
        game_folder_name = os.path.split(existing_instance_game_folder)[1]
        existing_instance_local_folder = existing_instance.local_folder
        local_folder_name = os.path.split(existing_instance_local_folder)[1]
        existing_instance_workshop_folder = existing_instance.workshop_folder
        existing_instance_config_folder = existing_instance.config_folder
        existing_instance_run_args = existing_instance.run_args
        existing_instance_steamcmd_install_path = (
            existing_instance.steamcmd_install_path
        )
        existing_instance_steam_client_integration = (
            existing_instance.steam_client_integration
        )
        existing_instance_folder_override = existing_instance.instance_folder_override

        new_instance_name, _ok = QInputDialog.getText(
            None,
            QCoreApplication.translate("InstanceService", "Create new instance"),
            QCoreApplication.translate(
                "InstanceService",
                "Input a unique name of new instance that is not already used:",
            ),
        )
        new_instance_name = new_instance_name.strip() if new_instance_name else ""
        if (
            new_instance_name
            and new_instance_name != DEFAULT_INSTANCE_NAME
            and new_instance_name not in current_instances
        ):
            new_instance_path = str(
                InstanceController.get_instance_folder_path(
                    new_instance_name, existing_instance_folder_override
                )
            )
            answer = BinaryChoiceDialog(
                title=f"Clone instance [{existing_instance_name}]",
                text=f"Would you like to clone instance [{existing_instance_name}]"
                f" to create new instance [{new_instance_name}]?<br>"
                + "<br>This will clone the instance's game, mod, and configuration data."
                " This operation may take a long time depending on the amount of data being cloned.<br>"
                + "<br>The following folders will be cloned:",
                information=f"Game folder:<br>"
                f"{existing_instance_game_folder if existing_instance_game_folder else '&lt;None&gt;'}<br>"
                + f"<br>Configuration folder:<br>"
                f"{existing_instance_config_folder if existing_instance_config_folder else '&lt;None&gt;'}<br>"
                + f"<br>Local mods folder:<br>"
                f"{existing_instance_local_folder if existing_instance_local_folder else '&lt;None&gt;'}<br>"
                + f"<br>Workshop mods folder:<br>"
                f"{existing_instance_workshop_folder if existing_instance_workshop_folder else '&lt;None&gt;'}<br>"
                + "<br>SteamCMD install path (steamcmd + steam folders will be cloned):"
                + f"<br>{existing_instance_steamcmd_install_path if existing_instance_steamcmd_install_path else '&lt;None&gt;'}<br>"
                + f"<br>Run arguments:<br>"
                f"{existing_instance_run_args if existing_instance_run_args else '&lt;None&gt;'}<br>",
            )
            if answer.exec_is_positive():
                target_game_folder = str(Path(new_instance_path) / game_folder_name)
                target_local_folder = str(
                    Path(new_instance_path) / game_folder_name / local_folder_name
                )
                target_workshop_folder = ""
                target_config_folder = str(
                    Path(new_instance_path) / "InstanceData" / "Config"
                )
                EventBus().do_threaded_loading_animation.emit(
                    str(AppInfo().theme_data_folder / "default-icons" / "rimworld.gif"),
                    partial(
                        InstanceService.clone_essential_paths,
                        existing_instance_game_folder,
                        target_game_folder,
                        existing_instance_config_folder,
                        target_config_folder,
                    ),
                    f"Cloning RimWorld game / config folders from [{existing_instance_name}]"
                    f" to [{new_instance_name}] instance...",
                )
                local_folder_in_game = (
                    str(Path(existing_instance_game_folder) / local_folder_name)
                    == existing_instance_local_folder
                )
                if existing_instance_local_folder and not local_folder_in_game:
                    if os.path.exists(existing_instance_local_folder) and os.path.isdir(
                        existing_instance_local_folder
                    ):
                        EventBus().do_threaded_loading_animation.emit(
                            str(
                                AppInfo().theme_data_folder
                                / "default-icons"
                                / "rimworld.gif"
                            ),
                            partial(
                                InstanceService.copy_local_folder,
                                existing_instance_local_folder,
                                target_local_folder,
                            ),
                            f"Cloning local mods folder from [{existing_instance_name}]"
                            f" instance to [{new_instance_name}] instance...",
                        )
                if existing_instance_workshop_folder:
                    _answer = show_dialogue_conditional(
                        title=QCoreApplication.translate(
                            "InstanceService",
                            "Clone instance [{name}]",
                        ).format(name=existing_instance_name),
                        text=QCoreApplication.translate(
                            "InstanceService",
                            "What would you like to do with the configured"
                            " Workshop mods folder?",
                        ),
                        information=QCoreApplication.translate(
                            "InstanceService",
                            "Workshop folder: {folder}<br><br>"
                            "Option 1: Convert to SteamCMD<br>"
                            "RimSort will copy all Workshop mods to the new"
                            " instance's local mods folder, converting them to"
                            " SteamCMD mods that you can manage inside the new"
                            " instance. The Workshop folder will be ignored for"
                            " this instance to prevent duplicate mods.<br><br>"
                            "Option 2: Keep Workshop Folder<br>"
                            "The new instance will use the same Workshop folder"
                            " as the original instance. You can change this later"
                            " in the settings if needed.<br><br>"
                            "How would you like to proceed?",
                        ).format(folder=existing_instance_workshop_folder),
                        button_text_override=[
                            QCoreApplication.translate(
                                "InstanceService", "Convert to SteamCMD"
                            ),
                            QCoreApplication.translate(
                                "InstanceService", "Keep Workshop Folder"
                            ),
                        ],
                    )
                    answer_workshop_mods = str(_answer) or QCoreApplication.translate(
                        "InstanceService", "Cancelled"
                    )
                    if answer_workshop_mods == QCoreApplication.translate(
                        "InstanceService", "Convert to SteamCMD"
                    ):
                        if os.path.exists(
                            existing_instance_workshop_folder
                        ) and os.path.isdir(existing_instance_workshop_folder):
                            EventBus().do_threaded_loading_animation.emit(
                                str(
                                    AppInfo().theme_data_folder
                                    / "default-icons"
                                    / "steam_api.gif"
                                ),
                                partial(
                                    InstanceService.copy_workshop_mods_to_local,
                                    existing_instance_workshop_folder,
                                    target_local_folder,
                                ),
                                f"Cloning Workshop mods from [{existing_instance_name}]"
                                f" instance to [{new_instance_name}] instance's local mods...",
                            )
                        else:
                            show_warning(
                                title=QCoreApplication.translate(
                                    "InstanceService", "Workshop mods not found"
                                ),
                                text=QCoreApplication.translate(
                                    "InstanceService",
                                    "Workshop mods folder at"
                                    " [{existing_instance_workshop_folder}] not found.",
                                ).format(
                                    existing_instance_workshop_folder=existing_instance_workshop_folder
                                ),
                            )
                    elif answer_workshop_mods == QCoreApplication.translate(
                        "InstanceService", "Keep Workshop Folder"
                    ):
                        target_workshop_folder = str(existing_instance_workshop_folder)
                steamcmd_install_path = str(
                    Path(existing_instance_steamcmd_install_path) / STEAMCMD_FOLDER_NAME
                )
                if os.path.exists(steamcmd_install_path) and os.path.isdir(
                    steamcmd_install_path
                ):
                    target_steamcmd_install_path = str(
                        Path(new_instance_path) / STEAMCMD_FOLDER_NAME
                    )
                    if os.path.exists(target_steamcmd_install_path) and os.path.isdir(
                        target_steamcmd_install_path
                    ):
                        logger.info(
                            f"Replacing existing steamcmd folder at {target_steamcmd_install_path}"
                        )
                        rmtree(
                            target_steamcmd_install_path,
                            ignore_errors=False,
                            onerror=handle_remove_read_only,
                        )
                    logger.info(
                        f"Copying steamcmd folder from {steamcmd_install_path}"
                        f" to {target_steamcmd_install_path}"
                    )
                    copytree(
                        steamcmd_install_path,
                        target_steamcmd_install_path,
                        symlinks=True,
                    )
                steam_install_path = str(
                    Path(existing_instance_steamcmd_install_path) / STEAM_FOLDER_NAME
                )
                if os.path.exists(steam_install_path) and os.path.isdir(
                    steam_install_path
                ):
                    target_steam_install_path = str(
                        Path(new_instance_path) / STEAM_FOLDER_NAME
                    )
                    if os.path.exists(target_steam_install_path) and os.path.isdir(
                        target_steam_install_path
                    ):
                        logger.info(
                            f"Replacing existing steam folder at {target_steam_install_path}"
                        )
                        rmtree(
                            target_steam_install_path,
                            ignore_errors=False,
                            onerror=handle_remove_read_only,
                        )
                    logger.info(
                        f"Copying steam folder from {steam_install_path}"
                        f" to {target_steam_install_path}"
                    )
                    copytree(
                        steam_install_path,
                        target_steam_install_path,
                        symlinks=True,
                        ignore=lambda d, names: (
                            ["steamapps/workshop/content/294100"]
                            if d == steam_install_path
                            else []
                        ),
                    )
                    link_path = str(
                        Path(target_steam_install_path)
                        / "steamapps"
                        / "workshop"
                        / "content"
                        / "294100"
                    )
                    self.steamcmd_wrapper.create_symlink(
                        target_local_folder,
                        link_path,
                        show_dialogues=False,
                        force=True,
                    )
                self.create_new_instance(
                    instance_name=new_instance_name,
                    instance_data={
                        "game_folder": target_game_folder,
                        "local_folder": target_local_folder,
                        "workshop_folder": target_workshop_folder,
                        "config_folder": target_config_folder,
                        "run_args": existing_instance_run_args,
                        "steamcmd_install_path": str(
                            AppInfo().app_storage_folder
                            / INSTANCE_FOLDER_NAME
                            / new_instance_name
                        ),
                        "steam_client_integration": existing_instance_steam_client_integration,
                        "instance_folder_override": existing_instance_folder_override,
                    },
                )
        elif new_instance_name:
            show_warning(
                title=QCoreApplication.translate(
                    "InstanceService", "Error cloning instance"
                ),
                text=QCoreApplication.translate(
                    "InstanceService", "Unable to clone instance."
                ),
                information=QCoreApplication.translate(
                    "InstanceService",
                    "Please enter a valid, unique instance name."
                    " It cannot be '{name}' or empty.",
                ).format(name=DEFAULT_INSTANCE_NAME),
            )
        else:
            logger.debug("User cancelled clone operation")

    def create_new_instance(
        self,
        instance_name: str = "",
        instance_data: dict[str, Any] | None = None,
    ) -> None:
        """Create a new instance with the provided name and data."""
        if instance_data is None:
            instance_data = {}
        if not instance_name:
            new_instance_name, ok = QInputDialog.getText(
                None,
                QCoreApplication.translate("InstanceService", "Create new instance"),
                QCoreApplication.translate(
                    "InstanceService",
                    "Input a unique name of new instance that is not already used:",
                ),
            )
            if not ok or not new_instance_name.strip():
                logger.info("User cancelled operation")
                return
            instance_name = new_instance_name.strip()
        current_instances = list(self.settings.instances.keys())
        if (
            instance_name
            and instance_name != DEFAULT_INSTANCE_NAME
            and instance_name not in current_instances
        ):
            instance_folder_override = instance_data.get("instance_folder_override", "")
            if not instance_folder_override:
                current_instance = self.settings.instances[
                    self.settings.current_instance
                ]
                instance_folder_override = current_instance.instance_folder_override
            instance_path = InstanceController.get_instance_folder_path(
                instance_name, instance_folder_override
            )
            if not instance_path.exists():
                instance_path.mkdir(parents=True, exist_ok=True)
            current_inst = self.settings.instances[self.settings.current_instance]
            if not instance_data.get("game_folder"):
                instance_data["game_folder"] = current_inst.game_folder
            if not instance_data.get("config_folder"):
                instance_data["config_folder"] = current_inst.config_folder
            run_args = ""
            if instance_data.get("game_folder") and instance_data.get("config_folder"):
                log_path = str(instance_path / "RimWorld.log")
                savedata_path = str(instance_path / "InstanceData")
                preview_text = f"-logfile {log_path} -savedatafolder={savedata_path}"
                answer = show_dialogue_conditional(
                    title=QCoreApplication.translate(
                        "InstanceService",
                        "Create new instance [{instance_name}]",
                    ).format(instance_name=instance_name),
                    text=QCoreApplication.translate(
                        "InstanceService",
                        "Would you like to automatically generate run args"
                        " for the new instance?",
                    ),
                    information=QCoreApplication.translate(
                        "InstanceService",
                        "This will try to generate run args for the new instance"
                        " based on the configured Game/Config folders.<br><br>"
                        + "Generated run arguments preview:<br>{preview}",
                    ).format(preview=preview_text),
                )
                if answer == QMessageBox.StandardButton.Yes:
                    run_args = preview_text
                    config_path = instance_path / "InstanceData" / "Config"
                    config_path.mkdir(parents=True, exist_ok=True)
                    instance_data["config_folder"] = str(config_path)
                existing_args = instance_data.get("run_args", "")
                if existing_args:
                    run_args = f"{run_args} {existing_args}".strip()
            instance = InstanceController.create_instance(
                instance_name=instance_name,
                game_folder=instance_data.get("game_folder", ""),
                local_folder=instance_data.get("local_folder", ""),
                workshop_folder=instance_data.get("workshop_folder", ""),
                config_folder=instance_data.get("config_folder", ""),
                run_args=run_args,
                steamcmd_install_path=str(instance_path),
                steam_client_integration=instance_data.get(
                    "steam_client_integration", False
                ),
                instance_folder_override=instance_folder_override,
            )
            self.settings.instances[instance.name] = instance
            self.settings.save()
            EventBus().do_activate_current_instance.emit(instance_name)
        else:
            show_warning(
                title=QCoreApplication.translate(
                    "InstanceService", "Error creating instance"
                ),
                text=QCoreApplication.translate(
                    "InstanceService", "Unable to create new instance."
                ),
                information=QCoreApplication.translate(
                    "InstanceService",
                    "Please enter a valid, unique instance name."
                    " It cannot be '{name}' or empty.",
                ).format(name=DEFAULT_INSTANCE_NAME),
            )

    def delete_current_instance(self) -> None:
        """Delete the current instance and all its data."""
        if self.settings.current_instance == DEFAULT_INSTANCE_NAME:
            show_warning(
                title=QCoreApplication.translate(
                    "InstanceService", "Problem deleting instance"
                ),
                text=QCoreApplication.translate(
                    "InstanceService",
                    "Unable to delete instance {current_instance}.",
                ).format(current_instance=self.settings.current_instance),
                information=QCoreApplication.translate(
                    "InstanceService",
                    "The default instance cannot be deleted.",
                ),
            )
            return
        elif not self.settings.instances.get(self.settings.current_instance):
            show_fatal_error(
                title=QCoreApplication.translate(
                    "InstanceService", "Error deleting instance"
                ),
                text=QCoreApplication.translate(
                    "InstanceService",
                    "Unable to delete instance {current_instance}.",
                ).format(current_instance=self.settings.current_instance),
                information=QCoreApplication.translate(
                    "InstanceService",
                    "The selected instance does not exist.",
                ),
            )
            return
        else:
            answer = BinaryChoiceDialog(
                title=QCoreApplication.translate(
                    "InstanceService",
                    "Delete instance {current_instance}",
                ).format(current_instance=self.settings.current_instance),
                text=QCoreApplication.translate(
                    "InstanceService",
                    "Are you sure you want to delete the selected instance"
                    " and all of its data?",
                ),
                information=QCoreApplication.translate(
                    "InstanceService", "This action cannot be undone."
                ),
            )
            if answer.exec_is_positive():
                aux_metadata_controller = (
                    AuxMetadataController.get_or_create_cached_instance(
                        self.settings.aux_db_path
                    )
                )
                aux_metadata_controller.engine.dispose()
                try:
                    rmtree(
                        str(
                            Path(
                                AppInfo().app_storage_folder
                                / INSTANCE_FOLDER_NAME
                                / self.settings.current_instance
                            )
                        ),
                        ignore_errors=False,
                        onerror=handle_remove_read_only,
                    )
                except Exception as e:
                    logger.error(f"Error deleting instance: {e}")
                self.settings.instances.pop(self.settings.current_instance)
                EventBus().do_activate_current_instance.emit(DEFAULT_INSTANCE_NAME)

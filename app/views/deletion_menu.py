from enum import Enum
from errno import ENOTEMPTY
from pathlib import Path
from shutil import rmtree
from typing import Callable

from loguru import logger
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QMessageBox

from app.controllers.metadata_db_controller import AuxMetadataController
from app.controllers.settings_controller import SettingsController
from app.utils.event_bus import EventBus
from app.utils.generic import (
    attempt_chmod,
    delete_files_except_extension,
    delete_files_only_extension,
)
from app.utils.metadata import MetadataManager, ModMetadata
from app.views.dialogue import (
    show_dialogue_conditional,
    show_information,
    show_warning,
)


class DialogueResponse(Enum):
    """Enumeration for dialogue response constants."""

    YES = QMessageBox.StandardButton.Yes
    NO = QMessageBox.StandardButton.No


class DeletionResult:
    """Class to track deletion operation results."""

    def __init__(self) -> None:
        self.success_count: int = 0
        self.failed_count: int = 0
        self.steamcmd_purge_ids: set[str] = set()
        self.mods_for_unsubscribe: list[ModMetadata] = []


class ModDeletionMenu(QMenu):
    """Enhanced mod deletion menu with optimized operations and better error handling."""

    # Constants for better maintainability
    LUDEON_PACKAGE_PREFIX = "ludeon.rimworld"
    EXPANSION_DATA_SOURCE = "expansion"
    DDS_EXTENSION = ".dds"

    def __init__(
        self,
        settings_controller: SettingsController,
        get_selected_mod_metadata: Callable[[], list[ModMetadata]],
        remove_from_uuids: list[str] | None = None,
        menu_title: str = "Deletion options",
        enable_delete_mod: bool = True,
        enable_delete_keep_dds: bool = True,
        enable_delete_dds_only: bool = True,
        enable_delete_and_unsubscribe: bool = True,
        enable_delete_and_resubscribe: bool = True,
    ) -> None:
        super().__init__(title=self.tr("Deletion options"))
        self.remove_from_uuids = remove_from_uuids
        self.get_selected_mod_metadata = get_selected_mod_metadata
        self.metadata_manager = MetadataManager.instance()
        self.settings_controller = settings_controller
        self._actions_initialized = False

        # Build actions based on enabled features
        self.delete_actions: list[tuple[QAction, Callable[[], None]]] = []
        self._build_actions(
            enable_delete_mod,
            enable_delete_keep_dds,
            enable_delete_dds_only,
            enable_delete_and_unsubscribe,
            enable_delete_and_resubscribe,
        )

        self.aboutToShow.connect(self._refresh_actions)
        self._refresh_actions()

    def _build_actions(
        self,
        enable_delete_mod: bool,
        enable_delete_keep_dds: bool,
        enable_delete_dds_only: bool,
        enable_delete_and_unsubscribe: bool,
        enable_delete_and_resubscribe: bool,
    ) -> None:
        """Build the list of available deletion actions."""
        if enable_delete_mod:
            self.delete_actions.append(
                (QAction(self.tr("Delete mod completely")), self.delete_mod_completely)
            )

        if enable_delete_keep_dds:
            self.delete_actions.append(
                (
                    QAction(self.tr("Delete mod (keep .dds textures)")),
                    self.delete_mod_keep_dds,
                )
            )

        if enable_delete_dds_only:
            self.delete_actions.append(
                (
                    QAction(self.tr("Delete optimized textures (.dds files only)")),
                    self.delete_dds_files_only,
                )
            )

        if enable_delete_and_unsubscribe:
            self.delete_actions.append(
                (
                    QAction(self.tr("Delete mod and unsubscribe from Steam")),
                    self.delete_mod_and_unsubscribe,
                )
            )

        # Add new action for delete mod and resubscribe
        if enable_delete_and_resubscribe:
            self.delete_actions.append(
                (
                    QAction(self.tr("Delete mod and resubscribe using Steam")),
                    self.delete_mod_and_resubscribe,
                )
            )

    def _refresh_actions(self) -> None:
        """Refresh menu actions, optimized to avoid unnecessary reconnections."""
        if not self._actions_initialized:
            self.clear()
            for q_action, fn in self.delete_actions:
                q_action.triggered.connect(fn)
                self.addAction(q_action)
            self._actions_initialized = True

    def _is_official_expansion(self, mod_metadata: ModMetadata) -> bool:
        """Check if the mod is an official expansion that should not be deleted."""
        return mod_metadata.get(
            "data_source"
        ) == self.EXPANSION_DATA_SOURCE and mod_metadata.get(
            "packageid", ""
        ).startswith(self.LUDEON_PACKAGE_PREFIX)

    def _process_deletion_result(self, result: DeletionResult) -> None:
        """Process the results of a deletion operation."""
        # Clean up UUIDs from the remove list
        if self.remove_from_uuids is not None:
            for mod in result.mods_for_unsubscribe:
                if "uuid" in mod and mod["uuid"] in self.remove_from_uuids:
                    self.remove_from_uuids.remove(mod["uuid"])

        # Purge SteamCMD metadata for deleted mods
        if result.steamcmd_purge_ids:
            self.metadata_manager.steamcmd_purge_mods(
                publishedfileids=result.steamcmd_purge_ids
            )

        # Show success message
        if result.success_count > 0:
            show_information(
                title=self.tr("RimSort"),
                text=self.tr("Successfully deleted {count} selected mods.").format(
                    count=result.success_count
                ),
            )

    def _iterate_mods(
        self,
        deletion_fn: Callable[[ModMetadata], bool],
        mods: list[ModMetadata],
        collect_for_unsubscribe: bool = False,
        update_db: bool = True,
    ) -> DeletionResult:
        """
        Iterate through mods and apply the deletion function.

        Args:
            deletion_fn: Function to apply to each mod
            mods: List of mod metadata to process
            collect_for_unsubscribe: Whether to collect successfully deleted mods for unsubscription

        Returns:
            DeletionResult containing operation statistics
        """
        result = DeletionResult()

        for mod_metadata in mods:
            # Skip official expansions
            if self._is_official_expansion(mod_metadata):
                logger.info(
                    f"Skipping official expansion: {mod_metadata.get('name', 'Unknown')}"
                )
                continue

            try:
                if update_db:
                    self.delete_mod_from_aux_db(mod_metadata["path"])
                if deletion_fn(mod_metadata):
                    result.success_count += 1

                    # Collect for Steam unsubscription if requested
                    if collect_for_unsubscribe:
                        result.mods_for_unsubscribe.append(mod_metadata)

                    # Track UUIDs for removal
                    if (
                        self.remove_from_uuids is not None
                        and "uuid" in mod_metadata
                        and mod_metadata["uuid"] in self.remove_from_uuids
                    ):
                        self.remove_from_uuids.remove(mod_metadata["uuid"])

                    # Track SteamCMD mods for purging
                    if (
                        mod_metadata.get("steamcmd")
                        and "publishedfileid" in mod_metadata
                    ):
                        result.steamcmd_purge_ids.add(mod_metadata["publishedfileid"])
                else:
                    result.failed_count += 1
            except Exception as e:
                # TODO: Rollback DB deletion or better to let it delete?
                logger.error(
                    f"Unexpected error processing mod {mod_metadata.get('name', 'Unknown')}: {e}"
                )
                result.failed_count += 1

        return result

    def _delete_mod_directory(self, mod_metadata: ModMetadata) -> bool:
        """
        Common method to delete a mod's directory completely.

        Args:
            mod_metadata: Metadata of the mod to delete

        Returns:
            bool: True if deletion was successful, False otherwise
        """
        mod_path = mod_metadata.get("path")
        mod_name = mod_metadata.get("name", "Unknown")

        if not mod_path:
            logger.error(f"No path found for mod: {mod_name}")
            return False

        try:
            rmtree(mod_path, ignore_errors=False, onexc=attempt_chmod)
            logger.info(f"Successfully deleted mod directory: {mod_path}")
            return True

        except FileNotFoundError:
            logger.warning(f"Mod directory not found: {mod_path}")
            return False

        except OSError as e:
            error_code = e.errno

            if e.errno == ENOTEMPTY:
                warning_text = self.tr(
                    "Mod directory was not empty. Please close all programs accessing "
                    "files or subfolders in the directory (including your file manager) "
                    "and try again."
                )
            else:
                warning_text = self.tr("An OS error occurred while deleting the mod.")

            logger.error(f"Failed to delete mod at path: {mod_path} - {e}")

            show_warning(
                title=self.tr("Unable to delete mod"),
                text=warning_text,
                information=self.tr(
                    "{error_msg} occurred at {filename} with error code {error_code}."
                ).format(
                    error_msg=e.strerror or "Unknown error",
                    filename=e.filename or mod_path,
                    error_code=error_code,
                ),
            )
            return False

    def delete_mod_completely(self) -> None:
        """Delete selected mods completely from the filesystem."""
        selected_mods = self.get_selected_mod_metadata()

        if not selected_mods:
            show_information(
                title=self.tr("No mods selected"),
                text=self.tr("Please select at least one mod to delete."),
            )
            return

        answer = show_dialogue_conditional(
            title=self.tr("Confirm Complete Deletion"),
            text=self.tr(
                "You have selected {count} mod(s) for complete deletion."
            ).format(count=len(selected_mods)),
            information=self.tr(
                "\nThis operation will permanently delete the selected mod directories "
                "from the filesystem.\n\nDo you want to proceed?"
            ),
        )

        if answer == DialogueResponse.YES.value:
            result = self._iterate_mods(self._delete_mod_directory, selected_mods)
            self._process_deletion_result(result)

    def delete_dds_files_only(self) -> None:
        """Delete only .dds texture files from selected mods."""

        selected_mods = self.get_selected_mod_metadata()

        if not selected_mods:
            show_information(
                title=self.tr("No mods selected"),
                text=self.tr("Please select at least one mod to process."),
            )
            return

        answer = show_dialogue_conditional(
            title=self.tr("Confirm DDS Deletion"),
            text=self.tr(
                "You have selected {count} mod(s) for DDS texture deletion."
            ).format(count=len(selected_mods)),
            information=self.tr(
                "\nThis operation will only delete optimized textures (.dds files) "
                "from the selected mods.\n\nDo you want to proceed?"
            ),
        )

        if answer == DialogueResponse.YES.value:
            result = self._iterate_mods(
                self._delete_dds_from_mod, selected_mods, update_db=False
            )
            self._process_deletion_result(result)

    def _delete_dds_from_mod(self, mod_metadata: ModMetadata) -> bool:
        """Delete .dds files from a specific mod."""
        mod_path = mod_metadata.get("path")
        if not mod_path:
            return False
        return delete_files_only_extension(
            directory=str(mod_path),
            extension=self.DDS_EXTENSION,
        )

    def delete_mod_keep_dds(self) -> None:
        """Delete mod files but keep .dds texture files."""

        selected_mods = self.get_selected_mod_metadata()

        if not selected_mods:
            show_information(
                title=self.tr("No mods selected"),
                text=self.tr("Please select at least one mod to process."),
            )
            return

        answer = show_dialogue_conditional(
            title=self.tr("Confirm Selective Deletion"),
            text=self.tr(
                "You have selected {count} mod(s) for selective deletion."
            ).format(count=len(selected_mods)),
            information=self.tr(
                "\nThis operation will delete all mod files except for .dds texture files.\n"
                "The .dds files will be preserved.\n\nDo you want to proceed?"
            ),
        )

        if answer == DialogueResponse.YES.value:
            result = self._iterate_mods(self._delete_except_dds, selected_mods)
            self._process_deletion_result(result)

    def _delete_except_dds(self, mod_metadata: ModMetadata) -> bool:
        """Delete all files except .dds from a specific mod."""
        mod_path = mod_metadata.get("path")
        if not mod_path:
            return False
        return delete_files_except_extension(
            directory=str(mod_path),
            extension=self.DDS_EXTENSION,
        )

    def delete_mod_and_unsubscribe(self) -> None:
        """
        Delete selected mods and unsubscribe them from Steam Workshop.
        """
        self._delete_mods_and_manage_steam("unsubscribe")

    def _handle_steam_action(
        self, action: str, deleted_mods: list[ModMetadata]
    ) -> None:
        """
        Handle Steam Workshop unsubscription or resubscription for successfully deleted mods.

        Args:
            action: "unsubscribe" or "resubscribe"
            deleted_mods: List of successfully deleted mod metadata

        This method extracts valid Steam Workshop IDs from the deleted mods,
        converts them to integers, and emits the appropriate Steam API call
        via the EventBus. It also handles logging and user notifications
        for success or failure of the operation.
        """
        # Extract valid Steam Workshop IDs and convert to integers
        publishedfileids = []
        for mod in deleted_mods:
            pfid = mod.get("publishedfileid")
            if pfid and isinstance(pfid, str):
                try:
                    # Convert string to integer as required by Steam API
                    publishedfileids.append(int(pfid))
                except ValueError:
                    logger.warning(
                        f"Invalid publishedfileid format: {pfid} for mod {mod.get('name', 'Unknown')}"
                    )
                    # Continue processing other mods even if one ID is invalid
                    continue

        if not publishedfileids:
            logger.info(f"No Steam Workshop mods to {action}.")
            return

        try:
            logger.info(
                f"{action.capitalize()}ing {len(publishedfileids)} Steam Workshop mods."
            )

            # Emit the Steam API call
            EventBus().do_steamworks_api_call.emit(
                [
                    action,
                    publishedfileids,
                ]
            )

            # Show success message
            show_information(
                title=self.tr("Steam {action}").format(
                    action=self.tr(action).capitalize()
                ),
                text=self.tr(
                    "Successfully initiated {action} from {len} Steam Workshop mod(s).\n"
                    "The process may take a few moments to complete."
                ).format(
                    action=self.tr(action).capitalize(),
                    len=len(publishedfileids),
                ),
            )

            logger.info(
                f"Successfully initiated {action} for {len(publishedfileids)} mods."
            )

        except Exception as e:
            logger.error(f"Failed to initiate Steam {action}: {e}")
            show_warning(
                title=self.tr("{action} Error").format(
                    action=self.tr(action).capitalize()
                ),
                text=self.tr(
                    "An error occurred while trying to {action} from Steam Workshop mods."
                ).format(action=self.tr(action)),
                information=str(e),
            )

    def delete_mod_and_resubscribe(self) -> None:
        """
        Delete selected mods, and resubscribe them from Steam Workshop.
        """
        self._delete_mods_and_manage_steam("resubscribe")

    def _delete_mods_and_manage_steam(self, action: str) -> None:
        """
        Common method to delete mods and manage Steam Workshop subscription.

        Args:
            action: "unsubscribe" or "resubscribe"

        This method handles user confirmation, deletion of selected mods,
        and then calls the appropriate Steam Workshop action handler.
        """
        selected_mods = self.get_selected_mod_metadata()

        if not selected_mods:
            show_information(
                title=self.tr("No mods selected"),
                text=self.tr(
                    "Please select at least one mod to delete and {action}."
                ).format(action=self.tr(action)),
            )
            return

        # Filter mods that can be managed (have Steam Workshop IDs)
        steam_mods = [
            mod
            for mod in selected_mods
            if mod.get("publishedfileid")
            and isinstance(mod.get("publishedfileid"), str)
        ]

        answer = show_dialogue_conditional(
            title=self.tr("Confirm Deletion and {action}").format(
                action=self.tr(action).capitalize()
            ),
            text=self.tr(
                "You have selected {count} mod(s) for deletion.\n"
                "{steam_count} of these are Steam Workshop mods that will also be {action}."
            ).format(
                count=len(selected_mods),
                steam_count=len(steam_mods),
                action=self.tr(action + "d"),
            ),
            information=self.tr(
                "\nThis operation will:\n"
                "• Delete the selected mod directories from your filesystem\n"
                "• {action} Steam Workshop mods from your Steam account\n\n"
                "Do you want to proceed?"
            ).format(action=self.tr(action).capitalize()),
        )

        if answer == DialogueResponse.YES.value:
            # Perform deletion and collect successfully deleted mods
            result = self._iterate_mods(
                self._delete_mod_directory, selected_mods, collect_for_unsubscribe=True
            )

            # Process regular deletion results
            self._process_deletion_result(result)

            # Handle Steam action for successfully deleted mods
            self._handle_steam_action(action, result.mods_for_unsubscribe)

    def delete_mod_from_aux_db(self, path: str) -> None:
        """
        Delete mod entry from the auxiliary metadata db.

        This only deletes the mod for the relevant instance.
        """
        time_limit = self.settings_controller.settings.aux_db_time_limit
        if time_limit < 0:
            logger.debug(
                "Not deleting or setting item as outdated in Aux Metadata DB as time limit is negative."
            )
            return

        instance_path = Path(self.settings_controller.settings.current_instance_path)
        aux_metadata_controller = AuxMetadataController.get_or_create_cached_instance(
            instance_path / "aux_metadata.db"
        )
        mod_path = Path(path)
        with aux_metadata_controller.Session() as session:
            if time_limit > 0:
                logger.debug(
                    "Not deleting item from Aux Metadata DB as time limit is over 0. Setting as outdated instead."
                )
                aux_metadata_controller.update(session, mod_path, outdated=True)
                return
            aux_metadata_controller.delete(session, mod_path)

    # Backward compatibility aliases
    def delete_both(self) -> None:
        """Alias for delete_mod_completely for backward compatibility."""
        self.delete_mod_completely()

    def delete_dds(self) -> None:
        """Alias for delete_dds_files_only for backward compatibility."""
        self.delete_dds_files_only()

    def _dummy_translations(self) -> None:
        self.tr("unsubscribe")
        self.tr("resubscribe")
        self.tr("unsubscribed")
        self.tr("resubscribed")

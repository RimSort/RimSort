import errno
import os
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

    # Logging level constants
    LOG_LEVEL_DEBUG = "DEBUG"
    LOG_LEVEL_INFO = "INFO"
    LOG_LEVEL_WARNING = "WARNING"
    LOG_LEVEL_ERROR = "ERROR"

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
        completion_callback: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(title=self.tr("Deletion options"))
        self.remove_from_uuids = remove_from_uuids
        self.get_selected_mod_metadata = get_selected_mod_metadata
        self.metadata_manager = MetadataManager.instance()
        self.settings_controller = settings_controller
        self.completion_callback = completion_callback
        self._actions_initialized = False

        # Debug logging for remove_from_uuids
        logger.debug(
            f"ModDeletionMenu initialized with remove_from_uuids: {self.remove_from_uuids}"
        )

        # Synchronize remove_from_uuids with selected mods' UUIDs
        self._sync_remove_from_uuids_with_selected_mods()

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

    def _sync_remove_from_uuids_with_selected_mods(self) -> None:
        """Synchronize remove_from_uuids list with UUIDs of currently selected mods."""
        if self.remove_from_uuids is None:
            self.remove_from_uuids = []
        selected_mods = self.get_selected_mod_metadata()
        uuids = []
        for mod in selected_mods:
            uuid = mod.get("uuid")
            if not uuid:
                mod_path = mod.get("path")
                if mod_path:
                    uuid = self.metadata_manager.mod_metadata_dir_mapper.get(
                        str(mod_path)
                    )
            if uuid:
                uuids.append(uuid)
        # Remove duplicates and update the list
        self.remove_from_uuids = list(set(self.remove_from_uuids) | set(uuids))
        logger.debug(f"Synchronized remove_from_uuids: {self.remove_from_uuids}")

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

    def _has_steam_mods(self) -> bool:
        """Check if any selected mods are Steam Workshop mods."""
        selected_mods = self.get_selected_mod_metadata()
        return any(mod.get("publishedfileid") for mod in selected_mods)

    def _has_dds_files(self) -> bool:
        """Check if any selected mods contain .dds files."""
        selected_mods = self.get_selected_mod_metadata()
        for mod in selected_mods:
            mod_path = mod.get("path")
            if mod_path:
                try:
                    for root, dirs, files in os.walk(mod_path):
                        if any(file.endswith(self.DDS_EXTENSION) for file in files):
                            return True
                        # Limit depth to avoid performance issues
                        if root != mod_path:
                            break
                except (OSError, PermissionError):
                    continue
        return False

    def _refresh_actions(self) -> None:
        """Refresh menu actions, optimized to avoid unnecessary reconnections."""
        if not self._actions_initialized:
            self.clear()
            for q_action, fn in self.delete_actions:
                q_action.triggered.connect(fn)
                self.addAction(q_action)
            self._actions_initialized = True

        # Conditionally enable actions based on selected mods
        for q_action, fn in self.delete_actions:
            if fn == self.delete_dds_files_only:
                q_action.setEnabled(self._has_dds_files())
            elif fn in (
                self.delete_mod_and_unsubscribe,
                self.delete_mod_and_resubscribe,
            ):
                q_action.setEnabled(self._has_steam_mods())
            else:
                q_action.setEnabled(True)

    def _confirm_deletion(self, title: str, text: str, information: str) -> bool:
        """Helper method to show deletion confirmation dialog."""
        answer = show_dialogue_conditional(
            title=title,
            text=text,
            information=information,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _get_selected_mod_count(self) -> int:
        """Get the count of currently selected mods."""
        return len(self.get_selected_mod_metadata())

    def _show_no_mods_selected_message(self) -> None:
        """Show message when no mods are selected."""
        show_information(
            title=self.tr("No mods selected"),
            text=self.tr("Please select at least one mod to process."),
        )

    def _perform_deletion_operation(
        self,
        confirmation_title: str,
        confirmation_text: str,
        confirmation_info: str,
        deletion_fn: Callable[[ModMetadata], bool],
        update_db: bool = True,
        show_progress: bool = False,
    ) -> None:
        """
        Generic method to perform a deletion operation with confirmation and optional progress tracking.

        Args:
            confirmation_title: Title for the confirmation dialog
            confirmation_text: Main text for the confirmation dialog
            confirmation_info: Additional information for the confirmation dialog
            deletion_fn: Function to apply to each mod for deletion
            update_db: Whether to update the auxiliary database
            show_progress: Whether to show progress indicators during operation
        """
        selected_mods = self.get_selected_mod_metadata()

        if not selected_mods:
            self._show_no_mods_selected_message()
            return

        # Synchronize remove_from_uuids with current selected mods before deletion
        self._sync_remove_from_uuids_with_selected_mods()

        if self._confirm_deletion(
            confirmation_title, confirmation_text, confirmation_info
        ):
            result = self._iterate_mods(
                deletion_fn,
                selected_mods,
                update_db=update_db,
                show_progress=show_progress,
            )
            self._process_deletion_result(result)

    def _is_official_expansion(self, mod_metadata: ModMetadata) -> bool:
        """Check if the mod is an official expansion that should not be deleted."""
        return mod_metadata.get(
            "data_source"
        ) == self.EXPANSION_DATA_SOURCE and mod_metadata.get(
            "packageid", ""
        ).startswith(self.LUDEON_PACKAGE_PREFIX)

    def _process_deletion_result(self, result: DeletionResult) -> None:
        """Process the results of a deletion operation."""
        # Purge SteamCMD metadata for deleted mods
        if result.steamcmd_purge_ids:
            self.metadata_manager.steamcmd_purge_mods(
                publishedfileids=result.steamcmd_purge_ids
            )

        # Show success message
        if result.success_count > 0:
            show_information(
                title=self.tr("RimSort"),
                text=self.tr(
                    f"Successfully deleted {result.success_count} selected mods."
                ),
            )

            # Show failure message if any deletions failed
            if result.failed_count > 0:
                show_warning(
                    title=self.tr("Deletion Incomplete"),
                    text=self.tr(
                        f"Failed to delete {result.failed_count} mod(s). Check logs for details."
                    ),
                )

        # Call completion callback if provided
        if self.completion_callback:
            self.completion_callback()

    def _iterate_mods(
        self,
        deletion_fn: Callable[[ModMetadata], bool],
        mods: list[ModMetadata],
        collect_for_unsubscribe: bool = False,
        update_db: bool = True,
        show_progress: bool = False,
    ) -> DeletionResult:
        """
        Iterate through mods and apply the deletion function with improved error handling and optional progress tracking.

        Args:
            deletion_fn: Function to apply to each mod
            mods: List of mod metadata to process
            collect_for_unsubscribe: Whether to collect successfully deleted mods for unsubscription
            update_db: Whether to update the auxiliary database
            show_progress: Whether to show progress indicators during operation

        Returns:
            DeletionResult containing operation statistics
        """
        result = DeletionResult()
        total_mods = len(mods)
        processed_count = 0

        for mod_metadata in mods:
            processed_count += 1

            # Skip official expansions
            if self._is_official_expansion(mod_metadata):
                logger.info(
                    f"Skipping official expansion: {mod_metadata.get('name', 'Unknown')}"
                )
                self._log_progress_if_enabled(
                    processed_count, total_mods, show_progress
                )
                continue

            # Process the mod deletion
            if self._process_single_mod_deletion(
                mod_metadata, deletion_fn, result, collect_for_unsubscribe, update_db
            ):
                # Handle successful deletion tasks
                self._handle_successful_deletion(
                    mod_metadata, result, collect_for_unsubscribe
                )

            self._log_progress_if_enabled(processed_count, total_mods, show_progress)

        self._log_deletion_summary(result)
        return result

    def _process_single_mod_deletion(
        self,
        mod_metadata: ModMetadata,
        deletion_fn: Callable[[ModMetadata], bool],
        result: DeletionResult,
        collect_for_unsubscribe: bool,
        update_db: bool,
    ) -> bool:
        """
        Process deletion for a single mod with comprehensive error handling.

        Returns:
            bool: True if deletion was successful, False otherwise
        """
        mod_name = mod_metadata.get("name", "Unknown")
        mod_path = mod_metadata.get("path", "")

        try:
            # Update database first (if requested)
            if update_db and not self._update_mod_database(mod_path, mod_name):
                result.failed_count += 1
                return False

            # Retrieve UUID before deletion if not present
            if "uuid" not in mod_metadata:
                uuid = self.metadata_manager.mod_metadata_dir_mapper.get(mod_path)
                if uuid:
                    mod_metadata["uuid"] = uuid
                    logger.debug(
                        f"Retrieved UUID {uuid} for mod {mod_name} before deletion"
                    )
                else:
                    logger.warning(
                        f"Could not retrieve UUID for mod {mod_name} with path {mod_path} before deletion"
                    )

            # Perform the deletion operation
            return self._execute_deletion_operation(
                mod_metadata, deletion_fn, result, mod_name
            )

        except Exception as general_error:
            logger.error(f"Critical error processing mod {mod_name}: {general_error}")
            result.failed_count += 1
            return False

    def _update_mod_database(self, mod_path: str, mod_name: str) -> bool:
        """Update the auxiliary database for a mod. Returns True if successful."""
        try:
            self.delete_mod_from_aux_db(mod_path)
            return True
        except Exception as db_error:
            logger.error(f"Failed to update database for mod {mod_name}: {db_error}")
            return False

    def _execute_deletion_operation(
        self,
        mod_metadata: ModMetadata,
        deletion_fn: Callable[[ModMetadata], bool],
        result: DeletionResult,
        mod_name: str,
    ) -> bool:
        """Execute the deletion operation with specific error handling."""
        try:
            if deletion_fn(mod_metadata):
                result.success_count += 1
                return True
            else:
                result.failed_count += 1
                logger.warning(f"Deletion function returned False for mod: {mod_name}")
                return False

        except (OSError, PermissionError) as file_error:
            logger.error(f"File system error processing mod {mod_name}: {file_error}")
            result.failed_count += 1
            return False

        except (ValueError, TypeError) as data_error:
            logger.error(
                f"Data validation error processing mod {mod_name}: {data_error}"
            )
            result.failed_count += 1
            return False

        except Exception as deletion_error:
            logger.error(
                f"Unexpected error during deletion of mod {mod_name}: {deletion_error}"
            )
            result.failed_count += 1
            return False

    def _handle_successful_deletion(
        self,
        mod_metadata: ModMetadata,
        result: DeletionResult,
        collect_for_unsubscribe: bool,
    ) -> None:
        """Handle tasks that need to be performed after successful deletion."""
        # Collect for Steam unsubscription if requested
        if collect_for_unsubscribe:
            result.mods_for_unsubscribe.append(mod_metadata)

        # Handle UUID removal and signal emission
        self._handle_uuid_removal(mod_metadata)

        # Track SteamCMD mods for purging
        self._track_steamcmd_mod(mod_metadata, result)

    def _handle_uuid_removal(self, mod_metadata: ModMetadata) -> None:
        """Handle UUID removal from tracking list and emit signals."""
        logger.debug(
            f"_handle_uuid_removal called for mod: {mod_metadata.get('name', 'Unknown')}"
        )
        logger.debug(f"mod_metadata keys: {list(mod_metadata.keys())}")
        if self.remove_from_uuids is None:
            logger.debug("remove_from_uuids is None, skipping UUID removal")
            return
        if "uuid" not in mod_metadata:
            # Try to retrieve UUID from MetadataManager's mapper using the mod's path
            mod_path = mod_metadata.get("path")
            if mod_path:
                uuid = self.metadata_manager.mod_metadata_dir_mapper.get(str(mod_path))
                if uuid:
                    mod_metadata["uuid"] = uuid
                    logger.debug(
                        f"Retrieved UUID {uuid} for mod {mod_metadata.get('name', 'Unknown')} from path"
                    )
                else:
                    logger.debug(
                        f"Could not retrieve UUID for mod {mod_metadata.get('name', 'Unknown')} with path {mod_path}"
                    )
                    return
            else:
                logger.debug(
                    f"Mod {mod_metadata.get('name', 'Unknown')} has no path, cannot retrieve UUID"
                )
                return
        if mod_metadata["uuid"] not in self.remove_from_uuids:
            logger.debug(
                f"UUID {mod_metadata['uuid']} not in remove_from_uuids list, skipping removal"
            )
            return

        try:
            logger.debug(f"Emitting mod_deleted_signal for {mod_metadata['uuid']}")
            self.metadata_manager.mod_deleted_signal.emit(mod_metadata["uuid"])
            logger.debug(f"Removing UUID {mod_metadata['uuid']} from tracking list")
            self.remove_from_uuids.remove(mod_metadata["uuid"])
        except (ValueError, AttributeError) as uuid_error:
            logger.warning(
                f"Failed to remove UUID for mod {mod_metadata.get('name', 'Unknown')}: {uuid_error}"
            )

    def _track_steamcmd_mod(
        self, mod_metadata: ModMetadata, result: DeletionResult
    ) -> None:
        """Track SteamCMD mods for metadata purging."""
        if mod_metadata.get("steamcmd") and "publishedfileid" in mod_metadata:
            result.steamcmd_purge_ids.add(mod_metadata["publishedfileid"])

    def _log_progress_if_enabled(
        self, processed_count: int, total_mods: int, show_progress: bool
    ) -> None:
        """Log progress if progress tracking is enabled."""
        if show_progress and total_mods > 0:
            progress_percentage = (processed_count / total_mods) * 100
            logger.info(
                f"Deletion progress: {processed_count}/{total_mods} mods processed ({progress_percentage:.1f}%)"
            )

    def _log_deletion_summary(self, result: DeletionResult) -> None:
        """Log the final summary of the deletion operation."""
        total_processed = result.success_count + result.failed_count
        if total_processed > 0:
            logger.info(
                f"Deletion operation completed: {result.success_count} successful, {result.failed_count} failed"
            )

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
            logger.debug(f"Mod directory not found: {mod_path}")
            return False

        except OSError as e:
            error_code = e.errno

            if e.errno == errno.ENOTEMPTY:
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
                    f"{e.strerror or 'Unknown error'} occurred at {e.filename or mod_path} with error code {error_code}."
                ),
            )
            return False

    def delete_mod_completely(self) -> None:
        """Delete selected mods completely from the filesystem."""
        selected_count = len(self.get_selected_mod_metadata())
        self._perform_deletion_operation(
            confirmation_title=self.tr("Confirm Complete Deletion"),
            confirmation_text=self.tr(
                f"You have selected {selected_count} mod(s) for complete deletion."
            ),
            confirmation_info=self.tr(
                "\nThis operation will permanently delete the selected mod directories from the filesystem.\n\nDo you want to proceed?"
            ),
            deletion_fn=self._delete_mod_directory,
        )

    def delete_dds_files_only(self) -> None:
        """Delete only .dds texture files from selected mods."""
        selected_count = len(self.get_selected_mod_metadata())
        self._perform_deletion_operation(
            confirmation_title=self.tr("Confirm DDS Deletion"),
            confirmation_text=self.tr(
                f"You have selected {selected_count} mod(s) for DDS texture deletion."
            ),
            confirmation_info=self.tr(
                "\nThis operation will only delete optimized textures (.dds files) from the selected mods.\n\nDo you want to proceed?"
            ),
            deletion_fn=self._delete_dds_from_mod,
            update_db=False,
        )

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
        selected_count = len(self.get_selected_mod_metadata())
        self._perform_deletion_operation(
            confirmation_title=self.tr("Confirm Selective Deletion"),
            confirmation_text=self.tr(
                f"You have selected {selected_count} mod(s) for selective deletion."
            ),
            confirmation_info=self.tr(
                "\nThis operation will delete all mod files except for .dds texture files.\nThe .dds files will be preserved.\n\nDo you want to proceed?"
            ),
            deletion_fn=self._delete_except_dds,
        )

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
                    logger.debug(
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
            self._show_no_mods_selected_message()
            return

        # Filter mods that can be managed (have Steam Workshop IDs)
        steam_mods = [
            mod
            for mod in selected_mods
            if mod.get("publishedfileid")
            and isinstance(mod.get("publishedfileid"), str)
        ]

        selected_count = len(selected_mods)
        steam_count = len(steam_mods)
        action_capitalized = self.tr(action).capitalize()
        action_past = self.tr(action + "d")

        if self._confirm_deletion(
            self.tr(f"Confirm Deletion and {action_capitalized}"),
            self.tr(
                f"You have selected {selected_count} mod(s) for deletion.\n{steam_count} of these are Steam Workshop mods that will also be {action_past}."
            ),
            self.tr(
                f"\nThis operation will:\n• Delete the selected mod directories from your filesystem\n• {action_capitalized} Steam Workshop mods from your Steam account\n\nDo you want to proceed?"
            ),
        ):
            # Synchronize remove_from_uuids with current selected mods before deletion
            self._sync_remove_from_uuids_with_selected_mods()

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

        aux_metadata_controller = AuxMetadataController.get_or_create_cached_instance(
            self.settings_controller.settings.aux_db_path
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
        """
        Dummy method to ensure translation strings are included for i18n tools.
        Consider removing or replacing with proper translation extraction.
        """
        self.tr("unsubscribe")
        self.tr("resubscribe")
        self.tr("unsubscribed")
        self.tr("resubscribed")

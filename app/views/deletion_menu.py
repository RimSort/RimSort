from enum import Enum
from errno import ENOTEMPTY
from shutil import rmtree
from typing import Callable

from loguru import logger
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu

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

    YES = "&Yes"
    NO = "&No"


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
        get_selected_mod_metadata: Callable[[], list[ModMetadata]],
        remove_from_uuids: list[str] | None = None,
        menu_title: str = "Deletion options",
        enable_delete_mod: bool = True,
        enable_delete_keep_dds: bool = True,
        enable_delete_dds_only: bool = True,
        enable_delete_and_unsubscribe: bool = True,
        enable_delete_and_resubscribe: bool = True,
    ) -> None:
        super().__init__(title=self.tr(menu_title))
        self.remove_from_uuids = remove_from_uuids
        self.get_selected_mod_metadata = get_selected_mod_metadata
        self.metadata_manager = MetadataManager.instance()
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
            result = self._iterate_mods(self._delete_dds_from_mod, selected_mods)
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

        This method combines deletion with Steam unsubscription for a streamlined workflow.
        Only successfully deleted mods will be unsubscribed to maintain data consistency.
        """
        selected_mods = self.get_selected_mod_metadata()

        if not selected_mods:
            show_information(
                title=self.tr("No mods selected"),
                text=self.tr(
                    "Please select at least one mod to delete and unsubscribe."
                ),
            )
            return

        # Filter mods that can be unsubscribed (have Steam Workshop IDs)
        steam_mods = [
            mod
            for mod in selected_mods
            if mod.get("publishedfileid")
            and isinstance(mod.get("publishedfileid"), str)
        ]

        answer = show_dialogue_conditional(
            title=self.tr("Confirm Deletion and Unsubscribe"),
            text=self.tr(
                "You have selected {total_count} mod(s) for deletion.\n"
                "{steam_count} of these are Steam Workshop mods that will also be unsubscribed."
            ).format(total_count=len(selected_mods), steam_count=len(steam_mods)),
            information=self.tr(
                "\nThis operation will:\n"
                "• Delete the selected mod directories from your filesystem\n"
                "• Unsubscribe Steam Workshop mods from your Steam account\n\n"
                "Do you want to proceed?"
            ),
        )

        if answer == DialogueResponse.YES.value:
            # Perform deletion and collect successfully deleted mods
            result = self._iterate_mods(
                self._delete_mod_directory, selected_mods, collect_for_unsubscribe=True
            )

            # Process regular deletion results
            self._process_deletion_result(result)

            # Handle Steam unsubscription for successfully deleted mods
            self._handle_steam_unsubscription(result.mods_for_unsubscribe)

    def _handle_steam_unsubscription(self, deleted_mods: list[ModMetadata]) -> None:
        """
        Handle Steam Workshop unsubscription for successfully deleted mods.

        Args:
            deleted_mods: List of successfully deleted mod metadata
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
            logger.info("No Steam Workshop mods to unsubscribe from.")
            return

        try:
            logger.info(
                f"Unsubscribing from {len(publishedfileids)} Steam Workshop mods."
            )

            # Emit the Steam API call
            EventBus().do_steamworks_api_call.emit(
                [
                    "unsubscribe",
                    publishedfileids,
                ]
            )

            # Show success message
            show_information(
                title=self.tr("Steam Unsubscription"),
                text=self.tr(
                    "Successfully initiated unsubscription from {count} Steam Workshop mod(s).\n"
                    "The unsubscription process may take a few moments to complete."
                ).format(count=len(publishedfileids)),
            )

            logger.info(
                f"Successfully initiated unsubscription for {len(publishedfileids)} mods."
            )

        except Exception as e:
            logger.error(f"Failed to initiate Steam unsubscription: {e}")
            show_warning(
                title=self.tr("Unsubscription Error"),
                text=self.tr(
                    "An error occurred while trying to unsubscribe from Steam Workshop mods."
                ),
                information=str(e),
            )

    def delete_mod_and_resubscribe(self) -> None:
        """
        Delete selected mods, and resubscribe them from Steam Workshop.
        """
        selected_mods = self.get_selected_mod_metadata()

        if not selected_mods:
            show_information(
                title=self.tr("No mods selected"),
                text=self.tr(
                    "Please select at least one mod to delete and resubscribe."
                ),
            )
            return

        # Filter mods that can be resubscribed (have Steam Workshop IDs)
        steam_mods = [
            mod
            for mod in selected_mods
            if mod.get("publishedfileid")
            and isinstance(mod.get("publishedfileid"), str)
        ]

        answer = show_dialogue_conditional(
            title=self.tr("Confirm Deletion and Resubscribe"),
            text=self.tr(
                "You have selected {total_count} mod(s) for deletion.\n"
                "{steam_count} of these are Steam Workshop mods that will be resubscribed."
            ).format(total_count=len(selected_mods), steam_count=len(steam_mods)),
            information=self.tr(
                "\nThis operation will:\n"
                "• Delete the selected mod directories from your filesystem\n"
                "• Resubscribe to the Steam Workshop mods\n\n"
                "Do you want to proceed?"
            ),
        )

        if answer == DialogueResponse.YES.value:
            # Perform deletion and collect successfully deleted mods
            result = self._iterate_mods(
                self._delete_mod_directory, selected_mods, collect_for_unsubscribe=True
            )

            # Process regular deletion results
            self._process_deletion_result(result)

            # Handle Steam resubscription for successfully deleted mods
            self._handle_steam_resubscription(result.mods_for_unsubscribe)

    def _handle_steam_resubscription(self, deleted_mods: list[ModMetadata]) -> None:
        """
        Handle Steam Workshop resubscription for successfully deleted mods.

        Args:
            deleted_mods: List of successfully deleted mod metadata
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
            logger.info("No Steam Workshop mods to resubscribe.")
            return

        try:
            logger.info(
                f"Resubscribing from {len(publishedfileids)} Steam Workshop mods."
            )

            # Emit the Steam API call to resubscribe
            EventBus().do_steamworks_api_call.emit(
                [
                    "resubscribe",
                    publishedfileids,
                ]
            )

            # Show success message for resubscription
            show_information(
                title=self.tr("Steam Resubscription"),
                text=self.tr(
                    "Successfully initiated resubscription to {count} Steam Workshop mod(s).\n"
                    "The resubscription process may take a few moments to complete."
                ).format(count=len(publishedfileids)),
            )

            logger.info(
                f"Successfully initiated resubscription for {len(publishedfileids)} mods."
            )

        except Exception as e:
            logger.error(f"Failed to initiate Steam resubscription: {e}")
            show_warning(
                title=self.tr("Resubscription Error"),
                text=self.tr(
                    "An error occurred while trying to resubscribe from Steam Workshop mods."
                ),
                information=str(e),
            )

    # Backward compatibility aliases
    def delete_both(self) -> None:
        """Alias for delete_mod_completely for backward compatibility."""
        self.delete_mod_completely()

    def delete_dds(self) -> None:
        """Alias for delete_dds_files_only for backward compatibility."""
        self.delete_dds_files_only()

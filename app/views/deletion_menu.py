import sys
from errno import ENOTEMPTY
from shutil import rmtree
from typing import Any, Callable

from loguru import logger
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu

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


class ModDeletionMenu(QMenu):
    def __init__(
        self,
        get_selected_mod_metadata: Callable[[], list[ModMetadata]],
        remove_from_uuids: list[str] | None,
        menu_title: str = "Deletion options",
        delete_mod: bool = True,
        delete_both: bool = True,
        delete_dds: bool = True,
    ):
        super().__init__(title=self.tr("Deletion options"))
        self.remove_from_uuids = remove_from_uuids
        self.get_selected_mod_metadata = get_selected_mod_metadata
        self.metadata_manager = MetadataManager.instance()
        self.delete_actions: list[tuple[QAction, Callable[[], None]]] = []
        if delete_mod:
            self.delete_actions.append(
                (QAction(self.tr("Delete mod")), self.delete_both)
            )

        if delete_both:
            self.delete_actions.append(
                (QAction(self.tr("Delete mod (keep .dds)")), self.delete_mod_keep_dds)
            )
        if delete_dds:
            self.delete_actions.append(
                (
                    QAction(self.tr("Delete optimized textures (.dds files only)")),
                    self.delete_dds,
                )
            )

        self.aboutToShow.connect(self._refresh_actions)
        self._refresh_actions()

    def _refresh_actions(self) -> None:
        self.clear()
        for q_action, fn in self.delete_actions:
            q_action.triggered.connect(fn)
            self.addAction(q_action)

    def _iterate_mods(
        self, fn: Callable[[ModMetadata], bool], mods: list[ModMetadata]
    ) -> None:
        steamcmd_acf_pfid_purge: set[str] = set()

        count = 0
        for mod_metadata in mods:
            if mod_metadata[
                "data_source"  # Disallow Official Expansions
            ] != "expansion" or not mod_metadata["packageid"].startswith(
                "ludeon.rimworld"
            ):
                if fn(mod_metadata):
                    count = count + 1
                    if (
                        self.remove_from_uuids is not None
                        and "uuid" in mod_metadata
                        and mod_metadata["uuid"] in self.remove_from_uuids
                    ):
                        self.remove_from_uuids.remove(mod_metadata["uuid"])

                    if mod_metadata.get("steamcmd"):
                        steamcmd_acf_pfid_purge.add(mod_metadata["publishedfileid"])

        # Purge any deleted SteamCMD mods from acf metadata
        if steamcmd_acf_pfid_purge:
            self.metadata_manager.steamcmd_purge_mods(
                publishedfileids=steamcmd_acf_pfid_purge
            )

        show_information(
            title=self.tr("RimSort"),
            text=self.tr("Successfully deleted {count} seleted mods.").format(
                count=count
            ),
        )

    def delete_both(self) -> None:
        def _inner_delete_both(mod_metadata: dict[str, Any]) -> bool:
            try:
                rmtree(
                    mod_metadata["path"],
                    ignore_errors=False,
                    onexc=attempt_chmod,
                )
                return True
            except FileNotFoundError:
                logger.debug(
                    f"Unable to delete mod. Path does not exist: {mod_metadata['path']}"
                )
                return False
            except OSError as e:
                if sys.platform == "win32":
                    error_code = e.winerror
                else:
                    error_code = e.errno
                if e.errno == ENOTEMPTY:
                    warning_text = self.tr(
                        "Mod directory was not empty. Please close all programs accessing files or subfolders in the directory (including your file manager) and try again."
                    )
                else:
                    warning_text = self.tr("An OSError occurred while deleting mod.")

                logger.warning(
                    f"Unable to delete mod located at the path: {mod_metadata['path']}"
                )
                show_warning(
                    title=self.tr("Unable to delete mod"),
                    text=warning_text,
                    information=self.tr(
                        "{e.strerror} occurred at {e.filename} with error code {error_code}."
                    ).format(e=e, error_code=error_code),
                )
            return False

        uuids = self.get_selected_mod_metadata()
        answer = show_dialogue_conditional(
            title=self.tr("Are you sure?"),
            text=self.tr("You have selected {len} mods for deletion.").format(
                len=len(uuids)
            ),
            information=self.tr(
                "\nThis operation delete a mod's directory from the filesystem."
                + "\nDo you want to proceed?"
            ),
        )
        if answer == "&Yes":
            self._iterate_mods(_inner_delete_both, uuids)

    def delete_dds(self) -> None:
        mod_metadata = self.get_selected_mod_metadata()
        answer = show_dialogue_conditional(
            title=self.tr("Are you sure?"),
            text=self.tr(
                "You have selected {len} mods to Delete optimized textures (.dds files only)"
            ).format(len=len(mod_metadata)),
            information=self.tr(
                "\nThis operation will only delete optimized textures (.dds files only) from mod files."
                + "\nDo you want to proceed?"
            ),
        )
        if answer == "&Yes":
            self._iterate_mods(
                lambda mod_metadata: (
                    delete_files_only_extension(
                        directory=str(mod_metadata["path"]),
                        extension=".dds",
                    )
                ),
                mod_metadata,
            )

    def delete_mod_keep_dds(self) -> None:
        mod_metadata = self.get_selected_mod_metadata()
        answer = show_dialogue_conditional(
            title=self.tr("Are you sure?"),
            text=self.tr("You have selected {len} mods for deletion.").format(
                len=len(mod_metadata)
            ),
            information=self.tr(
                "\nThis operation will recursively delete all mod files, except for .dds textures found."
                + "\nDo you want to proceed?"
            ),
        )
        if answer == "&Yes":
            self._iterate_mods(
                lambda mod_metadata: delete_files_except_extension(
                    directory=mod_metadata["path"],
                    extension=".dds",
                ),
                mod_metadata,
            )

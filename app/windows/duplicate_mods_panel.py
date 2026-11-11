from loguru import logger

from app.controllers.metadata_controller import MetadataController
from app.utils.button_factory import ButtonConfig, ButtonType
from app.utils.mod_info import ModInfo
from app.windows.base_mods_panel import (
    BaseModsPanel,
)


def filter_ignored_duplicates(
    duplicate_mods: dict[str, list[str]],
    ignored: dict[str, list[str]],
) -> dict[str, list[str]]:
    """
    Remove duplicate groups the user ignored, unless their paths have changed.

    :param duplicate_mods: Package ID mapped to the paths of its copies.
    :param ignored: Lowercased package ID mapped to the sorted paths seen when
        the user ignored it.
    :return: A new dict with only the groups that should still be shown.
    """
    visible: dict[str, list[str]] = {}
    for packageid, paths in duplicate_mods.items():
        if ignored.get(packageid.lower()) == sorted(paths):
            logger.info(f"Ignoring duplicate mods for package ID: {packageid}")
            continue
        visible[packageid] = paths
    return visible


class DuplicateModsPanel(BaseModsPanel):
    """
    A panel used when duplicate mods are detected, allowing users to choose which version to keep.

    This panel displays duplicate mods grouped by their package ID, showing detailed
    information for each mod version. Users can select which versions to keep and
    use the deletion menu to remove unwanted duplicates.

    Attributes:
        duplicate_mods (dict[str, list[str]]): Dictionary mapping package IDs to lists of UUIDs
            of duplicate mods.
        metadata_controller: MetadataController instance from base class for accessing mod data.
    """

    def __init__(
        self,
        duplicate_mods: dict[str, list[str]],
        metadata_controller: MetadataController,
    ) -> None:
        """
        Initialize the DuplicateModsPanel with duplicate mods data.

        Args:
            duplicate_mods: Dictionary mapping package IDs to lists of UUIDs of duplicate mods.
        """
        logger.debug("Initializing DuplicateModsPanel")
        self.duplicate_mods = dict(duplicate_mods)

        super().__init__(
            object_name="duplicateModsPanel",
            window_title=self.tr("RimSort - Duplicate Mods Found"),
            title_text=self.tr("Duplicate mods detected!"),
            details_text=self.tr(
                "\nThe following table displays duplicate mods grouped by package ID. "
                "Select which versions to keep and choose an action."
            ),
            additional_columns=self._get_standard_mod_columns(),
            metadata_controller=metadata_controller,
        )

        button_configs = self._get_base_button_configs()
        self._extend_button_configs_with_steam_actions(button_configs)
        button_configs.append(
            ButtonConfig(
                button_type=ButtonType.CUSTOM,
                text=self.tr("Ignore Selected"),
                custom_callback=self._ignore_selected,
            )
        )
        button_configs.append(
            self._create_delete_button_config(self.tr("Delete Selected Mods"))
        )
        self._setup_buttons_from_config(button_configs)

        # Populate the table with duplicate mod data
        self._populate_from_metadata()
        # Sorting is disabled by default in _setup_table_and_model

        # TODO: let user configure window launch state and size from settings controller
        self.showNormal()

    def _ignore_selected(self) -> None:
        """
        Stop warning about the package IDs of the checked rows.

        The whole package ID group is ignored, even if only one row is checked.
        The warning comes back when the copies of that package ID change.
        """
        selected_paths = {
            path
            for row in self._get_selected_row_indices()
            if (path := self._get_key_from_row(row)) is not None
        }
        packageids = [
            packageid
            for packageid, paths in self.duplicate_mods.items()
            if selected_paths.intersection(paths)
        ]
        if not packageids:
            logger.info("Ignore requested with no duplicate mods selected")
            return

        for packageid in packageids:
            self.settings.ignored_duplicate_mods[packageid.lower()] = sorted(
                self.duplicate_mods.pop(packageid)
            )
        self.settings.save()
        logger.info(f"Ignored duplicate mods for package IDs: {packageids}")

        if self.duplicate_mods:
            self._populate_from_metadata()
        else:
            self.close()

    def _populate_from_metadata(self) -> None:
        """
        Populate the table with duplicate mod data.
        """
        try:
            self._clear_table_model()

            for packageid, paths in self.duplicate_mods.items():
                # Add group header
                self._add_group_header_row(packageid)

                for path in paths:
                    mod = self.metadata_controller.get_mod(path)
                    if mod is not None:
                        mod_info = ModInfo.from_listed_mod(mod)
                        mod_info.key = path
                        self._add_mod_row(mod_info)
                    else:
                        logger.warning(
                            f"Metadata not found for path: {path} in package group {packageid}"
                        )
        except Exception as e:
            logger.error(f"Error populating table from metadata: {e}")

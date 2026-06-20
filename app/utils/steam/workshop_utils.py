# TODO(debt): check_if_pfids_blacklisted and import_steamcmd_acf_data use GUI
# dialogs (show_warning, show_dialogue_conditional, show_dialogue_file). This
# creates a utils→views layer violation. Ideally these functions should accept
# callbacks or live in the views layer. Inherited from the old metadata.py.
import os
from dataclasses import dataclass
from typing import Any, Literal

from loguru import logger
from PySide6.QtCore import QCoreApplication

from app.models.metadata.metadata_structure import AboutXmlMod, ModType
from app.utils.dict_utils import recursively_update_dict
from app.utils.steam.steamfiles.wrapper import acf_to_dict, dict_to_acf
from app.utils.steam.webapi.wrapper import (
    ISteamRemoteStorage_GetPublishedFileDetails,
)
from app.views.dialogue import (
    show_dialogue_conditional,
    show_dialogue_file,
    show_warning,
)


@dataclass
class WorkshopUpdateResult:
    """Result of a workshop mod update check.

    :param status: Outcome — success, no_workshop_mods, partial, or failed
    :param mods_checked: Number of workshop mod pfids we attempted to query
    :param mods_updated: Number of mods that received update metadata
    :param failed_pfids: PublishedFileIds that could not be queried
    :param errors: Human-readable error descriptions for each failure
    """

    status: Literal["success", "no_workshop_mods", "partial", "failed"]
    mods_checked: int
    mods_updated: int
    failed_pfids: list[str]
    errors: list[str]


def check_if_pfids_blacklisted(
    publishedfileids: list[str], steamdb: dict[str, Any]
) -> list[str]:
    """Filter out blacklisted mods from a list of published file IDs.

    :param publishedfileids: List of Steam Workshop published file IDs
    :param steamdb: SteamDbSchema.database dict (str → SteamDbEntry)
    :return: Filtered list of published file IDs
    """
    if not steamdb:
        show_warning(
            title="No SteamDB found",
            text="Unable to check for blacklisted mods. Please configure a SteamDB for RimSort to use in Settings.",
        )
        return publishedfileids

    blacklisted_mods: dict[str, dict[str, str]] = {}
    for publishedfileid in publishedfileids:
        entry = steamdb.get(publishedfileid) or steamdb.get(str(publishedfileid))
        if entry is None:
            continue
        blacklist = getattr(entry, "blacklist", None)
        if blacklist and getattr(blacklist, "value", False):
            blacklisted_mods[publishedfileid] = {
                "name": getattr(entry, "steamName", ""),
                "comment": getattr(blacklist, "comment", ""),
            }

    if blacklisted_mods:
        blacklisted_mods_report = ""
        for pfid, info in blacklisted_mods.items():
            blacklisted_mods_report += f"{info['name']} ({pfid})\n"
            blacklisted_mods_report += f"Reason for blacklisting: {info['comment']}"
        answer = show_dialogue_conditional(
            title="Blacklisted mods found",
            text="Some mods are blacklisted in your SteamDB",
            information="Are you sure you want to download these mods? These mods are known mods that are recommended to be avoided.",
            details=blacklisted_mods_report,
            button_text_override=[
                QCoreApplication.translate(
                    "check_if_pfids_blacklisted", "Download blacklisted mods"
                ),
                QCoreApplication.translate(
                    "check_if_pfids_blacklisted", "Skip blacklisted mods"
                ),
            ],
        )
        answer_str = str(answer)
        skip_text = QCoreApplication.translate(
            "check_if_pfids_blacklisted", "Skip blacklisted mods"
        )
        if skip_text in answer_str:
            for pfid in blacklisted_mods:
                if pfid in publishedfileids:
                    publishedfileids.remove(pfid)
                    logger.debug(
                        f"Skipping download of blacklisted Workshop mod: {pfid}"
                    )

    return publishedfileids


def import_steamcmd_acf_data(
    rimsort_storage_path: str, steamcmd_appworkshop_acf_path: str
) -> None:
    logger.info(f"SteamCMD acf data path to update: {steamcmd_appworkshop_acf_path}")
    if os.path.exists(steamcmd_appworkshop_acf_path):
        logger.debug("Reading info...")
        steamcmd_appworkshop_acf = acf_to_dict(steamcmd_appworkshop_acf_path)
        logger.debug("Retrieved SteamCMD data to update...")
    else:
        logger.warning("Specified SteamCMD acf file not found! Nothing was done...")
        return
    logger.info("Opening file dialog to specify acf file to import")
    acf_to_import_path = show_dialogue_file(
        mode="open",
        caption="Input appworkshop_294100.acf from another SteamCMD prefix",
        _dir=rimsort_storage_path,
        _filter="ACF (*.acf)",
    )
    logger.info(f"SteamCMD acf data path to import: {acf_to_import_path}")
    if acf_to_import_path and os.path.exists(acf_to_import_path):
        logger.debug("Reading info...")
        acf_to_import = acf_to_dict(acf_to_import_path)
        logger.debug("Retrieved SteamCMD data to import...")
    else:
        logger.warning("Specified SteamCMD acf file not found! Nothing was done...")
        return
    # Output
    items_installed_before = len(
        steamcmd_appworkshop_acf["AppWorkshop"]["WorkshopItemsInstalled"].keys()
    )
    logger.debug(f"WorkshopItemsInstalled beforehand: {items_installed_before}")
    item_details_before = len(
        steamcmd_appworkshop_acf["AppWorkshop"]["WorkshopItemDetails"].keys()
    )
    logger.debug(f"WorkshopItemDetails beforehand: {item_details_before}")
    recursively_update_dict(
        steamcmd_appworkshop_acf["AppWorkshop"]["WorkshopItemsInstalled"],
        acf_to_import["AppWorkshop"]["WorkshopItemsInstalled"],
    )
    recursively_update_dict(
        steamcmd_appworkshop_acf["AppWorkshop"]["WorkshopItemDetails"],
        acf_to_import["AppWorkshop"]["WorkshopItemDetails"],
    )
    items_installed_after = len(
        steamcmd_appworkshop_acf["AppWorkshop"]["WorkshopItemsInstalled"].keys()
    )
    logger.debug(f"WorkshopItemsInstalled after: {items_installed_after}")
    item_details_after = len(
        steamcmd_appworkshop_acf["AppWorkshop"]["WorkshopItemDetails"].keys()
    )
    logger.debug(f"WorkshopItemDetails after: {item_details_after}")
    logger.info("Successfully imported data!")
    logger.info(f"Writing updated data back to path: {steamcmd_appworkshop_acf_path}")
    dict_to_acf(data=steamcmd_appworkshop_acf, path=steamcmd_appworkshop_acf_path)


def query_workshop_update_data(
    mods: dict[str, Any],
    metadata_controller: Any = None,
) -> WorkshopUpdateResult:
    """Query Steam WebAPI for update data for workshop/steamcmd mods.

    Populates aux DB entries with ``external_time_created`` and
    ``external_time_updated`` fields from the Steam API response.

    :param mods: Dict of mod metadata keyed by path
    :param metadata_controller: MetadataController instance for writing timestamps to aux DB
    :return: WorkshopUpdateResult describing what happened
    """
    logger.info("Querying Steam WebAPI for SteamCMD/Steam mod update metadata")

    workshop_mods_pfid_to_path: dict[str, str] = {}
    for path, mod in mods.items():
        if not isinstance(mod, AboutXmlMod):
            continue
        if mod.mod_type not in (ModType.STEAM_WORKSHOP, ModType.STEAM_CMD):
            continue
        pfid = mod.published_file_id
        if pfid:
            workshop_mods_pfid_to_path[pfid] = path

    if not workshop_mods_pfid_to_path:
        logger.info("No Workshop/SteamCMD mods found — skipping update check")
        return WorkshopUpdateResult(
            status="no_workshop_mods",
            mods_checked=0,
            mods_updated=0,
            failed_pfids=[],
            errors=[],
        )

    pfid_list = list(workshop_mods_pfid_to_path.keys())
    mods_checked = len(pfid_list)

    metadata_list, failed_pfids, errors = ISteamRemoteStorage_GetPublishedFileDetails(
        pfid_list
    )

    mods_updated = 0
    for workshop_mod_metadata in metadata_list:
        pfid = workshop_mod_metadata.get("publishedfileid")
        if pfid is None or pfid not in workshop_mods_pfid_to_path:
            continue
        mod_path = workshop_mods_pfid_to_path[pfid]
        time_created = workshop_mod_metadata.get("time_created")
        time_updated = workshop_mod_metadata.get("time_updated")
        if metadata_controller is not None and (time_created or time_updated):
            metadata_controller.update_workshop_timestamps(
                mod_path, time_created, time_updated
            )
        mods_updated += 1

    status: Literal["success", "no_workshop_mods", "partial", "failed"]
    if failed_pfids and mods_updated > 0:
        status = "partial"
    elif failed_pfids:
        status = "failed"
    else:
        status = "success"

    logger.info(
        f"Workshop update check complete: {mods_updated}/{mods_checked} mods updated"
        + (f", {len(failed_pfids)} failed" if failed_pfids else "")
    )
    return WorkshopUpdateResult(
        status=status,
        mods_checked=mods_checked,
        mods_updated=mods_updated,
        failed_pfids=failed_pfids,
        errors=errors,
    )

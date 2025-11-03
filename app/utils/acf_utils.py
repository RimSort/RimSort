"""
ACF Utilities Module

This module provides utility functions for handling ACF (AppWorkshop ACF) data,
which contains Steam Workshop item metadata including timestamps and other
information about installed workshop items.
"""

from typing import Dict

from app.utils.metadata import MetadataManager


def load_acf_data(mm: MetadataManager) -> Dict[str, int]:
    """
    Load ACF data to get timeupdated timestamps for mods from MetadataManager.

    This function refreshes ACF metadata and builds a dictionary mapping
    PublishedFileID to ACF timeupdated timestamps from both SteamCMD and
    Workshop ACF data sources.

    Args:
        mm (MetadataManager): Instance of MetadataManager to access ACF data.

    Returns:
        Dict[str, int]: Dictionary mapping PublishedFileID strings to timeupdated timestamps.
    """
    # Ensure ACF data is loaded
    mm.refresh_acf_metadata()

    # Directly build timeupdated_data from merged ACF sources
    timeupdated_data: Dict[str, int] = {}
    for acf_data in [mm.steamcmd_acf_data, mm.workshop_acf_data]:
        if acf_data:
            workshop_items = acf_data.get("AppWorkshop", {}).get(
                "WorkshopItemsInstalled", {}
            )
            for pfid, item in workshop_items.items():
                if isinstance(item, dict) and "timeupdated" in item:
                    timeupdated_data[str(pfid)] = item["timeupdated"]

    return timeupdated_data

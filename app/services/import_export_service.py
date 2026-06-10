"""Service for import/export operations on RimWorld mod lists."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from loguru import logger

from app.controllers.settings_controller import SettingsController
from app.models.divider import is_divider_uuid
from app.utils.app_info import AppInfo
from app.utils.metadata import MetadataManager
from app.utils.rentry.wrapper import RentryUpload
from app.utils.schema import generate_rimworld_mods_list
from app.utils.steam.webapi.wrapper import (
    ISteamRemoteStorage_GetPublishedFileDetails,
)
from app.utils.xml import json_to_xml_write


@dataclass
class ExportData:
    """Collected data from an active mod list widget ready for export."""

    active_mods: list[str] = field(default_factory=list)
    packageid_to_uuid: dict[str, str] = field(default_factory=dict)
    steam_packageid_to_pfid: dict[str, str] = field(default_factory=dict)
    pfid_to_preview_url: dict[str, str] = field(default_factory=dict)
    pfids: list[str] = field(default_factory=list)


class ImportExportService:
    """Business logic for import/export operations on mod lists.

    Handles data transformation (collecting mods, building reports,
    writing XML) while leaving UI interactions (file dialogs,
    clipboard access, notifications) to the view layer.
    """

    def __init__(
        self,
        metadata_manager: MetadataManager,
        settings_controller: SettingsController,
    ) -> None:
        self.metadata_manager = metadata_manager
        self.settings_controller = settings_controller

    def collect_active_mods(
        self,
        uuids: list[str],
        duplicate_mods: dict[str, Any] | None = None,
    ) -> ExportData:
        """Iterate list widget UUIDs and build all export data structures.

        :param uuids: UUIDs from a mod list widget
        :param duplicate_mods: dict of package_id -> list[uuid] for duplicates
        :return: ExportData with all collected structures
        """
        data = ExportData()
        seen: set[str] = set()

        for uuid in uuids:
            if is_divider_uuid(uuid):
                continue

            mod = self.metadata_manager.internal_local_metadata.get(uuid)
            if mod is None:
                continue

            package_id = mod["packageid"]
            if package_id in seen:
                logger.critical(
                    f"Tried to export more than 1 identical package ids to the same mod list. "
                    f"Skipping duplicate {package_id}"
                )
                continue

            seen.add(package_id)

            if duplicate_mods and package_id in duplicate_mods:
                if mod.get("data_source") == "workshop":
                    data.active_mods.append(package_id + "_steam")
                    continue

            data.active_mods.append(package_id)
            data.packageid_to_uuid[package_id] = uuid

            if mod.get("steamcmd") or mod.get("data_source") == "workshop":
                publishedfileid = mod.get("publishedfileid")
                if publishedfileid:
                    data.steam_packageid_to_pfid[package_id] = publishedfileid
                    data.pfids.append(publishedfileid)

        return data

    def fetch_steam_preview_urls(self, pfids: list[str]) -> dict[str, str]:
        """Fetch Steam Workshop preview image URLs for published file IDs.

        :param pfids: list of PublishedFileId strings
        :return: dict mapping pfid -> preview_url
        """
        pfid_to_preview_url: dict[str, str] = {}
        if not pfids:
            return pfid_to_preview_url

        webapi_response = ISteamRemoteStorage_GetPublishedFileDetails(pfids)
        if webapi_response is not None:
            for metadata_entry in webapi_response:
                pfid = metadata_entry["publishedfileid"]
                if metadata_entry["result"] != 1:
                    logger.warning(
                        f"Rentry.co export: Unable to get data for mod {pfid}"
                    )
                else:
                    pfid_to_preview_url[pfid] = metadata_entry["preview_url"]
        return pfid_to_preview_url

    def export_to_xml(self, active_mods: list[str], file_path: str) -> None:
        """Write mod list to ModsConfig.xml format.

        :param active_mods: list of package IDs
        :param file_path: destination file path
        :raises Exception: on write failure
        """
        mods_config_data = generate_rimworld_mods_list(
            self.metadata_manager.game_version, active_mods
        )
        target = file_path if file_path.endswith(".xml") else file_path + ".xml"
        json_to_xml_write(mods_config_data, target)

    def build_clipboard_report(
        self,
        active_mods: list[str],
        packageid_to_uuid: dict[str, str],
    ) -> str:
        """Build a human-readable clipboard report of active mods.

        :param active_mods: list of package IDs
        :param packageid_to_uuid: mapping from package ID to internal UUID
        :return: formatted report string
        """
        report = (
            f"Created with RimSort {AppInfo().app_version}"
            f"\nRimWorld game version this list was created for: "
            f"{self.metadata_manager.game_version}"
            f"\nTotal # of mods: {len(active_mods)}\n"
        )
        for package_id in active_mods:
            uuid = packageid_to_uuid.get(package_id)
            if uuid is None:
                continue
            mod = self.metadata_manager.internal_local_metadata.get(uuid, {})
            name = mod.get("name", "No name specified")
            url = mod.get("url") or mod.get("steam_url") or "No url specified"
            report += f"\n{name} [{package_id}][{url}]"
        return report

    def build_rentry_report(
        self,
        mods: list[str],
        packageid_to_uuid: dict[str, str],
        steam_packageid_to_pfid: dict[str, str],
        pfid_to_preview_url: dict[str, str],
        truncated: bool = False,
    ) -> str:
        """Build a Rentry.co formatted markdown report.

        :param mods: list of package IDs (may be truncated)
        :param packageid_to_uuid: mapping from package ID to internal UUID
        :param steam_packageid_to_pfid: mapping from package ID to PublishedFileId
        :param pfid_to_preview_url: mapping from PublishedFileId to preview URL
        :param truncated: whether the mod list has been truncated
        :return: Rentry markdown string
        """
        truncated_note = " (truncated)" if truncated else ""
        report = (
            "# RimWorld mod list       "
            "![](https://github.com/RimSort/RimSort/blob/main/docs/rentry_preview.png?raw=true)"
            f"\nCreated with RimSort {AppInfo().app_version}"
            f"\nMod list was created for game version: `{self.metadata_manager.game_version}`"
            "\n!!! info Local mods are marked as yellow labels with packageid in brackets."
            f"\n\n\n\n!!! note Mod list length: `{len(mods)}`{truncated_note}\n"
        )
        for package_id in mods:
            count = mods.index(package_id) + 1
            uuid = packageid_to_uuid.get(package_id)
            if uuid is None:
                continue
            mod = self.metadata_manager.internal_local_metadata.get(uuid, {})
            name = mod.get("name", "No name specified")
            is_steam_mod = (
                mod.get("steamcmd") or mod.get("data_source") == "workshop"
            ) and steam_packageid_to_pfid.get(package_id)

            if is_steam_mod:
                pfid = steam_packageid_to_pfid[package_id]
                if pfid_to_preview_url.get(pfid):
                    preview_url = (
                        pfid_to_preview_url[pfid]
                        + "?imw=100&imh=100&impolicy=Letterbox"
                    )
                else:
                    preview_url = "https://github.com/RimSort/RimSort/blob/main/docs/rentry_steam_icon.png?raw=true"
                url = mod.get("steam_url") or mod.get("url")
                if url:
                    report += (
                        f"\n{count}. ![]({preview_url}) "
                        f"[{name}]({url} packageid: {package_id})"
                    )
                else:
                    report += (
                        f"\n{count}. ![]({preview_url}) {name} packageid: {package_id}"
                    )
            else:
                url = mod.get("url") or mod.get("steam_url")
                if url:
                    report += (
                        f"\n!!! warning {count}. [{name}]({url}) "
                        f"{{packageid: {package_id}}} "
                    )
                else:
                    report += (
                        f"\n!!! warning {count}. {name} {{packageid: {package_id}}} "
                    )
        return report

    def calculate_rentry_max_mods(
        self,
        mods: list[str],
        packageid_to_uuid: dict[str, str],
        steam_packageid_to_pfid: dict[str, str],
        pfid_to_preview_url: dict[str, str],
        max_chars: int = 200000,
    ) -> int:
        """Calculate the maximum number of mods that fit within Rentry's limit.

        :return: max mods count, or 0 if even the first mod exceeds the limit
        """
        max_mods = 0
        for i in range(1, len(mods) + 1):
            test_mods = mods[:i]
            test_report = self.build_rentry_report(
                test_mods,
                packageid_to_uuid,
                steam_packageid_to_pfid,
                pfid_to_preview_url,
                truncated=True,
            )
            if len(test_report) > max_chars:
                break
            max_mods = i
        return max_mods

    def upload_rentry_report(self, report: str) -> tuple[bool, str | None]:
        """Upload report to Rentry.co.

        :return: (success, url_accessible_via_browser_or_None)
        """
        uploader = RentryUpload(report)
        if uploader.upload_success and uploader.url:
            host = urlparse(uploader.url).hostname
            if host and host.endswith("rentry.co"):
                return True, uploader.url
        return False, None

    def save_to_mods_config(self, active_mods: list[str]) -> str:
        """Save active mods to the instance's ModsConfig.xml.

        :param active_mods: list of package IDs (with _steam suffixes as needed)
        :return: the path to the saved file
        :raises Exception: on write failure
        """
        current_instance = self.settings_controller.settings.current_instance
        config_folder = self.settings_controller.settings.instances[
            current_instance
        ].config_folder
        mods_config_path = str(Path(config_folder) / "ModsConfig.xml")

        mods_config_data = generate_rimworld_mods_list(
            self.metadata_manager.game_version, active_mods
        )
        json_to_xml_write(mods_config_data, mods_config_path)
        return mods_config_path

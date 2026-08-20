"""Parse RimWorld and RimSort mod list files."""

from dataclasses import dataclass
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Literal

from loguru import logger

from app.models.metadata.metadata_factory import value_extractor
from app.utils.schema import validate_rimworld_mods_list
from app.utils.xml import xml_path_to_json

SourceFormat = Literal["mods_config_xml", "rimsort_json", "rml", "rws", "savegame"]


class ModListFormatError(Exception):
    """Raised when a mod list file cannot be parsed."""


@dataclass
class ParsedModList:
    package_ids: list[str]
    game_version: str | None
    known_expansions: list[str]
    source_format: SourceFormat


def _normalize_package_ids(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, dict):
        if "li" in raw:
            return _normalize_package_ids(raw["li"])
        if not raw:
            return []
    if isinstance(raw, list):
        result: list[str] = []
        for item in raw:
            extracted = value_extractor(item)
            if isinstance(extracted, str):
                result.append(extracted)
            elif isinstance(extracted, list):
                result.extend(str(v) for v in extracted if v)
        return result
    extracted = value_extractor(raw)
    if isinstance(extracted, str):
        return [extracted]
    if isinstance(extracted, list):
        return [str(v) for v in extracted if v]
    raise ModListFormatError("Could not normalize active mod list entries")


def _detect_source_format(path: Path, data: dict[str, Any]) -> SourceFormat:
    suffix = path.suffix.lower()
    if suffix == ".rws":
        return "rws"
    if suffix == ".rml":
        return "rml"
    if "savegame" in data:
        return "savegame"
    if "ModsConfigData" in data:
        return "mods_config_xml"
    return "mods_config_xml"


def _parse_json_mod_list(data: dict[str, Any]) -> ParsedModList:
    if not all(key in data for key in ("version", "activeMods")):
        raise ModListFormatError(
            "JSON mod list must contain 'version' and 'activeMods' keys"
        )
    version = data.get("version")
    if version is not None and not isinstance(version, str):
        logger.warning(f"Unexpected mod list version type: {type(version)}")
    known = data.get("knownExpansions", [])
    if not isinstance(known, list):
        known = _normalize_package_ids(known)
    return ParsedModList(
        package_ids=_normalize_package_ids(data["activeMods"]),
        game_version=str(version) if version is not None else None,
        known_expansions=[str(x) for x in known],
        source_format="rimsort_json",
    )


def _parse_xml_mod_list(path: Path, data: dict[str, Any]) -> ParsedModList:
    source_format = _detect_source_format(path, data)
    mods_config = data.get("ModsConfigData")
    if not isinstance(mods_config, dict):
        mods_config = {}

    raw_active = mods_config.get("activeMods")
    if not raw_active:
        package_ids: list[str] = []
    else:
        package_ids = validate_rimworld_mods_list(data)

    version: str | None = None
    raw_version = mods_config.get("version")
    if isinstance(raw_version, str):
        version = raw_version
    elif isinstance(raw_version, dict):
        version = str(value_extractor(raw_version))
    known_expansions = _normalize_package_ids(mods_config.get("knownExpansions"))
    return ParsedModList(
        package_ids=package_ids,
        game_version=version,
        known_expansions=known_expansions,
        source_format=source_format,
    )


def parse_mod_list_file(path: str | Path) -> ParsedModList:
    """Detect format and parse a mod list file."""
    file_path = Path(path)
    if not file_path.is_file():
        raise ModListFormatError(f"File not found: {file_path}")

    preview = file_path.read_text(encoding="utf-8-sig")[:4096].lstrip()
    if preview.startswith("{"):
        try:
            import json

            data = json.loads(file_path.read_text(encoding="utf-8-sig"))
        except JSONDecodeError as exc:
            raise ModListFormatError(f"Invalid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise ModListFormatError("JSON mod list must be an object")
        return _parse_json_mod_list(data)

    if preview.startswith("<?xml") or preview.startswith("<"):
        try:
            data = xml_path_to_json(str(file_path))
        except Exception as exc:
            raise ModListFormatError(f"Invalid XML: {exc}") from exc
        return _parse_xml_mod_list(file_path, data)

    raise ModListFormatError(
        "Unrecognized mod list format. Expected RimWorld ModsConfig XML or RimSort JSON."
    )


def parsed_to_mods_config_dict(parsed: ParsedModList) -> dict[str, Any]:
    """Convert a parsed mod list to the dict shape used by json_to_xml_write."""
    version = parsed.game_version or "1.4"
    return {
        "ModsConfigData": {
            "version": version,
            "activeMods": {"li": parsed.package_ids},
            "knownExpansions": {"li": parsed.known_expansions},
        }
    }

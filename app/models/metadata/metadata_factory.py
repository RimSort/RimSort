import itertools
import os
import re
import traceback
from functools import cache
from pathlib import Path
from typing import Any, Sequence

import msgspec
import pygit2
from loguru import logger

from app.models.metadata.metadata_structure import (
    AboutXmlMod,
    BaseRules,
    CaseInsensitiveSet,
    CaseInsensitiveStr,
    DependencyMod,
    ExternalRulesSchema,
    ListedMod,
    ModType,
    Rules,
    ScenarioMod,
)
from app.utils.constants import RIMWORLD_DLC_METADATA
from app.utils.xml import xml_path_to_json


class MalformedDataException(Exception):
    """
    Exception raised when the data given is detected to be malformed.
    """

    def __init__(self, message: str):
        super().__init__(message)
        self.message = f"Malformed data: {message}"


def value_extractor(
    input: dict[str, str] | dict[str, list[str]] | Sequence[str] | str,
) -> str | list[Any] | dict[str, str] | dict[str, list[str]]:
    """
    Extract the value from a mod_data entry.
    Stops at the outermost list or string.
    Stops if more than one key other than #text and @IgnoreIfNoMatchingField is found.

    :param input: The dictionary or string or list of strings to extract the value from.
    :return: The extracted value or the input string.
    :raises:

    """

    if isinstance(input, str):
        return input
    elif isinstance(input, Sequence):
        # Convert sequence to list
        return list(input)
    elif isinstance(input, dict):
        # If only one key, recurse into the value
        if len(input) == 1:
            return value_extractor(next(iter(input.values())))
        elif input.keys() == {"@IgnoreIfNoMatchingField", "#text"}:
            return input["#text"]
        else:
            return input


def match_version(
    input: dict[str, Any], target_version: str, stop_at_first: bool = False
) -> tuple[bool, None | list[Any]]:
    """Attempts to match an input key with the target version using regex.

    If the key is not found, the function returns None.
    If the matching key(s) is found, the function returns the value of the key(s) in a list.

    :param input: The dictionary to search for the key.
    :param target_version: The version to match. Should be of the format 'major.minor'.
    :param stop_at_first: If True, the function will return the first match found only."""
    major, minor = target_version.split(".")[:2]
    version_regex = rf"v{major}\.{minor}"

    results = []
    for key, value in input.items():
        if re.match(version_regex, key):
            if stop_at_first:
                return True, [value]
            results.append(value)

    if not results:
        return False, None

    return True, results


def create_scenario_mod(scenario_data: dict[str, Any]) -> tuple[bool, ScenarioMod]:
    mod = ScenarioMod()
    if "meta" in scenario_data:
        game_version = value_extractor(scenario_data["meta"].get("gameVersion", False))
        if isinstance(game_version, str):
            mod.supported_versions = {game_version}
        elif isinstance(game_version, list):
            mod.supported_versions = set(game_version)
    else:
        _set_mod_invalid(
            mod, "No metadata found for scenario. This scenario may be invalid."
        )
        return False, mod

    if "scenario" in scenario_data:
        scenario_data = scenario_data["scenario"]

        name = value_extractor(scenario_data.get("name", False))
        summary = value_extractor(scenario_data.get("summary", ""))
        description = value_extractor(scenario_data.get("description", ""))

        if isinstance(name, str):
            mod.name = name
        else:
            _set_mod_invalid(
                mod, "Couldn't parse a valid name. This scenario may be invalid."
            )

        if isinstance(summary, str):
            mod.summary = summary
        else:
            _set_mod_invalid(
                mod, "Summary parsed seems invalid. This scenario may be invalid."
            )

        if isinstance(description, str):
            mod.description = description
        else:
            _set_mod_invalid(
                mod, "Description parsed seems invalid. This scenario may be invalid."
            )
    else:
        _set_mod_invalid(mod, "No scenario data found. This scenario may be invalid.")
        return False, mod

    return mod.valid, mod


def create_about_mod(
    mod_data: dict[str, Any], target_version: str
) -> tuple[bool, AboutXmlMod]:
    """Factory method for creating a ListedMod object.

    :param mod_data: The dictionary containing the mod data.
    :param target_version: The version of RimWorld to target.
    :return: A tuple containing a boolean indicating if the mod is valid and the mod object."""
    mod = _parse_basic(mod_data, AboutXmlMod())

    if not isinstance(mod, AboutXmlMod):
        ruled_mod = AboutXmlMod()
        ruled_mod.__dict__ = mod.__dict__
        mod = ruled_mod

    mod = _parse_optional(mod_data, mod, target_version)

    return mod.valid, mod


def _set_mod_invalid(mod: ListedMod, message: str) -> ListedMod:
    """
    Set the mod to be invalid and log a warning message.

    :param mod: ListedMod to be set as valid False.
    :param message: The message to be logged as a warning
    :return: The ListedMod now set as invalid.
    """
    mod.valid = False
    logger.warning(message)
    return mod


def _parse_basic(mod_data: dict[str, Any], mod: AboutXmlMod) -> AboutXmlMod:
    """
    Parse the basic fields from the mod_data and set them on the mod object.
    If package_id cannot be parsed correctly, the mod is considered invalid.

    :param mod_data: Dictionary with string keys to be used as the data source.
    :param mod: ListedMod the Listed mod that is the target of data being filled.
    :return: The filled out ListedMod
    """
    package_id = value_extractor(mod_data.get("packageId", False))
    if isinstance(package_id, str):
        mod.package_id = CaseInsensitiveStr(package_id)
    else:
        _set_mod_invalid(
            mod,
            f"packageId was not a string: {package_id}. This mod will be considered invalid by RimWorld.",
        )

    # Prioritize app id from about.xml over hardcoded DLC app id
    steam_app_id = value_extractor(mod_data.get("steamAppId", False))
    if isinstance(steam_app_id, str) and steam_app_id.isdigit():
        mod.steam_app_id = int(steam_app_id)
    elif mod.package_id in get_dlc_packageid_appid_map():
        mod.steam_app_id = int(get_dlc_packageid_appid_map()[mod.package_id])

    name = value_extractor(mod_data.get("name", False))
    if isinstance(name, str):
        mod.name = name
    else:
        mod.name = mod.package_id

    description = value_extractor(mod_data.get("description", False))
    if isinstance(description, str):
        mod.description = description

    author = value_extractor(mod_data.get("author", False))
    authors = value_extractor(mod_data.get("authors", False))

    if isinstance(author, str):
        mod.authors.append(author)

    if authors:
        mod.authors.extend(authors)

    supported_versions = value_extractor(mod_data.get("supportedVersions", False))
    if isinstance(supported_versions, list):
        mod.supported_versions = set(supported_versions)
    elif isinstance(supported_versions, str):
        mod.supported_versions = {supported_versions}

    return mod


def _parse_optional(
    mod_data: dict[str, Any], mod: AboutXmlMod, target_version: str
) -> AboutXmlMod:
    """
    Parse the optional fields from the mod_data and set them on the mod object.
    """

    mod_version = value_extractor(mod_data.get("modVersion", False))
    if mod_version and isinstance(mod_version, str):
        mod.mod_version = mod_version

    mod_icon_path = value_extractor(mod_data.get("modIconPath", False))
    if mod_icon_path and isinstance(mod_icon_path, str):
        mod.mod_icon_path = Path(mod_icon_path)

    url = value_extractor(mod_data.get("url", False))
    if url and isinstance(url, str):
        mod.url = url

    mod.about_rules = create_base_rules(mod_data, target_version)

    descriptions_by_version = value_extractor(
        mod_data.get("descriptionsByVersion", False)
    )
    if isinstance(descriptions_by_version, dict):
        _, description = match_version(descriptions_by_version, target_version)
        if description and isinstance(description, str):
            mod.description = description

    return mod


def _set_mod_type(
    mod: ListedMod, local_path: Path, rimworld_path: Path, workshop_path: Path | None
) -> ListedMod:
    """
    Set the mod type based on the paths given.

    :param mod: The mod to set the type on.
    :param local_path: The path to the local mod.
    :param rimworld_path: The path to the RimWorld mods folder.
    :param workshop_path: The path to the workshop folder.
    :return: The mod with the type set.
    """
    if mod.mod_path is None:
        mod.mod_type = ModType.UNKNOWN
        return mod

    parent_path = mod.mod_path.parent
    rimworld_expansion_path = rimworld_path / Path("Data")
    if parent_path == rimworld_expansion_path:
        mod.mod_type = ModType.LUDEON
    elif parent_path == workshop_path:
        mod.mod_type = ModType.STEAM_WORKSHOP
    elif parent_path == local_path:
        try:
            repo = pygit2.discover_repository(str(mod.mod_path))

            if (
                repo is not None
                and Path(repo).exists()
                and Path(repo).parent == mod.mod_path
            ):
                mod.mod_type = ModType.GIT
                return mod
        except pygit2.GitError as e:
            logger.error(
                f"Encountered git error while trying to discover git repository at: {mod.mod_path}"
            )
            logger.error(e)

        if (parent_path / Path("About/PublishedFileId.txt")).exists():
            mod.mod_type = ModType.STEAM_WORKSHOP
        else:
            mod.mod_type = ModType.LOCAL

    return mod


def create_base_rules(
    mod_data: dict[str, Any], target_version: str
) -> BaseRules | Rules:
    rules = BaseRules()

    # Dependencies
    mod_dependencies = value_extractor(mod_data.get("modDependencies", []))
    mod_dependencies = (
        mod_dependencies if isinstance(mod_dependencies, list) else [mod_dependencies]
    )
    versioned_mod_dependencies = value_extractor(
        mod_data.get("modDependenciesByVersion", {})
    )

    if isinstance(versioned_mod_dependencies, dict):
        _, dependencies = match_version(versioned_mod_dependencies, target_version)
        if dependencies:
            mod_dependencies.extend(dependencies)

    for dependency in mod_dependencies:
        if isinstance(dependency, dict):
            dep = create_mod_dependency(dependency)

            if dep.package_id in rules.dependencies:
                logger.warning(
                    f"Duplicate dependency found: {dep.package_id}. Skipping."
                )
            else:
                rules.dependencies[dep.package_id] = dep
        else:
            logger.warning(
                f"Skipping invalid dependency: {dependency}. This mod may be invalid."
            )

    def load_operations(
        mod_data: dict[str, Any], key: str, force_key: str, target_version: str
    ) -> CaseInsensitiveSet:
        load = value_extractor(mod_data.get(key, []))
        load = load if isinstance(load, list) else [load]

        loadByVersion = value_extractor(mod_data.get(f"{key}ByVersion", {}))
        if isinstance(loadByVersion, dict):
            _, load_versioned = match_version(loadByVersion, target_version)
            if load_versioned:
                load.extend(load_versioned)

        forceLoad = value_extractor(mod_data.get(force_key, []))
        forceLoad = forceLoad if isinstance(forceLoad, list) else [forceLoad]
        load.extend(forceLoad)

        return CaseInsensitiveSet(load)

    # Load Before
    rules.load_before = load_operations(
        mod_data, "loadBefore", "forceLoadBefore", target_version
    )

    # Load After
    rules.load_after = load_operations(
        mod_data, "loadAfter", "forceLoadAfter", target_version
    )

    # incompatibleWith
    incompatible_with = value_extractor(mod_data.get("incompatibleWith", []))
    incompatible_with = (
        incompatible_with
        if isinstance(incompatible_with, list)
        else [incompatible_with]
    )

    incompatible_withByVersion = value_extractor(
        mod_data.get("incompatibleWithByVersion", {})
    )
    if isinstance(incompatible_withByVersion, dict):
        _, incompatibles = match_version(incompatible_withByVersion, target_version)
        if incompatibles:
            incompatible_with.extend(incompatibles)

    rules.incompatible_with = CaseInsensitiveSet(incompatible_with)

    return rules


def create_mod_dependency(input_dict: dict[str, str]) -> DependencyMod:
    """
    Create a DependencyMod object from the input dictionary.

    :param input_dict: The dictionary containing the mod data.
    :return: The DependencyMod object.
    """
    mod = DependencyMod()
    package_id = input_dict.get("packageId", False)
    if isinstance(package_id, str):
        mod.package_id = CaseInsensitiveStr(package_id)

    name = input_dict.get("displayName", False)
    if isinstance(name, str):
        mod.name = name

    workshop_url = input_dict.get("workshopUrl", False)
    if isinstance(workshop_url, str):
        mod.workshop_url = workshop_url

    return mod


def _create_about_mod_from_xml(
    base_path: Path, mod_xml_path: Path, target_version: str
) -> tuple[bool, AboutXmlMod]:
    try:
        mod_data = xml_path_to_json(str(mod_xml_path))
    except Exception:
        logger.error(
            f"Unable to parse {mod_xml_path} with the exception: {traceback.format_exc()}"
        )
        return False, AboutXmlMod(valid=False)

    mod_data = {k.lower(): v for k, v in mod_data.items()}
    mod_data = mod_data.get("modmetadata", {})

    if not mod_data:
        logger.error(f"Could not parse {mod_xml_path}.")
        return False, AboutXmlMod(valid=False)

    valid, mod = create_about_mod(mod_data, target_version)

    mod.mod_path = base_path
    return valid, mod


def _create_scenario_mod_from_rsc(
    base_path: Path, mod_rsc_path: Path
) -> tuple[bool, ScenarioMod]:
    try:
        mod_data = xml_path_to_json(str(mod_rsc_path))
    except Exception:
        logger.error(
            f"Unable to parse {mod_rsc_path} with the exception: {traceback.format_exc()}"
        )
        return False, ScenarioMod(valid=False)

    mod_data = {k.lower(): v for k, v in mod_data.items()}
    mod_data = mod_data.get("savedscenario", {})

    if not mod_data:
        logger.error(f"Could not parse {mod_rsc_path}.")
        return False, ScenarioMod(valid=False)

    valid, mod = create_scenario_mod(mod_data)

    mod.mod_path = base_path

    return valid, mod


def create_listed_mod_from_path(
    path: Path,
    target_version: str,
    local_path: Path,
    rimworld_path: Path,
    workshop_path: Path | None,
) -> tuple[bool, ListedMod]:
    # Check if path is a directory
    if path.is_dir():
        # Check if About.xml exists
        about_xml_path = path / Path("About/About.xml")
        if about_xml_path.exists():
            success, about_mod = _create_about_mod_from_xml(
                path, about_xml_path, target_version
            )
            return success, _set_mod_type(
                about_mod, local_path, rimworld_path, workshop_path
            )

        # Check for any file with .rsc extension
        generator = path.glob("*.rsc")
        gen, _ = itertools.tee(generator, 2)

        gen1 = next(gen, None)
        gen2 = next(gen, None)

        rsc_files = list(path.glob("*.rsc"))

        # Abort if multiple .rsc files are found
        if gen2 is not None:
            logger.warning(
                f"Multiple .rsc files found in {path}. Cannot determine which file to use. Aborting parse of directory."
            )
            return False, _set_mod_type(
                ListedMod(valid=False, _mod_path=path),
                local_path,
                rimworld_path,
                workshop_path,
            )
        elif gen1 is not None:
            success, scenario_mod = _create_scenario_mod_from_rsc(path, rsc_files[0])
            return success, _set_mod_type(
                scenario_mod, local_path, rimworld_path, workshop_path
            )

        logger.warning(f"No About.xml or .rsc file found in directory: {path}")
        return False, _set_mod_type(
            ListedMod(valid=False, _mod_path=path),
            local_path,
            rimworld_path,
            workshop_path,
        )

    raise ValueError("Path must be a directory.")


@cache
def get_dlc_packageid_appid_map() -> dict[str, str]:
    return {dlc["packageid"]: appid for appid, dlc in RIMWORLD_DLC_METADATA.items()}


def get_rules_db(
    path: Path,
) -> ExternalRulesSchema | None:
    logger.info(f"Checking Rules DB at: {path}")
    if os.path.exists(path):  # Look for cached data & load it if available
        logger.info(
            "DB exists!",
        )
        with open(path, encoding="utf-8") as f:
            json_string = f.read()
            logger.info("Reading info from rules DB")
            rule_data = msgspec.json.decode(json_string, type=ExternalRulesSchema)
            total_entries = len(rule_data.rules)
            logger.info(f"Loaded {total_entries} additional rules")
            return rule_data
    else:  # Assume db_data_missing
        logger.warning("Rules DB not found at specified path.")
        return None

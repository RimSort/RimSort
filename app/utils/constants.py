from enum import Enum
from typing import Any

# Instance constants
DEFAULT_INSTANCE_NAME = "Default"
INSTANCE_FOLDER_NAME = "instances"
STEAMCMD_FOLDER_NAME = "steamcmd"
STEAM_FOLDER_NAME = "steam"

# Steam App ID for RimWorld
RIMWORLD_STEAM_APP_ID = "294100"

# Default packageId for mods with missing or invalid packageId
DEFAULT_MISSING_PACKAGEID = "missing.packageid"


class SortMethod(str, Enum):
    ALPHABETICAL = "Alphabetical"
    TOPOLOGICAL = "Topological"


DB_BUILDER_PRUNE_EXCEPTIONS = [
    "database",
    "rules",
]
DB_BUILDER_PURGE_KEYS = ["external_time_created", "external_time_updated"]
DB_BUILDER_RECURSE_EXCEPTIONS = [
    "incompatibleWith",
    "loadBefore",
    "loadAfter",
    "loadTop",
    "loadBottom",
]
MOD_RECURSE_EXCEPTIONS = [
    "incompatiblewith",
    "loadafter",
    "loadbefore",
    "moddependencies",
]
DEFAULT_USER_RULES: dict[str, int | dict[str, Any]] = {"timestamp": 0, "rules": {}}
RIMWORLD_DLC_METADATA = {
    "294100": {
        "packageid": "ludeon.rimworld",
        "name": "RimWorld",
        "steam_url": "https://store.steampowered.com/app/294100/RimWorld",
        "description": "Base game",
    },
    "1149640": {
        "packageid": "ludeon.rimworld.royalty",
        "name": "RimWorld - Royalty",
        "steam_url": "https://store.steampowered.com/app/1149640/RimWorld__Royalty",
        "description": "DLC #1",
    },
    "1392840": {
        "packageid": "ludeon.rimworld.ideology",
        "name": "RimWorld - Ideology",
        "steam_url": "https://store.steampowered.com/app/1392840/RimWorld__Ideology",
        "description": "DLC #2",
    },
    "1826140": {
        "packageid": "ludeon.rimworld.biotech",
        "name": "RimWorld - Biotech",
        "steam_url": "https://store.steampowered.com/app/1826140/RimWorld__Biotech",
        "description": "DLC #3",
    },
    "2380740": {
        "packageid": "ludeon.rimworld.anomaly",
        "name": "RimWorld - Anomaly",
        "steam_url": "https://store.steampowered.com/app/2380740/RimWorld__Anomaly/",
        "description": "DLC #4",
    },
    "3022790": {
        "packageid": "ludeon.rimworld.odyssey",
        "name": "RimWorld - Odyssey",
        "steam_url": "https://store.steampowered.com/app/3022790/RimWorld__Odyssey/",
        "description": "DLC #5",
    },
}
RIMWORLD_PACKAGE_IDS = [v["packageid"] for v in RIMWORLD_DLC_METADATA.values()]
KNOWN_MOD_REPLACEMENTS = {
    "brrainz.harmony": {"zetrith.prepatcher", "jikulopo.prepatcher"},
    "aoba.motorization.engine": {"rimthunder.core"},
}
KNOWN_TIER_ZERO_MODS = {
    "zetrith.prepatcher",
    "brrainz.harmony",
    "brrainz.visualexceptions",
    "ludeon.rimworld",
    "ludeon.rimworld.royalty",
    "ludeon.rimworld.ideology",
    "ludeon.rimworld.biotech",
    "ludeon.rimworld.anomaly",
    "ludeon.rimworld.odyssey",
}
DATABASE_DISPLAY_NAMES: dict[str, str] = {
    "community_rules": "Community Rules",
    "steam_workshop": "Steam Workshop",
    "no_version_warning": "No Version Warning",
    "use_this_instead": "Use This Instead",
}

KNOWN_TIER_ONE_MODS = {
    "adaptive.storage.framework",
    "aoba.framework",
    "aoba.exosuit.framework",
    "ebsg.framework",
    "imranfish.xmlextensions",
    "thesepeople.ritualattachableoutcomes",
    "ohno.asf.ab.local",
    "oskarpotocki.vanillafactionsexpanded.core",
    "owlchemist.cherrypicker",
    "redmattis.betterprerequisites",
    "smashphil.vehicleframework",
    "unlimitedhugs.hugslib",
    "vanillaexpanded.backgrounds",
}

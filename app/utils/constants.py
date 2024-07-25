from enum import Enum
from typing import Any


class SortMethod(str, Enum):
    ALPHABETICAL = "Alphabetical"
    TOPOLOGICAL = "Topological"


DB_BUILDER_PRUNE_EXCEPTIONS = [
    "database",
    "rules",
]
DB_BUILDER_PURGE_KEYS = ["external_time_created", "external_time_updated"]
DB_BUILDER_RECURSE_EXCEPTIONS = [
    "dependencies",
    "loadBefore",
    "loadAfter",
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
}
RIMWORLD_PACKAGE_IDS = [v["packageid"] for v in RIMWORLD_DLC_METADATA.values()]
SEARCH_DATA_SOURCE_FILTER_INDEXES = [
    "all",
    "expansion",
    "local",
    "git_repo",
    "steamcmd",
    "workshop",
    "csharp",
    "xml",
]
KNOWN_MOD_REPLACEMENTS = {"brrainz.harmony": {"zetrith.prepatcher"}}

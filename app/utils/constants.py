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
DEFAULT_SETTINGS = {
    "check_for_update_startup": False,
    "show_folder_rows": True,
    "sorting_algorithm": "Alphabetical",
    "external_steam_metadata_file_path": "steamDB.json",
    "external_steam_metadata_repo": "https://github.com/RimSort/Steam-Workshop-Database",
    "external_steam_metadata_source": "None",
    "external_community_rules_file_path": "communityRules.json",
    "external_community_rules_repo": "https://github.com/RimSort/Community-Rules-Database",
    "external_community_rules_metadata_source": "None",
    "db_builder_include": "all_mods",
    "database_expiry": 604800,
    "build_steam_database_dlc_data": True,
    "build_steam_database_update_toggle": False,
    "watchdog_toggle": True,
    "mod_type_filter_toggle": True,
    "duplicate_mods_warning": False,
    "steam_mods_update_check": False,
    "try_download_missing_mods": False,
    "steamcmd_validate_downloads": True,
    "todds_preset": "optimized",
    "todds_active_mods_target": True,
    "todds_dry_run": False,
    "todds_overwrite": False,
    "current_instance": "Default",
    "instances": {
        "Default": {
            "game_folder": "",
            "config_folder": "",
            "local_folder": "",
            "workshop_folder": "",
            "run_args": [],
            "steamcmd_install_path": "",
        }
    },
}
DEFAULT_USER_RULES = {"timestamp": 0, "rules": {}}
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

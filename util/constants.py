DB_BUILDER_EXCEPTIONS = ["dependencies"]
DEFAULT_SETTINGS = {
    "sorting_algorithm": "RimPy",
    "external_steam_metadata_source": "None",
    "external_community_rules_metadata_source": "None",
    "database_expiry": 1814400,
    "db_builder_include": "all_mods",
    "build_steam_database_dlc_data": True,
    "build_steam_database_update_toggle": False,
    "watchdog_toggle": True,
    "duplicate_mods_warning": False,
    "steam_mods_update_check": False,
    "steamcmd_install_path": ".",
    "steamcmd_validate_downloads": True,
    "todds_preset": "medium",
    "todds_active_mods_target": True,
    "todds_dry_run": False,
    "todds_overwrite": False,
}
RIMWORLD_DLC_METADATA = {
    "294100": {
        "packageId": "ludeon.rimworld",
        "name": "RimWorld",
        "steam_url": "https://store.steampowered.com/app/294100/RimWorld",
        "description": "Base game",
    },
    "1149640": {
        "packageId": "ludeon.rimworld.royalty",
        "name": "RimWorld - Royalty",
        "steam_url": "https://store.steampowered.com/app/1149640/RimWorld__Royalty",
        "description": "DLC #1",
    },
    "1392840": {
        "packageId": "ludeon.rimworld.ideology",
        "name": "RimWorld - Ideology",
        "steam_url": "https://store.steampowered.com/app/1392840/RimWorld__Ideology",
        "description": "DLC #2",
    },
    "1826140": {
        "packageId": "ludeon.rimworld.biotech",
        "name": "RimWorld - Biotech",
        "steam_url": "https://store.steampowered.com/app/1826140/RimWorld__Biotech",
        "description": "DLC #3",
    },
}

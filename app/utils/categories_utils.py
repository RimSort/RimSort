from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypeIs

from loguru import logger

from app.utils.app_info import AppInfo

DEFAULT_CATEGORIES: dict[str, Any] = {
    "categories": [
        {
            "name": "Core",
            "color": "#3b82f6",
            "mods": ["RimWorld"],
        }
    ]
}


def get_categories_path(settings_categories_file: str) -> Path:
    """Resolve the categories file path: her shareable path, or the default
    location in app storage when unset."""
    if settings_categories_file:
        return Path(settings_categories_file)
    return AppInfo().app_storage_folder / "categories.json"


def _valid_categories(data: object) -> TypeIs[dict[str, Any]]:
    """The structure every consumer walks: a dict holding a list of
    categories, each with a string name, color, and member list."""
    if not isinstance(data, dict):
        return False
    categories = data.get("categories")
    if not isinstance(categories, list):
        return False
    for category in categories:
        if not (
            isinstance(category, dict)
            and isinstance(category.get("name"), str)
            and isinstance(category.get("color"), str)
            and isinstance(category.get("mods"), list)
        ):
            return False
    return True


def load_categories(settings_categories_file: str) -> dict[str, Any]:
    """Load the categories file, creating the default ("Core" holding
    RimWorld) on first use."""
    path = get_categories_path(settings_categories_file)
    if not path.exists():
        logger.info(f"Creating default categories file: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(DEFAULT_CATEGORIES, indent=4), encoding="utf-8")
        return DEFAULT_CATEGORIES
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Failed to read categories file {path}: {e}")
        return DEFAULT_CATEGORIES
    if not _valid_categories(data):
        # Any parseable-but-wrong file (a bare list, a category without
        # its keys) would crash the color resolver while lists populate
        logger.warning(f"Invalid categories structure in {path}; using defaults")
        return DEFAULT_CATEGORIES
    return data


def save_categories(settings_categories_file: str, data: dict[str, Any]) -> bool:
    """Persist the categories file (her shareable file)."""
    path = get_categories_path(settings_categories_file)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=4), encoding="utf-8")
        return True
    except OSError as e:
        logger.warning(f"Failed to write categories file {path}: {e}")
        return False

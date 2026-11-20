"""Tests for the categories file loading fallbacks.

load_categories runs during main window construction: a missing,
unreadable, or uncreatable file must fall back to the default
categories instead of raising.
"""

from __future__ import annotations

from pathlib import Path

from app.utils.categories_utils import DEFAULT_CATEGORIES, load_categories


class TestLoadCategories:
    def test_missing_file_is_created_with_defaults(self, tmp_path: Path) -> None:
        target = tmp_path / "sub" / "categories.json"
        loaded = load_categories(str(target))
        assert loaded == DEFAULT_CATEGORIES
        assert target.exists()

    def test_uncreatable_location_falls_back_to_defaults(self, tmp_path: Path) -> None:
        # A configured path whose parent cannot hold the default file
        # (here: the parent is a regular file) must not raise during
        # startup
        blocker = tmp_path / "blocker"
        blocker.write_text("not a directory", encoding="utf-8")
        loaded = load_categories(str(blocker / "categories.json"))
        assert loaded == DEFAULT_CATEGORIES

    def test_invalid_structure_falls_back_to_defaults(self, tmp_path: Path) -> None:
        target = tmp_path / "categories.json"
        target.write_text("[]", encoding="utf-8")
        assert load_categories(str(target)) == DEFAULT_CATEGORIES

    def test_valid_file_loads(self, tmp_path: Path) -> None:
        target = tmp_path / "categories.json"
        target.write_text(
            '{"categories": [{"name": "Core", "color": "#3b82f6",'
            ' "mods": ["RimWorld"]}]}',
            encoding="utf-8",
        )
        loaded = load_categories(str(target))
        assert loaded["categories"][0]["name"] == "Core"

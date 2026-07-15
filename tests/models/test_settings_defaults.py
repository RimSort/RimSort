"""Test Settings model default values for HTTP database syncing."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

if TYPE_CHECKING:
    from app.models.settings import Settings


@pytest.fixture
def settings() -> "Settings":
    """Create a Settings instance with mocked QApplication and AppInfo."""
    with (
        patch("app.models.settings.QApplication") as mock_qapp,
        patch("app.models.settings.AppInfo") as mock_app_info,
    ):
        mock_qapp.font.return_value.family.return_value = "monospace"
        mock_app_info.return_value.app_storage_folder = MagicMock()
        mock_app_info.return_value.app_settings_file = MagicMock()

        from app.models.settings import Settings

        return Settings()


@pytest.fixture
def settings_with_databases() -> "Settings":
    """Create a Settings instance with databases_folder mocked to a real path."""
    with (
        patch("app.models.settings.QApplication") as mock_qapp,
        patch("app.models.settings.AppInfo") as mock_app_info,
    ):
        mock_qapp.font.return_value.family.return_value = "monospace"
        databases = Path("/mock/databases")
        mock_app_info.return_value.databases_folder = databases
        mock_app_info.return_value.app_settings_file = MagicMock()

        from app.models.settings import Settings

        return Settings()


class TestSettingsURLDefaults:
    """Test that new Settings instances have correct HTTP URL defaults."""

    def test_new_install_defaults_to_configured_url(self, settings: "Settings") -> None:
        """New installs should default all database sources to 'Configured URL'."""
        assert settings.external_steam_metadata_source == "Configured URL"
        assert settings.external_community_rules_metadata_source == "Configured URL"
        assert settings.external_no_version_warning_metadata_source == "Configured URL"
        assert settings.external_use_this_instead_metadata_source == "Configured URL"

    def test_url_fields_have_github_archive_defaults(
        self, settings: "Settings"
    ) -> None:
        """URL fields should point to GitHub archive ZIP URLs by default."""
        assert (
            "github.com/RimSort/Steam-Workshop-Database"
            in settings.external_steam_metadata_url
        )
        assert "archive" in settings.external_steam_metadata_url
        assert (
            "github.com/RimSort/Community-Rules-Database"
            in settings.external_community_rules_url
        )
        assert (
            "github.com/emipa606/NoVersionWarning"
            in settings.external_no_version_warning_url
        )
        assert (
            "github.com/emipa606/UseThisInstead"
            in settings.external_use_this_instead_url
        )

    def test_git_repo_fields_still_exist(self, settings: "Settings") -> None:
        """Git repo fields must remain for backward compatibility."""
        assert hasattr(settings, "external_steam_metadata_repo")
        assert hasattr(settings, "external_community_rules_repo")
        assert hasattr(settings, "external_no_version_warning_repo_path")
        assert hasattr(settings, "external_use_this_instead_repo_path")


class TestRecentlyUpdatedIndicatorDefaults:
    """Test defaults for the recently-updated mods indicator feature."""

    def test_recently_updated_indicator_defaults(self, settings: "Settings") -> None:
        """The indicator is opt-in (off) with a 3-day threshold by default."""
        assert settings.mod_list_updated_indicator is False
        assert settings.mod_list_updated_threshold_days == 3


class TestRimWorldVersionsDefaults:
    """Test defaults for the new RimWorld Versions DB feature."""

    def test_rimworld_versions_source_defaults_to_configured_url(
        self, settings: "Settings"
    ) -> None:
        assert settings.external_rimworld_versions_metadata_source == "Configured URL"

    def test_rimworld_versions_url_defaults(self, settings: "Settings") -> None:
        assert (
            settings.external_rimworld_versions_url
            == "https://github.com/bukforks/rimworld-versions/archive/refs/heads/main.zip"
        )
        assert "archive" in settings.external_rimworld_versions_url

    def test_rimworld_versions_file_path_ends_in_json(
        self, settings_with_databases: "Settings"
    ) -> None:
        assert settings_with_databases.external_rimworld_versions_file_path.endswith(
            "rimworld_versions.json"
        )

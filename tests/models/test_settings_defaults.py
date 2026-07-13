"""Test Settings model default values for HTTP database syncing."""

from unittest.mock import MagicMock, patch


class TestSettingsURLDefaults:
    """Test that new Settings instances have correct HTTP URL defaults."""

    @patch("app.models.settings.QApplication")
    @patch("app.models.settings.AppInfo")
    def test_new_install_defaults_to_configured_url(
        self, mock_app_info: MagicMock, mock_qapp: MagicMock
    ) -> None:
        """New installs should default all database sources to 'Configured URL'."""
        mock_qapp.font.return_value.family.return_value = "monospace"
        mock_app_info.return_value.app_storage_folder = MagicMock()
        mock_app_info.return_value.app_settings_file = MagicMock()

        from app.models.settings import Settings

        settings = Settings()

        assert settings.external_steam_metadata_source == "Configured URL"
        assert settings.external_community_rules_metadata_source == "Configured URL"
        assert settings.external_no_version_warning_metadata_source == "Configured URL"
        assert settings.external_use_this_instead_metadata_source == "Configured URL"

    @patch("app.models.settings.QApplication")
    @patch("app.models.settings.AppInfo")
    def test_url_fields_have_github_archive_defaults(
        self, mock_app_info: MagicMock, mock_qapp: MagicMock
    ) -> None:
        """URL fields should point to GitHub archive ZIP URLs by default."""
        mock_qapp.font.return_value.family.return_value = "monospace"
        mock_app_info.return_value.app_storage_folder = MagicMock()
        mock_app_info.return_value.app_settings_file = MagicMock()

        from app.models.settings import Settings

        settings = Settings()

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

    @patch("app.models.settings.QApplication")
    @patch("app.models.settings.AppInfo")
    def test_git_repo_fields_still_exist(
        self, mock_app_info: MagicMock, mock_qapp: MagicMock
    ) -> None:
        """Git repo fields must remain for backward compatibility."""
        mock_qapp.font.return_value.family.return_value = "monospace"
        mock_app_info.return_value.app_storage_folder = MagicMock()
        mock_app_info.return_value.app_settings_file = MagicMock()

        from app.models.settings import Settings

        settings = Settings()

        assert hasattr(settings, "external_steam_metadata_repo")
        assert hasattr(settings, "external_community_rules_repo")
        assert hasattr(settings, "external_no_version_warning_repo_path")
        assert hasattr(settings, "external_use_this_instead_repo_path")


class TestRecentlyUpdatedIndicatorDefaults:
    """Test defaults for the recently-updated mods indicator feature."""

    @patch("app.models.settings.QApplication")
    @patch("app.models.settings.AppInfo")
    def test_recently_updated_indicator_defaults(
        self, mock_app_info: MagicMock, mock_qapp: MagicMock
    ) -> None:
        """The indicator is opt-in (off) with a 3-day threshold by default."""
        mock_qapp.font.return_value.family.return_value = "monospace"
        mock_app_info.return_value.app_storage_folder = MagicMock()
        mock_app_info.return_value.app_settings_file = MagicMock()

        from app.models.settings import Settings

        settings = Settings()

        assert settings.mod_list_updated_indicator is False
        assert settings.mod_list_updated_threshold_days == 3

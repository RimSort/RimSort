"""Tests for ExternalMetadataLoader source constants and path resolution."""

from unittest.mock import MagicMock

import pytest

from app.utils.external_metadata_loaders import (
    SOURCE_DISABLED,
    SOURCE_FILE_PATH,
    SOURCE_GIT_REPO,
    SOURCE_URL,
    ExternalMetadataLoader,
)


class TestSourceConstants:
    """Test that all source constants are defined and distinct."""

    def test_source_url_constant_exists(self) -> None:
        """SOURCE_URL constant should exist with expected value."""
        assert SOURCE_URL == "Configured URL"

    def test_all_source_constants_are_distinct(self) -> None:
        """All four source constants should be unique strings."""
        sources = {SOURCE_FILE_PATH, SOURCE_GIT_REPO, SOURCE_URL, SOURCE_DISABLED}
        assert len(sources) == 4, "Source constants must all be distinct"
        assert all(isinstance(s, str) for s in sources)


class TestLoadMetadataBySource:
    """Test _load_metadata_by_source path resolution for different sources."""

    @pytest.fixture
    def manager(self) -> MagicMock:
        """Create a mock manager with show_warning_signal."""
        manager = MagicMock()
        manager.show_warning_signal = MagicMock()
        return manager

    @pytest.fixture
    def loader(self, manager: MagicMock) -> ExternalMetadataLoader:
        """Create an ExternalMetadataLoader instance with mock manager."""
        return ExternalMetadataLoader(manager)

    def test_url_source_resolves_path_like_git_repo(
        self, loader: ExternalMetadataLoader
    ) -> None:
        """URL source should call getter with same path as git repo source."""
        getter = MagicMock(return_value=({"key": "value"}, "/some/path"))
        file_path = "/custom/file/path.json"
        repo_path = "https://github.com/example/repo.git"
        file_name = "steamDB.json"
        subdir = ""

        # Call with SOURCE_GIT_REPO
        result_git = loader._load_metadata_by_source(
            SOURCE_GIT_REPO, file_path, repo_path, file_name, getter, subdir
        )

        # Call with SOURCE_URL
        getter.reset_mock()
        result_url = loader._load_metadata_by_source(
            SOURCE_URL, file_path, repo_path, file_name, getter, subdir
        )

        # Both should call getter with the same constructed path
        assert result_git == result_url
        assert getter.call_count == 1
        # Verify getter was called with constructed repo path, not file_path
        called_path = getter.call_args[0][0]
        assert called_path != file_path
        assert file_name in called_path

    def test_disabled_source_returns_none(self, loader: ExternalMetadataLoader) -> None:
        """Disabled source should return (None, None) without calling getter."""
        getter = MagicMock()
        result = loader._load_metadata_by_source(
            SOURCE_DISABLED,
            "/some/path.json",
            "https://example.com/repo.git",
            "file.json",
            getter,
        )

        assert result == (None, None)
        getter.assert_not_called()

    def test_file_path_source_uses_file_path(
        self, loader: ExternalMetadataLoader
    ) -> None:
        """File path source should call getter with provided file_path."""
        getter = MagicMock(return_value=({"data": "test"}, "/file/path"))
        file_path = "/custom/file/path.json"
        repo_path = "https://github.com/example/repo.git"
        file_name = "steamDB.json"

        result = loader._load_metadata_by_source(
            SOURCE_FILE_PATH, file_path, repo_path, file_name, getter
        )

        getter.assert_called_once_with(file_path)
        assert result == ({"data": "test"}, "/file/path")


class TestLoadMetadataSourceDispatch:
    """Verify URL source uses repo path for directory derivation."""

    @pytest.fixture
    def manager(self) -> MagicMock:
        manager = MagicMock()
        manager.show_warning_signal = MagicMock()
        return manager

    @pytest.fixture
    def loader(self, manager: MagicMock) -> ExternalMetadataLoader:
        return ExternalMetadataLoader(manager)

    def test_url_source_uses_repo_path_for_directory_derivation(
        self, loader: ExternalMetadataLoader
    ) -> None:
        """When source is URL, the repo URL (not archive URL) should be used for directory path derivation."""
        getter = MagicMock(return_value=({"data": True}, "/some/path"))

        loader._load_metadata_by_source(
            SOURCE_URL,
            "",
            "https://github.com/RimSort/Steam-Workshop-Database",
            "steamDB.json",
            getter,
        )

        called_path = getter.call_args[0][0]
        assert "Steam-Workshop-Database" in called_path

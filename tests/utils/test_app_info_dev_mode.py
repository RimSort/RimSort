"""Tests for AppInfo dev mode detection and path redirection."""

from collections.abc import Generator
from pathlib import Path

import pytest

from app.utils.app_info import AppInfo


@pytest.fixture(autouse=True)
def _reset_app_info_singleton() -> Generator[None, None, None]:
    """Reset AppInfo singleton between tests so __init__ re-runs."""
    original = AppInfo._instance
    AppInfo._instance = None
    yield
    AppInfo._instance = original


@pytest.fixture
def _suppress_mock_app_info(
    mock_app_info: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Disable the autouse mock_app_info fixture for these tests.

    We need real AppInfo.__init__ to run so we can test its dev-mode
    logic. Re-reset the singleton so our test creates a fresh one.

    Also redirects ``__main__.__file__`` into ``tmp_path`` so that
    ``AppInfo.__init__`` resolves ``_application_folder`` to a temp
    directory, keeping all created dirs (dev/data, dev/logs, etc.)
    hermetic — nothing is written outside the test's temp directory.
    """
    import sys

    fake_app_dir = tmp_path / "fake_repo" / "app"
    fake_app_dir.mkdir(parents=True)
    fake_main = fake_app_dir / "__main__.py"
    fake_main.touch()
    monkeypatch.setattr(sys.modules["__main__"], "__file__", str(fake_main))
    AppInfo._instance = None


class TestIsDevMode:
    """Test is_dev_mode property with env var and --dev flag."""

    @pytest.mark.usefixtures("_suppress_mock_app_info")
    def test_dev_mode_off_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("RIMSORT_DEV", raising=False)
        monkeypatch.delenv("RIMSORT_DEV_DIR", raising=False)
        info = AppInfo()
        assert info.is_dev_mode is False

    @pytest.mark.usefixtures("_suppress_mock_app_info")
    def test_env_var_forces_dev_mode_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RIMSORT_DEV", "0")
        monkeypatch.delenv("RIMSORT_DEV_DIR", raising=False)
        info = AppInfo()
        assert info.is_dev_mode is False

    @pytest.mark.usefixtures("_suppress_mock_app_info")
    def test_env_var_forces_dev_mode_on(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RIMSORT_DEV", "true")
        monkeypatch.delenv("RIMSORT_DEV_DIR", raising=False)
        info = AppInfo()
        assert info.is_dev_mode is True

    @pytest.mark.usefixtures("_suppress_mock_app_info")
    def test_env_var_false_string(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RIMSORT_DEV", "false")
        monkeypatch.delenv("RIMSORT_DEV_DIR", raising=False)
        info = AppInfo()
        assert info.is_dev_mode is False

    @pytest.mark.usefixtures("_suppress_mock_app_info")
    def test_env_var_1_string(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RIMSORT_DEV", "1")
        monkeypatch.delenv("RIMSORT_DEV_DIR", raising=False)
        info = AppInfo()
        assert info.is_dev_mode is True


class TestDevModePathRedirection:
    """Test that dev mode redirects storage and log paths."""

    @pytest.mark.usefixtures("_suppress_mock_app_info")
    def test_dev_mode_redirects_storage_to_dev_data(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("RIMSORT_DEV", "1")
        monkeypatch.delenv("RIMSORT_DEV_DIR", raising=False)
        info = AppInfo()
        assert info.is_dev_mode is True
        expected = info.application_folder / "dev" / "data"
        assert info.app_storage_folder == expected

    @pytest.mark.usefixtures("_suppress_mock_app_info")
    def test_dev_mode_redirects_logs_to_dev_logs(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("RIMSORT_DEV", "1")
        monkeypatch.delenv("RIMSORT_DEV_DIR", raising=False)
        info = AppInfo()
        expected = info.application_folder / "dev" / "logs"
        assert info.user_log_folder == expected

    @pytest.mark.usefixtures("_suppress_mock_app_info")
    def test_production_mode_uses_platformdirs(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("RIMSORT_DEV", raising=False)
        monkeypatch.delenv("RIMSORT_DEV_DIR", raising=False)
        info = AppInfo()
        assert "dev" not in info.app_storage_folder.parts[-2:]

    @pytest.mark.usefixtures("_suppress_mock_app_info")
    def test_derived_paths_follow_storage_redirect(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("RIMSORT_DEV", "1")
        monkeypatch.delenv("RIMSORT_DEV_DIR", raising=False)
        info = AppInfo()
        assert info.databases_folder == info.app_storage_folder / "dbs"
        assert info.app_settings_file == info.app_storage_folder / "settings.json"
        assert info.saved_modlists_folder == info.app_storage_folder / "modlists"


class TestDevModeCustomDir:
    """Test RIMSORT_DEV_DIR env var behavior."""

    @pytest.mark.usefixtures("_suppress_mock_app_info")
    def test_custom_dir_used_when_dev_mode_active(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        custom_dir = tmp_path / "my-dev"
        monkeypatch.setenv("RIMSORT_DEV", "1")
        monkeypatch.setenv("RIMSORT_DEV_DIR", str(custom_dir))
        info = AppInfo()
        assert info.app_storage_folder == custom_dir / "data"
        assert info.user_log_folder == custom_dir / "logs"

    @pytest.mark.usefixtures("_suppress_mock_app_info")
    def test_custom_dir_ignored_when_dev_mode_off(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        custom_dir = tmp_path / "my-dev"
        monkeypatch.setenv("RIMSORT_DEV", "0")
        monkeypatch.setenv("RIMSORT_DEV_DIR", str(custom_dir))
        info = AppInfo()
        assert info.app_storage_folder != custom_dir / "data"

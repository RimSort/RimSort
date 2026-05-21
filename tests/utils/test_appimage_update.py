"""Tests for AppImage self-update support."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.utils.app_info import AppInfo
from app.utils.update_utils import UpdateManager

# ---------------------------------------------------------------------------
# AppInfo detection
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_appinfo_singleton() -> None:
    """Reset the AppInfo singleton between tests so env var changes take effect."""
    AppInfo._instance = None


class TestAppInfoAppImage:
    def test_is_appimage_when_env_set(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        fake_appimage = tmp_path / "RimSort.AppImage"
        fake_appimage.touch()
        monkeypatch.setenv("APPIMAGE", str(fake_appimage))
        assert AppInfo().is_appimage is True

    def test_is_appimage_when_env_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("APPIMAGE", raising=False)
        assert AppInfo().is_appimage is False

    def test_is_appimage_when_env_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("APPIMAGE", "")
        assert AppInfo().is_appimage is False

    def test_appimage_path_returns_path(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        fake = tmp_path / "RimSort.AppImage"
        fake.touch()
        monkeypatch.setenv("APPIMAGE", str(fake))
        assert AppInfo().appimage_path == fake

    def test_appimage_path_returns_none_when_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("APPIMAGE", raising=False)
        assert AppInfo().appimage_path is None

    def test_bak_cleanup_on_startup(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        fake = tmp_path / "RimSort.AppImage"
        fake.touch()
        bak = tmp_path / "RimSort.AppImage.bak"
        bak.write_text("old version")
        monkeypatch.setenv("APPIMAGE", str(fake))

        AppInfo()
        assert not bak.exists()

    def test_bak_cleanup_does_nothing_when_no_bak(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        fake = tmp_path / "RimSort.AppImage"
        fake.touch()
        monkeypatch.setenv("APPIMAGE", str(fake))

        AppInfo()  # should not raise


# ---------------------------------------------------------------------------
# Asset selection
# ---------------------------------------------------------------------------


def _make_asset(name: str, url: str) -> dict[str, Any]:
    return {"name": name, "browser_download_url": url}


SAMPLE_ASSETS: list[dict[str, Any]] = [
    _make_asset(
        "RimSort-1.2.3-Ubuntu-22.04_x86_64.zip",
        "https://example.com/ubuntu.zip",
    ),
    _make_asset(
        "RimSort-1.2.3-x86_64.AppImage",
        "https://example.com/rimsort.AppImage",
    ),
    _make_asset(
        "RimSort-1.2.3-Windows_x86_64.zip",
        "https://example.com/windows.zip",
    ),
]


class TestAssetSelection:
    @pytest.fixture
    def _linux_update_manager(self, monkeypatch: pytest.MonkeyPatch) -> UpdateManager:
        """Create an UpdateManager-like object with Linux platform settings."""
        monkeypatch.setenv("APPIMAGE", "/home/user/RimSort.AppImage")
        mgr = MagicMock(spec=UpdateManager)
        mgr._system = "Linux"
        mgr._arch = "64bit"
        mgr._cached_patterns = UpdateManager._platform_patterns["Linux"]

        # Bind the real methods so we can test them
        mgr._find_appimage_asset = UpdateManager._find_appimage_asset.__get__(mgr)
        mgr._get_platform_download_url = UpdateManager._get_platform_download_url.__get__(mgr)
        mgr._find_best_asset_match = UpdateManager._find_best_asset_match.__get__(mgr)
        mgr._asset_matches = UpdateManager._asset_matches.__get__(mgr)
        mgr._is_in_protected_path = MagicMock(return_value=False)
        return mgr

    def test_prefers_appimage_when_running_as_appimage(
        self,
        _linux_update_manager: UpdateManager,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        fake = tmp_path / "RimSort.AppImage"
        fake.touch()
        monkeypatch.setenv("APPIMAGE", str(fake))

        result = _linux_update_manager._get_platform_download_url(SAMPLE_ASSETS)
        assert result is not None
        assert result["is_appimage"] is True
        assert result["url"] == "https://example.com/rimsort.AppImage"

    def test_falls_back_to_zip_when_no_appimage_asset(
        self,
        _linux_update_manager: UpdateManager,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        fake = tmp_path / "RimSort.AppImage"
        fake.touch()
        monkeypatch.setenv("APPIMAGE", str(fake))

        assets_without_appimage = [a for a in SAMPLE_ASSETS if not a["name"].endswith(".AppImage")]
        result = _linux_update_manager._get_platform_download_url(assets_without_appimage)
        assert result is not None
        assert result["is_appimage"] is False
        assert result["url"] == "https://example.com/ubuntu.zip"

    def test_no_appimage_selection_when_not_appimage(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("APPIMAGE", raising=False)

        mgr = MagicMock(spec=UpdateManager)
        mgr._system = "Linux"
        mgr._arch = "64bit"
        mgr._cached_patterns = UpdateManager._platform_patterns["Linux"]
        mgr._find_best_asset_match = UpdateManager._find_best_asset_match.__get__(mgr)
        mgr._get_platform_download_url = UpdateManager._get_platform_download_url.__get__(mgr)
        mgr._asset_matches = UpdateManager._asset_matches.__get__(mgr)
        mgr._is_in_protected_path = MagicMock(return_value=False)

        result = mgr._get_platform_download_url(SAMPLE_ASSETS)
        assert result is not None
        assert result["is_appimage"] is False
        assert "ubuntu.zip" in result["url"]


# ---------------------------------------------------------------------------
# _find_appimage_asset
# ---------------------------------------------------------------------------


class TestFindAppImageAsset:
    def test_matches_arch_specific(self) -> None:
        mgr = MagicMock(spec=UpdateManager)
        mgr._find_appimage_asset = UpdateManager._find_appimage_asset.__get__(mgr)

        result = mgr._find_appimage_asset(SAMPLE_ASSETS, ["x86_64", "amd64"])
        assert result is not None
        assert result["is_appimage"] is True
        assert "AppImage" in result["name"]

    def test_returns_none_when_no_appimage(self) -> None:
        mgr = MagicMock(spec=UpdateManager)
        mgr._find_appimage_asset = UpdateManager._find_appimage_asset.__get__(mgr)

        assets = [a for a in SAMPLE_ASSETS if not a["name"].endswith(".AppImage")]
        result = mgr._find_appimage_asset(assets, ["x86_64"])
        assert result is None

    def test_fallback_without_arch_match(self) -> None:
        mgr = MagicMock(spec=UpdateManager)
        mgr._find_appimage_asset = UpdateManager._find_appimage_asset.__get__(mgr)

        result = mgr._find_appimage_asset(SAMPLE_ASSETS, ["aarch64"])
        assert result is not None
        assert result["is_appimage"] is True


# ---------------------------------------------------------------------------
# _prepare_appimage_update
# ---------------------------------------------------------------------------


class TestPrepareAppImageUpdate:
    def test_writes_new_appimage_file(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        fake = tmp_path / "RimSort.AppImage"
        fake.write_bytes(b"old content")
        monkeypatch.setenv("APPIMAGE", str(fake))

        mgr = MagicMock(spec=UpdateManager)
        mgr._update_content = b"new appimage content"
        mgr._extracted_path = None
        mgr._prepare_appimage_update = UpdateManager._prepare_appimage_update.__get__(mgr)

        result = mgr._prepare_appimage_update()

        expected = tmp_path / "RimSort.AppImage.new"
        assert result == expected
        assert expected.exists()
        assert expected.read_bytes() == b"new appimage content"
        assert os.access(expected, os.X_OK)

    def test_raises_when_no_appimage_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("APPIMAGE", raising=False)

        mgr = MagicMock(spec=UpdateManager)
        mgr._update_content = b"content"
        mgr._prepare_appimage_update = UpdateManager._prepare_appimage_update.__get__(mgr)

        from app.utils.update_utils import UpdateExtractionError

        with pytest.raises(UpdateExtractionError, match="Cannot determine AppImage path"):
            mgr._prepare_appimage_update()

    @pytest.mark.skipif(
        sys.platform == "win32", reason="chmod on directories does not reliably restrict write access on Windows"
    )
    def test_raises_when_no_write_permission(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        fake = tmp_path / "readonly" / "RimSort.AppImage"
        fake.parent.mkdir()
        fake.touch()
        monkeypatch.setenv("APPIMAGE", str(fake))

        # Make directory read-only
        fake.parent.chmod(0o555)
        try:
            mgr = MagicMock(spec=UpdateManager)
            mgr._update_content = b"content"
            mgr._prepare_appimage_update = UpdateManager._prepare_appimage_update.__get__(mgr)

            from app.utils.update_utils import UpdateExtractionError

            with pytest.raises(UpdateExtractionError, match="no write permission"):
                mgr._prepare_appimage_update()
        finally:
            fake.parent.chmod(0o755)

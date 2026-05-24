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
    def test_is_appimage_when_env_set(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
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

    def test_appimage_path_returns_path(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        fake = tmp_path / "RimSort.AppImage"
        fake.touch()
        monkeypatch.setenv("APPIMAGE", str(fake))
        assert AppInfo().appimage_path == fake

    def test_appimage_path_returns_none_when_unset(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("APPIMAGE", raising=False)
        assert AppInfo().appimage_path is None

    def test_bak_cleanup_on_startup(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        fake = tmp_path / "RimSort.AppImage"
        fake.touch()
        bak = tmp_path / "RimSort.AppImage.bak"
        bak.write_text("old version")
        monkeypatch.setenv("APPIMAGE", str(fake))

        AppInfo()
        assert not bak.exists()

    def test_bak_cleanup_does_nothing_when_no_bak(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
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

SAMPLE_ASSETS_WITH_TAR_GZ: list[dict[str, Any]] = [
    _make_asset(
        "RimSort-1.2.3-Ubuntu-22.04_x86_64.tar.gz",
        "https://example.com/ubuntu.tar.gz",
    ),
    _make_asset(
        "RimSort-1.2.3-Ubuntu-22.04_x86_64.zip",
        "https://example.com/ubuntu.zip",
    ),
    _make_asset(
        "RimSort-1.2.3-x86_64.AppImage",
        "https://example.com/rimsort.AppImage",
    ),
    _make_asset(
        "RimSort-1.2.3-Darwin_arm.tar.gz",
        "https://example.com/darwin.tar.gz",
    ),
    _make_asset(
        "RimSort-1.2.3-Windows_x86_64.zip",
        "https://example.com/windows.zip",
    ),
]


def _make_platform_mgr(
    system: str,
    arch: str = "64bit",
    *,
    bind_appimage: bool = False,
) -> UpdateManager:
    """Build a mock UpdateManager with real asset-selection methods bound."""
    mgr = MagicMock(spec=UpdateManager)
    mgr._system = system
    mgr._arch = arch
    mgr._cached_patterns = UpdateManager._platform_patterns[system]
    mgr._find_best_asset_match = UpdateManager._find_best_asset_match.__get__(mgr)
    mgr._get_platform_download_url = UpdateManager._get_platform_download_url.__get__(
        mgr
    )
    mgr._asset_matches = UpdateManager._asset_matches.__get__(mgr)
    mgr._is_in_protected_path = MagicMock(return_value=False)
    if bind_appimage:
        mgr._find_appimage_asset = UpdateManager._find_appimage_asset.__get__(mgr)
    return mgr


class TestAssetSelection:
    @pytest.fixture
    def _linux_update_manager(self, monkeypatch: pytest.MonkeyPatch) -> UpdateManager:
        """Create an UpdateManager-like object with Linux AppImage settings."""
        monkeypatch.setenv("APPIMAGE", "/home/user/RimSort.AppImage")
        return _make_platform_mgr("Linux", bind_appimage=True)

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

        assets_without_appimage = [
            a for a in SAMPLE_ASSETS if not a["name"].endswith(".AppImage")
        ]
        result = _linux_update_manager._get_platform_download_url(
            assets_without_appimage
        )
        assert result is not None
        assert result["is_appimage"] is False
        assert result["url"] == "https://example.com/ubuntu.zip"

    def test_no_appimage_selection_when_not_appimage(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("APPIMAGE", raising=False)
        mgr = _make_platform_mgr("Linux")

        result = mgr._get_platform_download_url(SAMPLE_ASSETS)
        assert result is not None
        assert result["is_appimage"] is False
        assert "ubuntu.zip" in result["url"]


# ---------------------------------------------------------------------------
# tar.gz asset selection
# ---------------------------------------------------------------------------


class TestTarGzAssetSelection:
    @pytest.fixture
    def _linux_mgr(self, monkeypatch: pytest.MonkeyPatch) -> UpdateManager:
        monkeypatch.delenv("APPIMAGE", raising=False)
        return _make_platform_mgr("Linux")

    @pytest.fixture
    def _darwin_mgr(self, monkeypatch: pytest.MonkeyPatch) -> UpdateManager:
        monkeypatch.delenv("APPIMAGE", raising=False)
        return _make_platform_mgr("Darwin", arch="ARM64")

    def test_linux_prefers_tar_gz_over_zip(self, _linux_mgr: UpdateManager) -> None:
        result = _linux_mgr._get_platform_download_url(SAMPLE_ASSETS_WITH_TAR_GZ)
        assert result is not None
        assert result["is_tar_gz"] is True
        assert result["url"] == "https://example.com/ubuntu.tar.gz"

    def test_linux_falls_back_to_zip_when_no_tar_gz(
        self, _linux_mgr: UpdateManager
    ) -> None:
        result = _linux_mgr._get_platform_download_url(SAMPLE_ASSETS)
        assert result is not None
        assert result["is_tar_gz"] is False
        assert result["url"] == "https://example.com/ubuntu.zip"

    def test_darwin_prefers_tar_gz(self, _darwin_mgr: UpdateManager) -> None:
        result = _darwin_mgr._get_platform_download_url(SAMPLE_ASSETS_WITH_TAR_GZ)
        assert result is not None
        assert result["is_tar_gz"] is True
        assert result["url"] == "https://example.com/darwin.tar.gz"

    def test_windows_ignores_tar_gz(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("APPIMAGE", raising=False)
        mgr = _make_platform_mgr("Windows")

        result = mgr._get_platform_download_url(SAMPLE_ASSETS_WITH_TAR_GZ)
        assert result is not None
        assert result["is_tar_gz"] is False
        assert result["url"] == "https://example.com/windows.zip"


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
    def test_writes_new_appimage_file(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        fake = tmp_path / "RimSort.AppImage"
        fake.write_bytes(b"old content")
        monkeypatch.setenv("APPIMAGE", str(fake))

        mgr = MagicMock(spec=UpdateManager)
        mgr._update_content = b"new appimage content"
        mgr._extracted_path = None
        mgr._prepare_appimage_update = UpdateManager._prepare_appimage_update.__get__(
            mgr
        )

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
        mgr._prepare_appimage_update = UpdateManager._prepare_appimage_update.__get__(
            mgr
        )

        from app.utils.update_utils import UpdateExtractionError

        with pytest.raises(
            UpdateExtractionError, match="Cannot determine AppImage path"
        ):
            mgr._prepare_appimage_update()

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="chmod on directories does not reliably restrict write access on Windows",
    )
    def test_raises_when_no_write_permission(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        fake = tmp_path / "readonly" / "RimSort.AppImage"
        fake.parent.mkdir()
        fake.touch()
        monkeypatch.setenv("APPIMAGE", str(fake))

        # Make directory read-only
        fake.parent.chmod(0o555)
        try:
            mgr = MagicMock(spec=UpdateManager)
            mgr._update_content = b"content"
            mgr._prepare_appimage_update = (
                UpdateManager._prepare_appimage_update.__get__(mgr)
            )

            from app.utils.update_utils import UpdateExtractionError

            with pytest.raises(UpdateExtractionError, match="no write permission"):
                mgr._prepare_appimage_update()
        finally:
            fake.parent.chmod(0o755)


# ---------------------------------------------------------------------------
# _extract_tar_gz
# ---------------------------------------------------------------------------


def _run_tar_thread(tar_path: Path, extract_dir: Path) -> tuple[bool, str]:
    """Run a TarExtractThread synchronously and return (success, message)."""
    from app.utils.update_utils import TarExtractThread

    results: list[tuple[bool, str]] = []
    thread = TarExtractThread(str(tar_path), str(extract_dir))
    thread.finished.connect(lambda ok, msg: results.append((ok, msg)))
    thread.run()
    assert len(results) == 1
    return results[0]


def _make_extract_mgr() -> UpdateManager:
    """Build a mock UpdateManager with _extract_tar_gz bound."""
    mgr = MagicMock(spec=UpdateManager)
    mgr.mod_info_panel = None
    mgr._progress_widget = None
    mgr._extract_tar_gz = UpdateManager._extract_tar_gz.__get__(mgr)
    return mgr


class TestTarExtractThread:
    """Test TarExtractThread directly — no QApplication needed since we call run()."""

    def _create_tar_gz_file(self, tmp_path: Path, name: str = "RimSort") -> Path:
        """Create a tar.gz file on disk with a single entry."""
        import io
        import tarfile as tf

        tar_path = tmp_path / "test.tar.gz"
        with tf.open(str(tar_path), "w:gz") as tar:
            data = b"#!/bin/sh\necho hello"
            info = tf.TarInfo(name=name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        return tar_path

    def test_extracts_content(self, tmp_path: Path) -> None:
        tar_path = self._create_tar_gz_file(tmp_path)
        extract_dir = tmp_path / "extract"
        extract_dir.mkdir()

        success, _ = _run_tar_thread(tar_path, extract_dir)
        assert success is True
        assert (extract_dir / "RimSort").exists()

    def test_reports_progress(self, tmp_path: Path) -> None:
        from app.utils.update_utils import TarExtractThread

        tar_path = self._create_tar_gz_file(tmp_path)
        extract_dir = tmp_path / "extract"
        extract_dir.mkdir()

        progress_updates: list[tuple[int, str]] = []
        thread = TarExtractThread(str(tar_path), str(extract_dir))
        thread.progress.connect(lambda p, m: progress_updates.append((p, m)))
        thread.run()

        assert len(progress_updates) >= 1
        assert progress_updates[-1][0] == 100

    def test_emits_failure_on_invalid_archive(self, tmp_path: Path) -> None:
        bad_tar = tmp_path / "bad.tar.gz"
        bad_tar.write_bytes(b"not a tarball")
        extract_dir = tmp_path / "extract"
        extract_dir.mkdir()

        success, _ = _run_tar_thread(bad_tar, extract_dir)
        assert success is False

    def test_emits_failure_on_empty_archive(self, tmp_path: Path) -> None:
        import tarfile as tf

        empty_tar = tmp_path / "empty.tar.gz"
        with tf.open(str(empty_tar), "w:gz"):
            pass

        extract_dir = tmp_path / "extract"
        extract_dir.mkdir()

        success, msg = _run_tar_thread(empty_tar, extract_dir)
        assert success is False
        assert "empty" in msg

    def test_abort_stops_extraction(self, tmp_path: Path) -> None:
        import io
        import tarfile as tf

        from app.utils.update_utils import TarExtractThread

        tar_path = tmp_path / "multi.tar.gz"
        with tf.open(str(tar_path), "w:gz") as tar:
            for i in range(10):
                data = b"x" * 100
                info = tf.TarInfo(name=f"file_{i}")
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))

        extract_dir = tmp_path / "extract"
        extract_dir.mkdir()

        thread = TarExtractThread(str(tar_path), str(extract_dir))
        thread.stop()
        results: list[tuple[bool, str]] = []
        thread.finished.connect(lambda ok, msg: results.append((ok, msg)))
        thread.run()

        assert len(results) == 1
        assert results[0][0] is False
        assert "aborted" in results[0][1].lower()


class TestExtractTarGzIntegration:
    """Test _extract_tar_gz validation logic (thread interaction is mocked)."""

    def test_raises_on_invalid_tar_gz(self, tmp_path: Path) -> None:
        extract_dir = tmp_path / "extract"
        extract_dir.mkdir()

        from app.utils.update_utils import UpdateExtractionError

        with pytest.raises(UpdateExtractionError, match="Invalid tar.gz"):
            _make_extract_mgr()._extract_tar_gz(b"not a tarball", extract_dir)

    def test_raises_on_empty_tar_gz(self, tmp_path: Path) -> None:
        import io
        import tarfile as tf

        buf = io.BytesIO()
        with tf.open(fileobj=buf, mode="w:gz"):
            pass

        extract_dir = tmp_path / "extract"
        extract_dir.mkdir()

        from app.utils.update_utils import UpdateExtractionError

        with pytest.raises(UpdateExtractionError, match="empty"):
            _make_extract_mgr()._extract_tar_gz(buf.getvalue(), extract_dir)

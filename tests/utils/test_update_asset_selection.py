"""Application updates must match the installation's platform and package format."""

from collections.abc import Callable
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QMessageBox

from app.models.settings import Settings
from app.utils import update_utils
from app.utils.app_info import AppInfo
from app.utils.system_info import SystemInfo
from app.utils.update_utils import UpdateManager

RELEASE_NAMES = [
    "RimSort-v1.17.4-Darwin_arm64.tar.gz",
    "RimSort-v1.17.4-Ubuntu-22.04_x86_64.tar.gz",
    "RimSort-v1.17.4-Ubuntu-24.04_x86_64.tar.gz",
    "RimSort-v1.17.4-Windows_x86_64.msi",
    "RimSort-v1.17.4-Windows_x86_64.zip",
    "RimSort-v1.17.4-x86_64.AppImage",
]


def _assets(names: list[str]) -> list[dict[str, str]]:
    return [
        {"name": name, "browser_download_url": f"https://example.invalid/{name}"}
        for name in names
    ]


@pytest.fixture
def manager_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[[str, str], UpdateManager]:
    def create(system: str, machine: str) -> UpdateManager:
        monkeypatch.setattr(update_utils.platform, "system", lambda: system)
        monkeypatch.setattr(update_utils.platform, "machine", lambda: machine)
        bits = "32bit" if machine in ("i386", "i686", "x86") else "64bit"
        monkeypatch.setattr(update_utils.platform, "architecture", lambda: (bits, ""))
        monkeypatch.setattr(SystemInfo, "_instance", None)
        manager = UpdateManager(Settings(), None)
        monkeypatch.setattr(manager, "_is_in_protected_path", lambda: False)
        monkeypatch.setattr(manager, "_check_needs_elevation", lambda: False)
        return manager

    return create


@pytest.mark.parametrize(
    ("system", "machine"),
    [
        ("Darwin", "x86_64"),
        ("Linux", "aarch64"),
        ("Windows", "ARM64"),
        ("Windows", "i386"),
        ("Linux", "i686"),
        ("Linux", "mips64"),
        ("Darwin", ""),
        ("FreeBSD", "x86_64"),
    ],
)
def test_release_without_compatible_architecture_is_rejected(
    manager_factory: Callable[[str, str], UpdateManager], system: str, machine: str
) -> None:
    manager = manager_factory(system, machine)
    assert manager._get_platform_download_url(_assets(RELEASE_NAMES)) is None


@pytest.mark.parametrize(
    ("system", "machine", "filename"),
    [
        ("Darwin", "arm64", "RimSort-v1.17.4-Darwin_arm64.tar.gz"),
        ("Darwin", "aarch64", "RimSort-v1.17.4-macOS_ARM64.zip"),
        ("Darwin", "arm64e", "RimSort-v1.17.4-Mac_aarch64.tar.gz"),
        ("Darwin", "x86_64", "RimSort-v1.17.4-Darwin_AMD64.tar.gz"),
        ("Windows", "AMD64", "RimSort-v1.17.4-Win_x64.zip"),
        ("Linux", "x86_64", "RimSort-v1.17.4-Linux_amd64.tar.gz"),
        ("Linux", "aarch64", "RimSort-v1.17.4-Ubuntu_arm64.tar.gz"),
        ("Windows", "x86", "RimSort-v1.17.4-Windows_i386.zip"),
    ],
)
def test_compatible_architecture_aliases_are_preserved(
    manager_factory: Callable[[str, str], UpdateManager],
    system: str,
    machine: str,
    filename: str,
) -> None:
    manager = manager_factory(system, machine)
    result = manager._get_platform_download_url(_assets([filename]))
    assert result is not None
    assert result["name"] == filename


@pytest.mark.parametrize(
    ("system", "machine", "wrong", "correct"),
    [
        ("Darwin", "x86_64", "Darwin_arm64.tar.gz", "Darwin_x86_64.zip"),
        ("Windows", "AMD64", "Windows_arm64.zip", "Windows_x86_64.msi"),
        ("Windows", "AMD64", "Darwin_x86_64.zip", "Windows_x86_64.msi"),
        ("Linux", "x86_64", "Ubuntu_aarch64.tar.gz", "Ubuntu_x86_64.zip"),
    ],
)
def test_incompatible_preferred_asset_does_not_hide_compatible_format(
    manager_factory: Callable[[str, str], UpdateManager],
    system: str,
    machine: str,
    wrong: str,
    correct: str,
) -> None:
    manager = manager_factory(system, machine)
    result = manager._get_platform_download_url(_assets([wrong, correct]))
    assert result is not None
    assert result["name"] == correct


@pytest.mark.parametrize("protected", [False, True])
def test_windows_format_preference_is_preserved(
    manager_factory: Callable[[str, str], UpdateManager],
    monkeypatch: pytest.MonkeyPatch,
    protected: bool,
) -> None:
    manager = manager_factory("Windows", "AMD64")
    monkeypatch.setattr(manager, "_is_in_protected_path", lambda: protected)
    selected = manager._get_platform_download_url(_assets(RELEASE_NAMES), protected)
    assert selected is not None
    assert selected["is_msi"] is protected
    assert selected["name"].endswith(".msi" if protected else ".zip")


@pytest.mark.parametrize("appimage", [True, False])
def test_unlabelled_architecture_is_rejected(
    manager_factory: Callable[[str, str], UpdateManager],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    appimage: bool,
) -> None:
    manager = manager_factory("Linux", "x86_64")
    if appimage:
        monkeypatch.setenv("APPIMAGE", str(tmp_path / "RimSort.AppImage"))
    names = ["RimSort-Ubuntu.tar.gz", "RimSort.AppImage"]
    assert manager._get_platform_download_url(_assets(names)) is None


@pytest.mark.parametrize("condition", ["missing", "wrong_architecture", "compatible"])
def test_appimage_update_check_never_downloads_archive_fallback(
    manager_factory: Callable[[str, str], UpdateManager],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    condition: str,
) -> None:
    manager = manager_factory("Linux", "x86_64")
    current_appimage = tmp_path / "RimSort.AppImage"
    current_appimage.write_bytes(b"current application")
    monkeypatch.setenv("APPIMAGE", str(current_appimage))
    names = [name for name in RELEASE_NAMES if not name.endswith(".AppImage")]
    if condition != "missing":
        arch = "x86_64" if condition == "compatible" else "aarch64"
        names.append(f"RimSort-v1.17.4-{arch}.AppImage")
    response = MagicMock()
    response.json.return_value = {"tag_name": "v1.17.4", "assets": _assets(names)}
    monkeypatch.setattr(update_utils.http, "get", MagicMock(return_value=response))
    monkeypatch.setattr(manager, "_validate_prerequisites", lambda: True)
    AppInfo()._app_version = "1.17.3"
    warning = MagicMock()
    install = MagicMock()
    monkeypatch.setattr(update_utils.dialogue, "show_warning", warning)
    monkeypatch.setattr(manager, "_perform_update", install)
    monkeypatch.setattr(
        update_utils.dialogue,
        "show_dialogue_conditional",
        lambda **_kwargs: QMessageBox.StandardButton.Yes,
    )

    manager.do_check_for_update()

    if condition == "compatible":
        warning.assert_not_called()
        install.assert_called_once()
        assert install.call_args.args[0].endswith("-x86_64.AppImage")
        assert install.call_args.args[3] is True
    else:
        install.assert_not_called()
        warning.assert_called_once()
        information = warning.call_args.kwargs["information"]
        assert "https://github.com/RimSort/RimSort/releases" in information
        assert "AppImage" in information
    assert current_appimage.read_bytes() == b"current application"
    assert list(tmp_path.iterdir()) == [current_appimage]

"""Application backups must round-trip a complete signed macOS bundle."""

from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path
from unittest.mock import MagicMock
from zipfile import ZipFile

import pytest
from pytestqt.qtbot import QtBot

from app.models.settings import Settings
from app.utils import update_utils
from app.utils.app_info import AppInfo
from app.utils.update_utils import UpdateManager
from app.utils.zip_extractor import create_zip_backup


@pytest.fixture
def app_bundle(tmp_path: Path) -> Path:
    bundle = tmp_path / "--Renamed RimSórt's App.app"
    macos = bundle / "Contents" / "MacOS"
    macos.mkdir(parents=True)
    executable = macos / "RimSort"
    executable.write_text("#!/bin/sh\nexit 0\n")
    executable.chmod(0o755)
    (bundle / "Contents" / "Info.plist").write_bytes(
        plistlib.dumps(
            {
                "CFBundleExecutable": "RimSort",
                "CFBundleIdentifier": "org.rimsort.backup-test",
                "CFBundleName": "RimSort",
                "CFBundlePackageType": "APPL",
            }
        )
    )
    resources = bundle / "Contents" / "Resources"
    resources.mkdir()
    (resources / "translations.qm").write_bytes(b"translation resource")
    (resources / "empty").mkdir()
    return bundle


def _restore_archive(archive: Path, destination: Path) -> None:
    destination.mkdir()
    restore_env = dict(os.environ)
    restore_env.pop("DITTONORSRC", None)
    restore_env.pop("COPYFILE_DISABLE", None)
    subprocess.run(
        [
            "/usr/bin/tar",
            "--mac-metadata",
            "--acls",
            "--xattrs",
            "-xpf",
            str(archive),
            "-C",
            str(destination),
        ],
        check=True,
        env=restore_env,
    )


@pytest.mark.skipif(sys.platform != "darwin", reason="Requires macOS archive tools")
@pytest.mark.parametrize(
    "bundle_name", ["--Renamed RimSórt's App.app", "@Renamed RimSórt's App.app"]
)
def test_update_backup_contains_complete_named_bundle(
    app_bundle: Path, monkeypatch: pytest.MonkeyPatch, qtbot: QtBot, bundle_name: str
) -> None:
    app_bundle = app_bundle.rename(app_bundle.parent / bundle_name)
    monkeypatch.setattr(
        AppInfo(), "_application_folder", app_bundle / "Contents" / "MacOS"
    )
    monkeypatch.setattr(update_utils, "__compiled__", object(), raising=False)
    monkeypatch.setattr(update_utils, "TaskProgressWindow", MagicMock())
    manager = UpdateManager(Settings(), None)

    assert manager._create_backup_with_progress() is True

    backups = list(AppInfo().application_backups_folder.glob("RimSort_Backup_*.tar.gz"))
    assert len(backups) == 1
    with tarfile.open(backups[0]) as archive:
        names = {Path(name) for name in archive.getnames()}
        assert Path(app_bundle.name) / "Contents/Info.plist" in names
        assert Path(app_bundle.name) / "Contents/Resources/translations.qm" in names


@pytest.mark.skipif(sys.platform != "darwin", reason="Requires macOS signing tools")
def test_backup_restores_signed_bundle(
    app_bundle: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = app_bundle / "Contents" / "MacOS" / "RimSort"
    shutil.copyfile("/bin/echo", executable)
    resource = app_bundle / "Contents" / "Resources" / "translations.qm"
    framework = app_bundle / "Contents" / "Frameworks" / "Example"
    (framework / "Versions" / "A").mkdir(parents=True)
    (framework / "Versions" / "Current").symlink_to("A", target_is_directory=True)
    subprocess.run(["/usr/bin/codesign", "--sign", "-", str(resource)], check=True)
    subprocess.run(
        ["/usr/bin/codesign", "--force", "--deep", "--sign", "-", str(app_bundle)],
        check=True,
    )
    for directory in (app_bundle, resource.parent):
        subprocess.run(
            [
                "/usr/bin/xattr",
                "-w",
                "com.rimsort.backup",
                "directory metadata",
                str(directory),
            ],
            check=True,
        )
        subprocess.run(
            ["/bin/chmod", "+a", "everyone allow read", str(directory)], check=True
        )
    subprocess.run(
        ["/usr/bin/codesign", "--verify", "--deep", "--strict", str(app_bundle)],
        check=True,
    )
    destination = tmp_path / "backup.tar.gz"
    monkeypatch.setattr(update_utils, "__compiled__", object(), raising=False)

    update_utils._create_application_backup(app_bundle / "Contents/MacOS", destination)

    with tarfile.open(destination) as archive:
        entry = next(
            member
            for member in archive.getmembers()
            if Path(member.name) == Path(app_bundle.name) / "Contents/MacOS/RimSort"
        )
        assert entry.mode & 0o111
    restored = tmp_path / "restored"
    _restore_archive(destination, restored)
    restored_bundle = restored / app_bundle.name
    for directory in (app_bundle, resource.parent):
        restored_directory = restored_bundle / directory.relative_to(app_bundle)
        assert subprocess.check_output(
            ["/usr/bin/xattr", "-p", "com.rimsort.backup", str(restored_directory)]
        ) == subprocess.check_output(
            ["/usr/bin/xattr", "-p", "com.rimsort.backup", str(directory)]
        )
        assert (
            subprocess.check_output(
                ["/bin/ls", "-lde", str(restored_directory)]
            ).splitlines()[1:]
            == subprocess.check_output(
                ["/bin/ls", "-lde", str(directory)]
            ).splitlines()[1:]
        )
    subprocess.run(
        ["/usr/bin/codesign", "--verify", "--deep", "--strict", str(restored_bundle)],
        check=True,
    )
    assert (
        restored_bundle / resource.relative_to(app_bundle)
    ).read_bytes() == resource.read_bytes()
    assert (restored_bundle / "Contents/Resources/empty").is_dir()
    assert (
        restored_bundle / framework.relative_to(app_bundle) / "Versions/Current"
    ).readlink() == Path("A")


@pytest.mark.skipif(sys.platform != "darwin", reason="Requires macOS metadata tools")
def test_backup_restores_resource_fork_and_acl(
    app_bundle: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    resource = app_bundle / "Contents" / "Resources" / "translations.qm"
    subprocess.run(
        [
            "/usr/bin/xattr",
            "-w",
            "com.apple.ResourceFork",
            "resource fork",
            str(resource),
        ],
        check=True,
    )
    subprocess.run(
        ["/bin/chmod", "+a", "everyone allow read", str(resource)], check=True
    )
    destination = tmp_path / "backup.tar.gz"
    monkeypatch.setattr(update_utils, "__compiled__", object(), raising=False)
    monkeypatch.setenv("DITTONORSRC", "1")
    monkeypatch.setenv("COPYFILE_DISABLE", "1")

    update_utils._create_application_backup(app_bundle / "Contents/MacOS", destination)

    restored = tmp_path / "restored"
    _restore_archive(destination, restored)
    restored_resource = restored / app_bundle.name / resource.relative_to(app_bundle)
    assert (
        subprocess.check_output(
            ["/usr/bin/xattr", "-p", "com.apple.ResourceFork", str(restored_resource)]
        ).strip()
        == b"resource fork"
    )
    acl = subprocess.check_output(["/bin/ls", "-lde", str(restored_resource)])
    assert b"everyone allow read" in acl


@pytest.mark.parametrize(
    ("system", "compiled"),
    [("darwin", True), ("darwin", False), ("linux", True), ("win32", True)],
)
def test_application_backup_source(
    app_bundle: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    system: str,
    compiled: bool,
) -> None:
    monkeypatch.setattr(sys, "platform", system)
    if compiled:
        monkeypatch.setattr(update_utils, "__compiled__", object(), raising=False)
    else:
        monkeypatch.delattr(update_utils, "__compiled__", raising=False)
    archive = MagicMock()
    progress = MagicMock()
    monkeypatch.setattr(update_utils, "create_zip_backup", archive)
    native = MagicMock()
    monkeypatch.setattr(update_utils, "_create_macos_bundle_backup", native)
    source = app_bundle / "Contents" / "MacOS"
    extension = ".tar.gz" if system == "darwin" and compiled else ".zip"
    destination = tmp_path / f"backup{extension}"

    update_utils._create_application_backup(source, destination, progress)

    expected = app_bundle if system == "darwin" and compiled else source
    if system == "darwin" and compiled:
        native.assert_called_once_with(expected, destination, progress)
        archive.assert_not_called()
    else:
        archive.assert_called_once_with(expected, destination, progress)
        native.assert_not_called()


@pytest.mark.parametrize("missing", ["Info.plist", "MacOS/RimSort"])
def test_incomplete_compiled_bundle_is_not_backed_up_as_partial_application(
    app_bundle: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(update_utils, "__compiled__", object(), raising=False)
    (app_bundle / "Contents" / missing).unlink()
    archive = MagicMock()
    monkeypatch.setattr(update_utils, "create_zip_backup", archive)
    with pytest.raises(OSError, match="complete macOS application bundle"):
        update_utils._create_application_backup(
            app_bundle / "Contents" / "MacOS", tmp_path / "backup.zip"
        )
    archive.assert_not_called()


@pytest.mark.parametrize("failure", ["exit", "start", "heartbeat", "empty", "publish"])
def test_native_backup_failure_preserves_previous_archive(
    app_bundle: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    destination = tmp_path / "backup.zip"
    with ZipFile(destination, "w") as archive:
        archive.writestr("previous", b"last usable backup")
    previous = destination.read_bytes()
    process = MagicMock()
    process.__enter__.return_value = process
    process.returncode = 23 if failure == "exit" else 0
    process.communicate.return_value = (None, b"Controlled archiver failure")
    if failure == "heartbeat":
        process.communicate.side_effect = [
            subprocess.TimeoutExpired("tar", 0.1),
            (None, b""),
        ]

    def start(command: list[str], **_kwargs: object) -> MagicMock:
        if failure == "start":
            raise FileNotFoundError("Archiver unavailable")
        if failure != "empty":
            Path(command[command.index("-czf") + 1]).write_bytes(b"native archive")
        return process

    monkeypatch.setattr(update_utils.subprocess, "Popen", start)

    def progress(_current: int, _total: int) -> None:
        if failure == "heartbeat":
            calls = process.communicate.call_count
            if calls:
                raise InterruptedError("Backup cancelled")

    if failure == "publish":
        monkeypatch.setattr(
            update_utils.os, "replace", MagicMock(side_effect=OSError("Disk full"))
        )
    with pytest.raises(OSError):
        update_utils._create_macos_bundle_backup(app_bundle, destination, progress)
    assert destination.read_bytes() == previous
    assert not list(tmp_path.glob(".backup.zip.*"))
    if failure == "heartbeat":
        process.kill.assert_called_once()
        assert process.communicate.call_count == 2


def test_backup_destination_inside_bundle_is_rejected_without_changing_source(
    app_bundle: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    destination = app_bundle / "backups" / "backup.zip"
    with pytest.raises(OSError, match="outside the application bundle"):
        update_utils._create_macos_bundle_backup(app_bundle, destination, None)
    assert not destination.parent.exists()


def test_interruption_stops_and_reaps_archiver_process(
    app_bundle: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    destination = tmp_path / "backup.zip"
    destination.write_bytes(b"previous backup")
    real_popen = subprocess.Popen
    children: list[subprocess.Popen[bytes]] = []

    def start(
        command: list[str], *, stdout: int, stderr: int, env: dict[str, str]
    ) -> subprocess.Popen[bytes]:
        child = real_popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            stdout=stdout,
            stderr=stderr,
            env=env,
        )
        children.append(child)
        Path(command[command.index("-czf") + 1]).write_bytes(b"unfinished archive")
        return child

    def cancel(_current: int, _total: int) -> None:
        if children:
            raise InterruptedError("Backup cancelled")

    monkeypatch.setattr(update_utils.subprocess, "Popen", start)
    try:
        with pytest.raises(InterruptedError, match="Backup cancelled"):
            update_utils._create_macos_bundle_backup(app_bundle, destination, cancel)
        assert len(children) == 1
        assert children[0].poll() is not None
        assert children[0].returncode != 0
        assert destination.read_bytes() == b"previous backup"
        assert not list(tmp_path.glob(".backup.zip.*"))
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
                child.communicate()


@pytest.mark.parametrize("system", ["linux", "win32"])
def test_non_macos_app_directory_uses_existing_zip_writer(
    app_bundle: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, system: str
) -> None:
    monkeypatch.setattr(sys, "platform", system)
    native = MagicMock(side_effect=AssertionError("Native macOS tool called"))
    monkeypatch.setattr(update_utils.subprocess, "Popen", native)
    destination = tmp_path / "backup.zip"
    create_zip_backup(app_bundle, destination)
    with ZipFile(destination) as archive:
        assert (
            archive.read("Contents/Resources/translations.qm")
            == b"translation resource"
        )
    native.assert_not_called()


def test_retention_counts_legacy_zip_and_complete_bundle_archives(
    monkeypatch: pytest.MonkeyPatch, qtbot: QtBot
) -> None:
    settings = Settings()
    settings.max_backups = 2
    manager = UpdateManager(settings, None)
    folder = AppInfo().application_backups_folder
    folder.mkdir(parents=True)
    names = [
        "RimSort_Backup_old.zip",
        "RimSort_Backup_middle.tar.gz",
        "RimSort_Backup_new.zip",
    ]
    for modified, name in enumerate(names, 1):
        archive = folder / name
        archive.write_bytes(b"backup contents")
        os.utime(archive, (modified, modified))
    unrelated = folder / "unrelated.tar.gz"
    unrelated.write_bytes(b"keep")

    manager._cleanup_old_backups()

    assert not (folder / names[0]).exists()
    assert (folder / names[1]).exists()
    assert (folder / names[2]).exists()
    assert unrelated.read_bytes() == b"keep"

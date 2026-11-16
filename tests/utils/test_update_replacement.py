"""Exercise replacement and recovery through the real update script."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QObject
from PySide6.QtWidgets import QMainWindow
from pytestqt.qtbot import QtBot

from app.controllers.app_controller import AppController
from app.utils.app_info import AppInfo
from app.utils.update_utils import UpdateManager

_COMMAND_WRAPPER = r"""
import json
import os
import signal
import subprocess
import sys
from pathlib import Path

name = Path(sys.argv[0]).name
args = sys.argv[1:]
config = json.loads(Path(os.environ["UPDATE_TEST_CONFIG"]).read_text())
with Path(config["trace"]).open("a") as trace:
    trace.write(json.dumps({"command": name, "args": args}) + "\n")
fault = config.get("fault", "")
old = Path(config["old"])
payload = Path(config["payload"])
source = Path(args[-2]) if len(args) > 1 else Path()
destination = Path(args[-1]) if args else Path()
staged = ".rimsort-update." in str(source)
new_copy = (
    (name in {"rsync", "cp"} and source == payload)
    or (name == "mv" and source == payload)
)
commit = name == "mv" and staged and "/new/" in str(source)
backup = name == "mv" and source == old
rollback = name == "mv" and staged and "/old/" in str(source)

if name == "uname":
    print(config["system"])
    sys.exit(0)
if name == "stat":
    path = Path(args[-1])
    device = os.lstat(path).st_dev
    if path == old:
        count = config.get("target_stat_count", 0) + 1
        config["target_stat_count"] = count
        Path(os.environ["UPDATE_TEST_CONFIG"]).write_text(json.dumps(config))
        if fault == "mounted_target" or (fault == "device_changed" and count >= 3):
            device += 1
    print(device)
    sys.exit(0)
if name in {"killall", "pgrep"}:
    sys.exit(1)
if name in {"sleep", "open", "nohup"}:
    sys.exit(0)
if new_copy and fault in {"copy", "interrupt_copy"}:
    if config["mode"] == "appimage":
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"partial")
    else:
        destination.mkdir(parents=True, exist_ok=True)
        executable = destination / config["executable"]
        executable.parent.mkdir(parents=True, exist_ok=True)
        executable.write_bytes(b"partial")
    if fault == "interrupt_copy":
        os.kill(os.getppid(), signal.SIGTERM)
    sys.exit(23)
if name == "chmod" and fault == "permissions":
    sys.exit(1)
if name == "ln" and fault in {"backup", "backup_copy"}:
    sys.exit(1)
if name == "cp" and source == old and fault == "backup":
    destination.write_bytes(b"partial backup")
    sys.exit(1)
if backup and fault == "backup":
    sys.exit(1)
if commit and fault in {"commit", "rollback"}:
    sys.exit(1)
if rollback and fault == "rollback":
    sys.exit(1)
if commit and fault == "target_appears":
    old.mkdir()
    (old / "unexpected.txt").write_text("preserve competing destination")

result = subprocess.run([config["commands"][name], *args], check=False).returncode
if backup and fault in {"interrupt_backup", "hard_interrupt_backup"} and result == 0:
    os.kill(os.getppid(), signal.SIGKILL if fault == "hard_interrupt_backup" else signal.SIGTERM)
    sys.exit(143)
sys.exit(result)
"""


@dataclass
class Installer:
    root: Path
    old: Path
    payload: Path
    script: Path
    executable: str
    environment: dict[str, str] = field(repr=False)
    config: Path
    mode: str

    def run(
        self, fault: str = "", dry_run: bool = False
    ) -> subprocess.CompletedProcess[str]:
        config = json.loads(self.config.read_text())
        config["fault"] = fault
        config["target_stat_count"] = 0
        self.config.write_text(json.dumps(config))
        install = self.old.parent if self.mode == "appimage" else self.old
        args = ["bash", str(self.script)]
        if dry_run:
            args.append("--dry-run")
        args.extend([str(self.payload), "", str(install)])
        return subprocess.run(
            args,
            check=False,
            cwd=self.root,
            env=self.environment,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=20,
        )

    def binary(self, base: Path | None = None) -> Path:
        target = base if base is not None else self.old
        return target if self.mode == "appimage" else target / self.executable

    def calls(self) -> list[dict[str, object]]:
        trace = self.root / "commands.jsonl"
        return [json.loads(line) for line in trace.read_text().splitlines()]

    def assert_original(self) -> None:
        assert self.binary().read_bytes() == b"old"
        assert self.payload.exists()
        assert not list(self.old.parent.glob(".rimsort-update.*"))

    def fail(self, fault: str = "") -> subprocess.CompletedProcess[str]:
        result = self.run(fault)
        assert result.returncode != 0, result.stdout + result.stderr
        return result


@pytest.fixture
def installer(tmp_path: Path) -> Callable[[str], Installer]:
    if os.name != "posix" or shutil.which("bash") is None:
        pytest.skip("Requires POSIX bash")

    def make(mode: str) -> Installer:
        system = "Darwin" if mode == "macos" else "Linux"
        appimage = mode == "appimage"
        data_root = tmp_path / "paths $ & ' \" \\n"
        old = (
            data_root
            / "installed"
            / (
                "RimSort.AppImage"
                if appimage
                else "Custom RimSort.app"
                if mode == "macos"
                else "RimSort"
            )
        )
        executable = "Contents/MacOS/RimSort" if mode == "macos" else "RimSort"
        payload = (
            data_root
            / "download"
            / (
                "new.AppImage"
                if appimage
                else "RimSort.app"
                if mode == "macos"
                else "payload"
            )
        )
        old_binary = old if appimage else old / executable
        new_binary = payload if appimage else payload / executable
        for binary, data in ((old_binary, b"old"), (new_binary, b"new")):
            binary.parent.mkdir(parents=True, exist_ok=True)
            binary.write_bytes(data)
        if not appimage:
            (old / "old-only.txt").write_text("old application data")
            (payload / "new-only.txt").write_text("new application data")
            (payload / "alias-to-new").symlink_to("new-only.txt")
            (old / "linked-data").symlink_to(tmp_path / "external-data")
            (tmp_path / "external-data").write_text("preserve")
        old_binary.chmod(0o755)
        script = (
            tmp_path / "mount" / "update.sh"
            if appimage
            else old_binary.parent / "update.sh"
        )
        script.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(Path(__file__).parents[2] / "update.sh", script)
        config = tmp_path / "config.json"
        names = (
            "mv",
            "cp",
            "ln",
            "chmod",
            "stat",
            "rsync",
            "uname",
            "killall",
            "sleep",
            "open",
            "nohup",
            "pgrep",
        )
        config.write_text(
            json.dumps(
                {
                    "mode": mode,
                    "system": system,
                    "old": str(old),
                    "payload": str(payload),
                    "executable": executable,
                    "trace": str(tmp_path / "commands.jsonl"),
                    "commands": {name: shutil.which(name) for name in names},
                }
            )
        )
        commands = tmp_path / "commands"
        commands.mkdir()
        for name in names:
            command = commands / name
            command.write_text(f"#!{sys.executable}\n" + _COMMAND_WRAPPER)
            command.chmod(0o755)
        environment = {
            **os.environ,
            "PATH": str(commands) + os.pathsep + os.environ["PATH"],
            "UPDATE_TEST_CONFIG": str(config),
        }
        environment.pop("APPIMAGE", None)
        if appimage:
            environment["APPIMAGE"] = str(old)
        return Installer(
            tmp_path, old, payload, script, executable, environment, config, mode
        )

    return make


@pytest.mark.parametrize("mode", ["macos", "linux", "appimage"])
def test_failed_copy_keeps_installed_application(
    installer: Callable[[str], Installer], mode: str
) -> None:
    update = installer(mode)
    update.fail("copy")
    update.assert_original()


@pytest.mark.parametrize("mode", ["macos", "linux", "appimage"])
@pytest.mark.parametrize("fault", ["permissions", "backup", "commit", "interrupt_copy"])
def test_failed_replacement_recovers_original(
    installer: Callable[[str], Installer], mode: str, fault: str
) -> None:
    update = installer(mode)
    update.fail(fault)
    update.assert_original()
    if mode != "appimage":
        assert (update.old / "old-only.txt").read_text() == "old application data"
        assert (update.old / "linked-data").is_symlink()
        assert (update.root / "external-data").read_text() == "preserve"


@pytest.mark.parametrize("mode", ["macos", "linux"])
def test_interruption_after_backup_restores_original(
    installer: Callable[[str], Installer], mode: str
) -> None:
    update = installer(mode)
    update.fail("interrupt_backup")
    update.assert_original()


@pytest.mark.parametrize("mode", ["macos", "linux"])
@pytest.mark.parametrize("fault", ["rollback", "target_appears"])
def test_unavailable_rollback_preserves_recovery_files(
    installer: Callable[[str], Installer], mode: str, fault: str
) -> None:
    update = installer(mode)
    result = update.fail(fault)
    roots = list(update.old.parent.glob(".rimsort-update.*"))
    assert len(roots) == 1
    previous = roots[0] / "old" / update.old.name
    assert update.binary(previous).read_bytes() == b"old"
    assert update.binary(roots[0] / "new" / update.old.name).read_bytes() == b"new"
    assert str(previous) in result.stdout
    if fault == "target_appears":
        assert (
            update.old / "unexpected.txt"
        ).read_text() == "preserve competing destination"


@pytest.mark.parametrize("mode", ["macos", "linux", "appimage"])
def test_successful_replacement(
    installer: Callable[[str], Installer], mode: str
) -> None:
    update = installer(mode)
    result = update.run()

    assert result.returncode == 0, result.stdout + result.stderr
    assert update.binary().read_bytes() == b"new"
    assert os.access(update.binary(), os.X_OK)
    assert not update.payload.exists()
    assert not list(update.old.parent.glob(".rimsort-update.*"))
    if mode == "appimage":
        assert update.old.with_suffix(".AppImage.bak").read_bytes() == b"old"
    else:
        assert not (update.old / "old-only.txt").exists()
        assert (update.old / "new-only.txt").read_text() == "new application data"
        assert (update.old / "alias-to-new").is_symlink()
        assert (update.old / "alias-to-new").read_text() == "new application data"
        assert (update.root / "external-data").read_text() == "preserve"


@pytest.mark.parametrize("mode", ["macos", "linux", "appimage"])
def test_dry_run_does_not_change_or_launch_installation(
    installer: Callable[[str], Installer], mode: str
) -> None:
    update = installer(mode)
    result = update.run(dry_run=True)

    assert result.returncode == 0, result.stdout + result.stderr
    update.assert_original()
    assert not any(
        call["command"] in {"killall", "open", "nohup"} for call in update.calls()
    )


@pytest.mark.parametrize("fault", ["", "backup_copy", "backup"])
def test_appimage_preserves_existing_backup(
    installer: Callable[[str], Installer], fault: str
) -> None:
    update = installer("appimage")
    backup = update.old.with_suffix(".AppImage.bak")
    backup.write_bytes(b"previous usable backup")
    result = update.run(fault)

    assert result.returncode != 0
    assert update.binary().read_bytes() == b"old"
    assert backup.read_bytes() == b"previous usable backup"


def test_appimage_backup_copy_fallback(installer: Callable[[str], Installer]) -> None:
    update = installer("appimage")
    result = update.run("backup_copy")

    assert result.returncode == 0, result.stdout + result.stderr
    assert update.old.read_bytes() == b"new"
    assert update.old.with_suffix(".AppImage.bak").read_bytes() == b"old"


def test_successful_startup_allows_next_appimage_update(
    installer: Callable[[str], Installer],
    monkeypatch: pytest.MonkeyPatch,
    qtbot: QtBot,
) -> None:
    update = installer("appimage")
    first = update.run()
    assert first.returncode == 0, first.stdout + first.stderr
    backup = update.old.with_suffix(".AppImage.bak")
    assert backup.read_bytes() == b"old"
    monkeypatch.setenv("APPIMAGE", str(update.old))
    controller = AppController.__new__(AppController)
    QObject.__init__(controller)
    window = QMainWindow()
    qtbot.addWidget(window)
    window.show()
    controller.main_window = MagicMock(wraps=window)

    controller._cleanup_appimage_backup()

    assert not backup.exists()
    update.payload.write_bytes(b"next version")
    second = update.run()
    assert second.returncode == 0, second.stdout + second.stderr
    assert update.old.read_bytes() == b"next version"
    assert backup.read_bytes() == b"new"


@pytest.mark.parametrize("system", ["Darwin", "Linux"])
def test_directory_swap_requires_writable_parent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, system: str
) -> None:
    app = (
        tmp_path / "install" / "RimSort.app" / "Contents" / "MacOS"
        if system == "Darwin"
        else tmp_path / "install" / "RimSort"
    )
    parent = tmp_path / "install"
    monkeypatch.delenv("APPIMAGE", raising=False)
    monkeypatch.setattr(AppInfo, "application_folder", app)
    monkeypatch.setattr(os, "access", lambda path, _mode: Path(path) != parent)
    manager = MagicMock(spec=UpdateManager)
    manager._system = system
    manager._elevation_needed = None

    assert UpdateManager._check_needs_elevation(manager) is True


@pytest.mark.parametrize("mode", ["macos", "linux", "appimage"])
def test_installed_application_cannot_be_its_own_update(
    installer: Callable[[str], Installer], mode: str
) -> None:
    update = installer(mode)
    update.payload = update.old
    result = update.run()

    assert result.returncode != 0
    update.assert_original()


@pytest.mark.parametrize("mode", ["macos", "linux"])
def test_missing_replacement_executable_keeps_original(
    installer: Callable[[str], Installer], mode: str
) -> None:
    update = installer(mode)
    (update.payload / update.executable).unlink()
    result = update.run()

    assert result.returncode != 0
    assert update.binary().read_bytes() == b"old"
    assert update.payload.exists()


@pytest.mark.parametrize("mode", ["macos", "linux", "appimage"])
@pytest.mark.parametrize("fault", ["mounted_target", "device_changed"])
def test_filesystem_change_does_not_replace_installation(
    installer: Callable[[str], Installer], mode: str, fault: str
) -> None:
    update = installer(mode)
    update.fail(fault)
    update.assert_original()
    assert not any(call["command"] == "killall" for call in update.calls())


@pytest.mark.parametrize("kind", ["directory", "dangling_symlink"])
def test_appimage_preserves_nonfile_backup(
    installer: Callable[[str], Installer], kind: str
) -> None:
    update = installer("appimage")
    backup = update.old.with_suffix(".AppImage.bak")
    target = update.root / "unowned-target"
    if kind == "directory":
        backup.mkdir()
        (backup / "marker").write_text("preserve")
    else:
        backup.symlink_to(target)
    update.fail()
    update.assert_original()
    if kind == "directory":
        assert (backup / "marker").read_text() == "preserve"
    else:
        assert backup.is_symlink()
        assert not target.exists()


@pytest.mark.parametrize("mode", ["macos", "linux"])
def test_forced_termination_leaves_manual_recovery_copy(
    installer: Callable[[str], Installer], mode: str
) -> None:
    update = installer(mode)
    result = update.run("hard_interrupt_backup")

    assert result.returncode != 0
    roots = list(update.old.parent.glob(".rimsort-update.*"))
    assert len(roots) == 1
    previous = roots[0] / "old" / update.old.name
    assert str(roots[0]) in result.stdout
    assert update.binary(previous).read_bytes() == b"old"
    assert not update.old.exists()
    subprocess.run(["mv", str(previous), str(update.old.parent) + "/"], check=True)
    assert update.binary().read_bytes() == b"old"


@pytest.mark.parametrize("mode", ["macos", "linux"])
def test_existing_directory_symlink_keeps_its_identity(
    installer: Callable[[str], Installer], mode: str
) -> None:
    update = installer(mode)
    real = update.root / "physical" / update.old.name
    real.parent.mkdir()
    update.old.rename(real)
    update.old.symlink_to(real, target_is_directory=True)
    result = update.run()

    assert result.returncode == 0, result.stdout + result.stderr
    assert update.old.is_symlink()
    assert update.old.resolve() == real
    assert update.binary().read_bytes() == b"new"


@pytest.mark.skipif(
    sys.platform == "win32" or (hasattr(os, "geteuid") and os.geteuid() == 0),
    reason="Requires non-root POSIX permissions",
)
@pytest.mark.parametrize("mode", ["macos", "linux", "appimage"])
def test_read_only_parent_leaves_original_untouched(
    installer: Callable[[str], Installer], mode: str
) -> None:
    update = installer(mode)
    update.old.parent.chmod(0o555)
    try:
        result = update.run()
    finally:
        update.old.parent.chmod(0o755)

    assert result.returncode != 0, result.stdout + result.stderr
    assert update.binary().read_bytes() == b"old"
    assert update.payload.exists()
    assert not any(call["command"] == "killall" for call in update.calls())


@pytest.mark.skipif(sys.platform != "darwin", reason="Requires native macOS xattr")
def test_directory_replacement_preserves_bundle_metadata(
    installer: Callable[[str], Installer],
) -> None:
    update = installer("macos")
    source_file = update.payload / update.executable
    attribute = "com.rimsort.update-test"
    subprocess.run(["xattr", "-w", attribute, "metadata", str(source_file)], check=True)
    result = update.run()

    assert result.returncode == 0, result.stdout + result.stderr
    attribute_result = subprocess.run(
        ["xattr", "-p", attribute, str(update.binary())],
        check=True,
        capture_output=True,
        text=True,
    )
    assert attribute_result.stdout.strip() == "metadata"


@pytest.mark.parametrize("mode", ["macos", "linux"])
def test_relative_source_is_cleaned_before_relaunch(
    installer: Callable[[str], Installer], mode: str
) -> None:
    update = installer(mode)
    original_source = update.payload
    update.payload = original_source.relative_to(update.root)
    result = update.run()

    assert result.returncode == 0, result.stdout + result.stderr
    assert update.binary().read_bytes() == b"new"
    assert not original_source.exists()


@pytest.mark.skipif(
    sys.platform == "win32" or (hasattr(os, "geteuid") and os.geteuid() == 0),
    reason="Requires non-root POSIX permissions",
)
def test_appimage_source_cleanup_failure_keeps_valid_replacement(
    installer: Callable[[str], Installer],
) -> None:
    update = installer("appimage")
    update.payload.parent.chmod(0o555)
    try:
        result = update.run()
    finally:
        update.payload.parent.chmod(0o755)

    assert result.returncode == 0, result.stdout + result.stderr
    assert update.binary().read_bytes() == b"new"
    assert update.old.with_suffix(".AppImage.bak").read_bytes() == b"old"
    assert update.payload.exists()

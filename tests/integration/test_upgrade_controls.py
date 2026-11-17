"""Portable tests for the native updater harness's safety and failure boundaries."""

import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import psutil
import pytest

from tests.integration import native_filesystem
from tests.integration.archive_probe import msi_process
from tests.integration.native_filesystem import (
    exhaust_volume,
    limited_volume,
    windows_read_lock,
)
from tests.integration.test_packaged_upgrade import install_baseline, unpack
from tests.integration.upgrade_process import contained, launch, stop, terminal


def test_msi_boundary_preserves_handoff_and_contains_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staged = tmp_path / "staging/candidate.msi"
    staged.parent.mkdir()
    staged.write_bytes(b"fixture")
    (tmp_path / "events").mkdir()
    monkeypatch.setenv("RIMSORT_UPGRADE_TEST_PYTHON", sys.executable)
    calls = []

    def create(command: object, **kwargs: object) -> object:
        calls.append((command, kwargs))
        return "process"

    command = [
        "msiexec",
        "/i",
        str(staged),
        "/passive",
        "/norestart",
        "/log",
        str(tmp_path / "profile/logs/updater.log"),
    ]
    supervisor = msi_process(tmp_path, create)
    assert supervisor(command) == "process"
    assert (
        json.loads((tmp_path / "events/msi-handoff.json").read_text())["command"]
        == command
    )
    forwarded, options = calls.pop()
    assert isinstance(forwarded, list) and forwarded[0:2] == [sys.executable, "-I"]
    assert forwarded[-3:] == ["msi", str(tmp_path), str(staged)] and options == {}
    assert supervisor(["other", "command"], cwd="unchanged") == "process"
    assert calls == [(["other", "command"], {"cwd": "unchanged"})]
    with pytest.raises(RuntimeError, match="Unexpected MSI handoff"):
        supervisor(command[:-1])


def test_installer_paths_and_stop_commands_refuse_unowned_targets(
    tmp_path: Path,
) -> None:
    with pytest.raises(RuntimeError, match="escaped fixture"):
        contained(tmp_path, str(tmp_path.parent / "unowned"))
    with pytest.raises(RuntimeError, match="Unexpected process termination"):
        stop(tmp_path, ["unrelated-application"])
    with pytest.raises(RuntimeError, match="Unexpected terminal AppleScript"):
        terminal(tmp_path, ["-e", 'tell application "Finder" to quit'])


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX executable fixture")
def test_supervised_launch_survives_retired_macos_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "fixture.app/Contents/MacOS/RimSort"
    target.parent.mkdir(parents=True)
    target.write_text(
        f"#!{sys.executable}\nimport os\nfrom pathlib import Path\nPath(os.environ['RIMSORT_UPGRADE_TEST_ROOT'], 'cwd.txt').write_text(os.getcwd())\nraise SystemExit(7)\n"
    )
    target.chmod(0o755)
    events = tmp_path / "events"
    events.mkdir()
    (events / "release").touch()
    retired = tmp_path / "retired"
    retired.mkdir()
    original = Path.cwd()
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setenv("RIMSORT_UPGRADE_TEST_ROOT", str(tmp_path))
    monkeypatch.setenv("RIMSORT_UPGRADE_TEST_EXECUTABLE", str(target))
    try:
        os.chdir(retired)
        retired.rmdir()
        # The real installer can retire its own cwd. The open supervisor must
        # not pass that directory to the ordinary macOS executable.
        assert launch(tmp_path, [str(tmp_path / "fixture.app")]) == 7
    finally:
        os.chdir(original)
    assert (tmp_path / "cwd.txt").read_text() == str(tmp_path)
    assert json.loads((events / "exit.json").read_text()) == {"code": 7}


def test_msi_supervisor_refuses_missing_transform(tmp_path: Path) -> None:
    helper = Path(__file__).with_name("upgrade_process.py")
    package = tmp_path / "candidate.msi"
    package.write_bytes(b"fixture")
    (tmp_path / "events").mkdir()
    result = subprocess.run(
        [sys.executable, "-I", str(helper), "msi", str(tmp_path), str(package)],
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    assert result.returncode != 0
    assert "Missing test-only launch transform" in result.stderr
    assert not (tmp_path / "events/installer-exit.json").exists()


def test_stop_refuses_reused_pid(tmp_path: Path) -> None:
    (tmp_path / "events").mkdir()
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        identity = {
            "pid": child.pid,
            "started": psutil.Process(child.pid).create_time() + 1,
        }
        (tmp_path / "events/old-process.json").write_text(json.dumps(identity))
        arguments = (
            ["/F", "/im", "RimSort.exe"]
            if sys.platform == "win32"
            else ["-q", "RimSort"]
        )
        with pytest.raises(RuntimeError, match="PID was reused"):
            stop(tmp_path, arguments)
        assert child.poll() is None
    finally:
        child.terminate()
        child.wait(timeout=10)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX executable mode")
@pytest.mark.parametrize("nested", [False, True])
def test_restore_zip_layout_and_executable_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, nested: bool
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    archive = tmp_path / "backup.zip"
    name = "RimSort/RimSort" if nested else "RimSort"
    info = zipfile.ZipInfo(name)
    info.create_system = 3
    info.external_attr = 0o100755 << 16
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr(info, b"executable fixture")
    restored = unpack(archive, tmp_path / "restored")
    assert (restored / "RimSort").read_bytes() == b"executable fixture"
    assert os.access(restored / "RimSort", os.X_OK)


@pytest.mark.parametrize("operation", ["lock", "volume", "exhaust"])
def test_filesystem_controls_refuse_non_ci_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    with pytest.raises(RuntimeError, match="disposable native CI runner"):
        if operation == "lock":
            with windows_read_lock(tmp_path, tmp_path / "RimSort.exe"):
                pytest.fail("Unscoped file lock was acquired")
        elif operation == "volume":
            with limited_volume(tmp_path, 128 * 1024 * 1024):
                pytest.fail("Unscoped filesystem was mounted")
        else:
            exhaust_volume(tmp_path, tmp_path)


@pytest.fixture
def ci_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    owner = tmp_path / "task"
    root = owner / "case"
    root.mkdir(parents=True)
    monkeypatch.setenv("RIMSORT_UPGRADE_ROOT", str(owner))
    return root


@pytest.fixture
def linux_ci_root(ci_root: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(sys, "platform", "linux")
    return ci_root


def test_filesystem_controls_refuse_a_mount_outside_owned_root(
    tmp_path: Path, linux_ci_root: Path
) -> None:
    with (
        pytest.raises(RuntimeError, match="escaped its runner task root"),
        limited_volume(tmp_path, 128 * 1024 * 1024),
    ):
        pytest.fail("Unowned filesystem was mounted")


def test_exhaustion_refuses_an_unowned_filesystem(
    linux_ci_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = linux_ci_root
    volume = root / "volume"
    volume.mkdir()
    monkeypatch.setattr(
        native_filesystem,
        "mount_identity",
        lambda _: {"source": "user-volume", "fstype": "ext4", "target": str(volume)},
    )
    with pytest.raises(RuntimeError, match="isolated Linux mount"):
        exhaust_volume(root, volume)
    assert list(volume.iterdir()) == []


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX mount safety control")
def test_volume_cleanup_refuses_a_changed_mount(
    linux_ci_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = linux_ci_root
    foreign = {
        "source": "user-volume",
        "fstype": "tmpfs",
        "target": str(root / "volume"),
    }
    states = iter([None, foreign, foreign])
    monkeypatch.setattr(native_filesystem, "mount_identity", lambda _: next(states))
    calls: list[list[str]] = []

    def command(_root: Path, args: list[str], *_args: object, **_kwargs: object) -> int:
        calls.append(args)
        return 0

    monkeypatch.setattr(native_filesystem, "run_external", command)
    with (
        pytest.raises(RuntimeError, match="Refusing to unmount"),
        limited_volume(root, 128 * 1024 * 1024),
    ):
        pytest.fail("Foreign mount was accepted")
    assert len(calls) == 1 and calls[0][:3] == ["sudo", "-n", "mount"]


@pytest.mark.skipif(sys.platform != "win32", reason="Native Win32 file sharing")
def test_windows_lock_allows_backup_reads_and_releases(
    ci_root: Path,
) -> None:
    root = ci_root
    target = root / "RimSort.exe"
    target.write_bytes(b"previous executable")
    with windows_read_lock(root, target):
        assert target.read_bytes() == b"previous executable"
        with pytest.raises(PermissionError):
            target.write_bytes(b"replacement executable")
    target.write_bytes(b"replacement executable")
    assert target.read_bytes() == b"replacement executable"


@pytest.mark.skipif(sys.platform != "win32", reason="Native Windows command parser")
def test_windows_baseline_installer_preserves_spaced_arguments(
    ci_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = ci_root
    (root / "events").mkdir()
    (root / "events/configured.json").write_text(
        json.dumps({"backups": str(root / "backups")})
    )
    bootstrap = root / "script with spaces"
    bootstrap.mkdir()
    (bootstrap / "update.bat").write_text('@echo off\n> "%~2" echo %~1\nexit /b 23\n')
    installed = root / "installed with spaces"
    installed.mkdir()
    stage = root / "stage with spaces"
    stage.mkdir()
    monkeypatch.setattr(
        "tests.integration.test_packaged_upgrade.run_external", lambda *_args, **_kw: 0
    )
    monkeypatch.setattr(
        "tests.integration.test_packaged_upgrade.unpack", lambda *_args: stage
    )
    child = install_baseline(
        root, installed, bootstrap, root / "input.zip", dict(os.environ)
    )
    try:
        assert child.wait(timeout=15) == 23
    finally:
        if child.poll() is None:
            child.terminate()
            child.wait(timeout=15)
    assert (root / "profile/logs/updater.log").read_text().strip() == str(stage)

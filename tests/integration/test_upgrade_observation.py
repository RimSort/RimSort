"""Regressions for installer results, backup integrity and real partial writes."""

import json
import shlex
import shutil
import subprocess
import sys
import zipfile
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from subprocess import Popen

import psutil
import pytest

from tests.integration import test_packaged_upgrade as harness
from tests.integration.archive_probe import linux_process
from tests.integration.upgrade_process import partial_copy, stop_processes


@pytest.fixture
def bash() -> str:
    executable = shutil.which("bash")
    assert executable is not None, "Bash is required for native shell controls"
    return executable


@pytest.mark.skipif(sys.platform == "win32", reason="Real POSIX shell control")
@pytest.mark.parametrize("as_list", [False, True])
def test_linux_installer_supervisor_preserves_command_and_records_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, as_list: bool
) -> None:
    monkeypatch.setenv("RIMSORT_UPGRADE_TEST_PYTHON", sys.executable)
    monkeypatch.setenv("RIMSORT_UPGRADE_TEST_ROOT", str(tmp_path))
    (tmp_path / "events").mkdir()
    script = tmp_path / "update.sh"
    script.write_text(
        '#!/bin/sh\nprintf "%s" "$1" > "$RIMSORT_UPGRADE_TEST_ROOT/argument.txt"\nexit 23\n'
    )
    script.chmod(0o755)
    arguments = [str(script), "argument with 'quotes'"]
    command = arguments if as_list else shlex.join(arguments)
    process = linux_process(tmp_path, subprocess.Popen)(
        command, shell=not as_list, cwd=str(tmp_path)
    )
    assert isinstance(process, Popen)
    assert process.wait(timeout=15) == 23
    assert (tmp_path / "argument.txt").read_text() == arguments[1]
    assert json.loads((tmp_path / "events/installer-exit.json").read_text()) == {
        "code": 23
    }


def test_partial_copy_changes_destination_before_reporting_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    source, target = tmp_path / "source", tmp_path / "install"
    source.mkdir()
    target.mkdir()
    (tmp_path / "events").mkdir()
    payload = b"unchanged candidate bytes" * 1000
    (source / "RimSort.exe").write_bytes(payload)
    (target / "RimSort.exe").write_bytes(payload)
    assert partial_copy(tmp_path, [str(source), str(target)]) == 8
    damaged = (target / "RimSort.exe").read_bytes()
    assert 0 < len(damaged) < len(payload) and payload.startswith(damaged)
    assert (source / "RimSort.exe").read_bytes() == payload
    assert json.loads((tmp_path / "events/copy-failed.json").read_text())[
        "bytes"
    ] == len(damaged)


@pytest.mark.parametrize("corrupt", [False, True])
def test_backup_round_trip_rejects_incomplete_or_invalid_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, corrupt: bool
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    installed = tmp_path / "install"
    installed.mkdir()
    (installed / "RimSort").write_bytes(b"original executable")
    (installed / "required-resource").write_bytes(b"preserve resource")
    archive = tmp_path / "backup.zip"
    if corrupt:
        archive.write_bytes(b"not a valid archive")
    else:
        with zipfile.ZipFile(archive, "w") as output:
            output.write(installed / "RimSort", "RimSort")
    with pytest.raises((zipfile.BadZipFile, AssertionError)):
        harness.verify_backup(tmp_path, archive, harness.manifest(installed))


def test_candidate_success_rejects_late_installer_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    candidate = tmp_path / "input/RimSort"
    candidate.mkdir(parents=True)
    (candidate / "RimSort").write_bytes(b"candidate executable")
    archive = tmp_path / "candidate.tar.gz"
    archive.write_bytes(b"controlled download")
    fixture = tmp_path / "fixture"
    fixture.mkdir()

    @contextmanager
    def environment(root: Path, target: Path, fault: str) -> Generator[dict[str, str]]:
        (root / "events").mkdir()
        yield {}

    def configure(root: Path, target: Path, env: dict[str, str]) -> None:
        backups = root / "profile/backups"
        backups.mkdir(parents=True)
        (root / "fixture/local").mkdir(parents=True)
        with zipfile.ZipFile(backups / "RimSort_Backup_fixture.zip", "w") as output:
            output.write(candidate / "RimSort", "RimSort")
        (root / "events/configured.json").write_text(
            json.dumps({"backups": str(backups)})
        )

    def update(root: Path, *args: object, **kwargs: object) -> None:
        for name, data in {
            "relaunch": {},
            "installer-exit": {"code": 123},
            "exit": {"code": 0},
        }.items():
            (root / "events" / f"{name}.json").write_text(json.dumps(data))

    @contextmanager
    def serve(root: Path, name: str) -> Generator[tuple[str, list[str]]]:
        yield "http://fixture.invalid", [f"GET /{name} 200"]

    monkeypatch.setattr(harness, "environment", environment)
    monkeypatch.setattr(harness, "configure", configure)
    monkeypatch.setattr(harness, "update", update)
    monkeypatch.setattr(harness, "serve", serve)
    monkeypatch.setattr(harness, "stop_all", lambda root: None)
    monkeypatch.setattr(harness, "healthy_and_close", lambda root, target: None)
    with pytest.raises(AssertionError, match="Installer exited with 123"):
        harness.test_native_packaged_upgrade(
            harness.Inputs(candidate, candidate, archive), fixture, "candidate"
        )


@pytest.mark.skipif(sys.platform == "win32", reason="Real system-shell cleanup")
@pytest.mark.parametrize("mode", ["installer", "direct", "terminal"])
def test_cleanup_retains_system_shell_descendants(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str, bash: str
) -> None:
    if mode == "terminal" and sys.platform != "darwin":
        pytest.skip("Native AppleScript compilation requires macOS")
    (tmp_path / "events").mkdir()
    script = tmp_path / "fixture.sh"
    script.write_text(
        f'#!{bash}\nprintf "%s" "$$" > "$RIMSORT_UPGRADE_TEST_ROOT/shell.pid"\n'
        'sleep 60 &\nchild=$!\nprintf "%s" "$child" > "$RIMSORT_UPGRADE_TEST_ROOT/sleep.pid"\nwait "$child"\n'
    )
    env = {**harness.clean_environment(), "RIMSORT_UPGRADE_TEST_ROOT": str(tmp_path)}
    helper = harness.PROCESS
    if mode == "direct":
        command = [bash, str(script)]
    elif mode == "terminal":
        shell_command = (
            "/bin/bash " + shlex.quote(str(script)) + '; read -p "Press enter to close"'
        )
        escaped = shell_command.replace("\\", "\\\\").replace('"', '\\"')
        command = [
            sys.executable,
            "-I",
            str(helper),
            "osascript",
            str(tmp_path),
            "-e",
            f'tell app "Terminal" to do script "{escaped}"',
        ]
    else:
        request = tmp_path / "events/installer-command.json"
        request.write_text(
            json.dumps(
                {
                    "command": [bash, str(script)],
                    "options": {"cwd": str(tmp_path)},
                }
            )
        )
        command = [
            sys.executable,
            "-I",
            str(helper),
            "installer",
            str(tmp_path),
            str(request),
        ]
    runner = subprocess.Popen(command, env=env)
    supervisor = psutil.Process(runner.pid)
    retained = [supervisor]
    try:
        harness.wait_for((tmp_path / "sleep.pid").exists, "real shell descendant")
        retained.extend(
            psutil.Process(int((tmp_path / name).read_text()))
            for name in ("shell.pid", "sleep.pid")
        )
        # Model an OS that hides system-process environments: ownership must
        # propagate from a retained supervisor instead of a child marker.
        monkeypatch.setattr(harness, "owned", lambda root: [supervisor])
        if mode == "direct":
            stop_processes([supervisor])
        else:
            harness.stop_all(tmp_path)
        assert all(
            not process.is_running() or process.status() == psutil.STATUS_ZOMBIE
            for process in retained
        )
        runner.wait(timeout=10)
    finally:
        for process in reversed(retained):
            try:
                if process.is_running():
                    process.kill()
            except psutil.NoSuchProcess:
                pass
        runner.wait(timeout=10)


@pytest.mark.skipif(sys.platform == "win32", reason="Real native-child timeout control")
def test_baseline_backup_timeout_stops_native_descendants(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bash: str
) -> None:
    (tmp_path / "events").mkdir()
    (tmp_path / "events/configured.json").write_text(
        json.dumps({"backups": str(tmp_path / "backups")})
    )
    script = tmp_path / "archive-fixture.sh"
    script.write_text(
        f'#!{bash}\nprintf "%s" "$$" > "$RIMSORT_UPGRADE_TEST_ROOT/shell.pid"\n'
        'sleep 60 &\nchild=$!\nprintf "%s" "$child" > "$RIMSORT_UPGRADE_TEST_ROOT/sleep.pid"\nwait "$child"\n'
    )
    bootstrap = tmp_path / "bootstrap/Fixture.app"
    binary = harness.executable(bootstrap)
    binary.parent.mkdir(parents=True)
    binary.write_text(
        f"#!{sys.executable}\nimport subprocess\nsubprocess.Popen([{bash!r}, {str(script)!r}]).wait()\n"
    )
    binary.chmod(0o755)
    retained: list[psutil.Process] = []

    class BackupTimeout(Popen[bytes]):
        def force_timeout(self, timeout: float | None) -> None:
            if timeout == 120:
                files = [tmp_path / name for name in ("shell.pid", "sleep.pid")]
                harness.wait_for(
                    lambda: all(path.exists() and path.read_text() for path in files),
                    "backup native children",
                )
                retained.extend(psutil.Process(int(path.read_text())) for path in files)
                raise subprocess.TimeoutExpired(self.args, timeout)

        def wait(self, timeout: float | None = None) -> int:
            self.force_timeout(timeout)
            return super().wait(timeout=timeout)

        def communicate(
            self, input: bytes | None = None, timeout: float | None = None
        ) -> tuple[bytes, bytes]:
            self.force_timeout(timeout)
            return super().communicate(input=input, timeout=timeout)

    monkeypatch.setattr(subprocess, "Popen", BackupTimeout)
    env = {**harness.clean_environment(), "RIMSORT_UPGRADE_TEST_ROOT": str(tmp_path)}
    try:
        with pytest.raises(subprocess.TimeoutExpired):
            harness.install_baseline(
                tmp_path,
                tmp_path / "installed",
                bootstrap,
                tmp_path / "unused.tar.gz",
                env,
            )
        harness.stop_all(tmp_path)
        assert retained and all(
            not process.is_running() or process.status() == psutil.STATUS_ZOMBIE
            for process in retained
        )
    finally:
        for process in retained:
            try:
                if process.is_running():
                    process.kill()
            except psutil.NoSuchProcess:
                pass

"""Opt-in native archive upgrades, plus portable controls for their harness."""

import ctypes
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tarfile
import zipfile
from collections.abc import Generator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path

import psutil
import pytest

from tests.integration.native_filesystem import (
    MIB,
    exhaust_volume,
    limited_volume,
    windows_read_lock,
)
from tests.integration.test_appimage_upgrade import (
    clean_environment,
    digest,
    download_baseline,
    gui_pid,
    quit_gui,
    read,
    serve,
    wait_for,
    write_executable,
)
from tests.integration.test_windows_msi import close_window, print_diagnostics
from tests.integration.upgrade_process import run_external, stop_processes

PROBE = Path(__file__).with_name("archive_probe.py")
PROCESS = Path(__file__).with_name("upgrade_process.py")
RELEASES = {
    "darwin": (
        "Darwin_arm64.tar.gz",
        "a4295f2f81320cf7b012442f69ff2a84e1225863d92283b1ec3ac5df21a92c74",
    ),
    "linux": (
        "Ubuntu-22.04_x86_64.tar.gz",
        "a4f13cd74ce0d7f081f7f6996a8859c967e23e84a0fb670796b46afca39c2fe2",
    ),
    "linux24": (
        "Ubuntu-24.04_x86_64.tar.gz",
        "c30b485836a7c7933f9baf6dee2f1036ea6be51ade461422e06ede2665625e8c",
    ),
    "win32": (
        "Windows_x86_64.zip",
        "2eb3584c26779e882a0143af0549f0b480bdedb687f7faf5e1d56cc79f97631c",
    ),
}


def executable(directory: Path) -> Path:
    if sys.platform == "darwin":
        return directory / "Contents/MacOS/RimSort"
    return directory / ("RimSort.exe" if sys.platform == "win32" else "RimSort")


def manifest(directory: Path) -> dict[str, str]:
    return {
        path.relative_to(directory).as_posix(): digest(path)
        for path in directory.rglob("*")
        if path.is_file()
    }


def verify_signature(directory: Path) -> None:
    if sys.platform == "darwin":
        subprocess.run(
            ["codesign", "--verify", "--deep", "--strict", str(directory)],
            check=True,
            timeout=60,
        )


def unpack(archive: Path, destination: Path) -> Path:
    destination.mkdir(parents=True)
    if sys.platform == "darwin":
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
            timeout=90,
        )
    elif archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as package:
            package.extractall(destination)
            if sys.platform != "win32":
                for item in package.infolist():
                    mode = stat.S_IMODE(item.external_attr >> 16)
                    if mode:
                        (destination / item.filename).chmod(mode)
    else:
        with tarfile.open(archive) as package:
            package.extractall(destination, filter="data")
    candidates = (
        [destination]
        if executable(destination).is_file()
        else [
            path
            for path in destination.iterdir()
            if path.is_dir() and executable(path).is_file()
        ]
    )
    assert len(candidates) == 1, (
        f"Ambiguous package root: {list(destination.iterdir())}"
    )
    return candidates[0]


def package(directory: Path, destination: Path) -> None:
    if sys.platform == "darwin":
        subprocess.run(
            [
                "/usr/bin/tar",
                "--mac-metadata",
                "--acls",
                "--xattrs",
                "-czf",
                str(destination),
                "-C",
                str(directory.parent),
                "--",
                f"./{directory.name}",
            ],
            check=True,
            timeout=90,
        )
    elif sys.platform == "win32":
        with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as output:
            for path in directory.rglob("*"):
                output.write(path, path.relative_to(directory.parent))
    else:
        with tarfile.open(destination, "w:gz") as output:
            output.add(directory, arcname=directory.name)


def verify_backup(root: Path, archive: Path, expected: dict[str, str]) -> Path:
    restored = unpack(archive, root / "backup-verified")
    assert manifest(restored) == expected, (
        "Backup does not match the previous installation"
    )
    verify_signature(restored)
    return restored


@dataclass(frozen=True)
class Inputs:
    baseline: Path
    candidate: Path
    archive: Path


@pytest.fixture(scope="session")
def archive_inputs(tmp_path_factory: pytest.TempPathFactory) -> Inputs:
    candidate_arg = os.environ.get("RIMSORT_UPGRADE_CANDIDATE_DIR")
    if not candidate_arg:
        pytest.skip("Requires explicit native packaged inputs")
    root = Path(os.environ["RIMSORT_UPGRADE_ROOT"]).resolve(strict=True)
    inputs = tmp_path_factory.mktemp("archive-inputs").resolve()
    assert inputs.is_relative_to(root), "Pytest data escaped task root"
    candidate = Path(candidate_arg).resolve(strict=True)
    assert candidate.is_relative_to(root) and executable(candidate).is_file()
    if sys.platform != "darwin":
        assert os.environ.get("GITHUB_ACTIONS") == "true", (
            "Windows/Linux native tests require disposable CI"
        )
    if sys.platform == "linux":
        assert (
            os.getuid() != 0 and shutil.which("xdotool") and os.environ.get("DISPLAY")
        )
    platform_key = os.environ.get("RIMSORT_UPGRADE_PLATFORM", sys.platform)
    assert platform_key in (
        {"linux", "linux24"} if sys.platform == "linux" else {sys.platform}
    )
    suffix, checksum = RELEASES[platform_key]
    baseline_archive = inputs / f"baseline.{suffix.rsplit('.', 1)[-1]}"
    download_baseline(
        baseline_archive,
        f"https://github.com/RimSort/RimSort/releases/download/v1.17.4/RimSort-v1.17.4-{suffix}",
        checksum,
    )
    baseline = unpack(baseline_archive, inputs / "baseline")
    archive = inputs / (
        "candidate.zip" if sys.platform == "win32" else "candidate.tar.gz"
    )
    package(candidate, archive)
    return Inputs(baseline, candidate, archive)


def owned(root: Path) -> list[psutil.Process]:
    processes = []
    for process in psutil.process_iter():
        try:
            if process.environ().get("RIMSORT_UPGRADE_TEST_ROOT") == str(root):
                processes.append(process)
        except psutil.NoSuchProcess, psutil.AccessDenied:
            pass
    return processes


def stop_all(root: Path) -> None:
    stop_processes(owned(root))


@contextmanager
def environment(root: Path, target: Path, fault: str) -> Generator[dict[str, str]]:
    env = clean_environment()
    env.update(
        RIMSORT_UPGRADE_TEST_ROOT=str(root),
        RIMSORT_UPGRADE_TEST_PYTHON=sys.executable,
        RIMSORT_UPGRADE_TEST_HELPER=str(PROCESS),
        RIMSORT_UPGRADE_TEST_EXECUTABLE=str(target),
        RIMSORT_DEV="1",
        RIMSORT_DEV_DIR=str(root / "profile"),
        QT_QPA_PLATFORM={"darwin": "cocoa", "win32": "windows"}.get(
            sys.platform, "xcb"
        ),
        PATH=f"{root / 'bin'}{os.pathsep}{env['PATH']}",
    )
    for key, name in (
        ("TMPDIR", "tmp"),
        ("TMP", "tmp"),
        ("TEMP", "tmp"),
        ("XDG_CACHE_HOME", "cache"),
        ("XDG_CONFIG_HOME", "config"),
        ("XDG_DATA_HOME", "data"),
        ("XDG_RUNTIME_DIR", "runtime"),
    ):
        folder = root / name
        folder.mkdir(mode=0o700, exist_ok=True)
        env[key] = str(folder)
    for name in ("bin", "events", "profile"):
        (root / name).mkdir()
    if sys.platform == "win32" and fault != "msi":
        code = run_external(
            root,
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(PROCESS.with_name("upgrade_shim.ps1")),
                "-OutputDirectory",
                str(root / "bin"),
            ],
            "shim.log",
            env=env,
            timeout=60,
        )
        assert code == 0, f"Windows fixture shim compilation exited with {code}"
        if fault == "copy":
            shutil.copy2(root / "bin/taskkill.exe", root / "bin/robocopy.exe")
    elif sys.platform != "win32":
        commands = (
            ["killall", "open", "osascript"]
            if sys.platform == "darwin"
            else ["killall", "nohup"]
        )
        if fault == "copy":
            commands.append("cp")
        for command in commands:
            arguments = shlex.join(
                [sys.executable, "-I", str(PROCESS), command, str(root)]
            )
            write_executable(
                root / "bin" / command, f'#!/bin/sh\nexec {arguments} "$@"\n'
            )
    try:
        yield env
    finally:
        stop_all(root)


def quit_macos(pid: int) -> None:
    ctypes.CDLL("/System/Library/Frameworks/AppKit.framework/AppKit")
    objc = ctypes.CDLL("/usr/lib/libobjc.A.dylib")
    objc.objc_getClass.argtypes = [ctypes.c_char_p]
    objc.objc_getClass.restype = ctypes.c_void_p
    objc.sel_registerName.argtypes = [ctypes.c_char_p]
    objc.sel_registerName.restype = ctypes.c_void_p
    lookup = ctypes.CFUNCTYPE(
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int
    )(("objc_msgSend", objc))
    terminate = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)(
        ("objc_msgSend", objc)
    )
    application = lookup(
        objc.objc_getClass(b"NSRunningApplication"),
        objc.sel_registerName(b"runningApplicationWithProcessIdentifier:"),
        pid,
    )
    assert application and terminate(
        application, objc.sel_registerName(b"terminate")
    ), "Native Quit request failed"


def healthy_and_close(root: Path, target: Path) -> None:
    log = root / "profile/logs/RimSort.log"
    wait_for(
        lambda: (
            "Finished MainWindow initialization" in read(log)
            and "Finished inserting mod data into active [1] and inactive [0] mod lists"
            in read(log)
            and "User preference is not configured to check Workshop mod for updates. Skipping.."
            in read(log)
        ),
        "normal installed GUI readiness",
    )
    process = psutil.Process(gui_pid(log))
    assert Path(process.exe()).resolve() == target.resolve()
    assert process.environ().get("RIMSORT_UPGRADE_TEST_ROOT") == str(root)
    if sys.platform == "darwin":
        quit_macos(process.pid)
    elif sys.platform == "win32":
        close_window(process.pid)
    else:
        quit_gui(process.pid)
    if sys.platform != "win32":
        wait_for(
            lambda: (
                not process.is_running() or process.status() == psutil.STATUS_ZOMBIE
            ),
            "normal GUI shutdown",
        )
    else:
        assert process.wait(timeout=30) == 0


def configure(root: Path, target: Path, env: dict[str, str]) -> None:
    code = run_external(
        root,
        [
            str(target),
            "--steamcmd-helper",
            str(PROBE),
            "configure",
            str(root),
            str(target),
        ],
        "configure.log",
        env=env,
        cwd=root,
        timeout=90,
    )
    assert code == 0, f"Compiled fixture configuration exited with {code}"
    assert (root / "events/configured.json").exists()


def launch_and_close(root: Path, target: Path, env: dict[str, str]) -> None:
    (root / "profile/logs/RimSort.log").unlink(missing_ok=True)
    with (root / "recovered-app.log").open("w") as output:
        child = subprocess.Popen(
            [str(target)], env=env, cwd=root, stdout=output, stderr=subprocess.STDOUT
        )
        try:
            healthy_and_close(root, target)
            assert child.wait(timeout=30) == 0
        finally:
            if child.poll() is None:
                stop_processes([psutil.Process(child.pid)])
                child.wait(timeout=15)


def update(
    root: Path,
    target: Path,
    env: dict[str, str],
    url: str,
    fault: str,
    kind: str | None = None,
) -> None:
    kind = kind or ("zip" if sys.platform == "win32" else "tar")
    with (root / "old-app.log").open("w") as output:
        old = subprocess.Popen(
            [
                str(target),
                "--steamcmd-helper",
                str(PROBE),
                "update",
                str(root),
                str(target),
                kind,
                url,
                fault,
            ],
            env=env,
            cwd=root,
            stdout=output,
            stderr=subprocess.STDOUT,
        )
        try:

            def ready() -> bool:
                assert old.poll() is None, f"Old GUI exited with {old.returncode}"
                return (root / "events/ready.json").exists()

            wait_for(ready, "old packaged GUI")
            identity = json.loads((root / "events/ready.json").read_text())
            identity["started"] = psutil.Process(identity["pid"]).create_time()
            (root / "events/old-process.json").write_text(json.dumps(identity))
            (root / "events/begin").touch()
            old.wait(timeout=180)
            (root / "events/old-exit.json").write_text(
                json.dumps({"code": old.returncode})
            )
            if fault == "corrupt":
                assert old.returncode == 0 and (root / "events/rejected.json").exists()
            else:
                assert (root / "events/confirmed.json").exists()
                assert (root / "events/handoff-requested.json").exists(), (
                    f"Old GUI exited before installer handoff ({old.returncode})"
                )
        finally:
            if old.poll() is None:
                stop_processes([psutil.Process(old.pid)])
                old.wait(timeout=15)


def install_baseline(
    root: Path, installed: Path, bootstrap: Path, archive: Path, env: dict[str, str]
) -> subprocess.Popen[bytes]:
    configured = json.loads((root / "events/configured.json").read_text())
    extension = ".tar.gz" if sys.platform == "darwin" else ".zip"
    backup = Path(configured["backups"]) / f"RimSort_Backup_baseline{extension}"
    code = run_external(
        root,
        [
            str(executable(bootstrap)),
            "--steamcmd-helper",
            str(PROBE),
            "backup",
            str(root),
            str(executable(bootstrap)),
            str(executable(installed).parent),
            str(backup),
        ],
        "backup.log",
        env=env,
        cwd=root,
        timeout=120,
    )
    assert code == 0, f"Compiled baseline backup exited with {code}"
    staged = unpack(archive, root / "staged")
    script = executable(bootstrap).parent / (
        "update.bat" if sys.platform == "win32" else "update.sh"
    )
    log = root / "profile/logs/updater.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    arguments = [str(script), str(staged), str(log)]
    command: str | list[str]
    if sys.platform == "win32":
        command = f'cmd.exe /d /s /c "{subprocess.list2cmdline(arguments)}"'
    else:
        command = ["/bin/bash", *arguments, str(installed)]
    with (root / "installer.log").open("w") as output:
        return subprocess.Popen(
            command,
            env=env,
            cwd=executable(installed).parent,
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT,
        )


@pytest.mark.parametrize(
    "scenario",
    [
        "baseline",
        "candidate",
        "corrupt",
        "copy",
        pytest.param(
            "legacy",
            marks=pytest.mark.skipif(
                os.environ.get("RIMSORT_UPGRADE_LEGACY") != "1",
                reason="Opt-in diagnostic for the immutable legacy updater's known failures",
            ),
        ),
    ],
)
def test_native_packaged_upgrade(
    archive_inputs: Inputs, tmp_path: Path, scenario: str
) -> None:
    inputs = archive_inputs
    root = tmp_path / (
        "legacy-upgrade"
        if scenario in {"legacy", "baseline"}
        else "Upgrade path with spaces"
        if sys.platform == "win32"
        else "Upgrade path 'é'"
    )
    root.mkdir()
    installed = root / (
        ("RimSort.app" if scenario in {"legacy", "baseline"} else "RimSort custom.app")
        if sys.platform == "darwin"
        else "install"
    )
    previous = (
        inputs.baseline if scenario in {"baseline", "legacy"} else inputs.candidate
    )
    configure_copy = root / "bootstrap" / inputs.candidate.name
    shutil.copytree(inputs.candidate, configure_copy, symlinks=True)
    installer: subprocess.Popen[bytes] | None = None
    try:
        with environment(root, executable(installed), scenario) as env:
            configure(root, executable(configure_copy), env)
            if scenario != "baseline":
                shutil.rmtree(configure_copy)
            if sys.platform == "darwin":
                subprocess.run(
                    ["/usr/bin/ditto", str(previous), str(installed)],
                    check=True,
                    timeout=90,
                )
            else:
                shutil.copytree(previous, installed, symlinks=True)
            sentinels = [
                root / "profile/data/keep.txt",
                root / "fixture/local/keep.txt",
            ]
            if sys.platform == "win32":
                sentinels.append(installed / "user/keep.txt")
            for path in sentinels:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("preserve user data")
            original = manifest(installed)
            payload = root / inputs.archive.name
            if scenario == "corrupt":
                payload.write_bytes(b"Corrupt package fixture\n" * 100)
            else:
                shutil.copy2(inputs.archive, payload)
            if scenario == "baseline":
                installer = install_baseline(
                    root, installed, configure_copy, payload, env
                )
            else:
                with serve(root, payload.name) as (url, requests):
                    update(root, executable(installed), env, url, scenario)
                assert f"GET /{payload.name} 200" in requests
            if scenario == "corrupt":
                assert not (root / "events/confirmed.json").exists()
                assert all(
                    digest(installed / name) == checksum
                    for name, checksum in original.items()
                )
            else:
                config = json.loads((root / "events/configured.json").read_text())
                backups = list(Path(config["backups"]).glob("RimSort_Backup_*"))
                assert len(backups) == 1, backups
                restored = verify_backup(root, backups[0], original)
                if scenario == "copy":
                    wait_for(
                        (root / "events/copy-failed.json").exists,
                        "controlled installer copy failure",
                    )
                    wait_for(
                        lambda: (
                            "Update failed during file copy"
                            in read(root / "profile/logs/updater.log")
                            if sys.platform == "win32"
                            else (root / "events/installer-exit.json").exists()
                        ),
                        "installer failure result",
                    )
                    if sys.platform != "win32":
                        assert (
                            json.loads(
                                (root / "events/installer-exit.json").read_text()
                            )["code"]
                            != 0
                        )
                        assert manifest(installed) == original
                    else:
                        fault = json.loads(
                            (root / "events/copy-failed.json").read_text()
                        )
                        assert (installed / "RimSort.exe").stat().st_size == fault[
                            "bytes"
                        ]
                        assert (
                            digest(installed / "RimSort.exe") != original["RimSort.exe"]
                        )
                    stop_all(root)
                    shutil.rmtree(installed)
                    restored.rename(installed)
                    assert manifest(installed) == original
                    verify_signature(installed)
                else:
                    if sys.platform == "win32":
                        wait_for(
                            lambda: (
                                "update completed and launched successfully"
                                in read(root / "profile/logs/updater.log")
                            ),
                            "batch installer success",
                        )
                    else:
                        wait_for(
                            (root / "events/relaunch.json").exists,
                            "installer ordinary relaunch",
                        )
                    expected = manifest(inputs.candidate)
                    assert all(
                        digest(installed / name) == checksum
                        for name, checksum in expected.items()
                    )
                    verify_signature(installed)
            log = root / "profile/logs/RimSort.log"
            if sys.platform != "win32" or scenario in {"corrupt", "copy"}:
                log.unlink(missing_ok=True)
            if scenario in {"corrupt", "copy"}:
                launch_and_close(root, executable(installed), env)
            else:
                (root / "events/release").touch()
                healthy_and_close(root, executable(installed))
                if sys.platform != "win32":
                    wait_for(
                        (root / "events/exit.json").exists, "supervised GUI exit code"
                    )
                    assert (
                        json.loads((root / "events/exit.json").read_text())["code"] == 0
                    )
            assert all(path.read_text() == "preserve user data" for path in sentinels)
            if installer is not None:
                assert installer.wait(timeout=30) == 0
            elif scenario not in {"corrupt", "copy"} and sys.platform != "win32":
                wait_for(
                    (root / "events/installer-exit.json").exists, "installer completion"
                )
                code = json.loads((root / "events/installer-exit.json").read_text())[
                    "code"
                ]
                assert code == 0, f"Installer exited with {code}"
    except BaseException:
        print_diagnostics(root)
        for event in (root / "events").glob("*.json"):
            print(f"\n{event.name}\n{read(event)}")
        raise
    finally:
        if installer is not None and installer.poll() is None:
            stop_processes([psutil.Process(installer.pid)])
            installer.wait(timeout=15)
        stop_all(root)
        shutil.rmtree(root)


@pytest.mark.parametrize(
    "failure",
    [
        pytest.param(
            "windows-lock",
            marks=pytest.mark.skipif(
                sys.platform != "win32", reason="Native Win32 lock"
            ),
        ),
        pytest.param(
            "linux-enospc",
            marks=pytest.mark.skipif(
                sys.platform != "linux", reason="Native Linux mount"
            ),
        ),
    ],
)
def test_native_filesystem_failure(
    archive_inputs: Inputs, tmp_path: Path, failure: str
) -> None:
    inputs = archive_inputs
    root = tmp_path / "Filesystem failure with spaces"
    root.mkdir()
    installer: subprocess.Popen[bytes] | None = None
    try:
        with ExitStack() as resources:
            previous = (
                inputs.baseline if failure == "windows-lock" else inputs.candidate
            )
            volume: Path | None = None
            if failure == "linux-enospc":
                size = sum(
                    path.stat().st_size
                    for path in previous.rglob("*")
                    if path.is_file()
                )
                capacity = max(128 * MIB, (size // MIB + 65) * MIB)
                volume = resources.enter_context(limited_volume(root, capacity))
                installed = volume / "install"
            else:
                installed = root / "install"
            env = resources.enter_context(
                environment(root, executable(installed), "filesystem")
            )
            bootstrap = root / "bootstrap" / inputs.candidate.name
            shutil.copytree(inputs.candidate, bootstrap, symlinks=True)
            configure(root, executable(bootstrap), env)
            shutil.copytree(previous, installed, symlinks=True)
            sentinels = [
                root / "profile/data/keep.txt",
                root / "fixture/local/keep.txt",
            ]
            if failure == "windows-lock":
                sentinels.append(installed / "user/keep.txt")
            for path in sentinels:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("preserve user data")
            original = manifest(installed)
            if failure == "windows-lock":
                target = executable(installed)
                assert digest(target) != digest(executable(inputs.candidate))
                resources.enter_context(windows_read_lock(root, target))
            else:
                assert volume is not None
                assert exhaust_volume(root, volume) <= MIB
            installer = install_baseline(
                root, installed, bootstrap, inputs.archive, env
            )
            try:
                assert installer.wait(timeout=120) != 0
            finally:
                if installer.poll() is None:
                    stop_processes([psutil.Process(installer.pid)])
                    installer.wait(timeout=15)
            log = read(root / "profile/logs/updater.log")
            output = read(root / "installer.log")
            if failure == "windows-lock":
                result = re.search(r"Robocopy completed with exit code: (\d+)", log)
                assert result is not None and int(result[1]) >= 8
                assert "0x00000020" in output
                assert "Update failed during file copy" in log
                assert "Launching RimSort" not in log
            else:
                assert "No space left on device" in output
                assert "Update failed" in output
                assert manifest(installed) == original
            assert "update completed and launched successfully" not in log
            assert not (root / "events/relaunch.json").exists()
            config = json.loads((root / "events/configured.json").read_text())
            backups = list(Path(config["backups"]).glob("RimSort_Backup_*.zip"))
            assert len(backups) == 1
            restored = verify_backup(root, backups[0], original)
            assert all(path.read_text() == "preserve user data" for path in sentinels)
        launch_and_close(root, executable(restored), env)
        assert manifest(restored) == original
    except BaseException:
        print_diagnostics(root)
        raise
    finally:
        if installer is not None and installer.poll() is None:
            stop_processes([psutil.Process(installer.pid)])
            installer.wait(timeout=15)
        stop_all(root)
        if (root / "volume").is_mount():
            raise RuntimeError("Refusing to delete a fixture with a live mount")
        shutil.rmtree(root)

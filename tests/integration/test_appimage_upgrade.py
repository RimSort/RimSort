"""Opt-in native AppImage upgrade/recovery tests; controls also run on macOS."""

import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from collections.abc import Callable, Generator
from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import psutil
import pytest

BASELINE_URL = (
    "https://github.com/RimSort/RimSort/releases/download/v1.17.4/"
    "RimSort-v1.17.4-x86_64.AppImage"
)
BASELINE_SHA256 = "c2c763268b546ba6dfa7cd406ee11e866cc4c6d54e6af832edf5057a32d47c7c"
PROBE = Path(__file__).with_name("appimage_probe.py")

# Production killall must never target other RimSort sessions on a developer host.
STOP = r"""#!/bin/bash
set -eu
[[ "$*" == '-q RimSort' ]] || exit 64
read -r pid started < "$RIMSORT_APPIMAGE_TEST_ROOT/events/stop-target"
[[ "$pid" =~ ^[0-9]+$ && "$pid" -gt 1 && "$started" =~ ^[0-9]+$ ]] || exit 65
[[ -r "/proc/$pid/stat" ]] || exit 1
[[ "$(awk '{print $22}' "/proc/$pid/stat")" == "$started" ]] || exit 66
kill -TERM "$pid"
"""

# Keep the ordinary relaunch arguments and cwd. Gate only the timing, then
# supervise real nohup so an exit code can be checked after a normal GUI quit.
LAUNCH = r"""#!/bin/bash
set -u
root="$RIMSORT_APPIMAGE_TEST_ROOT"
[[ "$#" == 1 && "$1" == "$APPIMAGE" ]] || exit 64
echo "$$" > "$root/events/launcher"
for ((attempt = 0; attempt < 600; attempt++)); do
    [[ -f "$root/events/release" ]] && break
    sleep 0.1
done
[[ -f "$root/events/release" ]] || exit 70
"$RIMSORT_APPIMAGE_TEST_NOHUP" "$@" > "$root/new-app.log" 2>&1 &
child=$!
echo "$child" > "$root/events/child"
cd "$root" || exit 71
wait "$child"
echo "$?" > "$root/events/exit"
"""

# Source Qt control: exercise the actual bootstrap/timers and GUI initialization,
# intercepting the installer boundary. Frozen markers are simulated only here.
SOURCE_BOOTSTRAP = """
import os
import runpy
import sys
from pathlib import Path

root, repo = map(Path, sys.argv[1:])
sys.path.insert(0, str(repo))
sys.modules['__main__'].__file__ = str(repo / 'app/__main__.py')
from app.utils import app_info
app_info.AppInfo()
app_info.__compiled__ = True
from app.controllers.app_controller import AppController
from app.utils import update_utils
from PySide6.QtCore import QTimer
update_utils.__compiled__ = True
probe = runpy.run_path(str(repo / 'tests/integration/appimage_probe.py'))
sys.excepthook = probe['fail_fast']
(root / 'install/RimSort.AppImage').write_bytes(b'candidate')
(root / 'install/RimSort.AppImage.bak').write_bytes(b'previous')
probe['configure'](root)
(root / 'events/begin').touch()
def perform(self, url, tag, is_msi, is_appimage=False, is_tar_gz=False):
    if not (url == 'http://test.invalid/candidate.AppImage' and is_appimage):
        raise RuntimeError('Incorrect updater handoff')
    (root / 'events/performed').touch()
    raise SystemExit(0)
update_utils.UpdateManager._perform_update = perform
original = AppController.run
def run(self):
    QTimer.singleShot(5000, lambda: os._exit(74))
    return original(self)
AppController.run = run
probe['update'](root, 'http://test.invalid/candidate.AppImage')
if not (root / 'events/performed').exists():
    raise RuntimeError('Bootstrap did not invoke updater')
"""


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def download_baseline(
    destination: Path, url: str = BASELINE_URL, checksum: str = BASELINE_SHA256
) -> None:
    partial_path = destination.with_suffix(".partial")
    try:
        with (
            urllib.request.urlopen(url, timeout=60) as response,
            partial_path.open("wb") as output,
        ):
            shutil.copyfileobj(response, output)
        if digest(partial_path) != checksum:
            raise RuntimeError("Baseline download SHA256 mismatch")
        partial_path.replace(destination)
        destination.chmod(0o755)
    finally:
        partial_path.unlink(missing_ok=True)


def wait_for(condition: Callable[[], object], description: str) -> None:
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.1)
    raise AssertionError(f"Timed out waiting for {description}")


def write_executable(path: Path, script: str) -> None:
    shebang, body = script.split("\n", 1)
    interpreter = shutil.which(Path(shebang.removeprefix("#!")).name)
    if interpreter is None:
        raise RuntimeError(f"Test shell is unavailable: {shebang}")
    path.write_text(f"#!{interpreter}\n{body}", encoding="utf-8")
    path.chmod(0o755)


@contextmanager
def serve(
    directory: Path, filename: str = "candidate.AppImage"
) -> Generator[tuple[str, list[str]]]:
    requests: list[str] = []

    class Handler(SimpleHTTPRequestHandler):
        def log_request(self, code: int | str = "-", size: int | str = "-") -> None:
            requests.append(f"{self.command} {self.path} {code}")

    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(Handler, directory=str(directory))
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/{filename}", requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def owned_processes(root: Path) -> list[psutil.Process]:
    result = []
    for process in psutil.process_iter():
        try:
            if process.environ().get("RIMSORT_APPIMAGE_TEST_ROOT") == str(root):
                result.append(process)
        except psutil.NoSuchProcess, psutil.AccessDenied:
            continue
    return result


def clean_environment() -> dict[str, str]:
    env = os.environ.copy()
    for key in (
        "PYTHONPATH",
        "PYTHONHOME",
        "APPIMAGE",
        "APPDIR",
        "APPIMAGE_EXTRACT_AND_RUN",
        "__PYVENV_LAUNCHER__",
    ):
        env.pop(key, None)
    return env


@contextmanager
def isolated_environment(root: Path) -> Generator[dict[str, str]]:
    env = clean_environment()
    env.update(
        RIMSORT_APPIMAGE_TEST_ROOT=str(root),
        RIMSORT_DEV="1",
        RIMSORT_DEV_DIR=str(root / "profile"),
        QT_QPA_PLATFORM="xcb",
        LANG="en_US.UTF-8",
        PATH=f"{root / 'bin'}:{env['PATH']}",
    )
    for key, directory in (
        ("TMPDIR", "tmp"),
        ("XDG_CACHE_HOME", "cache"),
        ("XDG_CONFIG_HOME", "config"),
        ("XDG_DATA_HOME", "data"),
        ("XDG_RUNTIME_DIR", "runtime"),
    ):
        folder = root / directory
        folder.mkdir(mode=0o700)
        env[key] = str(folder)
    for directory in ("bin", "events", "profile", "install", "input"):
        (root / directory).mkdir()
    if sys.platform != "win32":
        real_nohup = shutil.which("nohup")
        if real_nohup is None:
            raise RuntimeError("Test requires nohup on PATH")
        env["RIMSORT_APPIMAGE_TEST_NOHUP"] = real_nohup
        write_executable(root / "bin/killall", STOP)
        write_executable(root / "bin/nohup", LAUNCH)
    try:
        yield env
    finally:
        # psutil retains process identities and checks PID reuse before signalling.
        processes = owned_processes(root)
        for process in processes:
            try:
                process.terminate()
            except psutil.NoSuchProcess:
                pass
        _, alive = psutil.wait_procs(processes, timeout=5)
        for process in alive:
            try:
                process.kill()
            except psutil.NoSuchProcess:
                pass
        psutil.wait_procs(alive, timeout=5)


def read(path: Path) -> str:
    return path.read_text(errors="replace") if path.exists() else ""


def gui_pid(log: Path) -> int:
    matches = re.findall(r"\]\[(\d+)\]\[MainThread\]", read(log))
    assert matches, f"No GUI PID in {log}"
    return int(matches[-1])


def quit_gui(pid: int, fatal: bool = False) -> None:
    command = ["xdotool", "search", "--all", "--onlyvisible", "--pid", str(pid)]
    command.extend(["--name", "^Fatal Error$" if fatal else "^RimSort "])

    def windows() -> list[str]:
        result = subprocess.run(
            command, text=True, capture_output=True, check=False, timeout=10
        )
        assert result.returncode in (0, 1), result.stderr
        return result.stdout.splitlines()

    wait_for(windows, f"visible window for GUI PID {pid}")
    window = windows()[-1]
    assert subprocess.check_output(
        ["xdotool", "getwindowpid", window], text=True, timeout=10
    ).strip() == str(pid)
    subprocess.run(
        [
            "xdotool",
            "windowfocus",
            "--sync",
            window,
            "key",
            "Escape" if fatal else "ctrl+q",
        ],
        check=True,
        timeout=15,
    )


@pytest.fixture(scope="session")
def images(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    candidate_arg = os.environ.get("RIMSORT_APPIMAGE_CANDIDATE")
    if sys.platform != "linux" or not candidate_arg:
        pytest.skip("Requires Linux, Xvfb/FUSE and RIMSORT_APPIMAGE_CANDIDATE")
    assert os.getuid() != 0, "Native AppImage updater must run as a regular user"
    candidate = Path(candidate_arg).resolve(strict=True)
    assert shutil.which("xdotool") and os.environ.get("DISPLAY")
    baseline = tmp_path_factory.mktemp("appimage-input") / "baseline.AppImage"
    download_baseline(baseline)
    return baseline, candidate


@pytest.mark.parametrize(
    ("from_baseline", "startup_failure"),
    [(True, False), (False, False), (False, True)],
    ids=["stable-upgrade", "candidate-upgrade", "candidate-recovery"],
)
def test_native_appimage_upgrade(
    images: tuple[Path, Path],
    tmp_path: Path,
    from_baseline: bool,
    startup_failure: bool,
) -> None:
    baseline, candidate = images
    root = tmp_path.resolve()
    installed = root / "install/RimSort.AppImage"
    backup = installed.with_suffix(".AppImage.bak")
    app_log = root / "profile/logs/RimSort.log"
    events = root / "events"
    try:
        with isolated_environment(root) as env:
            shutil.copy2(candidate, installed)
            installed.chmod(0o755)
            os.link(baseline, backup)
            with (root / "configure.log").open("w") as output:
                subprocess.run(
                    [
                        str(installed),
                        "--steamcmd-helper",
                        str(PROBE),
                        "configure",
                        str(root),
                    ],
                    cwd=root,
                    env=env,
                    stdout=output,
                    stderr=subprocess.STDOUT,
                    check=True,
                    timeout=90,
                )
            config = json.loads((events / "configured.json").read_text())
            database = Path(config["database"])
            assert database.is_relative_to(root)
            assert digest(backup) == BASELINE_SHA256
            backup.unlink()
            previous = baseline if from_baseline else candidate
            shutil.copy2(previous, installed)
            installed.chmod(0o755)
            previous_inode = installed.stat().st_ino
            previous_digest = digest(previous)
            sentinels = [
                root / "profile/data/keep.txt",
                root / "fixture/local/user-note.txt",
            ]
            for path in sentinels:
                path.write_text("preserve user data")
            shutil.copy2(candidate, root / "input/candidate.AppImage")
            with serve(root / "input") as (url, requests):
                with (root / "old-app.log").open("w") as output:
                    old = subprocess.Popen(
                        [
                            str(installed),
                            "--steamcmd-helper",
                            str(PROBE),
                            "update",
                            str(root),
                            url,
                        ],
                        cwd=root,
                        env=env,
                        stdout=output,
                        stderr=subprocess.STDOUT,
                        start_new_session=True,
                    )
                    try:
                        wait_for((events / "ready.json").exists, "old GUI readiness")
                        pid = json.loads((events / "ready.json").read_text())["pid"]
                        assert os.getsid(pid) == old.pid
                        assert psutil.Process(pid).name() == "RimSort"
                        stat = (
                            Path(f"/proc/{pid}/stat")
                            .read_text()
                            .rsplit(")", 1)[1]
                            .split()
                        )
                        (events / "stop-target").write_text(f"{pid} {stat[19]}\n")
                        (events / "begin").touch()
                        wait_for((events / "launcher").exists, "installer relaunch")
                        old.wait(timeout=15)
                    finally:
                        if old.poll() is None:
                            old.terminate()
                            old.wait(timeout=15)
                assert "HEAD /candidate.AppImage 200" in requests
                assert "GET /candidate.AppImage 200" in requests
            assert (events / "confirmed.json").exists()
            assert digest(installed) == digest(candidate)
            assert digest(backup) == previous_digest
            assert installed.stat().st_ino != previous_inode
            assert not Path(config["mount"]).exists(), "Configuration mount leaked"
            snapshot: dict[Path, bytes] = {}
            if startup_failure:
                for suffix in ("", "-wal", "-shm"):
                    path = Path(f"{database}{suffix}")
                    if path.exists():
                        snapshot[path] = path.read_bytes()
                        path.unlink()
                database.write_bytes(b"Deliberately invalid fixture SQLite database\n")
            app_log.unlink(missing_ok=True)
            (events / "release").touch()
            marker = (
                "file is not a database"
                if startup_failure
                else "Cleaned up old AppImage backup"
            )
            wait_for(lambda: marker in read(app_log), marker)
            if startup_failure:
                assert backup.exists()
                assert "Cleaned up old AppImage backup" not in read(app_log)
            else:
                assert not backup.exists()
                assert "Finished MainWindow initialization" in read(app_log)
                assert "/fixture/game/Data/Core" in read(app_log)
            quit_gui(gui_pid(app_log), fatal=startup_failure)
            wait_for((events / "exit").exists, "new app shutdown")
            assert (events / "exit").read_text().strip() == "0"
            if startup_failure:
                assert digest(backup) == previous_digest
                backup.replace(installed)
                for suffix in ("", "-wal", "-shm"):
                    Path(f"{database}{suffix}").unlink(missing_ok=True)
                for path, data in snapshot.items():
                    path.write_bytes(data)
                app_log.rename(root / "failed-startup.log")
                with (root / "recovered-app.log").open("w") as output:
                    recovered = subprocess.Popen(
                        [str(installed)],
                        cwd=root,
                        env=env,
                        stdout=output,
                        stderr=subprocess.STDOUT,
                    )
                    try:
                        wait_for(
                            lambda: (
                                "Finished MainWindow initialization" in read(app_log)
                                and "/fixture/game/Data/Core" in read(app_log)
                                and "User preference is not configured to check Workshop mod for updates. Skipping.."
                                in read(app_log)
                            ),
                            "restored GUI",
                        )
                        quit_gui(gui_pid(app_log))
                        assert recovered.wait(timeout=30) == 0
                    finally:
                        if recovered.poll() is None:
                            recovered.terminate()
                            recovered.wait(timeout=15)
                assert digest(installed) == previous_digest
            assert all(path.read_text() == "preserve user data" for path in sentinels)
    except BaseException:
        for path in [*root.glob("*.log"), app_log, *events.glob("*")]:
            print(f"\n--- {path.relative_to(root)} ---\n{read(path)[-12000:]}")
        raise


def test_baseline_checksum_mismatch(tmp_path: Path) -> None:
    source = tmp_path / "untrusted.AppImage"
    source.write_bytes(b"not the pinned release")
    destination = tmp_path / "baseline.AppImage"
    with pytest.raises(RuntimeError, match="SHA256 mismatch"):
        download_baseline(destination, source.as_uri())
    assert not destination.exists()
    assert not destination.with_suffix(".partial").exists()


def test_bootstrap_dispatches_update_after_gui_startup(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    with isolated_environment(root) as env:
        env.update(
            QT_QPA_PLATFORM="offscreen",
            APPIMAGE=str(root / "install/RimSort.AppImage"),
            APPDIR=str(root / "tmp/mount"),
            RIMSORT_DISABLE_UPDATER="1",
        )
        repo = PROBE.parents[2]
        result = subprocess.run(
            [sys.executable, "-c", SOURCE_BOOTSTRAP, str(root), str(repo)],
            cwd=repo,
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert (root / "events/ready.json").exists()
        assert (root / "events/performed").exists()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX launcher control")
def test_launch_gate_preserves_args_cwd_and_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tools = tmp_path / "available-tools"
    tools.mkdir()
    for name in ("bash", "sh"):
        executable = shutil.which(name)
        assert executable is not None
        (tools / name).symlink_to(executable)
    real_nohup = shutil.which("nohup")
    assert real_nohup is not None
    write_executable(
        tools / "nohup",
        '#!/bin/sh\ntouch "$RIMSORT_APPIMAGE_TEST_ROOT/events/real-nohup-used"\n'
        f'exec {shlex.quote(real_nohup)} "$@"\n',
    )
    monkeypatch.setenv("PATH", f"{tools}{os.pathsep}{os.environ['PATH']}")
    with isolated_environment(tmp_path) as env:
        events = tmp_path / "events"
        application = tmp_path / "candidate"
        write_executable(
            application, '#!/bin/sh\npwd > "$RIMSORT_APPIMAGE_TEST_ROOT/cwd"\nexit 7\n'
        )
        env["APPIMAGE"] = str(application)
        child_cwd = tmp_path / "inherited-cwd"
        child_cwd.mkdir()
        process = subprocess.Popen(
            [str(tmp_path / "bin/nohup"), str(application)], cwd=child_cwd, env=env
        )
        try:
            wait_for((events / "launcher").exists, "test launch gate")
            assert not (tmp_path / "cwd").exists()
            (events / "release").touch()
            assert process.wait(timeout=10) == 0
            assert (events / "real-nohup-used").exists()
            assert (events / "exit").read_text().strip() == "7"
            assert (tmp_path / "cwd").read_text().strip() == str(child_cwd)
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX stop control")
def test_stop_control_refuses_unscoped_signal(tmp_path: Path) -> None:
    script = tmp_path / "killall"
    write_executable(script, STOP)
    env = {**os.environ, "RIMSORT_APPIMAGE_TEST_ROOT": str(tmp_path)}
    result = subprocess.run(
        [str(script), "-q", "RimSort"], env=env, capture_output=True, check=False
    )
    assert result.returncode != 0

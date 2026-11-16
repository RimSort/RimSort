"""Real MSI installation tests, opt-in only on disposable Windows CI runners."""

import ctypes
import hashlib
import json
import os
import subprocess
import sys
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from xml.etree import ElementTree

import psutil
import pytest
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from tests.integration.msi_helpers import require_windows_ci, run_msi

DATABASE = Path(__file__).with_name("msi_database.ps1")
LAUNCHER = Path(__file__).with_name("msi_launch.py")
BASELINE_SHA256 = "35ebb1903bfedbac20ed450648bfb7c67e3c7dab3b450313efc5a3d14d2657da"
UPGRADE_CODE = "{D4F7C3B9-8A5E-4E52-BB9F-3C2D1F7A9E24}"


@dataclass(frozen=True)
class Package:
    path: Path
    code: str
    package_code: str
    component: str
    files: frozenset[str]


def database(mode: str, **arguments: str) -> object:
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(DATABASE),
            "-Mode",
            mode,
            *(item for key, value in arguments.items() for item in (f"-{key}", value)),
        ],
        capture_output=True,
        encoding="utf-8",
        check=False,
        timeout=90,
    )
    if result.returncode:
        raise RuntimeError(
            f"MSI database {mode} failed ({result.returncode}):\n"
            f"{result.stdout}\n{result.stderr}"
        )
    return json.loads(result.stdout) if result.stdout.strip() else None


def payload_paths(
    directories: list[list[str]], components: list[list[str]], files: list[list[str]]
) -> dict[str, str]:
    directory_map = {key: (parent, name) for key, parent, name in directories}
    component_map = {key: (guid, directory) for key, guid, directory in components}
    result = {}
    for filename, component in files:
        guid, directory = component_map[component]
        parts = [filename.rsplit("|", 1)[-1]]
        visited: set[str] = set()
        while directory != "INSTALLFOLDER":
            if directory in visited or directory not in directory_map:
                raise ValueError(
                    "MSI file is outside INSTALLFOLDER or has a directory cycle"
                )
            visited.add(directory)
            directory, name = directory_map[directory]
            target = name.split(":", 1)[0].rsplit("|", 1)[-1]
            if target != ".":
                parts.insert(0, target)
        relative = PureWindowsPath(*parts)
        if relative.is_absolute() or relative.drive or ".." in relative.parts:
            raise ValueError(f"Invalid MSI payload path: {relative}")
        key = relative.as_posix().casefold()
        if key in result:
            raise ValueError(f"Duplicate MSI payload path: {relative}")
        result[key] = guid
    return result


def inspect_package(path: Path) -> Package:
    data = database("Inspect", MsiPath=str(path))
    assert isinstance(data, dict)
    properties = data["properties"]
    assert properties["ProductName"] == "RimSort"
    assert properties["UpgradeCode"].upper() == UPGRADE_CODE
    files = payload_paths(data["directories"], data["components"], data["files"])
    return Package(
        path,
        properties["ProductCode"],
        data["package"],
        files["rimsort.exe"],
        frozenset(files),
    )


def state(package: Package) -> tuple[int, str]:
    data = database("State", ProductCode=package.code, ComponentCode=package.component)
    assert isinstance(data, dict)
    return int(data["state"]), str(data["executable"])


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def configure_profile(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.models.settings import Settings
    from app.utils.app_info import AppInfo

    storage = root / "profile/data"
    storage.mkdir(parents=True)
    info = AppInfo()
    monkeypatch.setattr(info, "_app_storage_folder", storage)
    monkeypatch.setattr(info, "_settings_file", storage / "settings.json")
    settings = Settings()
    for field, value in {
        "language": "en_US",
        "check_for_update_startup": False,
        "update_databases_on_startup": False,
        "github_update_check_enabled": False,
        "steam_mods_update_check": False,
        "watchdog_toggle": False,
        "auto_load_player_log_on_startup": False,
        "debug_logging_enabled": True,
    }.items():
        setattr(settings, field, value)
    instance = settings.instances[settings.current_instance]
    instance.initial_setup = False
    instance.steamcmd_ignore = True
    for field in (
        "game_folder",
        "config_folder",
        "local_folder",
        "steamcmd_install_path",
    ):
        path = root / "fixture" / field
        path.mkdir(parents=True)
        setattr(instance, field, str(path))
    about = Path(instance.game_folder) / "Data/Core/About/About.xml"
    about.parent.mkdir(parents=True)
    metadata = ElementTree.Element("ModMetaData")
    for tag, value in {
        "name": "Core",
        "packageId": "ludeon.rimworld",
        "author": "Ludeon",
    }.items():
        ElementTree.SubElement(metadata, tag).text = value
    ElementTree.SubElement(
        ElementTree.SubElement(metadata, "supportedVersions"), "li"
    ).text = "1.6"
    ElementTree.ElementTree(metadata).write(about, encoding="utf-8")
    (Path(instance.game_folder) / "Version.txt").write_text("1.6.0 rev0")
    config = ElementTree.Element("ModsConfigData")
    ElementTree.SubElement(config, "version").text = "1.6.0"
    ElementTree.SubElement(
        ElementTree.SubElement(config, "activeMods"), "li"
    ).text = "ludeon.rimworld"
    ElementTree.ElementTree(config).write(
        Path(instance.config_folder) / "ModsConfig.xml", encoding="utf-8"
    )
    settings.save()


def close_window(pid: int) -> None:
    if sys.platform != "win32":
        raise RuntimeError("Native GUI close requires Windows")
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    user32.GetWindowThreadProcessId.argtypes = [
        wintypes.HWND,
        ctypes.POINTER(wintypes.DWORD),
    ]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.PostMessageW.argtypes = [
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    ]
    user32.PostMessageW.restype = wintypes.BOOL
    windows = []

    def visit(hwnd: int, extra: int) -> bool:
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        title = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, title, len(title))
        if (
            owner.value == pid
            and user32.IsWindowVisible(hwnd)
            and title.value.startswith("RimSort ")
        ):
            windows.append(hwnd)
        return True

    callback = callback_type(visit)
    if not user32.EnumWindows(callback, 0):
        raise ctypes.WinError(ctypes.get_last_error())
    assert len(windows) == 1, f"Expected one main window for PID {pid}: {windows}"
    owner = wintypes.DWORD()
    user32.GetWindowThreadProcessId(windows[0], ctypes.byref(owner))
    assert owner.value == pid
    if not user32.PostMessageW(windows[0], 0x0010, 0, 0):  # WM_CLOSE
        raise ctypes.WinError(ctypes.get_last_error())


def verify_gui(root: Path, phase: str, qtbot: QtBot) -> None:
    launched = root / f"{phase}-launch.json"
    exited = root / f"{phase}-exit.json"
    error = root / f"{phase}-error.json"
    log = root / "profile/logs/RimSort.log"

    def ready() -> bool:
        assert not error.exists(), error.read_text() if error.exists() else ""
        assert not exited.exists(), f"GUI exited before readiness: {exited.read_text()}"
        content = log.read_text(errors="replace") if log.exists() else ""
        return (
            launched.exists()
            and "Finished MainWindow initialization" in content
            and "Finished inserting mod data into active [1] and inactive [0] mod lists"
            in content
            and "User preference is not configured to check Workshop mod for updates. Skipping.."
            in content
        )

    qtbot.waitUntil(ready, timeout=90000)
    data = json.loads(launched.read_text())
    process = psutil.Process(data["pid"])
    assert process.create_time() == data["started"]
    assert Path(process.exe()).resolve() == (root / "install/RimSort.exe").resolve()
    assert process.environ()["RIMSORT_DEV_DIR"] == str(root / "profile")
    close_window(process.pid)
    qtbot.waitUntil(exited.exists, timeout=90000)
    assert json.loads(exited.read_text())["code"] == 0
    log.rename(root / f"{phase}-app.log")


def stop_owned_apps(root: Path) -> None:
    owned = []
    for process in psutil.process_iter():
        try:
            command = process.cmdline()
            if process.environ().get("RIMSORT_MSI_TEST_ROOT") == str(root) or (
                str(LAUNCHER) in command and str(root) in command
            ):
                owned.append(process)
        except psutil.NoSuchProcess, psutil.AccessDenied:
            continue
    for process in owned:
        try:
            process.terminate()
        except psutil.NoSuchProcess:
            pass
    _, alive = psutil.wait_procs(owned, timeout=10)
    for process in alive:
        try:
            process.kill()
        except psutil.NoSuchProcess:
            pass
    _, alive = psutil.wait_procs(alive, timeout=10)
    assert not alive, "Owned GUI processes survived cleanup"


def print_diagnostics(root: Path) -> None:
    paths = [*root.glob("*.log"), *(root / "profile/logs").glob("*.log")]
    for path in sorted(paths):
        raw = path.read_bytes()
        encoding = "utf-16" if raw.startswith(b"\xff\xfe") else "utf-8"
        text = raw.decode(encoding, errors="replace")
        print(f"\n{path.relative_to(root)}")
        failure = text.find("Return value 3")
        if failure >= 0:
            print(text[max(0, failure - 4000) : failure + 200])
        print(text[-12000:])


def install(root: Path, phase: str, package: Package, qtbot: QtBot) -> None:
    transform = root / f"{phase}.mst"
    arguments = (
        subprocess.list2cmdline(["-I", str(LAUNCHER), str(root), phase])
        + ' "[RIMSORTTARGET]"'
    )
    database(
        "Transform",
        MsiPath=str(package.path),
        TransformPath=str(transform),
        PythonPath=sys.executable,
        LaunchArguments=arguments,
    )
    result = run_msi(
        root,
        phase,
        ["/i", str(package.path)],
        {"INSTALLFOLDER": root / "install", "TRANSFORMS": transform},
    )
    assert result == 0, f"MSI {phase} returned {result}"
    installed_state, executable = state(package)
    assert installed_state == 5
    assert Path(executable).resolve() == (root / "install/RimSort.exe").resolve()
    verify_gui(root, phase, qtbot)


def test_native_windows_msi_install_upgrade(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, qtbot: QtBot
) -> None:
    candidate_arg = os.environ.get("RIMSORT_MSI_CANDIDATE")
    if sys.platform != "win32" or not candidate_arg:
        pytest.skip("Requires Windows CI and real MSI inputs")
    require_windows_ci(tmp_path)
    root = tmp_path / "MSI path 'test'"
    root.mkdir()
    (root / "tmp").mkdir()
    baseline_path = Path(os.environ["RIMSORT_MSI_BASELINE"]).resolve(strict=True)
    assert sha256(baseline_path) == BASELINE_SHA256
    baseline = inspect_package(baseline_path)
    candidate = inspect_package(Path(candidate_arg).resolve(strict=True))
    assert baseline.code != candidate.code
    expected = Path(os.environ["RIMSORT_MSI_EXPECTED_DIR"]).resolve(strict=True)
    manifest = {
        path.relative_to(expected).as_posix().casefold(): sha256(path)
        for path in expected.rglob("*")
        if path.is_file()
    }
    assert frozenset(manifest) == candidate.files
    # Preserve pre-existing products even if the opt-in guard is misconfigured.
    assert state(baseline)[0] == -1 and state(candidate)[0] == -1
    assert database("Related", UpgradeCode=UPGRADE_CODE) == []
    configure_profile(root, monkeypatch)
    sentinels = [root / "profile/data/keep.txt", root / "install/user/keep.txt"]
    for sentinel in sentinels:
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        sentinel.write_text("preserve user data")
    try:
        install(root, "baseline", baseline, qtbot)
        install(root, "upgrade", candidate, qtbot)
        assert state(baseline)[0] == -1
        for relative, checksum in manifest.items():
            assert sha256(root / "install" / relative) == checksum, relative
        assert not any(
            (root / "install" / path).exists()
            for path in baseline.files - candidate.files
        )
        corrupt = root / "corrupt.msi"
        corrupt.write_bytes(b"Not a Windows Installer database")
        assert run_msi(root, "rejected", ["/i", str(corrupt)]) in (1619, 1620)
        assert state(candidate)[0] == 5
        for relative, checksum in manifest.items():
            assert sha256(root / "install" / relative) == checksum, relative
        launcher = subprocess.Popen(
            [
                sys.executable,
                "-I",
                str(LAUNCHER),
                str(root),
                "after-rejection",
                str(root / "install/RimSort.exe"),
            ]
        )
        try:
            verify_gui(root, "after-rejection", qtbot)
            assert launcher.wait(timeout=15) == 0
        finally:
            if launcher.poll() is None:
                launcher.terminate()
                launcher.wait(timeout=15)
        assert all(path.read_text() == "preserve user data" for path in sentinels)
    finally:
        try:
            stop_owned_apps(root)
        finally:
            try:
                cleanup_failures = []
                for package in (candidate, baseline):
                    try:
                        if state(package)[0] != -1:
                            assert (
                                run_msi(
                                    root,
                                    f"uninstall-{package.code}",
                                    ["/x", package.code],
                                )
                                == 0
                            )
                        assert state(package)[0] == -1
                    except Exception as error:
                        cleanup_failures.append(f"{package.code}: {error}")
                assert not cleanup_failures, cleanup_failures
            finally:
                print_diagnostics(root)
    assert database("Related", UpgradeCode=UPGRADE_CODE) == []
    assert not (root / "install/RimSort.exe").exists()
    assert all(path.read_text() == "preserve user data" for path in sentinels)


def test_msi_payload_directory_resolution() -> None:
    files = payload_paths(
        [
            ["INSTALLFOLDER", "TARGETDIR", "RimSort"],
            ["nested", "INSTALLFOLDER", "SHORT|Long folder:source"],
            ["alias", "nested", "."],
        ],
        [["main", "exe-guid", "INSTALLFOLDER"], ["data", "data-guid", "alias"]],
        [["RIMSOR~1.EXE|RimSort.exe", "main"], ["data.txt", "data"]],
    )
    assert files == {"rimsort.exe": "exe-guid", "long folder/data.txt": "data-guid"}


@pytest.mark.parametrize("parent", ["loop", "missing"])
def test_msi_rejects_unresolvable_payload(parent: str) -> None:
    with pytest.raises(ValueError, match="outside INSTALLFOLDER|cycle"):
        payload_paths(
            [["loop", parent, "folder"]],
            [["component", "guid", "loop"]],
            [["file", "component"]],
        )


def test_profile_uses_real_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, qapp: QApplication
) -> None:
    configure_profile(tmp_path, monkeypatch)
    data = json.loads((tmp_path / "profile/data/settings.json").read_text())
    assert data["check_for_update_startup"] is False
    instance = data["instances"][data["current_instance"]]
    assert instance["initial_setup"] is False and instance["steamcmd_ignore"] is True
    assert Path(instance["game_folder"]).is_relative_to(tmp_path)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX stand-in executable")
def test_launch_supervision_isolates_profile_and_records_failure(
    tmp_path: Path,
) -> None:
    (tmp_path / "install").mkdir()
    (tmp_path / "tmp").mkdir()
    target = tmp_path / "install/RimSort.exe"
    target.write_text(
        f"#!{sys.executable}\n"
        "import json, os\nfrom pathlib import Path\n"
        "root = Path(os.environ['RIMSORT_MSI_TEST_ROOT'])\n"
        "(root / 'environment.json').write_text(json.dumps(dict(os.environ)))\n"
        "raise SystemExit(7)\n"
    )
    target.chmod(0o755)
    result = subprocess.run(
        [sys.executable, "-I", str(LAUNCHER), str(tmp_path), "control", str(target)],
        env={**os.environ, "PYTHONPATH": "invalid-source-path"},
        check=False,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 7, result.stderr
    assert json.loads((tmp_path / "control-exit.json").read_text()) == {"code": 7}
    environment = json.loads((tmp_path / "environment.json").read_text())
    assert environment["RIMSORT_DEV_DIR"] == str(tmp_path / "profile")
    assert environment["TMP"] == str(tmp_path / "tmp")
    assert "PYTHONPATH" not in environment


def test_launch_refuses_wrong_installer_target(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            str(LAUNCHER),
            str(tmp_path),
            "control",
            str(tmp_path / "wrong.exe"),
        ],
        check=False,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode != 0
    error = json.loads((tmp_path / "control-error.json").read_text())
    assert "unexpected launch target" in error["traceback"]
    assert not (tmp_path / "control-launch.json").exists()


def test_failed_gui_diagnostics_include_live_app_log(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    log = tmp_path / "profile/logs/RimSort.log"
    log.parent.mkdir(parents=True)
    log.write_text("GUI stopped before initialization completed", encoding="utf-8")
    (tmp_path / "install-msi.log").write_bytes(
        (
            "Actual MSI failure\nAction ended: Return value 3\n"
            + "padding" * 2000
            + "\nInstaller detail"
        ).encode("utf-16")
    )
    print_diagnostics(tmp_path)
    output = capsys.readouterr().out
    assert "GUI stopped before initialization completed" in output
    assert "Installer detail" in output
    assert "Actual MSI failure" in output


def test_database_errors_preserve_com_details(monkeypatch: pytest.MonkeyPatch) -> None:
    def failing_command(
        args: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.CompletedProcess(args, 1, "", "COM database error detail")
        if kwargs.get("check"):
            raise subprocess.CalledProcessError(1, args, stderr=result.stderr)
        return result

    monkeypatch.setattr(subprocess, "run", failing_command)
    with pytest.raises(RuntimeError, match="COM database error detail"):
        database("Inspect", MsiPath="fixture.msi")


def test_msi_quotes_property_values(monkeypatch: pytest.MonkeyPatch) -> None:
    def installer_command(
        command: str, **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        assert command.replace("\\", "/") == (
            'msiexec.exe /i "package path/candidate.msi" /qn /norestart /L*V '
            "\"MSI path 'test'/install-msi.log\" "
            "INSTALLFOLDER=\"MSI path 'test'/install\" "
            "TRANSFORMS=\"MSI path 'test'/baseline.mst\""
        )
        assert kwargs == {"check": False, "timeout": 240}
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(subprocess, "run", installer_command)
    root = Path("MSI path 'test'")
    assert (
        run_msi(
            root,
            "install",
            ["/i", "package path/candidate.msi"],
            {"INSTALLFOLDER": root / "install", "TRANSFORMS": root / "baseline.mst"},
        )
        == 0
    )

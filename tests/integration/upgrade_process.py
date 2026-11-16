"""Constrain installer process boundaries to one disposable upgrade fixture."""

import json
import os
import re
import runpy
import subprocess
import sys
import time
from pathlib import Path

import psutil


def record(root: Path, name: str, value: object) -> None:
    destination = root / "events" / f"{name}.json"
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(json.dumps(value), encoding="utf-8")
    temporary.replace(destination)


def contained(root: Path, path: str) -> Path:
    resolved = Path(path).resolve()
    if not resolved.is_relative_to(root):
        raise RuntimeError(f"Installer path escaped fixture: {path}")
    return resolved


def stop_processes(parents: list[psutil.Process]) -> None:
    retained = {process.pid: process for process in parents}
    for process in parents:
        try:
            retained.update(
                (child.pid, child) for child in process.children(recursive=True)
            )
        except psutil.NoSuchProcess:
            pass
    processes = list(retained.values())
    for process in reversed(processes):
        try:
            process.terminate()
        except psutil.NoSuchProcess:
            pass
    _, alive = psutil.wait_procs(processes, timeout=10)
    for process in alive:
        try:
            process.kill()
        except psutil.NoSuchProcess:
            pass
    _, alive = psutil.wait_procs(alive, timeout=10)
    if alive:
        raise RuntimeError(
            f"Owned processes survived cleanup: {[process.pid for process in alive]}"
        )


def run_external(
    root: Path,
    command: str | list[str],
    log: str,
    *,
    shell: bool = False,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    timeout: float = 180,
) -> int:
    with (root / log).open("w", encoding="utf-8") as output:
        child = subprocess.Popen(
            command,
            shell=shell,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT,
        )
        identity = psutil.Process(child.pid)
        try:
            return child.wait(timeout=timeout)
        finally:
            if child.poll() is None:
                stop_processes([identity])
                child.wait(timeout=15)


def stop(root: Path, arguments: list[str]) -> int:
    expected = (
        ["/F", "/im", "RimSort.exe"] if sys.platform == "win32" else ["-q", "RimSort"]
    )
    if arguments != expected:
        raise RuntimeError(f"Unexpected process termination: {arguments}")
    if not (root / "events/old-process.json").exists():
        return 1
    identity = json.loads((root / "events/old-process.json").read_text())
    try:
        process = psutil.Process(identity["pid"])
        if process.create_time() != identity["started"]:
            raise RuntimeError("Old GUI PID was reused")
        contained(root, process.exe())
        if process.environ().get("RIMSORT_UPGRADE_TEST_ROOT") != str(root):
            raise RuntimeError("Old GUI does not belong to fixture")
        process.terminate()
        process.wait(timeout=15)
    except psutil.NoSuchProcess:
        return 1
    return 0


def launch(root: Path, arguments: list[str]) -> int:
    if len(arguments) != 1:
        raise RuntimeError(f"Unexpected relaunch: {arguments}")
    target = contained(root, arguments[0])
    expected = Path(os.environ["RIMSORT_UPGRADE_TEST_EXECUTABLE"])
    if sys.platform == "darwin":
        target /= "Contents/MacOS/RimSort"
    if target != expected:
        raise RuntimeError(f"Wrong relaunch executable: {target}")
    try:
        inherited_cwd = os.getcwd()
    except FileNotFoundError:
        inherited_cwd = None
    record(root, "relaunch", {"target": str(target), "cwd": inherited_cwd})
    deadline = time.monotonic() + 90
    while not (root / "events/release").exists():
        if time.monotonic() > deadline:
            raise TimeoutError("Relaunch gate was not released")
        time.sleep(0.1)
    with (root / "new-app.log").open("w", encoding="utf-8") as output:
        child = subprocess.Popen(
            [str(target)],
            cwd=root if sys.platform == "darwin" else None,
            stdout=output,
            stderr=subprocess.STDOUT,
        )
        try:
            record(
                root,
                "child",
                {"pid": child.pid, "started": psutil.Process(child.pid).create_time()},
            )
            code = child.wait(timeout=180)
            record(root, "exit", {"code": code})
            return code
        finally:
            if child.poll() is None:
                stop_processes([psutil.Process(child.pid)])
                child.wait(timeout=15)


def terminal(root: Path, arguments: list[str]) -> int:
    if len(arguments) != 2 or arguments[0] != "-e":
        raise RuntimeError("Unexpected AppleScript invocation")
    match = re.fullmatch(
        r'tell app "Terminal" to do script "((?:[^"\\]|\\["\\])*)"', arguments[1]
    )
    if match is None:
        raise RuntimeError("Unexpected terminal AppleScript")
    command = re.sub(r'\\(["\\])', r"\1", match[1])
    suffix = '; read -p "Press enter to close"'
    if not command.startswith("/bin/bash ") or not command.endswith(suffix):
        raise RuntimeError("Unexpected terminal shell command")
    subprocess.run(
        ["/usr/bin/osacompile", "-o", str(root / "terminal.scpt"), "-e", arguments[1]],
        check=True,
        timeout=30,
    )
    code = run_external(
        root, ["/bin/bash", "-c", command.removesuffix(suffix)], "terminal.log"
    )
    record(root, "installer-exit", {"code": code})
    return code


def partial_copy(root: Path, arguments: list[str]) -> int:
    if sys.platform == "win32":
        source, destination = arguments[:2]
        executable = "RimSort.exe"
        code = 8
    else:
        source, destination = arguments[-2:]
        executable = "Contents/MacOS/RimSort" if sys.platform == "darwin" else "RimSort"
        code = 23
    source_path = contained(root, source)
    destination_path = contained(root, destination)
    if not source_path.is_dir():
        raise RuntimeError("Copy fault requires an existing fixture source")
    destination_path.mkdir(parents=True, exist_ok=True)
    source_file = source_path / executable
    target = destination_path / executable
    if source_file.resolve() == target.resolve():
        raise RuntimeError("Copy fault must not modify its source")
    target.parent.mkdir(parents=True, exist_ok=True)
    with source_file.open("rb") as original, target.open("wb") as partial:
        partial.write(original.read(min(4096, source_file.stat().st_size // 2)))
    assert 0 < target.stat().st_size < source_file.stat().st_size
    record(
        root,
        "copy-failed",
        {
            "arguments": arguments,
            "partial": str(target),
            "bytes": target.stat().st_size,
        },
    )
    return code


def installer(root: Path, arguments: list[str]) -> int:
    if len(arguments) != 1:
        raise RuntimeError("Unexpected installer supervisor arguments")
    request = json.loads(contained(root, arguments[0]).read_text())
    command, options = request["command"], request["options"]
    cwd = contained(root, options["cwd"])
    code = run_external(
        root, command, "installer.log", shell=options.get("shell", False), cwd=cwd
    )
    record(root, "installer-exit", {"code": code})
    return code


def msi(root: Path, arguments: list[str]) -> int:
    if len(arguments) != 1:
        raise RuntimeError("Unexpected MSI supervisor arguments")
    package = contained(root, arguments[0])
    transform = root / "upgrade.mst"
    if not transform.is_file():
        raise RuntimeError("Missing test-only launch transform")
    helpers = runpy.run_path(str(Path(__file__).with_name("msi_helpers.py")))
    code = helpers["run_msi"](
        root,
        "upgrade",
        ["/i", str(package)],
        {"INSTALLFOLDER": root / "install", "TRANSFORMS": transform},
    )
    record(root, "installer-exit", {"code": code})
    return code


if __name__ == "__main__":
    action, root_arg, *rest = sys.argv[1:]
    case_root = Path(root_arg).resolve(strict=True)
    if action == "cli":
        request = json.loads(contained(case_root, rest[0]).read_text(encoding="utf-8"))
        action, rest = request["operation"], request["args"]
    try:
        actions = {
            "killall": stop,
            "taskkill": stop,
            "nohup": launch,
            "open": launch,
            "osascript": terminal,
            "cp": partial_copy,
            "robocopy": partial_copy,
            "msi": msi,
            "installer": installer,
        }
        raise SystemExit(actions[action](case_root, rest))
    except Exception as error:
        record(case_root, f"{action}-error", {"error": repr(error)})
        raise

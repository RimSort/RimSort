"""Supervise only the MSI's final app launch with an isolated test profile."""

import json
import os
import subprocess
import sys
import traceback
from pathlib import Path

import psutil


def report(root: Path, phase: str, kind: str, data: dict[str, object]) -> None:
    destination = root / f"{phase}-{kind}.json"
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(json.dumps(data), encoding="utf-8")
    temporary.replace(destination)


def launch(root: Path, phase: str, target: Path) -> int:
    expected = root / "install/RimSort.exe"
    if target.resolve() != expected.resolve() or not expected.is_file():
        raise RuntimeError(f"MSI selected an unexpected launch target: {target}")
    env = os.environ.copy()
    for name in ("PYTHONPATH", "PYTHONHOME", "APPIMAGE", "APPDIR"):
        env.pop(name, None)
    env.update(
        RIMSORT_DEV="1",
        RIMSORT_DEV_DIR=str(root / "profile"),
        RIMSORT_MSI_TEST_ROOT=str(root),
        TMP=str(root / "tmp"),
        TEMP=str(root / "tmp"),
        TMPDIR=str(root / "tmp"),
    )
    if sys.platform == "win32":
        env["QT_QPA_PLATFORM"] = "windows"
    with (root / f"{phase}-stdout.log").open("w", encoding="utf-8") as output:
        child = subprocess.Popen(
            [str(target)], env=env, stdout=output, stderr=subprocess.STDOUT
        )
        try:
            report(
                root,
                phase,
                "launch",
                {
                    "target": str(target),
                    "pid": child.pid,
                    "started": psutil.Process(child.pid).create_time(),
                    "profile": env["RIMSORT_DEV_DIR"],
                    "cwd": os.getcwd(),
                },
            )
            result = child.wait(timeout=180)
            report(root, phase, "exit", {"code": result})
            return result
        finally:
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=15)


if __name__ == "__main__":
    case_root = Path(sys.argv[1]).resolve(strict=True)
    phase_name = sys.argv[2]
    try:
        sys.exit(launch(case_root, phase_name, Path(sys.argv[3])))
    except Exception:
        report(case_root, phase_name, "error", {"traceback": traceback.format_exc()})
        raise

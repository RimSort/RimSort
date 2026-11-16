"""Windows Installer command construction shared by the native test harnesses."""

import ctypes
import os
import subprocess
import sys
from ctypes import wintypes
from pathlib import Path


def require_windows_ci(directory: Path) -> None:
    if sys.platform != "win32":
        raise RuntimeError("Native MSI validation requires Windows")
    assert (
        os.environ.get("GITHUB_ACTIONS") == "true"
        and os.environ.get("RUNNER_OS") == "Windows"
    )
    assert directory.resolve().is_relative_to(Path(os.environ["RUNNER_TEMP"]).resolve())
    shell32 = ctypes.WinDLL("shell32")
    shell32.IsUserAnAdmin.argtypes = []
    shell32.IsUserAnAdmin.restype = wintypes.BOOL
    assert shell32.IsUserAnAdmin(), "MSI CI requires an already elevated runner"


def run_msi(
    root: Path,
    phase: str,
    arguments: list[str],
    properties: dict[str, Path] | None = None,
) -> int:
    command = subprocess.list2cmdline(
        [
            "msiexec.exe",
            *arguments,
            "/qn",
            "/norestart",
            "/L*V",
            str(root / f"{phase}-msi.log"),
        ]
    )
    # Windows Installer requires NAME="value", not "NAME=value".
    for name, value in (properties or {}).items():
        command += f' {name}="{value}"'
    return subprocess.run(command, check=False, timeout=240).returncode

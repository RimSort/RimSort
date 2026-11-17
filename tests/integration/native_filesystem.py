"""Real filesystem failure controls, restricted to owned disposable CI fixtures."""

import ctypes
import errno
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Generator
from contextlib import contextmanager
from ctypes import wintypes
from pathlib import Path
from uuid import uuid4

from tests.integration.upgrade_process import run_external

MIB = 1024 * 1024


def require_native_ci(root: Path, platform: str) -> None:
    if sys.platform != platform or os.environ.get("GITHUB_ACTIONS") != "true":
        raise RuntimeError("Filesystem controls require a disposable native CI runner")
    owner = Path(os.environ["RIMSORT_UPGRADE_ROOT"]).resolve(strict=True)
    runner = Path(os.environ["RUNNER_TEMP"]).resolve(strict=True)
    resolved = root.resolve(strict=True)
    if (
        resolved == owner
        or owner == runner
        or not resolved.is_relative_to(owner)
        or not owner.is_relative_to(runner)
    ):
        raise RuntimeError("Filesystem fixture escaped its runner task root")


@contextmanager
def windows_read_lock(root: Path, target: Path) -> Generator[None]:
    require_native_ci(root, "win32")
    if sys.platform != "win32":
        raise RuntimeError("Win32 file locking is unavailable")
    if not target.resolve(strict=True).is_relative_to(root.resolve(strict=True)):
        raise RuntimeError("Lock target escaped fixture")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    # Permit the actual backup reader, but deny installer writes and deletion.
    handle = kernel.CreateFileW(str(target), 0x80000000, 1, None, 3, 0x80, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        probe = kernel.CreateFileW(str(target), 0x40000000, 7, None, 3, 0x80, None)
        if probe != ctypes.c_void_p(-1).value:
            kernel.CloseHandle(probe)
            raise AssertionError("Win32 lock did not reject write access")
        error = ctypes.get_last_error()
        if error != 32:
            raise ctypes.WinError(error)
        yield
    finally:
        if not kernel.CloseHandle(handle):
            raise ctypes.WinError(ctypes.get_last_error())


def mount_identity(target: Path) -> dict[str, str] | None:
    result = subprocess.run(
        [
            "findmnt",
            "--json",
            "--mountpoint",
            str(target),
            "-o",
            "SOURCE,FSTYPE,TARGET",
        ],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if result.returncode == 1:
        return None
    result.check_returncode()
    entries = json.loads(result.stdout)["filesystems"]
    if len(entries) != 1:
        raise RuntimeError("Ambiguous filesystem mount")
    return entries[0]


@contextmanager
def limited_volume(root: Path, capacity: int) -> Generator[Path]:
    require_native_ci(root, "linux")
    if sys.platform != "linux":
        raise RuntimeError("Linux filesystem mounts are unavailable")
    if not 128 * MIB <= capacity <= 2 * 1024 * MIB or os.getuid() == 0:
        raise RuntimeError("Unsupported filesystem capacity or root test process")
    target = root / "volume"
    target.mkdir()
    expected = {
        "source": f"rimsort-test-{uuid4().hex}",
        "fstype": "tmpfs",
        "target": str(target.resolve()),
    }
    if mount_identity(target) is not None:
        raise RuntimeError("Fixture is already a mount")
    try:
        code = run_external(
            root,
            [
                "sudo",
                "-n",
                "mount",
                "-t",
                "tmpfs",
                "-o",
                f"size={capacity},nodev,nosuid,uid={os.getuid()},gid={os.getgid()}",
                expected["source"],
                str(target),
            ],
            "mount.log",
            timeout=30,
        )
        if code:
            raise RuntimeError(f"Isolated filesystem mount exited with {code}")
        if (
            mount_identity(target) != expected
            or target.stat().st_dev == root.stat().st_dev
        ):
            raise RuntimeError("Isolated filesystem was not mounted as requested")
        yield target
    finally:
        actual = mount_identity(target)
        if actual is not None:
            if actual != expected:
                raise RuntimeError("Refusing to unmount an unexpected filesystem")
            code = run_external(
                root,
                ["sudo", "-n", "umount", str(target)],
                "unmount.log",
                timeout=30,
            )
            if code or mount_identity(target) is not None:
                raise RuntimeError("Fixture filesystem survived unmount")


def exhaust_volume(root: Path, volume: Path) -> int:
    require_native_ci(root, "linux")
    if sys.platform != "linux":
        raise RuntimeError("Linux allocation controls are unavailable")
    identity = mount_identity(volume)
    if (
        volume != root / "volume"
        or identity is None
        or identity["fstype"] != "tmpfs"
        or identity["target"] != str(volume.resolve())
        or re.fullmatch(r"rimsort-test-[0-9a-f]{32}", identity["source"]) is None
    ):
        raise RuntimeError("Disk exhaustion requires an isolated Linux mount")
    remaining = MIB
    assert shutil.disk_usage(volume).free > 2 * remaining
    with (volume / "space-filler").open("wb") as output:
        os.posix_fallocate(
            output.fileno(), 0, shutil.disk_usage(volume).free - remaining
        )
    probe = volume / "enospc-probe"
    try:
        with probe.open("wb") as output:
            try:
                os.posix_fallocate(output.fileno(), 0, 2 * remaining)
            except OSError as error:
                if error.errno != errno.ENOSPC:
                    raise
            else:
                raise AssertionError("Isolated filesystem did not report ENOSPC")
    finally:
        probe.unlink(missing_ok=True)
    available = shutil.disk_usage(volume).free
    assert 0 < available <= remaining
    return available

"""Diagnose SteamCMD binaries that cannot execute on this Linux host.

SteamCMD ships a 32-bit Linux build that needs a 32-bit glibc loader
(``/lib/ld-linux.so.2``). On distros without multilib installed, the launcher
reports ``cannot execute: required file not found``, which names no missing
package and is unactionable for users (#2475).

Rather than executing SteamCMD (which would trigger a network self-update), this
module reads the binary's ELF headers to find the exact interpreter it needs and
reports it when that interpreter is absent, together with the package names that
provide it on the host distro.

Nothing here touches Qt or translations; rendering is left to the caller.
"""

import struct
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

_ELF_MAGIC = b"\x7fELF"
_PT_INTERP = 3
# Sanity bounds so a corrupt or hostile header cannot spin us.
_MAX_PHNUM = 128
_MIN_PHENTSIZE = 32

# Probed only when the interpreter cannot be read from the binary itself.
_FALLBACK_32BIT_LOADERS = (
    "/lib/ld-linux.so.2",
    "/lib32/ld-linux.so.2",
    "/lib/i386-linux-gnu/ld-linux.so.2",
)

# os-release ID (or an ID_LIKE family) -> packages providing 32-bit glibc.
_MULTILIB_PACKAGES: dict[str, str] = {
    "arch": "lib32-glibc and lib32-gcc-libs",
    "manjaro": "lib32-glibc and lib32-gcc-libs",
    "cachyos": "lib32-glibc and lib32-gcc-libs",
    "endeavouros": "lib32-glibc and lib32-gcc-libs",
    "artix": "lib32-glibc",
    "debian": "lib32gcc-s1 and lib32stdc++6",
    "ubuntu": "lib32gcc-s1 and lib32stdc++6",
    "linuxmint": "lib32gcc-s1 and lib32stdc++6",
    "raspbian": "lib32gcc-s1 and lib32stdc++6",
    "fedora": "glibc.i686 and libstdc++.i686",
    "rhel": "glibc.i686 and libstdc++.i686",
    "centos": "glibc.i686 and libstdc++.i686",
    "opensuse": "lib32glibc2 and lib32stdc++6",
    "suse": "lib32glibc2 and lib32stdc++6",
    "gentoo": "app-emul32-i386",
    "alpine": "lib32-gcompat (musl hosts)",
}
_GENERIC_HINT = "a 32-bit glibc runtime (multilib support)"

_DEFAULT_OS_RELEASE = Path("/etc/os-release")


@dataclass(frozen=True)
class ElfInfo:
    """What we could learn from an ELF header.

    :param is_32bit: True when the binary is ELFCLASS32.
    :param interpreter: PT_INTERP path, or None when the header has none.
    """

    is_32bit: bool
    interpreter: str | None


@dataclass(frozen=True)
class SteamcmdProblem:
    """A SteamCMD install that cannot run on this host.

    :param binary: The offending SteamCMD binary.
    :param missing_loader: Interpreter path that does not exist on this host.
    :param distro_id: os-release ID when it could be read, else None.
    """

    binary: Path
    missing_loader: str
    distro_id: str | None


def _path_exists(path: Path) -> bool:
    return path.exists()


def read_elf_info(path: Path) -> ElfInfo | None:
    """Read ELF class and PT_INTERP from a binary.

    :param path: Candidate binary.
    :return: ElfInfo, or None when the file is missing or not a usable ELF.
    """
    try:
        data = path.read_bytes()
    except OSError:
        return None

    if len(data) < 16 or data[:4] != _ELF_MAGIC:
        return None

    ei_class, ei_data = data[4], data[5]
    if ei_class not in (1, 2) or ei_data not in (1, 2):
        return None

    endian = "<" if ei_data == 1 else ">"
    is_32bit = ei_class == 1

    try:
        if is_32bit:
            phoff = struct.unpack_from(f"{endian}I", data, 28)[0]
            phentsize = struct.unpack_from(f"{endian}H", data, 42)[0]
            phnum = struct.unpack_from(f"{endian}H", data, 44)[0]
        else:
            phoff = struct.unpack_from(f"{endian}Q", data, 32)[0]
            phentsize = struct.unpack_from(f"{endian}H", data, 54)[0]
            phnum = struct.unpack_from(f"{endian}H", data, 56)[0]
    except struct.error:
        return None

    if phentsize < _MIN_PHENTSIZE or phnum > _MAX_PHNUM:
        return ElfInfo(is_32bit, None)

    for index in range(phnum):
        header = phoff + index * phentsize
        try:
            # p_type sits at 0 in both classes; p_offset and p_filesz do not.
            p_type = struct.unpack_from(f"{endian}I", data, header)[0]
            if p_type != _PT_INTERP:
                continue
            if is_32bit:
                p_offset = struct.unpack_from(f"{endian}I", data, header + 4)[0]
                p_filesz = struct.unpack_from(f"{endian}I", data, header + 16)[0]
            else:
                p_offset = struct.unpack_from(f"{endian}Q", data, header + 8)[0]
                p_filesz = struct.unpack_from(f"{endian}Q", data, header + 32)[0]
            raw = data[p_offset : p_offset + p_filesz]
        except struct.error, IndexError:
            break
        interpreter = raw.split(b"\x00", 1)[0].decode("utf-8", errors="replace")
        return ElfInfo(is_32bit, interpreter or None)

    return ElfInfo(is_32bit, None)


def resolve_steamcmd_binary(
    install_path: Path, *, exists: Callable[[Path], bool] = _path_exists
) -> Path | None:
    """Locate the SteamCMD ELF binary inside an install directory.

    SteamCMD ships ``linux64/steamcmd`` and sometimes ``linux32/steamcmd``;
    the host's own bitness decides which one the launcher would use.

    :param install_path: The SteamCMD install directory.
    :param exists: Existence probe, injectable for tests.
    :return: Path to the binary the launcher would pick, or None if absent.
    """
    candidates = (
        ("linux64", "linux32") if sys.maxsize > 2**32 else ("linux32", "linux64")
    )
    for folder in candidates:
        candidate = Path(install_path) / folder / "steamcmd"
        if exists(candidate):
            return candidate
    return None


def detect_missing_loader(
    binary: Path, *, exists: Callable[[Path], bool] = _path_exists
) -> str | None:
    """Return the interpreter path this binary needs but cannot find.

    Only 32-bit binaries are judged: the 64-bit SteamCMD build is expected to
    find its own loader, so a missing one is a different (broken system)
    situation and must not be reported as a multilib problem.

    :param binary: SteamCMD binary to inspect.
    :param exists: Existence probe, injectable for tests.
    :return: The missing loader path, or None when the binary looks runnable.
    """
    info = read_elf_info(binary)
    if info is None:
        # Not an ELF (launcher script, or unreadable): nothing to judge here.
        return None

    if not info.is_32bit:
        return None

    if info.interpreter:
        return None if exists(Path(info.interpreter)) else info.interpreter

    # 32-bit binary with no PT_INTERP: the loader must be one of the usual ones.
    if any(exists(Path(candidate)) for candidate in _FALLBACK_32BIT_LOADERS):
        return None
    return _FALLBACK_32BIT_LOADERS[0]


def read_distro_id(
    os_release: Path = _DEFAULT_OS_RELEASE,
) -> str | None:
    """Read the distro identifier from an os-release file.

    Falls back to the first ID_LIKE entry when ID is absent or unknown.

    :param os_release: Path to the os-release file, injectable for tests.
    :return: Lower-case distro ID, or None when it cannot be determined.
    """
    try:
        text = os_release.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    fields: dict[str, str] = {}
    likes: list[str] = []
    for line in text.splitlines():
        key, _, value = line.partition("=")
        value = value.strip().strip('"').strip("'").lower()
        if key.strip() == "ID":
            fields["ID"] = value
        elif key.strip() == "ID_LIKE":
            likes = [item.strip() for item in value.split() if item.strip()]

    distro = fields.get("ID", "")
    if distro:
        return distro
    return likes[0] if likes else None


def multilib_hint(distro_id: str | None) -> str:
    """Return the packages that provide 32-bit glibc on this distro.

    :param distro_id: os-release ID, or None when unknown.
    :return: Human-readable package hint, generic when the distro is unknown.
    """
    if not distro_id:
        return _GENERIC_HINT
    if distro_id in _MULTILIB_PACKAGES:
        return _MULTILIB_PACKAGES[distro_id]
    for like in distro_id.split():
        if like in _MULTILIB_PACKAGES:
            return _MULTILIB_PACKAGES[like]
    return _GENERIC_HINT


def diagnose_steamcmd_executable(
    install_path: Path,
    *,
    system: str,
    exists: Callable[[Path], bool] = _path_exists,
    os_release: Path = _DEFAULT_OS_RELEASE,
) -> SteamcmdProblem | None:
    """Check whether an installed SteamCMD can execute on this host.

    :param install_path: The SteamCMD install directory.
    :param system: ``platform.system()`` value; only Linux is diagnosed.
    :param exists: Existence probe, injectable for tests.
    :param os_release: os-release path, injectable for tests.
    :return: SteamcmdProblem when a required loader is missing, else None.
    """
    if system != "Linux":
        return None

    binary = resolve_steamcmd_binary(Path(install_path), exists=exists)
    if binary is None:
        return None

    missing = detect_missing_loader(binary, exists=exists)
    if missing is None:
        return None

    return SteamcmdProblem(
        binary=binary,
        missing_loader=missing,
        distro_id=read_distro_id(os_release),
    )

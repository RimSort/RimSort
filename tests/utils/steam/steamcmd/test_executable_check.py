"""Tests for the Linux SteamCMD runnability diagnostics (#2475).

SteamCMD's 32-bit Linux build needs a 32-bit glibc loader. On distros without
multilib the launcher only reports "cannot execute: required file not found",
which names no package. These tests build real (tiny) ELF headers so the
parser is exercised rather than trusted.
"""

import struct
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QCoreApplication

from app.utils.steam.steamcmd import executable_check as ec
from app.utils.steam.steamcmd import wrapper
from app.utils.steam.steamcmd.wrapper import SteamcmdInterface

_PT_INTERP = 3
_PT_LOAD = 1


def _build_elf(interpreter: str | None, *, is_32bit: bool = True) -> bytes:
    """Build a minimal ELF file with a single PT_INTERP program header."""
    endian = "<"
    ident = b"\x7fELF" + bytes([1 if is_32bit else 2, 1]) + b"\x00" * 10

    interp_bytes = (interpreter + "\x00").encode() if interpreter else b""

    if is_32bit:
        header_size, phentsize, phoff = 52, 32, 52
        rest = struct.pack(
            f"{endian}HHIIIIIHHHHHH",
            2,  # e_type
            3,  # e_machine
            1,  # e_version
            0,  # e_entry
            phoff,  # e_phoff
            0,  # e_shoff
            0,  # e_flags
            header_size,  # e_ehsize
            phentsize,  # e_phentsize
            1,  # e_phnum
            40,  # e_shentsize
            0,  # e_shnum
            0,  # e_shstrndx
        )
    else:
        header_size, phentsize, phoff = 64, 56, 64
        rest = struct.pack(
            f"{endian}HHIQQQIHHHHHH",
            2,  # e_type
            62,  # e_machine (x86-64)
            1,  # e_version
            0,  # e_entry
            phoff,  # e_phoff
            0,  # e_shoff
            0,  # e_flags
            header_size,  # e_ehsize
            phentsize,  # e_phentsize
            1,  # e_phnum
            64,  # e_shentsize
            0,  # e_shnum
            0,  # e_shstrndx
        )

    interp_offset = phoff + phentsize
    if is_32bit:
        phdr = struct.pack(
            f"{endian}IIIIIIII",
            _PT_INTERP,
            interp_offset,
            0,
            0,
            len(interp_bytes),
            0,
            1,
            0,
        )
    else:
        phdr = struct.pack(
            f"{endian}IIQQQQQQ",
            _PT_INTERP,
            4,  # p_flags
            interp_offset,
            0,
            0,
            len(interp_bytes),
            0,
            1,
        )
    return ident + rest + phdr + interp_bytes


def _write_install(root: Path, binary_bytes: bytes, *, folder: str = "linux32") -> Path:
    binary = root / folder / "steamcmd"
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_bytes(binary_bytes)
    return binary


class TestReadElfInfo:
    def test_parses_32bit_interpreter(self, tmp_path: Path) -> None:
        binary = tmp_path / "steamcmd"
        binary.write_bytes(_build_elf("/lib/ld-linux.so.2"))

        info = ec.read_elf_info(binary)

        assert info is not None
        assert info.is_32bit is True
        assert info.interpreter == "/lib/ld-linux.so.2"

    def test_parses_64bit_interpreter(self, tmp_path: Path) -> None:
        binary = tmp_path / "steamcmd"
        binary.write_bytes(_build_elf("/lib64/ld-linux-x86-64.so.2", is_32bit=False))

        info = ec.read_elf_info(binary)

        assert info is not None
        assert info.is_32bit is False
        assert info.interpreter == "/lib64/ld-linux-x86-64.so.2"

    def test_ignores_non_elf(self, tmp_path: Path) -> None:
        script = tmp_path / "steamcmd.sh"
        script.write_text('#!/bin/sh\nexec linux32/steamcmd "$@"\n')

        assert ec.read_elf_info(script) is None

    def test_ignores_missing_file(self, tmp_path: Path) -> None:
        assert ec.read_elf_info(tmp_path / "absent") is None

    def test_rejects_corrupt_phnum(self, tmp_path: Path) -> None:
        raw = bytearray(_build_elf("/lib/ld-linux.so.2"))
        struct.pack_into("<H", raw, 44, 4096)  # e_phnum past our sanity bound
        binary = tmp_path / "steamcmd"
        binary.write_bytes(bytes(raw))

        info = ec.read_elf_info(binary)

        assert info is not None
        assert info.interpreter is None


class TestDetectMissingLoader:
    def test_reports_missing_interpreter(self, tmp_path: Path) -> None:
        binary = tmp_path / "steamcmd"
        binary.write_bytes(_build_elf("/lib/ld-linux.so.2"))

        missing = ec.detect_missing_loader(binary, exists=lambda _: False)

        assert missing == "/lib/ld-linux.so.2"

    def test_accepts_present_interpreter(self, tmp_path: Path) -> None:
        binary = tmp_path / "steamcmd"
        binary.write_bytes(_build_elf("/lib/ld-linux.so.2"))

        assert ec.detect_missing_loader(binary, exists=lambda _: True) is None

    def test_64bit_binary_never_flagged(self, tmp_path: Path) -> None:
        binary = tmp_path / "steamcmd"
        binary.write_bytes(_build_elf("/lib64/ld.so", is_32bit=False))

        assert ec.detect_missing_loader(binary, exists=lambda _: False) is None

    def test_falls_back_to_probe_list_without_interp(self, tmp_path: Path) -> None:
        binary = tmp_path / "steamcmd"
        binary.write_bytes(_build_elf(None))

        missing = ec.detect_missing_loader(binary, exists=lambda _: False)

        assert missing == "/lib/ld-linux.so.2"
        assert (
            ec.detect_missing_loader(
                binary, exists=lambda p: str(p) == "/lib32/ld-linux.so.2"
            )
            is None
        )

    def test_non_elf_is_not_judged(self, tmp_path: Path) -> None:
        binary = tmp_path / "steamcmd.sh"
        binary.write_text("#!/bin/sh\n")

        assert ec.detect_missing_loader(binary, exists=lambda _: False) is None


class TestDistroHints:
    @pytest.mark.parametrize(
        ("os_release_body", "expected"),
        [
            ('ID=arch\nNAME="Arch Linux"\n', "arch"),
            ('ID=debian\nID_LIKE="ubuntu debian"\n', "debian"),
            ('ID_LIKE="arch"\n', "arch"),
            ('ID="Fedora"\n', "fedora"),
            ("ID=weirdos\n", "weirdos"),
            ("", None),
        ],
    )
    def test_read_distro_id(
        self, tmp_path: Path, os_release_body: str, expected: str | None
    ) -> None:
        os_release = tmp_path / "os-release"
        os_release.write_text(os_release_body)

        assert ec.read_distro_id(os_release) == expected

    @pytest.mark.parametrize(
        ("distro", "expected"),
        [
            ("arch", "lib32-glibc and lib32-gcc-libs"),
            ("ubuntu", "lib32gcc-s1 and lib32stdc++6"),
            ("fedora", "glibc.i686 and libstdc++.i686"),
            ("nixos", ec._GENERIC_HINT),
            (None, ec._GENERIC_HINT),
        ],
    )
    def test_multilib_hint(self, distro: str | None, expected: str) -> None:
        assert ec.multilib_hint(distro) == expected


class TestDiagnoseSteamcmdExecutable:
    def test_ignores_non_linux(self, tmp_path: Path) -> None:
        _write_install(tmp_path, _build_elf("/lib/ld-linux.so.2"))

        assert ec.diagnose_steamcmd_executable(tmp_path, system="Windows") is None

    def test_ignores_missing_binary(self, tmp_path: Path) -> None:
        assert ec.diagnose_steamcmd_executable(tmp_path, system="Linux") is None

    def test_reports_problem_with_distro(self, tmp_path: Path) -> None:
        install = tmp_path / "steamcmd"
        _write_install(install, _build_elf("/lib/ld-linux.so.2"), folder="linux32")
        os_release = tmp_path / "os-release"
        os_release.write_text("ID=arch\n")

        def exists(candidate: Path) -> bool:
            # Only the installed binary exists; the system loader does not.
            return candidate == install / "linux32" / "steamcmd"

        problem = ec.diagnose_steamcmd_executable(
            install,
            system="Linux",
            exists=exists,
            os_release=os_release,
        )

        assert problem is not None
        assert problem.missing_loader == "/lib/ld-linux.so.2"
        assert problem.distro_id == "arch"
        assert ec.multilib_hint(problem.distro_id) == "lib32-glibc and lib32-gcc-libs"

    def test_clean_install_reports_nothing(self, tmp_path: Path) -> None:
        install = tmp_path / "steamcmd"
        _write_install(install, _build_elf("/lib/ld-linux.so.2"), folder="linux32")

        problem = ec.diagnose_steamcmd_executable(
            install, system="Linux", exists=lambda _: True
        )

        assert problem is None


class TestWrapperReportsProblem:
    """The wrapper must turn a diagnosis into actionable, translated output."""

    def _interface(self, install_path: Path, system: str = "Linux") -> Any:
        interface = SteamcmdInterface.__new__(SteamcmdInterface)
        interface.steamcmd_install_path = str(install_path)
        interface.system = system
        interface.translate = QCoreApplication.translate
        return interface

    def test_missing_loader_shows_distro_hint(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        problem = ec.SteamcmdProblem(
            binary=Path("/steamcmd/linux32/steamcmd"),
            missing_loader="/lib/ld-linux.so.2",
            distro_id="arch",
        )
        shown: dict[str, Any] = {}

        def fake_warning(**kwargs: Any) -> None:
            shown.update(kwargs)

        monkeypatch.setattr(
            wrapper, "diagnose_steamcmd_executable", lambda *a, **k: problem
        )
        monkeypatch.setattr(wrapper, "show_warning", fake_warning)
        runner = MagicMock()

        assert self._interface(tmp_path).check_steamcmd_runnable(runner) is False

        assert "/lib/ld-linux.so.2" in shown["information"]
        assert "lib32-glibc" in shown["information"]
        assert shown["title"] == "SteamCMD cannot run on this system"
        runner.message.assert_called_once()

    def test_healthy_install_is_silent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            wrapper, "diagnose_steamcmd_executable", lambda *a, **k: None
        )
        monkeypatch.setattr(
            wrapper, "show_warning", lambda **kwargs: pytest.fail("unexpected warning")
        )

        assert self._interface(tmp_path).check_steamcmd_runnable() is True

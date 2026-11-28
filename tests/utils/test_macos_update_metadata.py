"""macOS update extraction must restore AppleDouble signing metadata."""

import ctypes
import errno
import io
import os
import subprocess
import sys
import tarfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.utils.update_utils import TarExtractThread


def _extract(archive: Path, destination: Path) -> tuple[bool, str]:
    results: list[tuple[bool, str]] = []
    thread = TarExtractThread(str(archive), str(destination))
    thread.finished.connect(lambda success, message: results.append((success, message)))
    thread.run()
    assert len(results) == 1
    return results[0]


@pytest.fixture
def metadata_archive(tmp_path: Path) -> Path:
    return _write_metadata_archive(
        tmp_path, b"\x00\x05\x16\x07\x00\x02\x00\x00invalid metadata"
    )


def _write_metadata_archive(
    tmp_path: Path, sidecar: bytes, directory: bool = False
) -> Path:
    archive = tmp_path / "metadata.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        target = tarfile.TarInfo("resource")
        if directory:
            target.type = tarfile.DIRTYPE
        tar.addfile(target)
        for name, content in (
            ("._resource", sidecar),
            ("._ordinary", b"ordinary file"),
        ):
            info = tarfile.TarInfo(name)
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
    return archive


@pytest.fixture
def native_metadata(tmp_path: Path) -> bytes:
    source = tmp_path / "source"
    source.mkdir()
    resource = source / "resource"
    resource.write_bytes(b"data fork")
    for name, value in (
        ("com.rimsort.test", "metadata"),
        ("com.apple.ResourceFork", "resource fork"),
    ):
        subprocess.run(["/usr/bin/xattr", "-w", name, value, str(resource)], check=True)
    subprocess.run(
        ["/bin/chmod", "+a", "everyone allow read", str(resource)], check=True
    )
    archive = tmp_path / "native.tar.gz"
    archive_env = dict(os.environ)
    archive_env.pop("COPYFILE_DISABLE", None)
    subprocess.run(
        ["/usr/bin/tar", "--acls", "-czf", str(archive), "-C", str(source), "resource"],
        check=True,
        env=archive_env,
    )
    with tarfile.open(archive) as tar:
        stream = tar.extractfile("._resource")
        assert stream is not None
        content = stream.read()
    assert b"resource fork" in content
    assert b"com.rimsort.test" in content
    assert b"com.apple.acl.text" in content
    return content


@pytest.mark.skipif(sys.platform != "darwin", reason="Requires macOS archive tools")
def test_extract_preserves_macos_metadata(tmp_path: Path) -> None:
    source = tmp_path / "source" / "RimSort.app"
    resources = source / "Contents" / "Resources"
    resources.mkdir(parents=True)
    resource = resources / "translations.qm"
    resource.write_bytes(b"signed translation resource")
    subprocess.run(["/usr/bin/codesign", "--sign", "-", str(resource)], check=True)
    subprocess.run(
        ["/usr/bin/xattr", "-w", "com.rimsort.test", "archive metadata", str(source)],
        check=True,
    )
    fork_file = resources / "fork.dat"
    fork_file.write_bytes(b"data fork")
    subprocess.run(
        [
            "/usr/bin/xattr",
            "-w",
            "com.apple.ResourceFork",
            "resource fork",
            str(fork_file),
        ],
        check=True,
    )
    subprocess.run(
        ["/usr/bin/codesign", "--verify", "--strict", str(resource)], check=True
    )
    executable = source / "Contents" / "MacOS" / "RimSort"
    executable.parent.mkdir()
    executable.write_text("#!/bin/sh\nexit 0\n")
    executable.chmod(0o755)
    (resources / "current.qm").symlink_to(resource.name)
    archive = tmp_path / "update.tar.gz"
    archive_env = dict(os.environ)
    archive_env.pop("COPYFILE_DISABLE", None)
    subprocess.run(
        ["/usr/bin/tar", "-czf", str(archive), "-C", str(source.parent), source.name],
        check=True,
        env=archive_env,
    )
    destination = tmp_path / "extracted"
    destination.mkdir()
    success, message = _extract(archive, destination)
    assert success, message
    restored = destination / source.name
    restored_resource = restored / resource.relative_to(source)
    subprocess.run(
        ["/usr/bin/codesign", "--verify", "--strict", str(restored_resource)],
        check=True,
    )
    for original, extracted, attribute in (
        (source, restored, "com.rimsort.test"),
        (fork_file, restored / fork_file.relative_to(source), "com.apple.ResourceFork"),
    ):
        assert subprocess.check_output(
            ["/usr/bin/xattr", "-px", attribute, str(extracted)]
        ) == subprocess.check_output(
            ["/usr/bin/xattr", "-px", attribute, str(original)]
        )
    assert restored_resource.read_bytes() == resource.read_bytes()
    assert (restored / executable.relative_to(source)).stat().st_mode & 0o777 == 0o755
    assert (restored_resource.parent / "current.qm").readlink() == Path(resource.name)
    assert not list(destination.rglob("._*"))


@pytest.mark.skipif(sys.platform != "darwin", reason="Requires macOS metadata API")
def test_metadata_failure_does_not_report_success(
    tmp_path: Path, metadata_archive: Path
) -> None:
    destination = tmp_path / "extracted"
    destination.mkdir()
    success, message = _extract(metadata_archive, destination)
    assert not success
    assert "Extraction error" in message
    assert (destination / "._resource").exists()
    assert (destination / "resource").read_bytes() == b""


@pytest.mark.skipif(sys.platform != "darwin", reason="Requires macOS metadata API")
def test_native_error_is_not_hidden_by_acl_restore(
    tmp_path: Path, native_metadata: bytes
) -> None:
    archive = _write_metadata_archive(tmp_path, native_metadata, directory=True)
    destination = tmp_path / "extracted"
    success, message = _extract(archive, destination)
    assert not success
    assert "Extraction error" in message
    assert (destination / "._resource").read_bytes() == native_metadata


@pytest.mark.skipif(sys.platform != "darwin", reason="Requires macOS metadata API")
def test_metadata_restoration_does_not_depend_on_directory_scanning(
    tmp_path: Path, native_metadata: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = _write_metadata_archive(tmp_path, native_metadata)
    destination = tmp_path / "extracted"
    scan = MagicMock(side_effect=OSError(errno.EIO, "Directory scan failed"))
    monkeypatch.setattr(os, "scandir", scan)
    success, message = _extract(archive, destination)
    assert success, message
    scan.assert_not_called()
    assert not (destination / "._resource").exists()
    assert (
        subprocess.check_output(
            ["/usr/bin/xattr", "-p", "com.rimsort.test", str(destination / "resource")]
        ).strip()
        == b"metadata"
    )


@pytest.mark.skipif(sys.platform != "darwin", reason="Requires macOS metadata API")
def test_cancel_during_final_native_unpack(
    tmp_path: Path, native_metadata: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = _write_metadata_archive(tmp_path, native_metadata)
    thread = TarExtractThread(str(archive), str(tmp_path / "extracted"))
    results: list[tuple[bool, str]] = []
    thread.finished.connect(lambda success, message: results.append((success, message)))
    native = ctypes.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True)
    copyfile = native.copyfile
    copyfile.argtypes = [
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_void_p,
        ctypes.c_uint32,
    ]
    copyfile.restype = ctypes.c_int

    def unpack(source: bytes, destination: bytes, state: int, flags: int) -> int:
        result: int = copyfile(source, destination, state, flags)
        thread.stop()
        return result

    monkeypatch.setattr(native, "copyfile", MagicMock(side_effect=unpack))
    monkeypatch.setattr(ctypes, "CDLL", MagicMock(return_value=native))
    thread.run()
    assert results == [(False, "Operation aborted")]


@pytest.mark.skipif(sys.platform != "darwin", reason="Requires macOS metadata API")
def test_ordinary_dot_underscore_file_is_preserved(tmp_path: Path) -> None:
    archive = tmp_path / "ordinary.tar.gz"
    content = b"ordinary file, not AppleDouble metadata"
    with tarfile.open(archive, "w:gz") as tar:
        info = tarfile.TarInfo("._ordinary")
        info.size = len(content)
        tar.addfile(info, io.BytesIO(content))
    destination = tmp_path / "extracted"
    success, message = _extract(archive, destination)
    assert success, message
    assert (destination / "._ordinary").read_bytes() == content


@pytest.mark.skipif(sys.platform != "darwin", reason="Requires macOS metadata API")
def test_cancel_before_metadata_unpack(tmp_path: Path, metadata_archive: Path) -> None:
    thread = TarExtractThread(str(metadata_archive), str(tmp_path / "extracted"))
    results: list[tuple[bool, str]] = []
    thread.finished.connect(lambda success, message: results.append((success, message)))
    thread.progress.connect(
        lambda percent, _message: thread.stop() if percent == 100 else None
    )
    thread.run()
    assert results == [(False, "Operation aborted")]


def test_non_macos_extraction_does_not_unpack_metadata(
    tmp_path: Path, metadata_archive: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    unpack = MagicMock(side_effect=AssertionError("macOS metadata API called"))
    monkeypatch.setattr(TarExtractThread, "_restore_macos_metadata", unpack)
    destination = tmp_path / "extracted"
    success, message = _extract(metadata_archive, destination)
    assert success, message
    unpack.assert_not_called()
    assert (destination / "._ordinary").read_bytes() == b"ordinary file"


@pytest.mark.parametrize("kind", ["parent-path", "symlink", "hardlink", "fifo"])
def test_unsafe_archive_members_are_rejected(tmp_path: Path, kind: str) -> None:
    archive = tmp_path / "unsafe.tar.gz"
    member = tarfile.TarInfo("resource")
    if kind == "parent-path":
        member.name = "../escaped"
    elif kind in {"symlink", "hardlink"}:
        member.type = tarfile.SYMTYPE if kind == "symlink" else tarfile.LNKTYPE
        member.linkname = "../escaped"
    else:
        member.type = tarfile.FIFOTYPE
    with tarfile.open(archive, "w:gz") as tar:
        tar.addfile(member)
    success, _ = _extract(archive, tmp_path / "extracted")
    assert not success
    assert not (tmp_path / "escaped").exists()

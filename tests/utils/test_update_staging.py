"""Update attempts must not share staging files or archive cleanup."""

import errno
import os
import stat
import tarfile
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from threading import Barrier
from unittest.mock import MagicMock, patch
from uuid import UUID
from zipfile import ZipFile

import pytest
from pytestqt.qtbot import QtBot

from app.models.settings import Settings
from app.utils import update_utils
from app.utils.update_utils import UpdateExtractionError, UpdateManager
from app.views.task_progress_window import TaskProgressWindow


@pytest.fixture
def staging_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    clock = MagicMock(wraps=datetime)
    clock.now.return_value = datetime(2026, 11, 15, 12, tzinfo=UTC)
    monkeypatch.setattr(update_utils, "datetime", clock)
    monkeypatch.setattr(update_utils.tempfile, "tempdir", str(tmp_path))
    return tmp_path


@pytest.fixture
def manager(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> UpdateManager:
    window = TaskProgressWindow

    def progress(
        title: str, show_message: bool, show_percent: bool
    ) -> TaskProgressWindow:
        widget = window(title, show_message, show_percent)
        qtbot.addWidget(widget)
        return widget

    monkeypatch.setattr(update_utils, "TaskProgressWindow", progress)
    return UpdateManager(Settings(), MagicMock())


def archive(content: bytes, is_tar_gz: bool) -> bytes:
    buffer = BytesIO()
    if is_tar_gz:
        with tarfile.open(fileobj=buffer, mode="w:gz") as output:
            entry = tarfile.TarInfo("payload.bin")
            entry.size = len(content)
            output.addfile(entry, BytesIO(content))
    else:
        with ZipFile(buffer, "w") as output:
            output.writestr("payload.bin", content)
    return buffer.getvalue()


def test_same_second_allocations_preserve_existing_files(
    manager: UpdateManager, staging_root: Path
) -> None:
    first = manager._create_temp_dir()
    (first / "marker").write_text("first attempt")
    second = manager._create_temp_dir()

    assert first != second
    assert first.parent == second.parent == staging_root
    assert (first / "marker").read_text() == "first attempt"
    assert list(second.iterdir()) == []


def test_parallel_allocations_are_exclusively_owned(
    manager: UpdateManager, staging_root: Path
) -> None:
    ready = Barrier(4)

    def allocate(index: int) -> Path:
        ready.wait(timeout=5)
        directory = manager._create_temp_dir()
        (directory / "marker").write_text(str(index))
        return directory

    with ThreadPoolExecutor(max_workers=4) as workers:
        directories = list(workers.map(allocate, range(4)))

    assert len(set(directories)) == 4
    for index, directory in enumerate(directories):
        assert directory.parent == staging_root
        assert (directory / "marker").read_text() == str(index)


def test_name_collision_preserves_existing_attempt(
    manager: UpdateManager, staging_root: Path
) -> None:
    with patch.object(update_utils, "uuid4", return_value=UUID(int=0), create=True):
        existing = manager._create_temp_dir()
        (existing / "marker").write_text("existing attempt")
        with pytest.raises(FileExistsError):
            manager._create_temp_dir()

    assert (existing / "marker").read_text() == "existing attempt"
    assert existing.parent == staging_root


@pytest.mark.skipif(os.name == "nt", reason="POSIX directory permissions")
def test_staging_preserves_directory_permissions(
    manager: UpdateManager, staging_root: Path
) -> None:
    """Staging permissions can be copied onto flat Linux installations."""
    control = staging_root / "control"
    control.mkdir()
    directory = manager._create_temp_dir()

    assert stat.S_IMODE(directory.stat().st_mode) == stat.S_IMODE(
        control.stat().st_mode
    )


def test_msi_retry_preserves_previous_installer(
    manager: UpdateManager, staging_root: Path
) -> None:
    manager._update_content = b"first installer"
    first = manager._extract_update(is_msi=True)
    manager._update_content = b"second installer"
    second = manager._extract_update(is_msi=True)

    assert first != second
    assert first.parent.parent == second.parent.parent == staging_root
    assert first.read_bytes() == b"first installer"
    assert second.read_bytes() == b"second installer"
    assert manager._extracted_path == second


@pytest.mark.parametrize("is_tar_gz", [False, True], ids=["zip", "tar-gz"])
@pytest.mark.parametrize("failure", [False, True], ids=["success", "failure-retry"])
def test_archive_cleanup_preserves_another_attempt(
    manager: UpdateManager, staging_root: Path, is_tar_gz: bool, failure: bool
) -> None:
    other = manager._create_temp_dir()
    (other / "marker").write_text("other attempt")
    extension = ".tar.gz" if is_tar_gz else ".zip"
    other_archive = other.parent / f"{other.name}{extension}"
    other_content = archive(b"other payload", is_tar_gz)
    other_archive.write_bytes(other_content)
    current = manager._create_temp_dir()
    extract = manager._extract_tar_gz if is_tar_gz else manager._extract_zip

    if failure:
        with pytest.raises(UpdateExtractionError):
            extract(b"invalid archive", current)
        assert list(current.iterdir()) == []
    else:
        assert extract(archive(b"current payload", is_tar_gz), current) == 1
        assert (current / "payload.bin").read_bytes() == b"current payload"

    current_archive = current.parent / f"{current.name}{extension}"
    assert not current_archive.exists()
    assert other_archive.read_bytes() == other_content
    assert (other / "marker").read_text() == "other attempt"

    if failure:
        retry = manager._create_temp_dir()
        assert retry not in (current, other)
        assert extract(archive(b"retry payload", is_tar_gz), retry) == 1
        assert (retry / "payload.bin").read_bytes() == b"retry payload"
        assert other_archive.read_bytes() == other_content
        assert not (retry.parent / f"{retry.name}{extension}").exists()
    assert other.parent == current.parent == staging_root


def test_allocation_failure_preserves_prepared_update(
    manager: UpdateManager, staging_root: Path
) -> None:
    manager._update_content = b"prepared installer"
    prepared = manager._extract_update(is_msi=True)
    manager._update_content = b"retry installer"

    with (
        patch.object(
            update_utils.os,
            "mkdir",
            side_effect=OSError(errno.ENOSPC, "No staging space"),
        ),
        patch.object(
            update_utils.datetime,
            "now",
            return_value=datetime(2026, 11, 15, 12, 0, 1, tzinfo=UTC),
        ),
        pytest.raises(UpdateExtractionError, match="No staging space"),
    ):
        manager._extract_update(is_msi=True)

    assert manager._extracted_path == prepared
    assert prepared.read_bytes() == b"prepared installer"
    assert prepared.parent.parent == staging_root

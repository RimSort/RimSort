import time
import zipfile
from pathlib import Path
from unittest.mock import MagicMock

from app.utils.files import (
    cleanup_old_backups,
    create_saves_backup,
    subfolder_contains_candidate_path,
)


class TestSubfolderContainsCandidatePath:
    def test_matching_file_in_subfolder(self, tmp_path: Path) -> None:
        candidate = tmp_path / "Assemblies"
        candidate.mkdir()
        (candidate / "MyMod.dll").write_text("dll content")
        assert (
            subfolder_contains_candidate_path(tmp_path, "Assemblies", "*.dll") is True
        )

    def test_no_matching_file(self, tmp_path: Path) -> None:
        candidate = tmp_path / "Assemblies"
        candidate.mkdir()
        (candidate / "readme.txt").write_text("text")
        assert (
            subfolder_contains_candidate_path(tmp_path, "Assemblies", "*.dll") is False
        )

    def test_candidate_not_exist(self, tmp_path: Path) -> None:
        assert subfolder_contains_candidate_path(tmp_path, "Missing", "*.dll") is False

    def test_none_subfolder_returns_false(self) -> None:
        assert subfolder_contains_candidate_path(None, "test", "*.dll") is False

    def test_none_candidate_uses_root(self, tmp_path: Path) -> None:
        (tmp_path / "file.dll").write_text("data")
        assert subfolder_contains_candidate_path(tmp_path, None, "*.dll") is True

    def test_checks_immediate_subdirs(self, tmp_path: Path) -> None:
        sub = tmp_path / "versioned"
        sub.mkdir()
        candidate = sub / "Assemblies"
        candidate.mkdir()
        (candidate / "mod.dll").write_text("dll")
        assert (
            subfolder_contains_candidate_path(tmp_path, "Assemblies", "*.dll") is True
        )

    def test_finds_dll_nested_inside_assemblies(self, tmp_path: Path) -> None:
        candidate = tmp_path / "Assemblies" / "net472"
        candidate.mkdir(parents=True)
        (candidate / "mod.dll").write_text("dll")
        assert (
            subfolder_contains_candidate_path(tmp_path, "Assemblies", "*.dll") is True
        )

    def test_empty_root_assemblies_finds_dll_in_subfolder(self, tmp_path: Path) -> None:
        (tmp_path / "Assemblies").mkdir()
        sub = tmp_path / "1.5" / "Assemblies"
        sub.mkdir(parents=True)
        (sub / "mod.dll").write_text("dll")
        assert (
            subfolder_contains_candidate_path(tmp_path, "Assemblies", "*.dll") is True
        )


class TestCleanupOldBackups:
    def _create_backups(self, backup_dir: Path, count: int) -> list[Path]:
        backups = []
        for i in range(count):
            f = backup_dir / f"Saves_{i:04d}.zip"
            f.write_text(f"backup {i}")
            time.sleep(0.01)
            backups.append(f)
        return backups

    def test_keeps_specified_number(self, tmp_path: Path) -> None:
        self._create_backups(tmp_path, 5)
        cleanup_old_backups(tmp_path, keep=2)
        remaining = list(tmp_path.glob("Saves_*.zip"))
        assert len(remaining) == 2

    def test_keep_negative_one_keeps_all(self, tmp_path: Path) -> None:
        self._create_backups(tmp_path, 5)
        cleanup_old_backups(tmp_path, keep=-1)
        remaining = list(tmp_path.glob("Saves_*.zip"))
        assert len(remaining) == 5

    def test_keep_zero_deletes_all(self, tmp_path: Path) -> None:
        self._create_backups(tmp_path, 3)
        cleanup_old_backups(tmp_path, keep=0)
        remaining = list(tmp_path.glob("Saves_*.zip"))
        assert len(remaining) == 0

    def test_fewer_than_keep_does_nothing(self, tmp_path: Path) -> None:
        self._create_backups(tmp_path, 2)
        cleanup_old_backups(tmp_path, keep=5)
        remaining = list(tmp_path.glob("Saves_*.zip"))
        assert len(remaining) == 2


class TestCreateSavesBackup:
    def test_creates_backup_zip(self, tmp_path: Path) -> None:
        saves = tmp_path / "Saves"
        saves.mkdir()
        (saves / "save1.rws").write_text("save data 1")
        (saves / "save2.rws").write_text("save data 2")
        backup_dir = tmp_path / "backups"

        settings = MagicMock()
        settings.auto_backup_compression_count = -1
        settings.auto_backup_retention_count = 5

        result = create_saves_backup(saves, backup_dir, settings)
        assert result is not None
        assert Path(result).exists()
        with zipfile.ZipFile(result) as zf:
            names = zf.namelist()
            assert "save1.rws" in names
            assert "save2.rws" in names

    def test_nonexistent_saves_dir_returns_none(self, tmp_path: Path) -> None:
        settings = MagicMock()
        result = create_saves_backup(tmp_path / "nope", tmp_path / "backups", settings)
        assert result is None

    def test_compression_count_zero_returns_none(self, tmp_path: Path) -> None:
        saves = tmp_path / "Saves"
        saves.mkdir()
        (saves / "save.rws").write_text("data")
        settings = MagicMock()
        settings.auto_backup_compression_count = 0
        result = create_saves_backup(saves, tmp_path / "backups", settings)
        assert result is None

    def test_compression_count_limits_files(self, tmp_path: Path) -> None:
        saves = tmp_path / "Saves"
        saves.mkdir()
        for i in range(5):
            (saves / f"save{i}.rws").write_text(f"data {i}")
            time.sleep(0.01)

        settings = MagicMock()
        settings.auto_backup_compression_count = 2
        settings.auto_backup_retention_count = 5

        result = create_saves_backup(saves, tmp_path / "backups", settings)
        assert result is not None
        with zipfile.ZipFile(result) as zf:
            assert len(zf.namelist()) == 2

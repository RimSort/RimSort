"""Tests for GitHub mod installer: zip extraction, unwrap heuristic, backup/restore."""

from pathlib import Path
from zipfile import ZipFile

import pytest

from app.utils.github.installer import (
    GitHubInstaller,
    UnwrapResult,
    unwrap_extracted_mod,
)


@pytest.fixture
def tmp_mods_dir(tmp_path: Path) -> Path:
    mods = tmp_path / "Mods"
    mods.mkdir()
    return mods


class TestUnwrapExtractedMod:
    def test_single_dir_with_about_xml(self, tmp_path: Path) -> None:
        wrapper = tmp_path / "ModName"
        wrapper.mkdir()
        about_dir = wrapper / "About"
        about_dir.mkdir()
        (about_dir / "About.xml").write_text("<xml/>")

        result = unwrap_extracted_mod(tmp_path)
        assert result == UnwrapResult.UNWRAPPED
        assert (tmp_path / "About" / "About.xml").exists()
        assert not wrapper.exists()

    def test_root_has_about_xml(self, tmp_path: Path) -> None:
        about_dir = tmp_path / "About"
        about_dir.mkdir()
        (about_dir / "About.xml").write_text("<xml/>")

        result = unwrap_extracted_mod(tmp_path)
        assert result == UnwrapResult.ALREADY_CORRECT
        assert (tmp_path / "About" / "About.xml").exists()

    def test_no_about_xml(self, tmp_path: Path) -> None:
        wrapper = tmp_path / "SomeDir"
        wrapper.mkdir()
        (wrapper / "readme.txt").write_text("hello")

        result = unwrap_extracted_mod(tmp_path)
        assert result == UnwrapResult.NO_ABOUT_XML

    def test_multiple_top_level_dirs(self, tmp_path: Path) -> None:
        (tmp_path / "DirA").mkdir()
        (tmp_path / "DirB").mkdir()

        result = unwrap_extracted_mod(tmp_path)
        assert result == UnwrapResult.NO_ABOUT_XML

    def test_case_insensitive_about_dir(self, tmp_path: Path) -> None:
        """About directory matching should be case-insensitive."""
        wrapper = tmp_path / "ModName"
        wrapper.mkdir()
        about_dir = wrapper / "about"
        about_dir.mkdir()
        (about_dir / "about.xml").write_text("<xml/>")

        result = unwrap_extracted_mod(tmp_path)
        assert result == UnwrapResult.UNWRAPPED

    def test_preserves_extra_content_on_unwrap(self, tmp_path: Path) -> None:
        """Unwrapping should move all contents, not just About/."""
        wrapper = tmp_path / "ModName"
        wrapper.mkdir()
        about_dir = wrapper / "About"
        about_dir.mkdir()
        (about_dir / "About.xml").write_text("<xml/>")
        defs_dir = wrapper / "Defs"
        defs_dir.mkdir()
        (defs_dir / "ThingDef.xml").write_text("<thing/>")

        result = unwrap_extracted_mod(tmp_path)
        assert result == UnwrapResult.UNWRAPPED
        assert (tmp_path / "Defs" / "ThingDef.xml").exists()


class TestGitHubInstallerExtract:
    def test_extract_zip_to_target(self, tmp_mods_dir: Path, tmp_path: Path) -> None:
        zip_path = tmp_path / "mod.zip"
        with ZipFile(zip_path, "w") as zf:
            zf.writestr("ModName/About/About.xml", "<xml/>")
            zf.writestr("ModName/Defs/ThingDef.xml", "<thing/>")

        target = tmp_mods_dir / "ModName"
        GitHubInstaller.extract_release_zip(str(zip_path), str(target))

        assert (target / "About" / "About.xml").exists()
        assert (target / "Defs" / "ThingDef.xml").exists()

    def test_extract_zip_already_correct_structure(
        self, tmp_mods_dir: Path, tmp_path: Path
    ) -> None:
        """ZIP where About/ is at root level (no wrapper dir)."""
        zip_path = tmp_path / "mod.zip"
        with ZipFile(zip_path, "w") as zf:
            zf.writestr("About/About.xml", "<xml/>")
            zf.writestr("Defs/ThingDef.xml", "<thing/>")

        target = tmp_mods_dir / "ModName"
        result = GitHubInstaller.extract_release_zip(str(zip_path), str(target))

        assert result == UnwrapResult.ALREADY_CORRECT
        assert (target / "About" / "About.xml").exists()

    def test_extract_zip_slip_protection(
        self, tmp_mods_dir: Path, tmp_path: Path
    ) -> None:
        """ZIP entries with path traversal should be skipped."""
        zip_path = tmp_path / "evil.zip"
        with ZipFile(zip_path, "w") as zf:
            zf.writestr("About/About.xml", "<xml/>")
            zf.writestr("../../../etc/passwd", "evil")

        target = tmp_mods_dir / "SafeMod"
        GitHubInstaller.extract_release_zip(str(zip_path), str(target))

        assert (target / "About" / "About.xml").exists()
        # The traversal entry should NOT have been extracted outside target
        assert not (tmp_mods_dir / ".." / ".." / "etc" / "passwd").exists()


class TestBackupRestore:
    def test_backup_creates_backup_dir(self, tmp_mods_dir: Path) -> None:
        mod_dir = tmp_mods_dir / "TestMod"
        mod_dir.mkdir()
        (mod_dir / "About").mkdir()
        (mod_dir / "About" / "About.xml").write_text("<xml/>")

        backup = GitHubInstaller.backup_mod(mod_dir)

        assert backup.exists()
        assert backup.name == "TestMod.rimsort_backup"
        assert not mod_dir.exists()
        assert (backup / "About" / "About.xml").exists()

    def test_restore_backup(self, tmp_mods_dir: Path) -> None:
        mod_dir = tmp_mods_dir / "TestMod"
        mod_dir.mkdir()
        (mod_dir / "data.txt").write_text("original")

        backup = GitHubInstaller.backup_mod(mod_dir)
        assert not mod_dir.exists()

        GitHubInstaller.restore_backup(backup, mod_dir)
        assert mod_dir.exists()
        assert (mod_dir / "data.txt").read_text() == "original"
        assert not backup.exists()

    def test_delete_backup(self, tmp_mods_dir: Path) -> None:
        backup = tmp_mods_dir / "TestMod.rimsort_backup"
        backup.mkdir()
        (backup / "file.txt").write_text("backup data")

        GitHubInstaller.delete_backup(backup)
        assert not backup.exists()

    def test_check_stale_backup_found(self, tmp_mods_dir: Path) -> None:
        mod_dir = tmp_mods_dir / "TestMod"
        mod_dir.mkdir()
        backup = tmp_mods_dir / "TestMod.rimsort_backup"
        backup.mkdir()

        result = GitHubInstaller.check_stale_backup(mod_dir)
        assert result == backup

    def test_check_stale_backup_not_found(self, tmp_mods_dir: Path) -> None:
        mod_dir = tmp_mods_dir / "TestMod"
        mod_dir.mkdir()

        result = GitHubInstaller.check_stale_backup(mod_dir)
        assert result is None

    def test_backup_removes_existing_backup(self, tmp_mods_dir: Path) -> None:
        mod_dir = tmp_mods_dir / "TestMod"
        mod_dir.mkdir()
        (mod_dir / "new.txt").write_text("new")

        old_backup = tmp_mods_dir / "TestMod.rimsort_backup"
        old_backup.mkdir()
        (old_backup / "old.txt").write_text("old")

        backup = GitHubInstaller.backup_mod(mod_dir)
        assert (backup / "new.txt").exists()
        assert not (backup / "old.txt").exists()

    def test_restore_overwrites_existing_mod_dir(self, tmp_mods_dir: Path) -> None:
        """If mod_dir already exists when restoring, it should be replaced."""
        mod_dir = tmp_mods_dir / "TestMod"
        mod_dir.mkdir()
        (mod_dir / "original.txt").write_text("original")

        backup = GitHubInstaller.backup_mod(mod_dir)

        # Create a new mod_dir with different content (simulating a failed install)
        mod_dir.mkdir()
        (mod_dir / "broken.txt").write_text("broken")

        GitHubInstaller.restore_backup(backup, mod_dir)
        assert (mod_dir / "original.txt").exists()
        assert not (mod_dir / "broken.txt").exists()

    def test_delete_backup_noop_if_missing(self, tmp_mods_dir: Path) -> None:
        """delete_backup should not raise if the backup doesn't exist."""
        nonexistent = tmp_mods_dir / "Ghost.rimsort_backup"
        GitHubInstaller.delete_backup(nonexistent)  # Should not raise

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from app.utils.acf_utils import cleanup_orphaned_workshop_items
from app.utils.steam.steamfiles.wrapper import dict_to_acf


def _create_acf_file(
    path: Path,
    installed_pfids: list[str],
    details_pfids: list[str],
) -> None:
    """Write a valid ACF file with the given PFIDs in both sections."""
    acf_data: dict[str, Any] = {
        "AppWorkshop": {
            "appid": "294100",
            "SizeOnDisk": "0",
            "NeedsUpdate": "0",
            "NeedsDownload": "0",
            "TimeLastUpdated": "0",
            "TimeLastAppRan": "0",
            "LastBuildID": "0",
            "WorkshopItemsInstalled": {
                pfid: {"size": "100", "timeupdated": "1700000000", "manifest": "123"}
                for pfid in installed_pfids
            },
            "WorkshopItemDetails": {
                pfid: {
                    "manifest": "123",
                    "timeupdated": "1700000000",
                    "timetouched": "1700000000",
                }
                for pfid in details_pfids
            },
        }
    }
    dict_to_acf(data=acf_data, path=str(path))


@pytest.fixture
def acf_workshop_setup(tmp_path: Path) -> tuple[Path, Path, list[str], list[str]]:
    """Create a workshop directory structure with some installed mods and an ACF file with orphans."""
    workshop_dir = tmp_path / "workshop" / "content" / "294100"
    workshop_dir.mkdir(parents=True)

    existing_pfids = ["111111111", "222222222", "333333333"]
    for pfid in existing_pfids:
        (workshop_dir / pfid).mkdir()

    all_pfids = existing_pfids + ["444444444", "555555555"]
    orphaned_pfids = ["444444444", "555555555"]

    acf_path = tmp_path / "workshop" / "appworkshop_294100.acf"
    _create_acf_file(acf_path, all_pfids, all_pfids)

    return acf_path, workshop_dir, existing_pfids, orphaned_pfids


class TestCleanupOrphanedWorkshopItems:
    def test_removes_orphaned_entries(
        self, acf_workshop_setup: tuple[Path, Path, list[str], list[str]]
    ) -> None:
        """Orphaned PFIDs should be removed from both ACF sections."""
        acf_path, workshop_dir, existing_pfids, orphaned_pfids = acf_workshop_setup

        result = cleanup_orphaned_workshop_items(acf_path, workshop_dir)

        assert result == sorted(orphaned_pfids)

        from app.utils.acf_utils import load_acf_from_path

        updated = load_acf_from_path(acf_path)
        installed = updated["AppWorkshop"]["WorkshopItemsInstalled"]
        details = updated["AppWorkshop"]["WorkshopItemDetails"]

        for pfid in orphaned_pfids:
            assert pfid not in installed
            assert pfid not in details

        for pfid in existing_pfids:
            assert pfid in installed
            assert pfid in details

    def test_no_orphans_returns_empty(self, tmp_path: Path) -> None:
        """When all ACF entries have matching directories, return empty list and create no backup."""
        workshop_dir = tmp_path / "content"
        workshop_dir.mkdir()

        pfids = ["111", "222"]
        for pfid in pfids:
            (workshop_dir / pfid).mkdir()

        acf_path = tmp_path / "appworkshop_294100.acf"
        _create_acf_file(acf_path, pfids, pfids)

        result = cleanup_orphaned_workshop_items(acf_path, workshop_dir)

        assert result == []
        assert not Path(str(acf_path) + ".backup").exists()

    def test_creates_backup_file(self, tmp_path: Path) -> None:
        """A backup should be created before modifying the ACF file."""
        workshop_dir = tmp_path / "content"
        workshop_dir.mkdir()
        (workshop_dir / "111").mkdir()

        acf_path = tmp_path / "appworkshop_294100.acf"
        _create_acf_file(acf_path, ["111", "222"], ["111", "222"])

        original_content = acf_path.read_bytes()

        cleanup_orphaned_workshop_items(acf_path, workshop_dir)

        backup_path = Path(str(acf_path) + ".backup")
        assert backup_path.exists()
        assert backup_path.read_bytes() == original_content

    def test_write_failure_restores_backup(self, tmp_path: Path) -> None:
        """If dict_to_acf fails, the original ACF should be restored from backup."""
        workshop_dir = tmp_path / "content"
        workshop_dir.mkdir()
        (workshop_dir / "111").mkdir()

        acf_path = tmp_path / "appworkshop_294100.acf"
        _create_acf_file(acf_path, ["111", "222"], ["111", "222"])

        original_content = acf_path.read_bytes()

        with (
            patch("app.utils.acf_utils.dict_to_acf", side_effect=OSError("disk full")),
            pytest.raises(OSError, match="disk full"),
        ):
            cleanup_orphaned_workshop_items(acf_path, workshop_dir)

        assert acf_path.read_bytes() == original_content

    def test_missing_acf_file_returns_empty(self, tmp_path: Path) -> None:
        """A non-existent ACF path should return empty list without crashing."""
        workshop_dir = tmp_path / "content"
        workshop_dir.mkdir()

        result = cleanup_orphaned_workshop_items(
            tmp_path / "nonexistent.acf", workshop_dir
        )

        assert result == []

    def test_missing_workshop_directory_returns_empty(self, tmp_path: Path) -> None:
        """A non-existent workshop content path should return empty list."""
        acf_path = tmp_path / "appworkshop_294100.acf"
        _create_acf_file(acf_path, ["111"], ["111"])

        result = cleanup_orphaned_workshop_items(acf_path, tmp_path / "nonexistent")

        assert result == []

    def test_mixed_sections(self, tmp_path: Path) -> None:
        """Orphans should be removed from whichever section contains them."""
        workshop_dir = tmp_path / "content"
        workshop_dir.mkdir()
        (workshop_dir / "111").mkdir()

        acf_path = tmp_path / "appworkshop_294100.acf"
        # 222 only in WorkshopItemsInstalled, 333 only in WorkshopItemDetails
        _create_acf_file(acf_path, ["111", "222"], ["111", "333"])

        result = cleanup_orphaned_workshop_items(acf_path, workshop_dir)

        assert result == ["222", "333"]

        from app.utils.acf_utils import load_acf_from_path

        updated = load_acf_from_path(acf_path)
        installed = updated["AppWorkshop"]["WorkshopItemsInstalled"]
        details = updated["AppWorkshop"]["WorkshopItemDetails"]

        assert "222" not in installed
        assert "333" not in details
        assert "111" in installed
        assert "111" in details

    def test_all_entries_orphaned(self, tmp_path: Path) -> None:
        """When no directories exist, all entries should be removed."""
        workshop_dir = tmp_path / "content"
        workshop_dir.mkdir()

        acf_path = tmp_path / "appworkshop_294100.acf"
        _create_acf_file(acf_path, ["111", "222"], ["111", "222"])

        result = cleanup_orphaned_workshop_items(acf_path, workshop_dir)

        assert result == ["111", "222"]

        from app.utils.acf_utils import load_acf_from_path

        updated = load_acf_from_path(acf_path)
        installed = updated["AppWorkshop"]["WorkshopItemsInstalled"]
        details = updated["AppWorkshop"]["WorkshopItemDetails"]

        assert installed == {}
        assert details == {}

    def test_ignores_non_numeric_directories(self, tmp_path: Path) -> None:
        """Non-numeric directory names should not count as installed mods."""
        workshop_dir = tmp_path / "content"
        workshop_dir.mkdir()
        (workshop_dir / "111").mkdir()
        (workshop_dir / "not_a_mod").mkdir()
        (workshop_dir / ".tmp").mkdir()

        acf_path = tmp_path / "appworkshop_294100.acf"
        _create_acf_file(acf_path, ["111", "222"], ["111", "222"])

        result = cleanup_orphaned_workshop_items(acf_path, workshop_dir)

        assert result == ["222"]

"""Tests for ACF utilities, specifically cleanup_orphaned_workshop_items()."""

from pathlib import Path
from typing import Any

import pytest

from app.utils.acf_utils import cleanup_orphaned_workshop_items
from app.utils.steam.steamfiles.wrapper import acf_to_dict, dict_to_acf


@pytest.fixture
def sample_acf_data() -> dict[str, Any]:
    """
    Sample ACF data with both orphaned and non-orphaned workshop items.

    Returns ACF structure with:
    - 1111111111: Has corresponding folder (non-orphaned)
    - 2222222222: No folder (orphaned)
    - 3333333333: Has corresponding folder (non-orphaned)
    - 4444444444: No folder (orphaned)
    """
    return {
        "AppWorkshop": {
            "appid": "294100",
            "SizeOnDisk": "1234567890",
            "WorkshopItemsInstalled": {
                "1111111111": {
                    "size": "100000",
                    "timeupdated": "1700000000",
                    "manifest": "1234567890123456789",
                },
                "2222222222": {
                    "size": "200000",
                    "timeupdated": "1700000100",
                    "manifest": "9876543210987654321",
                },
                "3333333333": {
                    "size": "300000",
                    "timeupdated": "1700000200",
                    "manifest": "1111222233334444555",
                },
                "4444444444": {
                    "size": "400000",
                    "timeupdated": "1700000300",
                    "manifest": "5555444433332222111",
                },
            },
            "WorkshopItemDetails": {
                "1111111111": {
                    "manifest": "1234567890123456789",
                    "timeupdated": "1700000000",
                    "timetouched": "1700000000",
                    "subscribedby": "12345678",
                    "latest_timeupdated": "1700000000",
                    "latest_manifest": "1234567890123456789",
                },
                "2222222222": {
                    "manifest": "9876543210987654321",
                    "timeupdated": "1700000100",
                    "timetouched": "1700000100",
                    "subscribedby": "12345678",
                    "latest_timeupdated": "1700000100",
                    "latest_manifest": "9876543210987654321",
                },
                "3333333333": {
                    "manifest": "1111222233334444555",
                    "timeupdated": "1700000200",
                    "timetouched": "1700000200",
                    "subscribedby": "12345678",
                    "latest_timeupdated": "1700000200",
                    "latest_manifest": "1111222233334444555",
                },
                "4444444444": {
                    "manifest": "5555444433332222111",
                    "timeupdated": "1700000300",
                    "timetouched": "1700000300",
                    "subscribedby": "12345678",
                    "latest_timeupdated": "1700000300",
                    "latest_manifest": "5555444433332222111",
                },
            },
        }
    }


@pytest.fixture
def sample_acf_data_no_orphans() -> dict[str, Any]:
    """Sample ACF data where all items have corresponding folders."""
    return {
        "AppWorkshop": {
            "appid": "294100",
            "SizeOnDisk": "1234567890",
            "WorkshopItemsInstalled": {
                "1111111111": {
                    "size": "100000",
                    "timeupdated": "1700000000",
                    "manifest": "1234567890123456789",
                },
                "3333333333": {
                    "size": "300000",
                    "timeupdated": "1700000200",
                    "manifest": "1111222233334444555",
                },
            },
            "WorkshopItemDetails": {
                "1111111111": {
                    "manifest": "1234567890123456789",
                    "timeupdated": "1700000000",
                    "timetouched": "1700000000",
                    "subscribedby": "12345678",
                    "latest_timeupdated": "1700000000",
                    "latest_manifest": "1234567890123456789",
                },
                "3333333333": {
                    "manifest": "1111222233334444555",
                    "timeupdated": "1700000200",
                    "timetouched": "1700000200",
                    "subscribedby": "12345678",
                    "latest_timeupdated": "1700000200",
                    "latest_manifest": "1111222233334444555",
                },
            },
        }
    }


def test_cleanup_orphaned_workshop_items_success(
    tmp_path: Path, sample_acf_data: dict[str, Any]
) -> None:
    """Test successful cleanup of orphaned workshop items."""
    # Setup: Create ACF file and workshop directory
    acf_file = tmp_path / "appworkshop_294100.acf"
    workshop_dir = tmp_path / "content" / "294100"
    workshop_dir.mkdir(parents=True)

    # Create folders for non-orphaned items only
    (workshop_dir / "1111111111").mkdir()
    (workshop_dir / "3333333333").mkdir()
    # Note: 2222222222 and 4444444444 are orphaned (no folders)

    # Write ACF file
    dict_to_acf(sample_acf_data, str(acf_file))

    # Action: Clean up orphaned items
    removed = cleanup_orphaned_workshop_items(acf_file, workshop_dir)

    # Assert: Correct items were removed
    assert sorted(removed) == ["2222222222", "4444444444"]

    # Assert: Backup was created
    backup_file = acf_file.with_suffix(".acf.backup")
    assert backup_file.exists()

    # Assert: ACF file was modified correctly
    cleaned_data = acf_to_dict(str(acf_file))
    installed = cleaned_data["AppWorkshop"]["WorkshopItemsInstalled"]
    details = cleaned_data["AppWorkshop"]["WorkshopItemDetails"]

    # Non-orphaned items should remain
    assert "1111111111" in installed
    assert "3333333333" in installed
    assert "1111111111" in details
    assert "3333333333" in details

    # Orphaned items should be removed
    assert "2222222222" not in installed
    assert "4444444444" not in installed
    assert "2222222222" not in details
    assert "4444444444" not in details


def test_cleanup_orphaned_workshop_items_no_orphans(
    tmp_path: Path, sample_acf_data_no_orphans: dict[str, Any]
) -> None:
    """Test cleanup when there are no orphaned items."""
    # Setup: Create ACF file and workshop directory with all folders
    acf_file = tmp_path / "appworkshop_294100.acf"
    workshop_dir = tmp_path / "content" / "294100"
    workshop_dir.mkdir(parents=True)

    # Create folders for all items
    (workshop_dir / "1111111111").mkdir()
    (workshop_dir / "3333333333").mkdir()

    # Write ACF file
    dict_to_acf(sample_acf_data_no_orphans, str(acf_file))

    # Read original data for comparison
    original_data = acf_to_dict(str(acf_file))

    # Action: Clean up (should find no orphans)
    removed = cleanup_orphaned_workshop_items(acf_file, workshop_dir)

    # Assert: No items were removed
    assert removed == []

    # Assert: ACF file unchanged
    cleaned_data = acf_to_dict(str(acf_file))
    assert cleaned_data == original_data


def test_cleanup_orphaned_workshop_items_missing_acf(tmp_path: Path) -> None:
    """Test handling of missing ACF file."""
    # Setup: Point to non-existent file
    acf_file = tmp_path / "nonexistent.acf"
    workshop_dir = tmp_path / "content" / "294100"
    workshop_dir.mkdir(parents=True)

    # Action: Attempt cleanup
    removed = cleanup_orphaned_workshop_items(acf_file, workshop_dir)

    # Assert: Returns empty list (graceful failure)
    assert removed == []


def test_cleanup_orphaned_workshop_items_missing_workshop_dir(
    tmp_path: Path, sample_acf_data: dict[str, Any]
) -> None:
    """Test handling of missing workshop directory."""
    # Setup: Create ACF file but no workshop directory
    acf_file = tmp_path / "appworkshop_294100.acf"
    workshop_dir = tmp_path / "content" / "294100"  # Not created

    # Write ACF file
    dict_to_acf(sample_acf_data, str(acf_file))

    # Action: Attempt cleanup
    removed = cleanup_orphaned_workshop_items(acf_file, workshop_dir)

    # Assert: Returns empty list (graceful failure)
    assert removed == []


def test_cleanup_orphaned_workshop_items_backup_created(
    tmp_path: Path, sample_acf_data: dict[str, Any]
) -> None:
    """Test that backup file is created before cleanup."""
    # Setup: Create ACF file and workshop directory
    acf_file = tmp_path / "appworkshop_294100.acf"
    workshop_dir = tmp_path / "content" / "294100"
    workshop_dir.mkdir(parents=True)

    # Create folder for one item (others are orphaned)
    (workshop_dir / "1111111111").mkdir()

    # Write ACF file
    dict_to_acf(sample_acf_data, str(acf_file))

    # Read original content
    original_data = acf_to_dict(str(acf_file))

    # Action: Clean up orphaned items
    removed = cleanup_orphaned_workshop_items(acf_file, workshop_dir)

    # Assert: Items were removed
    assert len(removed) > 0

    # Assert: Backup file exists
    backup_file = acf_file.with_suffix(".acf.backup")
    assert backup_file.exists()

    # Assert: Backup contains original data
    backup_data = acf_to_dict(str(backup_file))
    assert backup_data == original_data


def test_cleanup_orphaned_workshop_items_both_sections(
    tmp_path: Path, sample_acf_data: dict[str, Any]
) -> None:
    """Test that orphaned items are removed from both ACF sections."""
    # Setup: Create ACF file and workshop directory
    acf_file = tmp_path / "appworkshop_294100.acf"
    workshop_dir = tmp_path / "content" / "294100"
    workshop_dir.mkdir(parents=True)

    # Create folder for only one item
    (workshop_dir / "1111111111").mkdir()
    # 2222222222, 3333333333, 4444444444 are orphaned

    # Write ACF file
    dict_to_acf(sample_acf_data, str(acf_file))

    # Action: Clean up orphaned items
    removed = cleanup_orphaned_workshop_items(acf_file, workshop_dir)

    # Assert: All orphaned items were removed
    assert sorted(removed) == ["2222222222", "3333333333", "4444444444"]

    # Assert: Orphaned items removed from both sections
    cleaned_data = acf_to_dict(str(acf_file))
    installed = cleaned_data["AppWorkshop"]["WorkshopItemsInstalled"]
    details = cleaned_data["AppWorkshop"]["WorkshopItemDetails"]

    # Check WorkshopItemsInstalled
    assert "1111111111" in installed  # Not orphaned
    assert "2222222222" not in installed  # Orphaned
    assert "3333333333" not in installed  # Orphaned
    assert "4444444444" not in installed  # Orphaned

    # Check WorkshopItemDetails
    assert "1111111111" in details  # Not orphaned
    assert "2222222222" not in details  # Orphaned
    assert "3333333333" not in details  # Orphaned
    assert "4444444444" not in details  # Orphaned

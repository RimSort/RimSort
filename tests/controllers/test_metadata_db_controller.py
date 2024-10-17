from pathlib import Path
from typing import Generator
from unittest.mock import patch

import pytest

from app.controllers.metadata_db_controller import AuxMetadataController
from app.models.metadata.metadata_db import AuxMetadataEntry
from app.utils.app_info import AppInfo


@pytest.fixture()
def temp_db(tmp_path: Path) -> Generator[AuxMetadataController, None, None]:
    db_path = tmp_path / "test_metadata.db"
    with patch.object(AppInfo, "aux_metadata_db", db_path):
        controller = AuxMetadataController()
        yield controller


def test_get_or_create(temp_db: AuxMetadataController) -> None:
    item_path = Path("/test/path")
    with temp_db.Session() as session:
        entry = temp_db.get_or_create(session, item_path)
        assert entry is not None
        assert entry.path == str(item_path)
        assert entry.notes == ""  # Default value
        entry.notes = "test_notes"
        session.commit()

    # Fetch the same entry again and ensure it's the same
    with temp_db.Session() as session:
        same_entry = temp_db.get_or_create(session, item_path)
        assert same_entry is not None
        assert same_entry.path == str(item_path)
        assert same_entry.notes == "test_notes"

    # Ensure only one entry exists
    with temp_db.Session() as session:
        entries = session.query(AuxMetadataEntry).all()
        assert len(entries) == 1
        assert entries[0].path == str(item_path)


def test_get(temp_db: AuxMetadataController) -> None:
    item_path = Path("/test/path")
    with temp_db.Session() as session:
        temp_db.get_or_create(session, item_path)  # Ensure the entry exists

    with temp_db.Session() as session:
        entry = temp_db.get(session, item_path)
        assert entry is not None
        assert entry.path == str(item_path)


def test_get_value_equals(temp_db: AuxMetadataController) -> None:
    item_path1 = Path("/test/path1")
    item_path2 = Path("/test/path2")
    item_path3 = Path("/test/path3")
    with temp_db.Session() as session:
        entry1 = temp_db.get_or_create(session, item_path1)
        entry2 = temp_db.get_or_create(session, item_path2)
        _ = temp_db.get_or_create(session, item_path3)

        assert entry1 is not None
        assert entry2 is not None
        entry1.notes = "test_key"
        entry1.color_hex = "test_value"
        entry2.notes = "test_key"
        entry2.color_hex = "test_value"

        session.commit()

    with temp_db.Session() as session:
        entries = temp_db.get_value_equals(session, "color_hex", "test_value")
        assert len(entries) == 2
        assert Path(entries[0].path) in [item_path1, item_path2]
        assert Path(entries[1].path) in [item_path1, item_path2]

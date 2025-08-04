from pathlib import Path
from typing import Generator

import pytest

from app.controllers.metadata_db_controller import AuxMetadataController
from app.models.metadata.metadata_db import AuxMetadataEntry, TagsEntry


@pytest.fixture()
def temp_db(tmp_path: Path) -> Generator[AuxMetadataController, None, None]:
    db_path = tmp_path / "test_metadata.db"
    controller = AuxMetadataController(db_path)
    yield controller


def test_get_or_create(temp_db: AuxMetadataController) -> None:
    item_path = Path("/test/path")
    with temp_db.Session() as session:
        entry = temp_db.get_or_create(session, item_path)
        assert entry is not None
        assert entry.path == str(item_path)
        assert entry.user_notes == ""  # Default value
        entry.user_notes = "test_notes"
        session.commit()

    # Fetch the same entry again and ensure it's the same
    with temp_db.Session() as session:
        same_entry = temp_db.get_or_create(session, item_path)
        assert same_entry is not None
        assert same_entry.path == str(item_path)
        assert same_entry.user_notes == "test_notes"

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
        entry1.user_notes = "test_key"
        entry1.color_hex = "test_value"
        entry2.user_notes = "test_key"
        entry2.color_hex = "test_value"

        session.commit()

    with temp_db.Session() as session:
        entries = temp_db.get_value_equals(session, "color_hex", "test_value")
        assert len(entries) == 2
        assert Path(entries[0].path) in [item_path1, item_path2]
        assert Path(entries[1].path) in [item_path1, item_path2]


def test_tags(temp_db: AuxMetadataController) -> None:
    item_path = Path("/test/path")
    with temp_db.Session() as session:
        entry: AuxMetadataEntry | None = temp_db.get_or_create(session, item_path)
        assert entry is not None
        assert len(entry.tags) == 0

        entry.tags = [TagsEntry(tag="tag1"), TagsEntry(tag="tag2")]
        session.commit()

    with temp_db.Session() as session:
        entry = temp_db.get(session, item_path)
        assert entry is not None
        assert len(entry.tags) == 2
        assert entry.tags[0] == "tag1"
        assert entry.tags[1] == TagsEntry(tag="tag2")

        entry.tags.append(TagsEntry(tag="tag2"))
        entry.tags.append(TagsEntry(tag="tag3"))
        # Ensure unique constraint is enforced
        try:
            session.commit()
        except Exception:
            session.rollback()
        else:
            assert False

        entry.tags.append(TagsEntry(tag="tag3"))
        session.commit()

    with temp_db.Session() as session:
        entry = temp_db.get(session, item_path)
        assert entry is not None
        assert len(entry.tags) == 3
        assert entry.tags[2] == "tag3"

        # Remove a tag
        entry.tags.remove(TagsEntry(tag="tag2"))
        session.commit()

    with temp_db.Session() as session:
        entry = temp_db.get(session, item_path)
        assert entry is not None
        assert entry.tags == ["tag1", "tag3"]

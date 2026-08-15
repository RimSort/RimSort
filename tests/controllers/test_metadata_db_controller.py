from collections.abc import Generator
from pathlib import Path

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


def test_aux_metadata_webapi_timestamp_fields(tmp_path: Path) -> None:
    """WebAPI timestamp columns exist and default to -1."""
    from app.controllers.metadata_db_controller import AuxMetadataController

    controller = AuxMetadataController(tmp_path / "test.db")
    with controller.Session() as session:
        entry = controller.get_or_create(session, "/test/mod/path")
        assert entry.external_time_created == -1
        assert entry.external_time_updated == -1
        entry.external_time_created = 1234567890
        entry.external_time_updated = 1234567891
        session.commit()

    with controller.Session() as session:
        fetched = controller.get(session, "/test/mod/path")
        assert fetched is not None
        assert fetched.external_time_created == 1234567890
        assert fetched.external_time_updated == 1234567891


def test_schema_migration_from_legacy_published_file_id(tmp_path: Path) -> None:
    """Test migration of auxiliary_metadata from legacy schema (published_file_id is non-nullable INTEGER)."""
    import sqlite3
    db_path = tmp_path / "legacy.db"
    
    # 1. Create a legacy SQLite table manually
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "CREATE TABLE auxiliary_metadata ("
        "  path TEXT PRIMARY KEY, "
        "  published_file_id INTEGER NOT NULL"
        ")"
    )
    # Insert legacy rows: one valid integer ID, one placeholder -1
    cursor.execute(
        "INSERT INTO auxiliary_metadata (path, published_file_id) VALUES (?, ?)",
        (str(Path("/mods/mod_a")), 123456)
    )
    cursor.execute(
        "INSERT INTO auxiliary_metadata (path, published_file_id) VALUES (?, ?)",
        (str(Path("/mods/mod_b")), -1)
    )
    conn.commit()
    conn.close()

    # 2. Instantiate the controller. This triggers the schema migration.
    controller = AuxMetadataController(db_path)

    # 3. Verify the data migration and schema changes
    with controller.Session() as session:
        # Check mod_a: 123456 -> "123456"
        entry_a = controller.get(session, Path("/mods/mod_a"))
        assert entry_a is not None
        assert entry_a.published_file_id == "123456"

        # Check mod_b: -1 -> None
        entry_b = controller.get(session, Path("/mods/mod_b"))
        assert entry_b is not None
        assert entry_b.published_file_id is None

        # Verify added fields default correctly
        assert entry_a.external_time_created == -1


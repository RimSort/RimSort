from pathlib import Path
from typing import Any, Iterable

from loguru import logger
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.models.metadata.metadata_db import AuxMetadataEntry, Base
from app.models.metadata.metadata_structure import ModType
from app.utils.steam.steamfiles.wrapper import acf_to_dict


class MetadataDbController:
    def __init__(self, db: Path | str) -> None:
        # Ensure parent directory exists before opening SQLite file
        db_path = Path(db) if not isinstance(db, Path) else db
        try:
            if db_path.parent:
                db_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.exception(
                f"Failed to ensure database directory exists for {db_path}: {e}"
            )

        self.engine = create_engine(f"sqlite+pysqlite:///{db_path}")
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)


class AuxMetadataController(MetadataDbController):
    _instances: dict[
        Path, "AuxMetadataController"
    ] = {}  # db_path : AuxMetadataController

    def __init__(self, db_path: Path) -> None:
        super().__init__(db_path)
        Base.metadata.create_all(self.engine)

        # Add missing columns to existing databases
        with self.engine.connect() as conn:
            result = conn.execute(text("PRAGMA table_info(auxiliary_metadata)"))
            columns = [row[1] for row in result.fetchall()]

            if "mod_name" not in columns:
                conn.execute(
                    text(
                        "ALTER TABLE auxiliary_metadata ADD COLUMN mod_name TEXT DEFAULT ''"
                    )
                )
            if "author" not in columns:
                conn.execute(
                    text(
                        "ALTER TABLE auxiliary_metadata ADD COLUMN author TEXT DEFAULT ''"
                    )
                )
            if "packageid" not in columns:
                conn.execute(
                    text(
                        "ALTER TABLE auxiliary_metadata ADD COLUMN packageid TEXT DEFAULT ''"
                    )
                )
            if "supported_version" not in columns:
                conn.execute(
                    text(
                        "ALTER TABLE auxiliary_metadata ADD COLUMN supported_version TEXT DEFAULT ''"
                    )
                )
            if "filesystem_mtime" not in columns:
                conn.execute(
                    text(
                        "ALTER TABLE auxiliary_metadata ADD COLUMN filesystem_mtime INTEGER DEFAULT 0"
                    )
                )
            if "folder_size" not in columns:
                conn.execute(
                    text(
                        "ALTER TABLE auxiliary_metadata ADD COLUMN folder_size INTEGER DEFAULT 0"
                    )
                )

            conn.commit()

    @classmethod
    def get_or_create_cached_instance(cls, db_path: Path) -> "AuxMetadataController":
        """
        Get or create a cached instance of the controller.
        This cached controller is only for the specified db_path.
        """
        if db_path not in cls._instances:
            cls._instances[db_path] = cls(db_path)
        return cls._instances[db_path]

    @staticmethod
    def update(
        session: Session, item_path: Path | str, **kwargs: Any
    ) -> AuxMetadataEntry | None:
        """
        Update an aux metadata entry by the mod path.

        :param session: The database session.
        :type session: Session
        :param item_path: The key path.
        :type item_path: Path | str
        :param kwargs: The fields to update.
        :return: The updated aux metadata entry if found, otherwise None.
        :rtype: AuxMetadataEntry | None
        """
        if isinstance(item_path, Path):
            item_path = str(item_path)

        entry = AuxMetadataController.get(session, item_path)
        if entry is None:
            return None

        for key, value in kwargs.items():
            setattr(entry, key, value)

        try:
            session.commit()
        except Exception as e:
            session.rollback()
            logger.exception(f"Failed to update aux metadata entry: {e}")
            raise e

        return entry

    @staticmethod
    def get(session: Session, item_path: Path | str) -> AuxMetadataEntry | None:
        """Get an aux metadata entry by the key path.

        :param session: The database session.
        :type session: Session
        :param item_path: The key path.
        :type item_path: Path | str
        :return: The aux metadata entry if found, otherwise None.
        :rtype: AuxMetadataEntry | None
        """
        if isinstance(item_path, Path):
            item_path = str(item_path)

        return (
            session.query(AuxMetadataEntry)
            .filter(AuxMetadataEntry.path == item_path)
            .first()
        )

    @staticmethod
    def get_or_create(session: Session, item_path: Path | str) -> AuxMetadataEntry:
        """Get or create an aux metadata entry by the key path.

        :param session: The database session.
        :type session: Session
        :param item_path: The key path.
        :type item_path: Path | str
        :return: The aux metadata entry.
        :rtype: AuxMetadataEntry
        """

        if isinstance(item_path, Path):
            item_path = str(item_path)

        entry = AuxMetadataController.get(session, item_path)

        if entry is None:
            entry = AuxMetadataEntry(path=item_path)
            try:
                with session.begin_nested():
                    session.add(entry)
                    session.flush()
            except IntegrityError:
                session.rollback()
                # Query again to get the existing entry
                entry = AuxMetadataController.get(session, item_path)
                if entry is None:
                    logger.error(
                        f"Failed to create or retrieve aux metadata entry for path: {item_path}"
                    )
                    raise RuntimeError(
                        f"Failed to create or retrieve aux metadata entry for path: {item_path}"
                    )
            except Exception as e:
                session.rollback()
                logger.exception(f"Failed to create new aux metadata entry: {e}")
                raise e

        return entry

    @staticmethod
    def get_value_equals(
        session: Session, key: str, value: str
    ) -> list[AuxMetadataEntry]:
        """Get aux metadata entries where the key equals the value.

        :param session: The database session.
        :type session: Session
        :param key: The key to search for.
        :type key: str
        :param value: The value to search for.
        :type value: str
        :return: A list of aux metadata entries.
        :rtype: list[AuxMetadataEntry
        """
        return (
            session.query(AuxMetadataEntry)
            .filter(getattr(AuxMetadataEntry, key) == value)
            .all()
        )

    @staticmethod
    def query(session: Session, query: str) -> list[AuxMetadataEntry]:
        """Query the aux metadata entries.

        :param session: The database session.
        :type session: Session
        :param query: The query string.
        :type query: str
        :return: A list of aux metadata entries.
        :rtype: list[AuxMetadataEntry]
        """
        result = session.execute(text(query)).all()
        return [AuxMetadataEntry(**row._mapping) for row in result]

    @staticmethod
    def add(
        session: Session, item: AuxMetadataEntry | Iterable[AuxMetadataEntry]
    ) -> None:
        """Add an aux metadata entry or entries to the database.

        :param session: The database session.
        :type session: Session
        :param item: The aux metadata entry or entries to add.
        :type item: AuxMetadataEntry | Iterable[AuxMetadataEntry]
        """
        if isinstance(item, AuxMetadataEntry):
            session.add(item)
        else:
            session.add_all(item)
        session.commit()

    @staticmethod
    def delete(session: Session, *paths: Path) -> None:
        """Delete mod(s) from database."""

        for path in paths:
            session.query(AuxMetadataEntry).filter(
                AuxMetadataEntry.path == str(path)
            ).delete()

        session.commit()

    def reset(self) -> None:
        """Reset the database by dropping all tables and recreating them."""
        Base.metadata.drop_all(self.engine)
        Base.metadata.create_all(self.engine)

    @staticmethod
    def update_from_acf(session: Session, acf_path: Path, mod_type: ModType) -> None:
        """Update the aux metadata from an ACF file.

        :param session: The database session.
        :type session: Session
        :param acf_path: The path to the ACF file.
        :type acf_path: Path
        :param mod_type: The mod type.
        :type mod_type: ModType
        """
        if not acf_path.exists():
            logger.warning(f".acf file not found at {acf_path}.")
            return

        try:
            acf_data = acf_to_dict(str(acf_path))
        except Exception as e:
            logger.error(f"Error reading .acf file at {acf_path}: {e}")
            return

        workshop_items = {
            published_file_id: data
            for published_file_id, data in acf_data.get("AppWorkshop", {})
            .get("WorkshopItemDetails", {})
            .items()
        }

        entries = (
            session.query(AuxMetadataEntry)
            .filter(
                AuxMetadataEntry.published_file_id.in_(workshop_items.keys()),
                AuxMetadataEntry.type == str(mod_type),
            )
            .all()
        )

        for entry in entries:
            data = workshop_items.get(str(entry.published_file_id), None)
            if data is None:
                continue

            entry.acf_time_updated = data.get("timeupdated", -1)
            entry.acf_time_touched = data.get("timetouched", -1)

        session.commit()

    @staticmethod
    def update_sorting_data(
        session: Session, mod_path: Path | str, **sorting_data: str | int
    ) -> AuxMetadataEntry | None:
        """
        Update sorting data fields for a mod entry.

        :param session: The database session.
        :type session: Session
        :param mod_path: The mod path.
        :type mod_path: Path | str
        :param sorting_data: Keyword arguments for sorting data fields (mod_name, author, packageid, supported_version, filesystem_mtime).
        :return: The updated aux metadata entry if found, otherwise None.
        :rtype: AuxMetadataEntry | None
        """
        if isinstance(mod_path, Path):
            mod_path = str(mod_path)

        entry = AuxMetadataController.get_or_create(session, mod_path)
        if entry is None:
            return None

        valid_fields = {
            "mod_name",
            "author",
            "packageid",
            "supported_version",
            "filesystem_mtime",
            "folder_size",
        }
        for key, value in sorting_data.items():
            if key in valid_fields:
                setattr(entry, key, value)

        try:
            session.commit()
        except Exception as e:
            session.rollback()
            logger.exception(f"Failed to update sorting data for {mod_path}: {e}")
            raise e

        return entry

    @staticmethod
    def get_sorting_data(
        session: Session, mod_path: Path | str
    ) -> dict[str, str | int] | None:
        """
        Get sorting data for a mod entry.

        :param session: The database session.
        :type session: Session
        :param mod_path: The mod path.
        :type mod_path: Path | str
        :return: Dictionary with sorting data if found, otherwise None.
        :rtype: dict[str, str | int] | None
        """
        if isinstance(mod_path, Path):
            mod_path = str(mod_path)

        entry = AuxMetadataController.get(session, mod_path)
        if entry is None:
            return None

        return {
            "mod_name": entry.mod_name,
            "author": entry.author,
            "packageid": entry.packageid,
            "supported_version": entry.supported_version,
            "filesystem_mtime": entry.filesystem_mtime,
            "folder_size": entry.folder_size,
        }

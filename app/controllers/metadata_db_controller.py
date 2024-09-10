from pathlib import Path
from typing import Iterable

from loguru import logger
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.models.metadata.metadata_db import AuxMetadataEntry, Base
from app.utils.app_info import AppInfo


class MetadataDbController:
    def __init__(self, db: Path | str) -> None:
        self.engine = create_engine(f"sqlite+pysqlite:///{db}")
        self.Session = sessionmaker(bind=self.engine)


class AuxMetadataController(MetadataDbController):
    def __init__(self) -> None:
        super().__init__(AppInfo().aux_metadata_db)
        Base.metadata.create_all(self.engine)

    def get(self, item_path: Path) -> AuxMetadataEntry | None:
        with self.Session() as session:
            return (
                session.query(AuxMetadataEntry)
                .filter(AuxMetadataEntry.path == item_path)
                .first()
            )

    def get_or_create(self, item_path: Path) -> AuxMetadataEntry:
        with self.Session() as session:
            entry = (
                session.query(AuxMetadataEntry)
                .filter(AuxMetadataEntry.path == item_path)
                .first()
            )

            if entry is None:
                entry = AuxMetadataEntry(path=item_path)
                try:
                    session.add(entry)
                    session.commit()
                except Exception as e:
                    session.rollback()
                    session.close()
                    logger.exception(f"Failed to create new aux metadata entry: {e}")
                    raise e

            return entry

    def get_value_equals(self, key: str, value: str) -> list[AuxMetadataEntry]:
        with self.Session() as session:
            return (
                session.query(AuxMetadataEntry)
                .filter(getattr(AuxMetadataEntry, key) == value)
                .all()
            )

    def query(self, query: str) -> list[AuxMetadataEntry]:
        with self.Session() as session:
            result = session.execute(text(query)).all()
            return [AuxMetadataEntry(**row._mapping) for row in result]

    def add(self, item: AuxMetadataEntry | Iterable[AuxMetadataEntry]) -> None:
        with self.Session() as session:
            if isinstance(item, AuxMetadataEntry):
                session.add(item)
            else:
                session.add_all(item)
            session.commit()

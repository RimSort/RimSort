from pathlib import Path
from typing import Iterable

from loguru import logger
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

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

    @staticmethod
    def get(session: Session, item_path: Path | str) -> AuxMetadataEntry | None:
        if isinstance(item_path, Path):
            item_path = str(item_path)

        return (
            session.query(AuxMetadataEntry)
            .filter(AuxMetadataEntry.path == item_path)
            .first()
        )

    @staticmethod
    def get_or_create(session: Session, item_path: Path | str) -> AuxMetadataEntry:
        if isinstance(item_path, Path):
            item_path = str(item_path)

        entry = AuxMetadataController.get(session, item_path)

        if entry is None:
            entry = AuxMetadataEntry(path=item_path)
            try:
                with session.begin_nested():
                    session.add(entry)
                    session.flush()
            except Exception as e:
                session.rollback()
                logger.exception(f"Failed to create new aux metadata entry: {e}")
                raise e

        return entry

    @staticmethod
    def get_value_equals(session: Session, key: str, value: str) -> list[AuxMetadataEntry]:
        return (
            session.query(AuxMetadataEntry)
            .filter(getattr(AuxMetadataEntry, key) == value)
            .all()
        )

    @staticmethod
    def query(session: Session, query: str) -> list[AuxMetadataEntry]:
        result = session.execute(text(query)).all()
        return [AuxMetadataEntry(**row._mapping) for row in result]

    def add(self, item: AuxMetadataEntry | Iterable[AuxMetadataEntry]) -> None:
        with self.Session() as session:
            if isinstance(item, AuxMetadataEntry):
                session.add(item)
            else:
                session.add_all(item)
            session.commit()

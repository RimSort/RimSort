from pathlib import Path

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class AuxMetadataEntry(Base):
    __tablename__ = "Auxiliary Metadata"

    path: Mapped[Path] = mapped_column(primary_key=True)

    acf_time_touched: Mapped[int] = mapped_column(Integer, default=-1)
    acf_time_updated: Mapped[int] = mapped_column(Integer, default=-1)

    notes: Mapped[str] = mapped_column(String, default="")
    color_hex: Mapped[str] = mapped_column(String, default="19232d")
    ignore_warnings: Mapped[bool] = mapped_column(Boolean, default=False)

    def __repr__(self) -> str:
        return f"Path: {self.path}, Time Touched: {self.acf_time_touched}, Time Updated: {self.acf_time_updated}"

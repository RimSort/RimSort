from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


tags_table = Table(
    "tags_table",
    Base.metadata,
    Column("left_id", Integer, ForeignKey("auxiliary_metadata.path")),
    Column("right_id", Integer, ForeignKey("mod_tags.id")),
)


class AuxMetadataEntry(Base):
    __tablename__ = "auxiliary_metadata"

    path: Mapped[str] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String, default="Unknown")

    published_file_id: Mapped[int] = mapped_column(Integer, default=-1)
    acf_time_touched: Mapped[int] = mapped_column(Integer, default=-1)
    acf_time_updated: Mapped[int] = mapped_column(Integer, default=-1)

    user_notes: Mapped[str] = mapped_column(String, default="")
    color_hex: Mapped[str] = mapped_column(
        String, default=None, nullable=True
    )  # None/NULL means use theme default
    ignore_warnings: Mapped[bool] = mapped_column(Boolean, default=False)

    outdated: Mapped[bool] = mapped_column(Boolean, default=False)
    db_time_touched = Column(DateTime, default=func.now(), onupdate=func.now())

    tags: Mapped[list["TagsEntry"]] = relationship(
        secondary=tags_table, back_populates="mods"
    )

    def __repr__(self) -> str:
        return f"Path: {self.path}, Time Touched: {self.acf_time_touched}, Time Updated: {self.acf_time_updated}"


class TagsEntry(Base):
    __tablename__ = "mod_tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    tag: Mapped[str] = mapped_column(String, unique=True)

    mods: Mapped[list[AuxMetadataEntry]] = relationship(
        secondary=tags_table, back_populates="tags"
    )

    def __eq__(self, other: object) -> bool:
        if isinstance(other, TagsEntry) and self.tag == other.tag:
            return True
        elif isinstance(other, str) and self.tag == other:
            return True

        return super().__eq__(other)

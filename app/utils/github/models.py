from pathlib import Path

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    create_engine,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.models.metadata.metadata_db import Base


class GitHubModEntry(Base):
    """Per-instance table -- lives in the same DB as auxiliary_metadata."""

    __tablename__ = "github_mods"
    __table_args__ = (UniqueConstraint("owner_repo", "mod_path", name="uq_github_mod"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_repo: Mapped[str] = mapped_column(String, index=True)
    mod_path: Mapped[str] = mapped_column(String, ForeignKey("auxiliary_metadata.path"))
    installed_version: Mapped[str] = mapped_column(String)
    installed_asset_name: Mapped[str | None] = mapped_column(
        String, nullable=True, default=None
    )
    installed_commit_sha: Mapped[str | None] = mapped_column(
        String, nullable=True, default=None
    )
    auto_update: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class CacheBase(DeclarativeBase):
    """Separate base for the global release cache DB."""

    pass


class GitHubReleaseCache(CacheBase):
    """Global table -- lives in app-level storage, shared across instances."""

    __tablename__ = "github_release_cache"

    owner_repo: Mapped[str] = mapped_column(String, primary_key=True)
    releases_json: Mapped[str] = mapped_column(String, default="[]")
    etag: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    last_checked = Column(DateTime, default=func.now())


def get_cache_session(db_path: Path) -> Session:
    """Create a session for the global release cache DB."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite+pysqlite:///{db_path}")
    CacheBase.metadata.create_all(engine)
    return sessionmaker(bind=engine)()

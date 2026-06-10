"""Shared fixtures for GitHub utility tests."""

from typing import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.utils.github.models import CacheBase


@pytest.fixture
def cache_session() -> Generator[Session, None, None]:
    """Session for the global cache DB (github_release_cache)."""
    engine = create_engine("sqlite:///:memory:")
    CacheBase.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()

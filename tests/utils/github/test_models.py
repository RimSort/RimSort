from typing import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.models.metadata.metadata_db import AuxMetadataEntry, Base
from app.utils.github.models import (
    GitHubModEntry,
    GitHubReleaseCache,
)


@pytest.fixture
def instance_session() -> Generator[Session, None, None]:
    """Session for the per-instance DB (aux_metadata + github_mods)."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


class TestGitHubModEntry:
    def test_create_entry(self, instance_session: Session) -> None:
        aux = AuxMetadataEntry(path="/mods/CoolMod")
        instance_session.add(aux)
        instance_session.flush()

        entry = GitHubModEntry(
            owner_repo="author/CoolMod",
            mod_path="/mods/CoolMod",
            installed_version="v1.2.0",
            installed_asset_name="CoolMod.zip",
            installed_commit_sha="abc1234",
        )
        instance_session.add(entry)
        instance_session.commit()

        result = instance_session.query(GitHubModEntry).first()
        assert result is not None
        assert result.owner_repo == "author/CoolMod"
        assert result.mod_path == "/mods/CoolMod"
        assert result.installed_version == "v1.2.0"
        assert result.auto_update is False
        assert result.created_at is not None
        assert result.updated_at is not None

    def test_unique_constraint(self, instance_session: Session) -> None:
        aux = AuxMetadataEntry(path="/mods/CoolMod")
        instance_session.add(aux)
        instance_session.flush()

        entry1 = GitHubModEntry(
            owner_repo="author/CoolMod",
            mod_path="/mods/CoolMod",
            installed_version="v1.0.0",
        )
        instance_session.add(entry1)
        instance_session.commit()

        entry2 = GitHubModEntry(
            owner_repo="author/CoolMod",
            mod_path="/mods/CoolMod",
            installed_version="v2.0.0",
        )
        instance_session.add(entry2)
        with pytest.raises(Exception):
            instance_session.commit()

    def test_head_install(self, instance_session: Session) -> None:
        aux = AuxMetadataEntry(path="/mods/HeadMod")
        instance_session.add(aux)
        instance_session.flush()

        entry = GitHubModEntry(
            owner_repo="author/HeadMod",
            mod_path="/mods/HeadMod",
            installed_version="HEAD",
            installed_commit_sha="def5678",
        )
        instance_session.add(entry)
        instance_session.commit()

        result = instance_session.query(GitHubModEntry).first()
        assert result is not None
        assert result.installed_version == "HEAD"
        assert result.installed_asset_name is None


class TestGitHubReleaseCache:
    def test_create_cache_entry(self, cache_session: Session) -> None:
        cache = GitHubReleaseCache(
            owner_repo="author/CoolMod",
            releases_json='[{"tag": "v1.0.0"}]',
            etag='"abc123"',
        )
        cache_session.add(cache)
        cache_session.commit()

        result = cache_session.query(GitHubReleaseCache).first()
        assert result is not None
        assert result.owner_repo == "author/CoolMod"
        assert result.releases_json == '[{"tag": "v1.0.0"}]'
        assert result.etag == '"abc123"'
        assert result.last_checked is not None

    def test_upsert_cache(self, cache_session: Session) -> None:
        cache = GitHubReleaseCache(
            owner_repo="author/CoolMod",
            releases_json='[{"tag": "v1.0.0"}]',
        )
        cache_session.add(cache)
        cache_session.commit()

        existing = (
            cache_session.query(GitHubReleaseCache)
            .filter_by(owner_repo="author/CoolMod")
            .first()
        )
        assert existing is not None
        existing.releases_json = '[{"tag": "v1.0.0"}, {"tag": "v1.1.0"}]'
        existing.etag = '"new_etag"'
        cache_session.commit()

        result = cache_session.query(GitHubReleaseCache).first()
        assert result is not None
        assert "v1.1.0" in result.releases_json

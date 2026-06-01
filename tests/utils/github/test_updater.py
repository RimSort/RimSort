import json
from datetime import datetime, timedelta, timezone
from typing import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.models.metadata.metadata_db import AuxMetadataEntry, Base
from app.utils.github.models import CacheBase, GitHubModEntry, GitHubReleaseCache
from app.utils.github.provider import GitHubProvider
from app.utils.github.updater import UpdateAvailable, check_for_updates


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Combined session: instance tables + cache tables in one in-memory DB for test convenience."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    CacheBase.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _release_dict(
    tag: str,
    published_at: datetime,
    *,
    body: str = "",
    prerelease: bool = False,
) -> dict[str, object]:
    """Build a minimal release JSON dict for cache seeding."""
    return {
        "tag": tag,
        "name": tag,
        "published_at": published_at.isoformat(),
        "prerelease": prerelease,
        "assets": [],
        "body": body,
    }


def _seed_and_check(
    session: Session,
    owner_repo: str,
    mod_path: str,
    installed_version: str,
    releases: list[dict[str, object]],
) -> list[UpdateAvailable]:
    """Insert a mod entry + cached releases, then run the update checker."""
    aux = AuxMetadataEntry(path=mod_path)
    session.add(aux)
    session.flush()

    session.add(
        GitHubModEntry(
            owner_repo=owner_repo,
            mod_path=mod_path,
            installed_version=installed_version,
        )
    )
    session.add(
        GitHubReleaseCache(
            owner_repo=owner_repo,
            releases_json=json.dumps(releases),
            last_checked=datetime.now(tz=timezone.utc),
        )
    )
    session.commit()

    provider = GitHubProvider(cache_session=session)
    return check_for_updates(
        instance_session=session,
        provider=provider,
        check_interval_hours=24,
    )


class TestCheckForUpdates:
    def test_update_available(self, db_session: Session) -> None:
        now = datetime.now(tz=timezone.utc)
        updates = _seed_and_check(
            db_session,
            "author/Mod",
            "/mods/Mod",
            "v1.0.0",
            [
                _release_dict("v2.0.0", now, body="New stuff"),
                _release_dict("v1.0.0", now - timedelta(days=30)),
            ],
        )
        assert len(updates) == 1
        assert updates[0].owner_repo == "author/Mod"
        assert updates[0].installed_version == "v1.0.0"
        assert updates[0].latest_version == "v2.0.0"

    def test_no_update_when_current(self, db_session: Session) -> None:
        now = datetime.now(tz=timezone.utc)
        updates = _seed_and_check(
            db_session,
            "author/Mod",
            "/mods/Mod",
            "v1.0.0",
            [_release_dict("v1.0.0", now)],
        )
        assert len(updates) == 0

    def test_head_mod_detects_new_releases(self, db_session: Session) -> None:
        now = datetime.now(tz=timezone.utc)
        updates = _seed_and_check(
            db_session,
            "author/Mod",
            "/mods/Mod",
            "HEAD",
            [_release_dict("v1.0.0", now, body="First release")],
        )
        assert len(updates) == 1
        assert updates[0].installed_version == "HEAD"
        assert updates[0].latest_version == "v1.0.0"

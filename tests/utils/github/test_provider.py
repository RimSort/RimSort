import json
from datetime import datetime, timedelta, timezone
from typing import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.utils.github.models import CacheBase, GitHubReleaseCache
from app.utils.github.provider import (
    GitHubProvider,
    GitHubRateLimitError,
    ReleaseAsset,
    ReleaseInfo,
    parse_github_url,
)


class TestParseGitHubUrl:
    def test_standard_url(self) -> None:
        assert parse_github_url("https://github.com/owner/repo") == ("owner", "repo")

    def test_url_with_git_suffix(self) -> None:
        assert parse_github_url("https://github.com/owner/repo.git") == (
            "owner",
            "repo",
        )

    def test_url_with_trailing_path(self) -> None:
        assert parse_github_url("https://github.com/owner/repo/tree/main") == (
            "owner",
            "repo",
        )

    def test_url_with_trailing_slash(self) -> None:
        assert parse_github_url("https://github.com/owner/repo/") == ("owner", "repo")

    def test_non_github_url(self) -> None:
        assert parse_github_url("https://gitlab.com/owner/repo") is None

    def test_invalid_url(self) -> None:
        assert parse_github_url("not-a-url") is None

    def test_github_url_missing_repo(self) -> None:
        assert parse_github_url("https://github.com/owner") is None


class TestReleaseInfo:
    def test_filter_zip_assets(self) -> None:
        assets = [
            ReleaseAsset(
                name="Mod.zip", download_url="https://example.com/Mod.zip", size=1000
            ),
            ReleaseAsset(
                name="Mod.7z", download_url="https://example.com/Mod.7z", size=900
            ),
            ReleaseAsset(
                name="Source code (zip)",
                download_url="https://example.com/src.zip",
                size=500,
            ),
        ]
        release = ReleaseInfo(
            tag="v1.0.0",
            name="Release 1.0",
            published_at=datetime.now(tz=timezone.utc),
            prerelease=False,
            assets=assets,
            body="Release notes here",
        )
        custom_zips = release.get_custom_zip_assets()
        assert len(custom_zips) == 1
        assert custom_zips[0].name == "Mod.zip"

    def test_filter_source_archives(self) -> None:
        assets = [
            ReleaseAsset(
                name="Source code (zip)",
                download_url="https://example.com/src.zip",
                size=500,
            ),
            ReleaseAsset(
                name="Source code (tar.gz)",
                download_url="https://example.com/src.tar.gz",
                size=600,
            ),
        ]
        release = ReleaseInfo(
            tag="v1.0.0",
            name="Release 1.0",
            published_at=datetime.now(tz=timezone.utc),
            prerelease=False,
            assets=assets,
            body="",
        )
        assert len(release.get_custom_zip_assets()) == 0


class TestGitHubRateLimitError:
    def test_is_exception(self) -> None:
        err = GitHubRateLimitError("rate limit exceeded")
        assert isinstance(err, Exception)
        assert str(err) == "rate limit exceeded"


class TestGitHubProvider:
    @pytest.fixture
    def cache_session(self) -> Generator[Session, None, None]:
        engine = create_engine("sqlite:///:memory:")
        CacheBase.metadata.create_all(engine)
        session = sessionmaker(bind=engine)()
        yield session
        session.close()

    def test_get_releases_uses_cache_when_fresh(self, cache_session: Session) -> None:
        now = datetime.now(tz=timezone.utc)
        cached = GitHubReleaseCache(
            owner_repo="author/Mod",
            releases_json=json.dumps(
                [
                    {
                        "tag": "v1.0.0",
                        "name": "Release 1.0",
                        "published_at": now.isoformat(),
                        "prerelease": False,
                        "assets": [],
                        "body": "",
                    }
                ]
            ),
            etag='"etag"',
            last_checked=now,
        )
        cache_session.add(cached)
        cache_session.commit()

        provider = GitHubProvider(cache_session=cache_session)
        releases = provider.get_releases("author/Mod", check_interval_hours=24)
        assert len(releases) == 1
        assert releases[0].tag == "v1.0.0"

    def test_get_latest_stable_release(self, cache_session: Session) -> None:
        now = datetime.now(tz=timezone.utc)
        releases_data = [
            {
                "tag": "v2.0.0-beta",
                "name": "Beta 2.0",
                "published_at": (now + timedelta(days=1)).isoformat(),
                "prerelease": True,
                "assets": [],
                "body": "",
            },
            {
                "tag": "v1.0.0",
                "name": "Release 1.0",
                "published_at": now.isoformat(),
                "prerelease": False,
                "assets": [],
                "body": "",
            },
        ]
        cached = GitHubReleaseCache(
            owner_repo="author/Mod",
            releases_json=json.dumps(releases_data),
            last_checked=now,
        )
        cache_session.add(cached)
        cache_session.commit()

        provider = GitHubProvider(cache_session=cache_session)
        releases = provider.get_releases("author/Mod", check_interval_hours=24)
        latest = provider.get_latest_stable_release(releases)
        assert latest is not None
        assert latest.tag == "v1.0.0"

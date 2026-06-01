import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from github import GithubException
from sqlalchemy.orm import Session

from app.utils.github.models import GitHubReleaseCache
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

    def test_get_latest_stable_release_empty_list(self) -> None:
        result = GitHubProvider.get_latest_stable_release([])
        assert result is None

    def test_get_latest_stable_release_all_prereleases(self) -> None:
        now = datetime.now(tz=timezone.utc)
        releases = [
            ReleaseInfo(
                tag="v2.0.0-beta",
                name="Beta",
                published_at=now,
                prerelease=True,
                assets=[],
                body="",
            ),
        ]
        result = GitHubProvider.get_latest_stable_release(releases)
        assert result is not None
        assert result.tag == "v2.0.0-beta"


def _make_mock_asset(name: str, url: str, size: int = 1000) -> MagicMock:
    asset = MagicMock()
    asset.name = name
    asset.browser_download_url = url
    asset.size = size
    return asset


def _make_mock_release(
    tag: str,
    name: str | None = None,
    published_at: datetime | None = None,
    prerelease: bool = False,
    draft: bool = False,
    body: str = "",
    assets: list[MagicMock] | None = None,
) -> MagicMock:
    rel = MagicMock()
    rel.tag_name = tag
    rel.name = name or tag
    rel.published_at = published_at or datetime.now(tz=timezone.utc)
    rel.prerelease = prerelease
    rel.draft = draft
    rel.body = body
    rel.get_assets.return_value = assets or []
    return rel


class TestFetchReleasesFromApi:
    """Tests for GitHubProvider._fetch_releases_from_api with mocked PyGitHub."""

    @patch("app.utils.github.provider.Github")
    def test_successful_fetch_returns_releases(
        self, mock_github_cls: MagicMock
    ) -> None:
        now = datetime.now(tz=timezone.utc)
        mock_asset = _make_mock_asset("Mod.zip", "https://github.com/dl/Mod.zip")
        mock_release = _make_mock_release(
            tag="v1.0.0",
            published_at=now,
            assets=[mock_asset],
            body="Release notes",
        )

        mock_repo = MagicMock()
        mock_repo.get_releases.return_value = [mock_release]
        mock_github_cls.return_value.get_repo.return_value = mock_repo

        provider = GitHubProvider()
        releases = provider.get_releases("author/Mod", force_refresh=True)

        assert len(releases) == 1
        assert releases[0].tag == "v1.0.0"
        assert releases[0].body == "Release notes"
        assert len(releases[0].assets) == 1
        assert releases[0].assets[0].name == "Mod.zip"

    @patch("app.utils.github.provider.Github")
    def test_successful_fetch_updates_cache(
        self, mock_github_cls: MagicMock, cache_session: Session
    ) -> None:
        now = datetime.now(tz=timezone.utc)
        mock_release = _make_mock_release(tag="v1.0.0", published_at=now)
        mock_repo = MagicMock()
        mock_repo.get_releases.return_value = [mock_release]
        mock_github_cls.return_value.get_repo.return_value = mock_repo

        provider = GitHubProvider(cache_session=cache_session)
        provider.get_releases("author/Mod", force_refresh=True)

        cached = (
            cache_session.query(GitHubReleaseCache)
            .filter_by(owner_repo="author/Mod")
            .first()
        )
        assert cached is not None
        assert "v1.0.0" in cached.releases_json

    @patch("app.utils.github.provider.Github")
    def test_rate_limit_raises_error(self, mock_github_cls: MagicMock) -> None:
        mock_github_cls.return_value.get_repo.side_effect = GithubException(
            403, {"message": "rate limit"}, None
        )

        provider = GitHubProvider()
        with pytest.raises(GitHubRateLimitError):
            provider.get_releases("author/Mod", force_refresh=True)

    @patch("app.utils.github.provider.Github")
    def test_429_raises_rate_limit_error(self, mock_github_cls: MagicMock) -> None:
        mock_github_cls.return_value.get_repo.side_effect = GithubException(
            429, {"message": "too many requests"}, None
        )

        provider = GitHubProvider()
        with pytest.raises(GitHubRateLimitError):
            provider.get_releases("author/Mod", force_refresh=True)

    @patch("app.utils.github.provider.Github")
    def test_404_returns_empty_list(self, mock_github_cls: MagicMock) -> None:
        mock_github_cls.return_value.get_repo.side_effect = GithubException(
            404, {"message": "not found"}, None
        )

        provider = GitHubProvider()
        releases = provider.get_releases("author/Mod", force_refresh=True)
        assert releases == []

    @patch("app.utils.github.provider.Github")
    def test_other_github_exception_propagates(
        self, mock_github_cls: MagicMock
    ) -> None:
        mock_github_cls.return_value.get_repo.side_effect = GithubException(
            500, {"message": "server error"}, None
        )

        provider = GitHubProvider()
        with pytest.raises(GithubException):
            provider.get_releases("author/Mod", force_refresh=True)

    @patch("app.utils.github.provider.Github")
    def test_naive_datetime_gets_utc_timezone(self, mock_github_cls: MagicMock) -> None:
        naive_dt = datetime(2024, 1, 1, 12, 0, 0)
        mock_release = _make_mock_release(tag="v1.0.0", published_at=naive_dt)
        mock_repo = MagicMock()
        mock_repo.get_releases.return_value = [mock_release]
        mock_github_cls.return_value.get_repo.return_value = mock_repo

        provider = GitHubProvider()
        releases = provider.get_releases("author/Mod", force_refresh=True)

        assert releases[0].published_at.tzinfo is not None
        assert releases[0].published_at.tzinfo == timezone.utc

    @patch("app.utils.github.provider.Github")
    def test_release_with_none_name_uses_tag(self, mock_github_cls: MagicMock) -> None:
        mock_release = _make_mock_release(tag="v1.0.0")
        mock_release.name = None
        mock_repo = MagicMock()
        mock_repo.get_releases.return_value = [mock_release]
        mock_github_cls.return_value.get_repo.return_value = mock_repo

        provider = GitHubProvider()
        releases = provider.get_releases("author/Mod", force_refresh=True)

        assert releases[0].name == "v1.0.0"

    @patch("app.utils.github.provider.Github")
    def test_release_with_none_body_uses_empty_string(
        self, mock_github_cls: MagicMock
    ) -> None:
        mock_release = _make_mock_release(tag="v1.0.0")
        mock_release.body = None
        mock_repo = MagicMock()
        mock_repo.get_releases.return_value = [mock_release]
        mock_github_cls.return_value.get_repo.return_value = mock_repo

        provider = GitHubProvider()
        releases = provider.get_releases("author/Mod", force_refresh=True)

        assert releases[0].body == ""

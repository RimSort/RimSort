"""
GitHub API provider with caching and rate limit handling.

Wraps PyGitHub to fetch release data from GitHub repositories,
caching results in SQLAlchemy-backed SQLite to respect rate limits.
"""

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from github import Github, GithubException
from loguru import logger
from sqlalchemy.orm import Session

from app.utils.github.models import GitHubReleaseCache


@dataclass
class ReleaseAsset:
    """A downloadable asset attached to a GitHub release."""

    name: str
    download_url: str
    size: int


@dataclass
class ReleaseInfo:
    """Parsed GitHub release with filtered asset access."""

    tag: str
    name: str
    published_at: datetime
    prerelease: bool
    assets: list[ReleaseAsset]
    body: str

    def get_custom_zip_assets(self) -> list[ReleaseAsset]:
        """Return .zip assets that are NOT auto-generated source archives.

        GitHub auto-generates "Source code (zip)" and "Source code (tar.gz)"
        for every release. Mod authors upload separate .zip files containing
        the actual mod contents. This method filters to only those.
        """
        source_prefixes = ("source code",)
        return [
            a
            for a in self.assets
            if a.name.lower().endswith(".zip")
            and not a.name.lower().startswith(source_prefixes)
        ]


class GitHubRateLimitError(Exception):
    """Raised when the GitHub API rate limit is exceeded."""


def parse_github_url(url: str) -> tuple[str, str] | None:
    """Extract (owner, repo) from a GitHub URL.

    :param url: URL to parse (e.g. ``https://github.com/owner/repo``)
    :return: ``(owner, repo)`` tuple, or ``None`` if the URL is not
        a valid GitHub repository URL.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return None

    if parsed.hostname not in ("github.com", "www.github.com"):
        return None

    path = parsed.path.strip("/")
    if path.endswith(".git"):
        path = path[:-4]

    parts = path.split("/")
    if len(parts) < 2:
        return None

    owner, repo = parts[0], parts[1]
    if not owner or not repo:
        return None
    return owner, repo


def _releases_from_json(data: str) -> list[ReleaseInfo]:
    """Deserialize cached JSON into ``ReleaseInfo`` objects."""
    raw: list[dict[str, object]] = json.loads(data)
    releases: list[ReleaseInfo] = []
    for r in raw:
        assets_raw = r.get("assets", [])
        assert isinstance(assets_raw, list)
        assets = [
            ReleaseAsset(
                name=str(a["name"]),
                download_url=str(a["download_url"]),
                size=int(a.get("size", 0)),
            )
            for a in assets_raw
        ]
        published_at_raw = r.get("published_at")
        assert isinstance(published_at_raw, str)
        releases.append(
            ReleaseInfo(
                tag=str(r["tag"]),
                name=str(r.get("name", r["tag"])),
                published_at=datetime.fromisoformat(published_at_raw),
                prerelease=bool(r.get("prerelease", False)),
                assets=assets,
                body=str(r.get("body", "")),
            )
        )
    return releases


def _releases_to_json(releases: list[ReleaseInfo]) -> str:
    """Serialize ``ReleaseInfo`` objects to JSON for caching."""
    data = []
    for r in releases:
        data.append(
            {
                "tag": r.tag,
                "name": r.name,
                "published_at": r.published_at.isoformat(),
                "prerelease": r.prerelease,
                "assets": [
                    {
                        "name": a.name,
                        "download_url": a.download_url,
                        "size": a.size,
                    }
                    for a in r.assets
                ],
                "body": r.body,
            }
        )
    return json.dumps(data)


class GitHubProvider:
    """Fetches GitHub release data with SQLite-backed caching.

    Wraps PyGitHub to query the GitHub Releases API. Results are cached
    in ``GitHubReleaseCache`` rows so repeated lookups within
    ``check_interval_hours`` avoid network calls entirely.

    :param github_token: Optional personal access token. Without one,
        the unauthenticated rate limit is 60 req/hour; with one it's 5,000.
    :param cache_session: SQLAlchemy session bound to a DB containing
        ``GitHubReleaseCache``. If ``None``, caching is disabled.
    """

    def __init__(
        self,
        github_token: str | None = None,
        cache_session: Session | None = None,
    ) -> None:
        self._token = github_token
        self._cache_session = cache_session

    def _get_github_client(self) -> Github:
        """Create a PyGitHub client, optionally authenticated."""
        if self._token:
            return Github(self._token)
        return Github()

    def get_releases(
        self,
        owner_repo: str,
        check_interval_hours: int = 24,
        force_refresh: bool = False,
    ) -> list[ReleaseInfo]:
        """Fetch releases for ``owner/repo``, using cache when fresh.

        :param owner_repo: Repository slug, e.g. ``"owner/repo"``.
        :param check_interval_hours: How many hours before cached data
            is considered stale. Defaults to 24.
        :param force_refresh: If ``True``, bypass cache entirely.
        :return: List of releases, newest first.
        :raises GitHubRateLimitError: If the API rate limit is exceeded.
        """
        if self._cache_session and not force_refresh:
            cached = self._get_cached_releases(owner_repo, check_interval_hours)
            if cached is not None:
                return cached

        return self._fetch_releases_from_api(owner_repo)

    def _get_cached_releases(
        self, owner_repo: str, check_interval_hours: int
    ) -> list[ReleaseInfo] | None:
        """Return cached releases if they exist and are fresh enough."""
        if self._cache_session is None:
            return None

        entry = (
            self._cache_session.query(GitHubReleaseCache)
            .filter_by(owner_repo=owner_repo)
            .first()
        )
        if entry is None:
            return None

        # last_checked is a legacy Column(DateTime); cast to datetime for
        # type-safe comparisons (at runtime SQLAlchemy returns a datetime).
        last_checked_raw: datetime | None = entry.last_checked  # type: ignore[assignment]
        if last_checked_raw is None:
            return None

        last_checked: datetime = last_checked_raw
        if last_checked.tzinfo is None:
            last_checked = last_checked.replace(tzinfo=timezone.utc)

        cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=check_interval_hours)
        if last_checked < cutoff:
            return None

        logger.debug(f"Using cached releases for {owner_repo}")
        return _releases_from_json(entry.releases_json)

    def _fetch_releases_from_api(self, owner_repo: str) -> list[ReleaseInfo]:
        """Hit the GitHub Releases API and update the cache."""
        try:
            gh = self._get_github_client()
            repo = gh.get_repo(owner_repo)
            gh_releases = repo.get_releases()

            releases: list[ReleaseInfo] = []
            for rel in gh_releases:
                assets = [
                    ReleaseAsset(
                        name=a.name,
                        download_url=a.browser_download_url,
                        size=a.size,
                    )
                    for a in rel.get_assets()
                ]
                published = rel.published_at
                if published and published.tzinfo is None:
                    published = published.replace(tzinfo=timezone.utc)
                releases.append(
                    ReleaseInfo(
                        tag=rel.tag_name,
                        name=rel.name or rel.tag_name,
                        published_at=published or datetime.now(tz=timezone.utc),
                        prerelease=rel.prerelease,
                        assets=assets,
                        body=rel.body or "",
                    )
                )

            self._update_cache(owner_repo, releases)
            return releases

        except GithubException as e:
            if e.status in (403, 429):
                logger.warning(f"GitHub rate limit hit for {owner_repo}")
                raise GitHubRateLimitError(
                    "GitHub API rate limit reached. Configure a GitHub token "
                    "in Settings for higher limits (5,000 requests/hour vs 60)."
                ) from e
            if e.status == 404:
                logger.warning(f"Repository {owner_repo} not found or private")
                return []
            raise

    def _update_cache(self, owner_repo: str, releases: list[ReleaseInfo]) -> None:
        """Upsert the release cache row for ``owner_repo``."""
        if self._cache_session is None:
            return

        entry = (
            self._cache_session.query(GitHubReleaseCache)
            .filter_by(owner_repo=owner_repo)
            .first()
        )
        now = datetime.now(tz=timezone.utc)
        if entry is None:
            entry = GitHubReleaseCache(
                owner_repo=owner_repo,
                releases_json=_releases_to_json(releases),
                last_checked=now,
            )
            self._cache_session.add(entry)
        else:
            entry.releases_json = _releases_to_json(releases)
            entry.last_checked = now  # type: ignore[assignment]

        self._cache_session.commit()

    @staticmethod
    def get_latest_stable_release(
        releases: list[ReleaseInfo],
    ) -> ReleaseInfo | None:
        """Return the most recently published non-prerelease.

        Falls back to the first release in the list (newest) if
        no stable release exists.

        :param releases: List of releases to search.
        :return: The latest stable release, or ``None`` if empty.
        """
        stable = [r for r in releases if not r.prerelease]
        if not stable:
            return releases[0] if releases else None
        return max(stable, key=lambda r: r.published_at)

"""
Update checker for GitHub-installed mods.

Compares installed version tags against cached release data to
determine which mods have newer versions available. Uses publish-date
comparison rather than semver parsing so it works with arbitrary tag
formats (``v1.0.0``, ``2024.3``, ``release-5``, etc.).
"""

from dataclasses import dataclass

from loguru import logger
from sqlalchemy.orm import Session

from app.utils.github.models import GitHubModEntry
from app.utils.github.provider import (
    GitHubProvider,
    GitHubRateLimitError,
    ReleaseInfo,
)


@dataclass
class UpdateAvailable:
    """Describes a pending update for a single GitHub-installed mod."""

    owner_repo: str
    mod_path: str
    installed_version: str
    latest_version: str
    release_notes: str
    latest_release: ReleaseInfo | None = None
    auto_update: bool = False


def check_for_updates(
    instance_session: Session,
    provider: GitHubProvider,
    check_interval_hours: int = 24,
) -> list[UpdateAvailable]:
    """Check all tracked GitHub mods for available updates.

    Iterates every ``GitHubModEntry`` in the instance DB, fetches
    releases via ``provider`` (which consults the cache first), and
    compares installed versions against the latest stable release.

    :param instance_session: SQLAlchemy session for the instance DB
        (contains ``GitHubModEntry`` rows).
    :param provider: :class:`GitHubProvider` configured with a cache
        session for the global release cache.
    :param check_interval_hours: Cache freshness window passed through
        to :meth:`GitHubProvider.get_releases`.
    :return: List of mods that have a newer release available.
    """
    mods = instance_session.query(GitHubModEntry).all()
    updates: list[UpdateAvailable] = []

    for mod in mods:
        try:
            releases = provider.get_releases(
                mod.owner_repo,
                check_interval_hours=check_interval_hours,
            )
        except GitHubRateLimitError:
            logger.warning(f"Rate limit hit while checking {mod.owner_repo}, skipping")
            continue
        except Exception as e:
            logger.error(f"Error checking updates for {mod.owner_repo}: {e}")
            continue

        if not releases:
            continue

        latest_stable = provider.get_latest_stable_release(releases)
        if latest_stable is None:
            continue

        if mod.installed_version == "HEAD":
            updates.append(
                _make_update(mod, latest_stable),
            )
            continue

        installed_release = _find_release_by_tag(releases, mod.installed_version)
        if installed_release is None:
            updates.append(_make_update(mod, latest_stable))
            continue

        if latest_stable.published_at > installed_release.published_at:
            updates.append(_make_update(mod, latest_stable))

    return updates


def _make_update(mod: GitHubModEntry, latest: ReleaseInfo) -> UpdateAvailable:
    """Build an ``UpdateAvailable`` from a DB entry and the latest release."""
    return UpdateAvailable(
        owner_repo=mod.owner_repo,
        mod_path=mod.mod_path,
        installed_version=mod.installed_version,
        latest_version=latest.tag,
        release_notes=_truncate(latest.body, 200),
        latest_release=latest,
        auto_update=mod.auto_update,
    )


def _find_release_by_tag(releases: list[ReleaseInfo], tag: str) -> ReleaseInfo | None:
    """Find a release matching ``tag`` exactly."""
    for r in releases:
        if r.tag == tag:
            return r
    return None


def _truncate(text: str, max_len: int) -> str:
    """Truncate ``text`` to ``max_len`` chars, adding ellipsis if needed."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."

from __future__ import annotations

from app.utils.update_utils import (
    extract_version_from_edge_release,
    filter_releases_by_stream,
)

MOCK_RELEASES = [
    {
        "tag_name": "Edge",
        "prerelease": True,
        "draft": False,
        "assets": [
            {
                "name": "RimSort-v1.3.0-edge7-Linux.tar.gz",
                "browser_download_url": "https://example.com/edge.tar.gz",
            }
        ],
    },
    {
        "tag_name": "v1.2.4-beta2",
        "prerelease": True,
        "draft": False,
        "assets": [
            {
                "name": "RimSort-v1.2.4-beta2-Linux.tar.gz",
                "browser_download_url": "https://example.com/beta2.tar.gz",
            }
        ],
    },
    {
        "tag_name": "v1.2.4-beta1",
        "prerelease": True,
        "draft": False,
        "assets": [
            {
                "name": "RimSort-v1.2.4-beta1-Linux.tar.gz",
                "browser_download_url": "https://example.com/beta1.tar.gz",
            }
        ],
    },
    {
        "tag_name": "v1.2.3",
        "prerelease": False,
        "draft": False,
        "assets": [
            {
                "name": "RimSort-v1.2.3-Linux.tar.gz",
                "browser_download_url": "https://example.com/stable.tar.gz",
            }
        ],
    },
    {
        "tag_name": "v1.2.2",
        "prerelease": False,
        "draft": False,
        "assets": [
            {
                "name": "RimSort-v1.2.2-Linux.tar.gz",
                "browser_download_url": "https://example.com/old.tar.gz",
            }
        ],
    },
]


def test_stable_stream_returns_first_non_prerelease() -> None:
    result = filter_releases_by_stream(MOCK_RELEASES, "stable")
    assert result is not None
    assert result["tag_name"] == "v1.2.3"


def test_beta_stream_returns_first_beta_tag() -> None:
    result = filter_releases_by_stream(MOCK_RELEASES, "beta")
    assert result is not None
    assert result["tag_name"] == "v1.2.4-beta2"


def test_edge_stream_returns_edge_tag() -> None:
    result = filter_releases_by_stream(MOCK_RELEASES, "edge")
    assert result is not None
    assert result["tag_name"] == "Edge"


def test_beta_falls_back_to_stable_when_no_betas() -> None:
    releases_no_beta = [r for r in MOCK_RELEASES if "-beta" not in r["tag_name"]]
    result = filter_releases_by_stream(releases_no_beta, "beta")
    assert result is not None
    assert result["tag_name"] == "v1.2.3"


def test_edge_falls_back_to_beta_then_stable() -> None:
    releases_no_edge = [r for r in MOCK_RELEASES if r["tag_name"] != "Edge"]
    result = filter_releases_by_stream(releases_no_edge, "edge")
    assert result is not None
    assert result["tag_name"] == "v1.2.4-beta2"


def test_edge_falls_back_to_stable_when_no_edge_or_beta() -> None:
    releases_stable_only = [r for r in MOCK_RELEASES if not r["prerelease"]]
    result = filter_releases_by_stream(releases_stable_only, "edge")
    assert result is not None
    assert result["tag_name"] == "v1.2.3"


def test_returns_none_for_empty_releases() -> None:
    result = filter_releases_by_stream([], "stable")
    assert result is None


def test_skips_draft_releases() -> None:
    releases_with_draft = [
        {"tag_name": "v2.0.0", "prerelease": False, "draft": True, "assets": []},
    ] + MOCK_RELEASES
    result = filter_releases_by_stream(releases_with_draft, "stable")
    assert result is not None
    assert result["tag_name"] == "v1.2.3"


def test_unknown_stream_defaults_to_stable() -> None:
    result = filter_releases_by_stream(MOCK_RELEASES, "unknown")
    assert result is not None
    assert result["tag_name"] == "v1.2.3"


# --- Tests for extract_version_from_edge_release ---


def test_extract_version_from_edge_asset_name() -> None:
    release = {
        "assets": [{"name": "RimSort-v1.3.0-edge7-Linux_x86_64.tar.gz"}],
        "body": "",
    }
    assert extract_version_from_edge_release(release) == "1.3.0.dev7"


def test_extract_version_from_edge_asset_with_commit_suffix() -> None:
    release = {
        "assets": [{"name": "RimSort-v1.3.0-edge7+abc1234-Linux_x86_64.tar.gz"}],
        "body": "",
    }
    assert extract_version_from_edge_release(release) == "1.3.0.dev7"


def test_extract_version_from_edge_body_fallback() -> None:
    release = {
        "assets": [{"name": "some-unrelated-file.zip"}],
        "body": "Edge release v1.3.0-edge7.\nThe latest commit is abc1234.",
    }
    assert extract_version_from_edge_release(release) == "1.3.0.dev7"


def test_extract_version_returns_0_0_0_when_no_match() -> None:
    release = {"assets": [{"name": "unknown.zip"}], "body": "No version here."}
    assert extract_version_from_edge_release(release) == "0.0.0"


def test_extract_version_prefers_asset_over_body() -> None:
    release = {
        "assets": [{"name": "RimSort-v1.3.0-edge7-Linux.tar.gz"}],
        "body": "Edge release v1.2.0-edge3.",
    }
    assert extract_version_from_edge_release(release) == "1.3.0.dev7"

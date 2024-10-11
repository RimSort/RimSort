from app.utils.generic import (
    check_valid_http_git_url,
    extract_git_dir_name,
    extract_git_user_or_org,
)

GIT_URLS = [
    "https://github.com/org/RimSort.git",
    "https://github.com/org/RimSort",
    "https://github.com/org/RimSort/",
    "http://github.com/org/RimSort.git",
    "github.com/org/RimSort.git",
    "github.com/org/RimSort",
    "github.com/org/RimSort/",
]


def test_get_git_dir_name() -> None:
    for url in GIT_URLS:
        assert extract_git_dir_name(url) == "RimSort"


def test_get_git_org_or_user() -> None:
    for url in GIT_URLS:
        assert extract_git_user_or_org(url) == "org"


def test_check_valid_http_git_url() -> None:
    assert check_valid_http_git_url("") is False

    assert check_valid_http_git_url("github.com/org/RimSort.git") is False

    assert check_valid_http_git_url("https://github.com/org/RimSort.git") is True

    assert check_valid_http_git_url("http://github.com/org/RimSort.git/") is True

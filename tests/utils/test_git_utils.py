"""Tests for git URL parsing utilities."""

from app.utils.git_utils import git_get_repo_name, parse_git_url


class TestParseGitUrl:
    """Tests for parse_git_url."""

    def test_simple_https_url(self) -> None:
        result = parse_git_url("https://github.com/user/repo")
        assert result is not None
        assert result.clone_url == "https://github.com/user/repo"
        assert result.branch is None
        assert result.repo_name == "repo"

    def test_https_url_with_git_suffix(self) -> None:
        result = parse_git_url("https://github.com/user/repo.git")
        assert result is not None
        assert result.clone_url == "https://github.com/user/repo.git"
        assert result.branch is None
        assert result.repo_name == "repo"

    def test_https_url_with_tree_branch(self) -> None:
        result = parse_git_url(
            "https://github.com/vjikholg/RimWorld-RocketMan/tree/development-1.6-alpha"
        )
        assert result is not None
        assert result.clone_url == "https://github.com/vjikholg/RimWorld-RocketMan"
        assert result.branch == "development-1.6-alpha"
        assert result.repo_name == "RimWorld-RocketMan"

    def test_https_url_with_dot_in_branch(self) -> None:
        result = parse_git_url("https://github.com/user/my-mod/tree/release-2.0.1")
        assert result is not None
        assert result.clone_url == "https://github.com/user/my-mod"
        assert result.branch == "release-2.0.1"
        assert result.repo_name == "my-mod"

    def test_https_url_with_blob_path(self) -> None:
        result = parse_git_url("https://github.com/user/repo/blob/main/README.md")
        assert result is not None
        assert result.clone_url == "https://github.com/user/repo"
        assert result.branch == "main/README.md"
        assert result.repo_name == "repo"

    def test_https_url_with_tree_no_branch(self) -> None:
        result = parse_git_url("https://github.com/user/repo/tree")
        assert result is not None
        assert result.clone_url == "https://github.com/user/repo"
        assert result.branch is None
        assert result.repo_name == "repo"

    def test_https_url_with_issues_path(self) -> None:
        result = parse_git_url("https://github.com/user/repo/issues/42")
        assert result is not None
        assert result.clone_url == "https://github.com/user/repo"
        assert result.branch is None
        assert result.repo_name == "repo"

    def test_ssh_url(self) -> None:
        result = parse_git_url("git@github.com:user/repo.git")
        assert result is not None
        assert result.clone_url == "git@github.com:user/repo.git"
        assert result.branch is None
        assert result.repo_name == "repo"

    def test_ssh_url_without_git_suffix(self) -> None:
        result = parse_git_url("git@github.com:user/repo")
        assert result is not None
        assert result.repo_name == "repo"

    def test_invalid_url(self) -> None:
        assert parse_git_url("invalid-url") is None

    def test_empty_string(self) -> None:
        assert parse_git_url("") is None

    def test_none_input(self) -> None:
        assert parse_git_url(None) is None  # type: ignore[arg-type]

    def test_https_url_with_only_owner(self) -> None:
        assert parse_git_url("https://github.com/user") is None

    def test_gitlab_url(self) -> None:
        result = parse_git_url("https://gitlab.com/group/project/tree/v2.0")
        assert result is not None
        assert result.clone_url == "https://gitlab.com/group/project"
        assert result.branch == "v2.0"
        assert result.repo_name == "project"

    def test_url_with_slash_in_branch(self) -> None:
        result = parse_git_url("https://github.com/user/repo/tree/feature/my-branch")
        assert result is not None
        assert result.clone_url == "https://github.com/user/repo"
        assert result.branch == "feature/my-branch"
        assert result.repo_name == "repo"

    def test_http_url(self) -> None:
        result = parse_git_url("http://github.com/user/repo")
        assert result is not None
        assert result.clone_url == "http://github.com/user/repo"
        assert result.repo_name == "repo"

    def test_url_with_trailing_slash(self) -> None:
        result = parse_git_url("https://github.com/user/repo/")
        assert result is not None
        assert result.repo_name == "repo"
        assert result.branch is None

    def test_repo_name_with_dots(self) -> None:
        result = parse_git_url("https://github.com/user/my.repo.name")
        assert result is not None
        assert result.repo_name == "my.repo.name"
        assert result.branch is None


class TestGitGetRepoName:
    """Tests for git_get_repo_name."""

    def test_simple_https(self) -> None:
        assert git_get_repo_name("https://github.com/user/repo.git") == "repo"

    def test_ssh(self) -> None:
        assert git_get_repo_name("git@github.com:user/repo.git") == "repo"

    def test_invalid(self) -> None:
        assert git_get_repo_name("invalid-url") == ""

    def test_browse_url_with_dot_in_branch(self) -> None:
        name = git_get_repo_name(
            "https://github.com/vjikholg/RimWorld-RocketMan/tree/development-1.6-alpha"
        )
        assert name == "RimWorld-RocketMan"

    def test_browse_url_returns_repo_not_branch(self) -> None:
        name = git_get_repo_name("https://github.com/user/MyMod/tree/some-branch")
        assert name == "MyMod"

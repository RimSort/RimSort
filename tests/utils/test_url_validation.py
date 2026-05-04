import unittest.mock as mock

from app.utils.rentry.wrapper import RentryImport


def _make_rentry_import() -> RentryImport:
    """Create a RentryImport instance without triggering the UI."""
    with mock.patch.object(RentryImport, "__init__", lambda self, *a, **kw: None):
        return RentryImport.__new__(RentryImport)


class TestRentryUrlValidation:
    """Test Rentry URL validation rejects spoofed domains."""

    def test_valid_rentry_url(self) -> None:
        ri = _make_rentry_import()
        assert ri.is_valid_rentry_link("https://rentry.co/modlist")

    def test_valid_rentry_raw_url(self) -> None:
        ri = _make_rentry_import()
        assert ri.is_valid_rentry_link("https://rentry.co/modlist/raw")

    def test_reject_subdomain_spoofing(self) -> None:
        ri = _make_rentry_import()
        assert not ri.is_valid_rentry_link("https://rentry.co.evil.com/modlist")

    def test_reject_http(self) -> None:
        ri = _make_rentry_import()
        assert not ri.is_valid_rentry_link("http://rentry.co/modlist")

    def test_reject_non_url(self) -> None:
        ri = _make_rentry_import()
        assert not ri.is_valid_rentry_link("not-a-url")

    def test_case_insensitive_hostname(self) -> None:
        ri = _make_rentry_import()
        assert ri.is_valid_rentry_link("https://RENTRY.CO/modlist")

    def test_reject_empty(self) -> None:
        ri = _make_rentry_import()
        assert not ri.is_valid_rentry_link("")

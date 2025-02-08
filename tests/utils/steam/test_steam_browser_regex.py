from app.utils.generic import extract_page_title_steam_browser


def test_steam_browser_title_regex() -> None:
    """Test regular expression for parsing the Steam Browser title for mod name.

    Tests that the regular expression can correctly parse the possible patterns used
    in the Steam Workshop browser title.
    """

    # Test Steam Community title
    community_test = "Steam Community::Test mod"
    assert extract_page_title_steam_browser(community_test) == "Test mod"
    # Test Steam Workshop title
    workshop_test = "Steam Workshop::Test mod"
    assert extract_page_title_steam_browser(workshop_test) == "Test mod"

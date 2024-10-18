from re import search


def test_steam_browser_title_regex() -> None:
    """Test regular expression for parsing the Steam Browser title for mod name.

    Tests that the regular expression can correctly parse the possible patterns used
    in the Steam Workshop browser title.
    """
    steam_browse_regex = r"Steam (?:Community|Workshop)::(.*)"

    # Test Steam Community title
    community_test = "Steam Community::Test mod"
    match = search(steam_browse_regex, community_test)
    assert match is not None
    assert match.group(1) == "Test mod"
    # Test Steam Workshop title
    workshop_test = "Steam Workshop::Test mod"
    match = search(steam_browse_regex, workshop_test)
    assert match is not None
    assert match.group(1) == "Test mod"

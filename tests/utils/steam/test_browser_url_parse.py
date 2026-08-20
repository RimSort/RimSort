from app.utils.steam.steambrowser.browser import (
    parse_publishedfileid_from_url,
    toolbar_add_to_list_visible,
)


class TestParsePublishedfileidFromUrl:
    def test_sharedfiles_url(self) -> None:
        url = "https://steamcommunity.com/sharedfiles/filedetails/?id=1234567890"
        assert parse_publishedfileid_from_url(url) == "1234567890"

    def test_workshop_url(self) -> None:
        url = "https://steamcommunity.com/workshop/filedetails/?id=9876543210"
        assert parse_publishedfileid_from_url(url) == "9876543210"

    def test_url_with_searchtext(self) -> None:
        url = (
            "https://steamcommunity.com/sharedfiles/filedetails/?id=111"
            "&searchtext=test"
        )
        assert parse_publishedfileid_from_url(url) == "111"

    def test_invalid_url(self) -> None:
        assert parse_publishedfileid_from_url("https://example.com") is None


class TestToolbarAddToListVisible:
    def test_mod_detail_page(self) -> None:
        url = "https://steamcommunity.com/sharedfiles/filedetails/?id=1234567890"
        assert toolbar_add_to_list_visible(url) is True

    def test_browse_page(self) -> None:
        url = (
            "https://steamcommunity.com/workshop/browse/?appid=294100"
            "&browsesort=trend&section=readytouseitems&p=2"
        )
        assert toolbar_add_to_list_visible(url) is False

    def test_workshop_hub(self) -> None:
        url = "https://steamcommunity.com/app/294100/workshop/"
        assert toolbar_add_to_list_visible(url) is False

    def test_myworkshopfiles(self) -> None:
        url = (
            "https://steamcommunity.com/profiles/76561197984862442/"
            "myworkshopfiles/?appid=294100"
        )
        assert toolbar_add_to_list_visible(url) is False

    def test_text_search_browse(self) -> None:
        url = (
            "https://steamcommunity.com/workshop/browse/?appid=294100"
            "&searchtext=Harmony&section=readytouseitems"
        )
        assert toolbar_add_to_list_visible(url) is False

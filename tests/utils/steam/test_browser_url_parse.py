from app.utils.steam.steambrowser.browser import (
    parse_publishedfileid_from_url,
    resolve_workshop_page_mode,
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
            "https://steamcommunity.com/sharedfiles/filedetails/?id=111&searchtext=test"
        )
        assert parse_publishedfileid_from_url(url) == "111"

    def test_invalid_url(self) -> None:
        assert parse_publishedfileid_from_url("https://example.com") is None

    def test_trailing_slash_stripped(self) -> None:
        url = "https://steamcommunity.com/sharedfiles/filedetails/?id=12345/"
        assert parse_publishedfileid_from_url(url) == "12345"

    def test_empty_id_after_strip_returns_none(self) -> None:
        url = "https://steamcommunity.com/sharedfiles/filedetails/?id=   "
        assert parse_publishedfileid_from_url(url) is None


class TestResolveWorkshopPageMode:
    def test_collections_page(self) -> None:
        url = (
            "https://steamcommunity.com/workshop/browse/?appid=294100"
            "&section=collections"
        )
        assert resolve_workshop_page_mode(url) == "browse"

    def test_non_steam_url(self) -> None:
        assert resolve_workshop_page_mode("https://example.com/page") == "other"

    def test_workshop_collection_detail(self) -> None:
        url = "https://steamcommunity.com/workshop/filedetails/?id=99999"
        assert resolve_workshop_page_mode(url) == "detail"


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

    def test_filedetails_without_id(self) -> None:
        url = "https://steamcommunity.com/sharedfiles/filedetails/"
        assert toolbar_add_to_list_visible(url) is False

    def test_non_steam_url(self) -> None:
        assert (
            toolbar_add_to_list_visible("https://example.com/filedetails/?id=1")
            is False
        )

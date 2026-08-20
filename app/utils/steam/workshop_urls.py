from urllib.parse import urlencode

WORKSHOP_BROWSE_URL = "https://steamcommunity.com/workshop/browse/?appid=294100"


def build_workshop_text_search_url(mod_name: str) -> str:
    params = {
        "appid": "294100",
        "browsesort": "textsearch",
        "section": "readytouseitems",
        "p": "1",
        "num_per_page": "30",
        "days": "7",
        "searchtext": mod_name,
    }
    return f"https://steamcommunity.com/workshop/browse/?{urlencode(params)}"

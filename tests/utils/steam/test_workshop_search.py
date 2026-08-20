from unittest.mock import MagicMock, patch

from app.utils.steam.workshop_search import search_workshop_by_text


def test_search_workshop_by_text_maps_results() -> None:
    mock_api = MagicMock()
    mock_api.call.return_value = {
        "response": {
            "publishedfiledetails": [
                {
                    "result": 1,
                    "publishedfileid": "2009463077",
                    "title": "Harmony",
                    "preview_url": "https://example.com/preview.jpg",
                    "short_description": "A library for modders",
                },
                {"result": 2, "publishedfileid": "999"},
            ]
        }
    }

    with patch("app.utils.steam.workshop_search.WebAPI", return_value=mock_api):
        matches = search_workshop_by_text("test-key", "harmony", limit=10)

    assert len(matches) == 1
    assert matches[0]["publishedfileid"] == "2009463077"
    assert matches[0]["title"] == "Harmony"
    assert "2009463077" in matches[0]["url"]
    assert matches[0]["short_description"] == "A library for modders"


def test_search_workshop_by_text_requires_api_key() -> None:
    try:
        search_workshop_by_text("", "harmony")
        assert False, "expected ValueError"
    except ValueError:
        pass

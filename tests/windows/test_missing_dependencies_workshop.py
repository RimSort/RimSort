from unittest.mock import MagicMock
from urllib.parse import parse_qs, urlparse

from pytestqt.qtbot import QtBot

from app.utils.steam.workshop_urls import (
    WORKSHOP_BROWSE_URL,
    build_workshop_text_search_url,
)
from app.views.main_content_panel import MainContent


def test_build_workshop_text_search_url() -> None:
    url = build_workshop_text_search_url("Harmony")
    parsed = urlparse(url)
    params = parse_qs(parsed.query)

    assert parsed.scheme == "https"
    assert parsed.netloc == "steamcommunity.com"
    assert parsed.path == "/workshop/browse/"
    assert params["searchtext"] == ["Harmony"]
    assert params["appid"] == ["294100"]
    assert params["browsesort"] == ["textsearch"]
    assert params["section"] == ["readytouseitems"]


def test_workshop_browse_url() -> None:
    parsed = urlparse(WORKSHOP_BROWSE_URL)
    params = parse_qs(parsed.query)

    assert parsed.path == "/workshop/browse/"
    assert params["appid"] == ["294100"]


class TestSteamBrowserRestore:
    def test_restore_shows_hidden_target(self) -> None:
        panel = MainContent.__new__(MainContent)
        panel._workshop_restore_target = None

        target = MagicMock()
        target.isVisible.return_value = False
        panel._workshop_restore_target = target

        panel._on_steam_browser_restore()

        target.show.assert_called_once()
        target.raise_.assert_called_once()
        target.activateWindow.assert_called_once()
        assert panel._workshop_restore_target is None

    def test_restore_skips_visible_target(self) -> None:
        panel = MainContent.__new__(MainContent)
        panel._workshop_restore_target = None

        target = MagicMock()
        target.isVisible.return_value = True
        panel._workshop_restore_target = target

        panel._on_steam_browser_restore()

        target.show.assert_not_called()
        target.raise_.assert_not_called()
        target.activateWindow.assert_not_called()
        assert panel._workshop_restore_target is None

    def test_restore_noop_when_target_none(self) -> None:
        panel = MainContent.__new__(MainContent)
        panel._workshop_restore_target = None

        panel._on_steam_browser_restore()

        assert panel._workshop_restore_target is None


def test_open_workshop_hides_dialog_and_sets_restore_target(qtbot: QtBot) -> None:
    from app.utils.event_bus import EventBus
    from app.windows.missing_dependencies_dialog import MissingDependenciesDialog

    metadata_controller = MagicMock()
    metadata_controller.get_mod_name_from_package_id.return_value = "Harmony"

    dialog = MissingDependenciesDialog(metadata_controller)
    qtbot.addWidget(dialog)
    dialog.show()

    event_bus = EventBus()
    event_bus.workshop_restore_target = None
    received_urls: list[str] = []
    event_bus.do_browse_workshop_url.connect(received_urls.append)

    dialog._open_workshop("test.mod", resolve=None)

    assert event_bus.workshop_restore_target is dialog
    assert not dialog.isVisible()
    assert len(received_urls) == 1
    assert "Harmony" in received_urls[0]

    event_bus.do_browse_workshop_url.disconnect(received_urls.append)

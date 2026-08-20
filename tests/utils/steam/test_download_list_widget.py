from pytestqt.qtbot import QtBot
from PySide6.QtWidgets import QLabel

from app.utils.steam.steambrowser.download_list_widget import ModDownloadListWidget


def _widget(qtbot: QtBot) -> ModDownloadListWidget:
    widget = ModDownloadListWidget(title="Test list")
    qtbot.addWidget(widget)
    return widget


def test_add_mod_tracks_and_adds_item(qtbot: QtBot) -> None:
    widget = _widget(qtbot)

    added = widget.add_mod("123", title="My Mod")

    assert added is True
    assert widget.mods_tracking == ["123"]
    assert widget.list_widget.count() == 1
    assert widget.has_mod("123")


def test_add_duplicate_mod_is_tracked_as_dupe(qtbot: QtBot) -> None:
    widget = _widget(qtbot)
    widget.add_mod("123", title="My Mod")

    added = widget.add_mod("123", title="My Mod")

    assert added is False
    assert widget.list_widget.count() == 1
    assert widget.pop_dupe_report() == {"123": "My Mod"}
    # dupe report is cleared after popping
    assert widget.pop_dupe_report() == {}


def test_remove_mod_updates_tracking_and_ui(qtbot: QtBot) -> None:
    widget = _widget(qtbot)
    widget.add_mod("123", title="My Mod")

    widget.remove_mod("123")

    assert widget.mods_tracking == []
    assert widget.list_widget.count() == 0
    assert not widget.has_mod("123")


def test_clear_list_emits_mod_removed_for_each_mod(qtbot: QtBot) -> None:
    widget = _widget(qtbot)
    widget.add_mod("123")
    widget.add_mod("456")
    removed: list[str] = []
    widget.mod_removed.connect(removed.append)

    widget.clear_list()

    assert widget.mods_tracking == []
    assert widget.list_widget.count() == 0
    assert sorted(removed) == ["123", "456"]


def test_download_requested_emits_current_tracking(qtbot: QtBot) -> None:
    widget = _widget(qtbot)
    widget.add_mod("123")
    widget.add_mod("456")
    received: list[list[str]] = []
    widget.download_requested.connect(received.append)

    widget.download_steamcmd_button.click()

    assert received == [["123", "456"]]


def test_set_item_tooltip_updates_existing_item(qtbot: QtBot) -> None:
    widget = _widget(qtbot)
    widget.add_mod("123", title="My Mod")

    widget.set_item_tooltip("123", "<b>Enriched</b>")

    assert widget.list_widget.item(0).toolTip() == "<b>Enriched</b>"


def test_set_item_title_updates_existing_item(qtbot: QtBot) -> None:
    widget = _widget(qtbot)
    widget.add_mod("123", title="123")

    widget.set_item_title("123", "Resolved Mod Name")

    label = widget.list_widget.itemWidget(widget.list_widget.item(0))
    assert isinstance(label, QLabel)
    assert label.text() == "Resolved Mod Name"

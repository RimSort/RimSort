from pathlib import Path
from typing import Any, Generator
from unittest.mock import MagicMock, Mock

import pytest
from PySide6.QtCore import QObject

import app.views.dialogue as dialogue
from app.views.main_content_panel import MainContent


@pytest.fixture(autouse=True)
def patch_dialogue(monkeypatch: pytest.MonkeyPatch) -> Mock:
    mock_dialog = Mock()
    mock_dialog.return_value = None
    monkeypatch.setattr(dialogue, "show_dialogue_conditional", mock_dialog)
    return mock_dialog


@pytest.fixture
def main_content(
    monkeypatch: pytest.MonkeyPatch,
    qapp: Any,
    mock_settings_controller: MagicMock,
    mock_metadata_controller: MagicMock,
    mock_steamcmd_interface: MagicMock,
) -> Generator[MainContent, None, None]:
    QObject.__setattr__(
        mock_settings_controller.settings,
        "active_mods_dividers",
        [
            {
                "uuid": "__divider__combat",
                "name": "Combat mods",
                "collapsed": False,
                "index": 2,
            }
        ],
    )
    save_mock = MagicMock()
    mock_settings_controller.settings.save = save_mock
    mc = MainContent(
        mock_settings_controller.settings,
        metadata_controller=mock_metadata_controller,
    )
    mc._test_save_mock = save_mock  # type: ignore[attr-defined]
    monkeypatch.setattr(mc, "__duplicate_mods_prompt", Mock())
    monkeypatch.setattr(mc, "__missing_mods_prompt", Mock())
    monkeypatch.setattr(mc, "_insert_data_into_lists", Mock())
    yield mc
    mc.deleteLater()
    qapp.processEvents()
    MainContent._instance = None


def test_importing_xml_mod_list_clears_stale_dividers(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    main_content: MainContent,
    mock_metadata_controller: MagicMock,
) -> None:
    """Loading a normal RimWorld XML list cannot preserve RimSort-only dividers.

    If stale divider state survives the import, dividers from the previous list are
    reinserted at old numeric positions in the newly imported list. That is the
    behavior reported in RimSort/RimSort#2284.
    """
    imported_list = tmp_path / "different-list.xml"
    imported_list.write_text("<ModsConfigData></ModsConfigData>")
    monkeypatch.setattr(
        dialogue, "show_dialogue_file", Mock(return_value=str(imported_list))
    )
    mock_metadata_controller.get_mods_from_list.return_value = (
        ["uuid.mod.a", "uuid.mod.b"],
        ["uuid.mod.c"],
        {},
        {},
    )

    main_content._do_import_list_file_xml()

    assert main_content.settings.active_mods_dividers == []
    main_content._test_save_mock.assert_called()  # type: ignore[attr-defined]

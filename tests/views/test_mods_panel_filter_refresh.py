from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from app.controllers.metadata_controller import MetadataController
from app.controllers.mods_panel_controller import ModsPanelController
from app.models.metadata.metadata_structure import (
    AboutXmlMod,
    CaseInsensitiveStr,
    ModType,
)
from app.models.settings import Settings
from app.sort.mod_sorting import ModsPanelSortKey
from app.views.mods_panel import ModsPanel


@pytest.fixture
def search_panel(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fresh_event_bus: None,
) -> ModsPanel:
    settings = Settings()
    settings.include_mod_notes_in_mod_name_filter = False
    settings.save_inactive_mods_sort_state = False
    mods = {}
    for key, name, package_id, author, source in [
        ("alpha", "Needle Alpha", "example.alpha", "Someone", ModType.LOCAL),
        ("beta", "Beta", "needle.beta", "Needle Author", ModType.LOCAL),
        ("gamma", "Needle Gamma", "example.gamma", "Other", ModType.STEAM_WORKSHOP),
    ]:
        path = tmp_path / key
        path.mkdir()
        mods[str(path)] = AboutXmlMod(
            name=name,
            package_id=CaseInsensitiveStr(package_id),
            authors=[author],
            _mod_path=path,
            _mod_type=source,
        )
    metadata = MagicMock()
    metadata.mods_metadata = mods
    metadata.get_mod.side_effect = mods.get
    metadata.is_version_mismatch.return_value = False
    metadata.has_alternative_mod.return_value = None
    metadata.game_version = "1.6"
    monkeypatch.setattr(MetadataController, "instance", lambda: metadata)
    panel = ModsPanel(settings, metadata)
    qtbot.addWidget(panel)
    for mod_list in [panel.active_mods_list, panel.inactive_mods_list]:
        mod_list.recreate_mod_list(mod_list.list_type, list(mods), filtering=True)
    return panel


def _assert_matches(
    panel: ModsPanel, list_type: str, matches: set[str], hide: bool
) -> None:
    mod_list = (
        panel.active_mods_list if list_type == "Active" else panel.inactive_mods_list
    )
    actual = set()
    for index in range(mod_list.count()):
        item = mod_list.item(index)
        data = item.data(Qt.ItemDataRole.UserRole)
        name = Path(data.path).name
        assert item.isHidden() == (hide and name not in matches)
        assert data.filtered == (not hide and name not in matches)
        assert data.hidden_by_filter == (hide and name not in matches)
        if not item.isHidden() and not data.filtered:
            actual.add(name)
    assert actual == matches
    label = (
        panel.active_mods_label if list_type == "Active" else panel.inactive_mods_label
    )
    expected_count = f"[{len(matches)}/3]" if len(matches) < 3 else "[3]"
    assert label.text() == f"{list_type} {expected_count}"


def _sort_inactive(panel: ModsPanel, qtbot: QtBot, action: str) -> None:
    if action == "direction":
        panel.inactive_mods_sort_order_button.click()
        qtbot.waitUntil(lambda: panel._pending_sort_params is None)
    elif action == "key":
        panel.inactive_mods_sort_combobox.setCurrentIndex(
            panel.inactive_mods_sort_combobox.findData(ModsPanelSortKey.PACKAGEID)
        )
        qtbot.waitUntil(lambda: panel._pending_sort_params is None)
    else:
        # Supply a completed worker result deterministically; use the real rebuild.
        paths = panel.inactive_mods_list.paths.copy()
        panel._size_current_uuids = paths
        panel._on_folder_size_finished(
            {
                path: {"alpha": 30, "beta": 10, "gamma": 20}[Path(path).name]
                for path in paths
            }
        )


@pytest.mark.parametrize("list_type", ["Active", "Inactive"])
@pytest.mark.parametrize("field", ["PackageId", "Author(s)"])
@pytest.mark.parametrize("hide", [True, False])
def test_field_change_reapplies_current_query(
    search_panel: ModsPanel, list_type: str, field: str, hide: bool
) -> None:
    panel = search_panel
    if not hide:
        panel.signal_search_mode_filter(list_type)
    search = (
        panel.active_mods_search
        if list_type == "Active"
        else panel.inactive_mods_search
    )
    selector = (
        panel.active_mods_search_filter
        if list_type == "Active"
        else panel.inactive_mods_search_filter
    )
    search.setText("needle")
    _assert_matches(panel, list_type, {"alpha", "gamma"}, hide)

    selector.setCurrentText(panel.tr(field))
    _assert_matches(panel, list_type, {"beta"}, hide)
    assert search.text() == "needle"

    selector.setCurrentText(panel.tr("Name"))
    _assert_matches(panel, list_type, {"alpha", "gamma"}, hide)
    search.clear()
    _assert_matches(panel, list_type, {"alpha", "beta", "gamma"}, hide)


@pytest.mark.parametrize("hide", [True, False])
@pytest.mark.parametrize("filter_kind", ["query", "source", "both", "none"])
@pytest.mark.parametrize("sort_action", ["direction", "key", "folder_size"])
def test_inactive_sort_preserves_current_filters(
    search_panel: ModsPanel,
    qtbot: QtBot,
    hide: bool,
    filter_kind: str,
    sort_action: str,
) -> None:
    panel = search_panel
    panel.inactive_mods_sort_combobox.setCurrentIndex(
        panel.inactive_mods_sort_combobox.findData(ModsPanelSortKey.MODNAME)
    )
    qtbot.waitUntil(lambda: panel._pending_sort_params is None)
    if not hide:
        panel.on_inactive_mods_mode_filter_toggle()
    if filter_kind in ("source", "both"):
        filter_panel = panel.inactive_filter_button.filter_panel
        for source, checkbox in filter_panel._source_checkboxes.items():
            checkbox.setChecked(source == "local")
    if filter_kind in ("query", "both"):
        panel.inactive_mods_search.setText("needle")
    expected = {
        "query": {"alpha", "gamma"},
        "source": {"alpha", "beta"},
        "both": {"alpha"},
        "none": {"alpha", "beta", "gamma"},
    }[filter_kind]
    _assert_matches(panel, "Inactive", expected, hide)
    paths = panel.inactive_mods_list.paths.copy()

    _sort_inactive(panel, qtbot, sort_action)

    _assert_matches(panel, "Inactive", expected, hide)
    assert set(panel.inactive_mods_list.paths) == set(paths)
    assert panel.inactive_mods_search.text() == (
        "needle" if filter_kind in ("query", "both") else ""
    )
    if sort_action == "direction":
        ordered = ["beta", "alpha", "gamma"]
    elif sort_action == "key":
        ordered = ["beta", "gamma", "alpha"]
    else:
        ordered = ["alpha", "gamma", "beta"]
    assert [Path(path).name for path in panel.inactive_mods_list.paths] == ordered


@pytest.mark.parametrize("summary", ["warnings", "errors", "new", "updated"])
@pytest.mark.parametrize("sort_action", ["direction", "key", "folder_size"])
def test_inactive_sort_preserves_active_summary_filter(
    search_panel: ModsPanel, qtbot: QtBot, summary: str, sort_action: str
) -> None:
    panel = search_panel
    panel.settings.show_save_comparison_indicators = True
    panel.settings.mod_list_updated_indicator = True
    panel.inactive_mods_search.setText("needle")
    controller = ModsPanelController(panel, panel.settings)
    active_list = panel.active_mods_list
    for index in range(active_list.count()):
        item = active_list.item(index)
        data = item.data(Qt.ItemDataRole.UserRole)
        matches = Path(data.path).name == "alpha"
        data.warnings = "warning" if matches else ""
        data.errors = "error" if matches else ""
        data.__dict__["is_new"] = matches
        data.__dict__["is_recently_updated"] = matches
        item.setData(Qt.ItemDataRole.UserRole, data)
    label = {
        "warnings": panel.warnings_text,
        "errors": panel.errors_text,
        "new": panel.new_text,
        "updated": panel.updated_text,
    }[summary]
    flag = "news_label_active" if summary == "new" else f"{summary}_label_active"
    label.clicked.emit()
    assert getattr(controller, flag)
    before = [
        active_list.item(index).isHidden() for index in range(active_list.count())
    ]
    assert before == [False, True, True]

    _sort_inactive(panel, qtbot, sort_action)

    assert getattr(controller, flag)
    assert [
        active_list.item(index).isHidden() for index in range(active_list.count())
    ] == before
    _assert_matches(panel, "Inactive", {"alpha", "gamma"}, True)

from unittest.mock import MagicMock, patch

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QApplication, QCheckBox

from app.windows.github_mods_panel import _COL_NAME, _COL_REPO, GitHubModsPanel


def _make_panel(**overrides: object) -> GitHubModsPanel:
    """Create a bare GitHubModsPanel without __init__ for unit testing."""
    panel = GitHubModsPanel.__new__(GitHubModsPanel)
    panel._update_worker = None
    panel._auto_update_signals_blocked = False
    panel.metadata_manager = MagicMock()
    panel.settings_controller = MagicMock()
    panel.settings_controller.settings.aux_db_path = "/tmp/test.db"
    panel.editor_model = MagicMock()
    panel.editor_table_view = MagicMock()
    panel.ui_elements = MagicMock()
    panel._populate_from_mods = MagicMock()
    for key, value in overrides.items():
        setattr(panel, key, value)
    return panel


class TestGitHubModsPanel:
    def test_panel_creates_without_error(self, qapp: QApplication) -> None:
        with patch("app.windows.github_mods_panel.GitHubModsPanel._populate_from_mods"):
            panel = GitHubModsPanel.__new__(GitHubModsPanel)
            assert panel is not None


class TestGetSelectedModData:
    def test_returns_data_for_checked_rows(self, qapp: QApplication) -> None:
        model = QStandardItemModel(2, 3)

        name_item_0 = QStandardItem("Mod Alpha")
        name_item_0.setData("/mods/alpha", Qt.ItemDataRole.UserRole)
        repo_item_0 = QStandardItem("owner/alpha")

        name_item_1 = QStandardItem("Mod Beta")
        name_item_1.setData("/mods/beta", Qt.ItemDataRole.UserRole)
        repo_item_1 = QStandardItem("owner/beta")

        checkbox_item_0 = QStandardItem()
        checkbox_item_1 = QStandardItem()

        model.setItem(0, 0, checkbox_item_0)
        model.setItem(0, _COL_NAME, name_item_0)
        model.setItem(0, _COL_REPO, repo_item_0)
        model.setItem(1, 0, checkbox_item_1)
        model.setItem(1, _COL_NAME, name_item_1)
        model.setItem(1, _COL_REPO, repo_item_1)

        panel = _make_panel(editor_model=model)

        cb_checked = QCheckBox()
        cb_checked.setChecked(True)
        cb_unchecked = QCheckBox()
        cb_unchecked.setChecked(False)

        def indexWidget_side_effect(idx: object) -> QCheckBox:
            if hasattr(idx, "row") and idx.row() == 0:
                return cb_checked
            return cb_unchecked

        panel.editor_table_view.indexWidget.side_effect = indexWidget_side_effect

        result = panel._get_selected_mod_data()

        assert len(result) == 1
        assert result[0]["mod_path"] == "/mods/alpha"
        assert result[0]["owner_repo"] == "owner/alpha"
        assert result[0]["display_name"] == "Mod Alpha"

    def test_returns_empty_when_no_rows_checked(self, qapp: QApplication) -> None:
        model = QStandardItemModel(1, 3)

        name_item = QStandardItem("Mod A")
        name_item.setData("/mods/a", Qt.ItemDataRole.UserRole)
        repo_item = QStandardItem("owner/a")
        checkbox_item = QStandardItem()

        model.setItem(0, 0, checkbox_item)
        model.setItem(0, _COL_NAME, name_item)
        model.setItem(0, _COL_REPO, repo_item)

        panel = _make_panel(editor_model=model)

        cb = QCheckBox()
        cb.setChecked(False)
        panel.editor_table_view.indexWidget.return_value = cb

        result = panel._get_selected_mod_data()
        assert result == []

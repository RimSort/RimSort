from pathlib import Path
from typing import cast
from unittest.mock import MagicMock, patch

from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QAbstractButton, QApplication, QCheckBox

from app.utils.metadata import MetadataManager
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
    panel._populate_from_mods = MagicMock()  # type: ignore[method-assign]
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

        def indexWidget_side_effect(idx: QModelIndex) -> QCheckBox:
            if idx.row() == 0:
                return cb_checked
            return cb_unchecked

        panel.editor_table_view.indexWidget.side_effect = indexWidget_side_effect  # type: ignore[attr-defined]

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
        panel.editor_table_view.indexWidget.return_value = cb  # type: ignore[attr-defined]

        result = panel._get_selected_mod_data()
        assert result == []


class TestOnUninstallDelete:
    # jscpd:ignore-start
    @patch("app.windows.github_mods_panel.EventBus")
    @patch("app.windows.github_mods_panel.shutil.rmtree")
    @patch("app.windows.github_mods_panel.QMessageBox")
    @patch("app.windows.github_mods_panel.AuxMetadataController")
    def test_deletes_files_and_db_entries_on_confirm(
        self,
        mock_aux_ctrl: MagicMock,
        mock_msgbox: MagicMock,
        mock_rmtree: MagicMock,
        mock_event_bus: MagicMock,
        qapp: QApplication,
    ) -> None:
        panel = _make_panel()
        panel._get_selected_mod_data = MagicMock(  # type: ignore[method-assign]
            return_value=[
                {
                    "mod_path": "/mods/alpha",
                    "owner_repo": "owner/alpha",
                    "display_name": "Mod Alpha",
                },
            ]
        )

        mock_msgbox.question.return_value = mock_msgbox.StandardButton.Yes

        mock_session = MagicMock()
        mock_aux_ctrl.get_or_create_cached_instance.return_value.Session.return_value.__enter__ = MagicMock(
            return_value=mock_session
        )
        mock_aux_ctrl.get_or_create_cached_instance.return_value.Session.return_value.__exit__ = MagicMock(
            return_value=False
        )

        mock_entry = MagicMock()
        mock_session.query.return_value.filter_by.return_value.first.return_value = (
            mock_entry
        )

        panel._on_uninstall_delete()

        mock_rmtree.assert_called_once_with(Path("/mods/alpha"))
        mock_session.delete.assert_called_once_with(mock_entry)
        mock_session.flush.assert_called_once()
        mock_aux_ctrl.delete.assert_called_once_with(mock_session, Path("/mods/alpha"))
        mock_event_bus.return_value.do_refresh_mods_lists.emit.assert_called_once()

    @patch("app.windows.github_mods_panel.QMessageBox")
    def test_does_nothing_when_cancelled(
        self,
        mock_msgbox: MagicMock,
        qapp: QApplication,
    ) -> None:
        panel = _make_panel()
        panel._get_selected_mod_data = MagicMock(  # type: ignore[method-assign]
            return_value=[
                {
                    "mod_path": "/mods/alpha",
                    "owner_repo": "owner/alpha",
                    "display_name": "Mod Alpha",
                },
            ]
        )
        mock_msgbox.question.return_value = mock_msgbox.StandardButton.No

        panel._on_uninstall_delete()

    # jscpd:ignore-end

    def test_does_nothing_when_no_selection(self, qapp: QApplication) -> None:
        panel = _make_panel()
        panel._get_selected_mod_data = MagicMock(return_value=[])  # type: ignore[method-assign]
        panel._on_uninstall_delete()


class TestOnUninstallConvertToGit:
    # jscpd:ignore-start
    @patch("app.windows.github_mods_panel.EventBus")
    @patch("app.windows.github_mods_panel.QMessageBox")
    @patch("app.windows.github_mods_panel.AuxMetadataController")
    def test_head_tracked_mod_just_deletes_db_entry(
        self,
        mock_aux_ctrl: MagicMock,
        mock_msgbox: MagicMock,
        mock_event_bus: MagicMock,
        qapp: QApplication,
    ) -> None:
        panel = _make_panel()
        panel._get_selected_mod_data = MagicMock(  # type: ignore[method-assign]
            return_value=[
                {
                    "mod_path": "/mods/alpha",
                    "owner_repo": "owner/alpha",
                    "display_name": "Mod Alpha",
                },
            ]
        )
        mock_msgbox.question.return_value = mock_msgbox.StandardButton.Yes

        mock_session = MagicMock()
        mock_aux_ctrl.get_or_create_cached_instance.return_value.Session.return_value.__enter__ = MagicMock(
            return_value=mock_session
        )
        mock_aux_ctrl.get_or_create_cached_instance.return_value.Session.return_value.__exit__ = MagicMock(
            return_value=False
        )

        mock_entry = MagicMock()
        mock_entry.installed_asset_name = None  # HEAD-tracked
        mock_session.query.return_value.filter_by.return_value.first.return_value = (
            mock_entry
        )

        panel._on_uninstall_convert_to_git()

        mock_session.delete.assert_called_with(mock_entry)
        mock_session.commit.assert_called()
        mock_event_bus.return_value.do_refresh_mods_lists.emit.assert_called_once()

    @patch("app.windows.github_mods_panel.EventBus")
    @patch("app.windows.github_mods_panel.GitHubInstaller")
    @patch("app.windows.github_mods_panel.QMessageBox")
    @patch("app.windows.github_mods_panel.AuxMetadataController")
    def test_release_based_mod_clones_head_then_deletes_entry(
        self,
        mock_aux_ctrl: MagicMock,
        mock_msgbox: MagicMock,
        mock_installer: MagicMock,
        mock_event_bus: MagicMock,
        qapp: QApplication,
    ) -> None:
        panel = _make_panel()
        panel._get_selected_mod_data = MagicMock(  # type: ignore[method-assign]
            return_value=[
                {
                    "mod_path": "/mods/alpha",
                    "owner_repo": "owner/alpha",
                    "display_name": "Mod Alpha",
                },
            ]
        )
        mock_msgbox.question.return_value = mock_msgbox.StandardButton.Yes

        mock_session = MagicMock()
        mock_aux_ctrl.get_or_create_cached_instance.return_value.Session.return_value.__enter__ = MagicMock(
            return_value=mock_session
        )
        mock_aux_ctrl.get_or_create_cached_instance.return_value.Session.return_value.__exit__ = MagicMock(
            return_value=False
        )

        mock_entry = MagicMock()
        mock_entry.installed_asset_name = "release.zip"  # Release-based
        mock_session.query.return_value.filter_by.return_value.first.return_value = (
            mock_entry
        )

        backup_path = Path("/mods/alpha.rimsort_backup")
        mock_installer.backup_mod.return_value = backup_path
        mock_installer.install_head.return_value = (True, "abc1234")

        panel._on_uninstall_convert_to_git()

        mock_installer.backup_mod.assert_called_once_with(Path("/mods/alpha"))
        mock_installer.install_head.assert_called_once_with(
            "https://github.com/owner/alpha.git", "/mods/alpha"
        )
        mock_installer.delete_backup.assert_called_once_with(backup_path)
        mock_session.delete.assert_called_with(mock_entry)
        mock_session.commit.assert_called()

    @patch("app.windows.github_mods_panel.EventBus")
    @patch("app.windows.github_mods_panel.GitHubInstaller")
    @patch("app.windows.github_mods_panel.QMessageBox")
    @patch("app.windows.github_mods_panel.AuxMetadataController")
    def test_release_based_mod_restores_backup_on_clone_failure(
        self,
        mock_aux_ctrl: MagicMock,
        mock_msgbox: MagicMock,
        mock_installer: MagicMock,
        mock_event_bus: MagicMock,
        qapp: QApplication,
    ) -> None:
        panel = _make_panel()
        panel._get_selected_mod_data = MagicMock(  # type: ignore[method-assign]
            return_value=[
                {
                    "mod_path": "/mods/alpha",
                    "owner_repo": "owner/alpha",
                    "display_name": "Mod Alpha",
                },
            ]
        )
        mock_msgbox.question.return_value = mock_msgbox.StandardButton.Yes

        mock_session = MagicMock()
        mock_aux_ctrl.get_or_create_cached_instance.return_value.Session.return_value.__enter__ = MagicMock(
            return_value=mock_session
        )
        mock_aux_ctrl.get_or_create_cached_instance.return_value.Session.return_value.__exit__ = MagicMock(
            return_value=False
        )

        mock_entry = MagicMock()
        mock_entry.installed_asset_name = "release.zip"
        mock_session.query.return_value.filter_by.return_value.first.return_value = (
            mock_entry
        )

        backup_path = Path("/mods/alpha.rimsort_backup")
        mock_installer.backup_mod.return_value = backup_path
        mock_installer.install_head.return_value = (False, None)  # Clone failed

        panel._on_uninstall_convert_to_git()

        mock_installer.restore_backup.assert_called_once_with(
            backup_path, Path("/mods/alpha")
        )
        mock_session.delete.assert_not_called()

    @patch("app.windows.github_mods_panel.QMessageBox")
    def test_does_nothing_when_cancelled(
        self,
        mock_msgbox: MagicMock,
        qapp: QApplication,
    ) -> None:
        panel = _make_panel()
        panel._get_selected_mod_data = MagicMock(  # type: ignore[method-assign]
            return_value=[
                {
                    "mod_path": "/mods/alpha",
                    "owner_repo": "owner/alpha",
                    "display_name": "Mod Alpha",
                },
            ]
        )
        mock_msgbox.question.return_value = mock_msgbox.StandardButton.No

        panel._on_uninstall_convert_to_git()

    # jscpd:ignore-end

    def test_does_nothing_when_no_selection(self, qapp: QApplication) -> None:
        panel = _make_panel()
        panel._get_selected_mod_data = MagicMock(return_value=[])  # type: ignore[method-assign]
        panel._on_uninstall_convert_to_git()


class TestUninstallButton:
    @patch("app.windows.github_mods_panel.GitHubModsPanel._populate_from_mods")
    @patch("app.windows.github_mods_panel.EventBus")
    @patch.object(MetadataManager, "instance")
    def test_uninstall_button_exists_in_layout(
        self,
        mock_mm_instance: MagicMock,
        mock_event_bus: MagicMock,
        mock_populate: MagicMock,
        qapp: QApplication,
    ) -> None:
        mock_mm = MagicMock()
        mock_mm.settings_controller.settings.aux_db_path = "/tmp/test.db"
        mock_mm_instance.return_value = mock_mm
        mock_event_bus.return_value.do_refresh_mods_lists = MagicMock()

        panel = GitHubModsPanel()
        layout = panel.layouts.editor_main_actions_layout

        button_texts: list[str] = []
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None and hasattr(widget, "text"):
                button_texts.append(cast(QAbstractButton, widget).text())

        assert "Uninstall" in button_texts

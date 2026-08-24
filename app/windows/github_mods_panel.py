from __future__ import annotations

import shutil
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.controllers.metadata_controller import MetadataController

from loguru import logger
from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QCloseEvent, QColor, QStandardItem
from PySide6.QtWidgets import QCheckBox, QMessageBox

from app.controllers.metadata_db_controller import AuxMetadataController
from app.models.metadata.metadata_db import Base
from app.utils.app_info import AppInfo
from app.utils.button_factory import ButtonConfig, ButtonType, MenuItem
from app.utils.event_bus import EventBus
from app.utils.github.installer import GitHubInstaller
from app.utils.github.models import CacheBase, GitHubModEntry, GitHubReleaseCache
from app.utils.github.provider import GitHubProvider, ReleaseInfo, _releases_from_json
from app.utils.github.worker import GitHubUpdateCheckWorker
from app.windows.base_mods_panel import BaseModsPanel

# Column indices (after the checkbox column 0 added by BaseModsPanel)
_COL_NAME = 1
_COL_REPO = 2
_COL_INSTALLED = 3
_COL_LATEST = 4
_COL_AUTO_UPDATE = 5


class GitHubModsPanel(BaseModsPanel):
    """Panel for managing GitHub mods -- view installed, check updates, switch versions."""

    def __init__(
        self,
        metadata_controller: MetadataController,
    ) -> None:
        self._update_worker: Any = None
        self._auto_update_signals_blocked = False

        super().__init__(
            object_name="githubModsPanel",
            window_title=self.tr("RimSort - GitHub Mods"),
            title_text=self.tr("GitHub Mods"),
            details_text=self.tr("\nManage mods installed from GitHub releases."),
            additional_columns=[
                "Mod Name",
                "Repository",
                "Installed Version",
                "Latest Version",
                "Auto-Update",
            ],
            metadata_controller=metadata_controller,
        )

        button_configs = [
            ButtonConfig(
                button_type=ButtonType.CUSTOM,
                text=self.tr("Check for Updates"),
                custom_callback=self._on_check_updates,
            ),
            ButtonConfig(
                button_type=ButtonType.CUSTOM,
                text=self.tr("Update Selected"),
                custom_callback=self._on_update_selected,
            ),
            ButtonConfig(
                button_type=ButtonType.SELECT,
                text=self.tr("Uninstall"),
                menu_items=[
                    MenuItem(
                        text=self.tr("Delete mod completely"),
                        callback=self._on_uninstall_delete,
                    ),
                    MenuItem(
                        text=self.tr("Convert to plain git mod"),
                        callback=self._on_uninstall_convert_to_git,
                    ),
                ],
            ),
        ]

        self._setup_buttons_from_config(button_configs)
        self._populate_from_mods()
        self._reconfigure_table_sorting(sorting_enabled=True)

        EventBus().do_refresh_mods_lists.connect(self._populate_from_mods)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Disconnect signals and wait for any running worker before closing."""
        try:
            EventBus().do_refresh_mods_lists.disconnect(self._populate_from_mods)
        except RuntimeError:
            logger.debug("Signal already disconnected during close")
        if self._update_worker is not None and self._update_worker.isRunning():
            self._update_worker.quit()
            self._update_worker.wait(5000)
        super().closeEvent(event)

    def _populate_from_mods(self) -> None:
        """Populate table from per-instance github_mods table and release cache."""
        self._auto_update_signals_blocked = True
        self._clear_table_model()
        self._auto_update_signals_blocked = False

        try:
            from sqlalchemy import create_engine
            from sqlalchemy.orm import sessionmaker as sa_sessionmaker

            aux_controller = AuxMetadataController.get_or_create_cached_instance(
                self.settings.aux_db_path
            )
            Base.metadata.create_all(aux_controller.engine)

            with aux_controller.Session() as session:
                entries = session.query(GitHubModEntry).all()
                mod_data: list[dict[str, Any]] = [
                    {
                        "owner_repo": e.owner_repo,
                        "mod_path": e.mod_path,
                        "installed_version": e.installed_version,
                        "auto_update": e.auto_update,
                    }
                    for e in entries
                ]

            if not mod_data:
                return

            cache_db = AppInfo().app_storage_folder / "github_release_cache.db"
            cache_engine = create_engine(f"sqlite+pysqlite:///{cache_db}")
            CacheBase.metadata.create_all(cache_engine)
            cache_session = sa_sessionmaker(bind=cache_engine)()

            try:
                release_map: dict[str, list[ReleaseInfo]] = {}
                for row in cache_session.query(GitHubReleaseCache).all():
                    release_map[row.owner_repo] = _releases_from_json(row.releases_json)
            finally:
                cache_session.close()

            update_highlight = QBrush(QColor(255, 200, 50, 60))

            for mod in mod_data:
                mod_name: str = mod["owner_repo"]
                listed_mod = self.metadata_controller.get_mod(mod["mod_path"])
                if listed_mod is not None:
                    mod_name = listed_mod.name or mod_name

                latest_version = "—"
                has_update = False
                releases = release_map.get(mod["owner_repo"], [])
                if releases:
                    latest = GitHubProvider.get_latest_stable_release(releases)
                    if latest:
                        latest_version = latest.tag
                        has_update = latest_version != mod["installed_version"]

                name_item = QStandardItem(str(mod_name))
                name_item.setData(mod["mod_path"], Qt.ItemDataRole.UserRole)

                latest_item = QStandardItem(latest_version)
                latest_item.setData(latest_version, Qt.ItemDataRole.UserRole)

                row_items = [
                    name_item,
                    QStandardItem(str(mod["owner_repo"])),
                    QStandardItem(str(mod["installed_version"])),
                    latest_item,
                    QStandardItem(""),
                ]

                if has_update:
                    for item in row_items:
                        item.setBackground(update_highlight)

                self._add_row(row_items)

                row_idx = self.editor_model.rowCount() - 1
                auto_cb = QCheckBox()
                auto_cb.setChecked(bool(mod["auto_update"]))
                auto_cb.toggled.connect(
                    partial(self._on_auto_update_toggled, str(mod["mod_path"]))
                )
                auto_item = self.editor_model.item(row_idx, _COL_AUTO_UPDATE)
                self.editor_table_view.setIndexWidget(auto_item.index(), auto_cb)

        except Exception:
            logger.opt(exception=True).warning("Failed to populate GitHub mods table")

    def _on_auto_update_toggled(self, mod_path: str, checked: bool) -> None:
        """Persist auto-update toggle to the instance DB."""
        if self._auto_update_signals_blocked:
            return

        try:
            aux_controller = AuxMetadataController.get_or_create_cached_instance(
                self.settings.aux_db_path
            )
            Base.metadata.create_all(aux_controller.engine)

            with aux_controller.Session() as session:
                entry = (
                    session.query(GitHubModEntry).filter_by(mod_path=mod_path).first()
                )
                if entry is not None:
                    entry.auto_update = checked
                    session.commit()
        except Exception:
            logger.opt(exception=True).warning(
                f"Failed to update auto_update for {mod_path}"
            )

    def _get_selected_mod_data(self) -> list[dict[str, str]]:
        """Collect mod_path, owner_repo, and display_name from checked rows."""
        selected = self._get_selected_row_indices()
        result: list[dict[str, str]] = []
        for row in selected:
            name_item = self.editor_model.item(row, _COL_NAME)
            repo_item = self.editor_model.item(row, _COL_REPO)
            if not name_item or not repo_item:
                continue
            mod_path = name_item.data(Qt.ItemDataRole.UserRole)
            if not mod_path:
                continue
            result.append(
                {
                    "mod_path": mod_path,
                    "owner_repo": repo_item.text(),
                    "display_name": name_item.text(),
                }
            )
        return result

    def _on_uninstall_delete(self) -> None:
        """Delete selected mods completely: files, GitHubModEntry, and AuxMetadataEntry."""
        selected = self._get_selected_mod_data()
        if not selected:
            return

        mod_list = "\n".join(
            f"  - {m['display_name']} ({m['owner_repo']})" for m in selected
        )
        answer = QMessageBox.question(
            self,
            self.tr("Delete mods"),
            self.tr(
                "Delete the following mods completely? This cannot be undone.\n\n{mod_list}"
            ).format(mod_list=mod_list),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        aux_controller = AuxMetadataController.get_or_create_cached_instance(
            self.settings.aux_db_path
        )
        Base.metadata.create_all(aux_controller.engine)

        deleted = 0
        fs_errors: list[str] = []

        with aux_controller.Session() as session:
            for mod in selected:
                mod_path = mod["mod_path"]
                fs_ok = True
                try:
                    shutil.rmtree(Path(mod_path))
                except FileNotFoundError:
                    logger.debug(f"Mod directory already missing: {mod_path}")
                except Exception as e:
                    logger.warning(f"Failed to delete {mod_path}: {e}")
                    fs_errors.append(mod["display_name"])
                    fs_ok = False

                try:
                    entry = (
                        session.query(GitHubModEntry)
                        .filter_by(mod_path=mod_path)
                        .first()
                    )
                    if entry is not None:
                        session.delete(entry)
                        session.flush()

                    AuxMetadataController.delete(session, Path(mod_path))
                    if fs_ok:
                        deleted += 1
                except Exception:
                    session.rollback()
                    logger.opt(exception=True).warning(
                        f"Failed to clean up DB for {mod_path}"
                    )

        EventBus().do_refresh_mods_lists.emit()

        msg = self.tr("Deleted {n} mod(s).").format(n=deleted)
        if fs_errors:
            msg += " " + self.tr("File deletion failed for: {names}").format(
                names=", ".join(fs_errors)
            )
        self.ui_elements.details_label.setText(msg)

    def _on_uninstall_convert_to_git(self) -> None:
        """Convert selected mods from GitHub release tracking to plain git tracking."""
        selected = self._get_selected_mod_data()
        if not selected:
            return

        aux_controller = AuxMetadataController.get_or_create_cached_instance(
            self.settings.aux_db_path
        )
        Base.metadata.create_all(aux_controller.engine)

        entries: list[tuple[dict[str, str], GitHubModEntry]] = []
        has_release_based = False
        with aux_controller.Session() as session:
            for mod in selected:
                entry = (
                    session.query(GitHubModEntry)
                    .filter_by(mod_path=mod["mod_path"])
                    .first()
                )
                if entry is not None:
                    entries.append((mod, entry))
                    if entry.installed_asset_name:
                        has_release_based = True

        if not entries:
            return

        mod_list = "\n".join(
            f"  - {m['display_name']} ({m['owner_repo']})" for m, _ in entries
        )
        message = self.tr(
            "Convert the following mods to git tracking? "
            "They will be updated via the Git Mod Updater instead of GitHub releases."
            "\n\n{mod_list}"
        ).format(mod_list=mod_list)
        if has_release_based:
            message += "\n\n" + self.tr(
                "Release-based mods will be re-cloned from HEAD, replacing current files."
            )

        answer = QMessageBox.question(
            self,
            self.tr("Convert to git tracking"),
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        converted = 0
        errors: list[str] = []

        with aux_controller.Session() as session:
            for mod, _cached_entry in entries:
                mod_path = mod["mod_path"]
                try:
                    entry = (
                        session.query(GitHubModEntry)
                        .filter_by(mod_path=mod_path)
                        .first()
                    )
                    if entry is None:
                        continue

                    if entry.installed_asset_name:
                        clone_url = f"https://github.com/{mod['owner_repo']}.git"
                        backup_path = GitHubInstaller.backup_mod(Path(mod_path))
                        success, _sha = GitHubInstaller.install_head(
                            clone_url, mod_path
                        )
                        if not success:
                            GitHubInstaller.restore_backup(backup_path, Path(mod_path))
                            errors.append(mod["display_name"])
                            logger.warning(
                                f"Failed to clone HEAD for {mod['owner_repo']}, "
                                f"restored backup"
                            )
                            continue
                        GitHubInstaller.delete_backup(backup_path)

                    session.delete(entry)
                    session.commit()
                    converted += 1
                except Exception:
                    session.rollback()
                    logger.opt(exception=True).warning(
                        f"Failed to convert {mod_path} to git tracking"
                    )
                    errors.append(mod["display_name"])

        EventBus().do_refresh_mods_lists.emit()

        msg = self.tr("Converted {n} mod(s) to git tracking.").format(n=converted)
        if errors:
            msg += " " + self.tr("Failed: {names}").format(names=", ".join(errors))
        self.ui_elements.details_label.setText(msg)

    def _on_check_updates(self) -> None:
        """Trigger update check for all GitHub mods, then refresh the table."""
        if self._update_worker is not None and self._update_worker.isRunning():
            return

        try:
            from sqlalchemy import create_engine
            from sqlalchemy.orm import sessionmaker as sa_sessionmaker

            aux_controller = AuxMetadataController.get_or_create_cached_instance(
                self.settings.aux_db_path
            )
            Base.metadata.create_all(aux_controller.engine)

            with aux_controller.Session() as session:
                if session.query(GitHubModEntry).count() == 0:
                    return

            cache_db = AppInfo().app_storage_folder / "github_release_cache.db"
            cache_engine = create_engine(f"sqlite+pysqlite:///{cache_db}")
            CacheBase.metadata.create_all(cache_engine)
            cache_session = sa_sessionmaker(bind=cache_engine)()

            settings = self.settings
            provider = GitHubProvider(
                github_token=settings.github_token or None,
                cache_session=cache_session,
            )

            self._update_worker = GitHubUpdateCheckWorker(
                provider=provider,
                instance_session_factory=aux_controller.Session,
                check_interval_hours=0,
            )
            self._update_worker.finished.connect(self._on_check_updates_finished)
            self._update_worker.error.connect(self._on_check_updates_error)
            self._update_worker.start()

            self.ui_elements.details_label.setText(self.tr("Checking for updates..."))

        except Exception:
            logger.opt(exception=True).warning("Failed to start GitHub update check")

    def _on_check_updates_finished(self, updates: list[Any]) -> None:
        """Refresh the table after an update check completes."""
        self._populate_from_mods()
        self._update_worker = None

        if updates:
            names = ", ".join(u.owner_repo for u in updates[:5])
            suffix = f" and {len(updates) - 5} more" if len(updates) > 5 else ""
            self.ui_elements.details_label.setText(
                self.tr("{count} update(s) available: {names}{suffix}").format(
                    count=len(updates), names=names, suffix=suffix
                )
            )
        else:
            self.ui_elements.details_label.setText(self.tr("All mods are up to date."))

    def _on_check_updates_error(self, msg: str) -> None:
        """Handle update check error."""
        logger.warning(f"GitHub update check failed: {msg}")
        self._update_worker = None
        self.ui_elements.details_label.setText(
            self.tr("Update check failed: {error}").format(error=msg)
        )

    def _on_update_selected(self) -> None:
        """Emit version-switch signals for each selected mod that has an update."""
        selected = self._get_selected_row_indices()
        if not selected:
            return

        for row in selected:
            name_item = self.editor_model.item(row, _COL_NAME)
            installed_item = self.editor_model.item(row, _COL_INSTALLED)
            latest_item = self.editor_model.item(row, _COL_LATEST)
            if not name_item or not installed_item or not latest_item:
                continue

            mod_path = name_item.data(Qt.ItemDataRole.UserRole)
            latest_tag = latest_item.data(Qt.ItemDataRole.UserRole)
            installed_tag = installed_item.text()

            if not mod_path or not latest_tag or latest_tag == "—":
                continue
            if latest_tag == installed_tag:
                continue

            EventBus().github_version_switch_requested.emit(mod_path, latest_tag)

    def _populate_from_metadata(self) -> None:
        """Required by BaseModsPanel but GitHub panel uses _populate_from_mods instead."""
        self._populate_from_mods()

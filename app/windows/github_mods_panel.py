from __future__ import annotations

from functools import partial
from typing import Any

from loguru import logger
from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QCloseEvent, QColor, QStandardItem
from PySide6.QtWidgets import QCheckBox

from app.utils.event_bus import EventBus
from app.windows.base_mods_panel import (
    BaseModsPanel,
    ButtonConfig,
    ButtonType,
)

# Column indices (after the checkbox column 0 added by BaseModsPanel)
_COL_NAME = 1
_COL_REPO = 2
_COL_INSTALLED = 3
_COL_LATEST = 4
_COL_AUTO_UPDATE = 5


class GitHubModsPanel(BaseModsPanel):
    """Panel for managing GitHub mods -- view installed, check updates, switch versions."""

    def __init__(self) -> None:
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

            from app.controllers.metadata_db_controller import AuxMetadataController
            from app.models.metadata.metadata_db import Base
            from app.utils.app_info import AppInfo
            from app.utils.github.models import (
                CacheBase,
                GitHubModEntry,
                GitHubReleaseCache,
            )
            from app.utils.github.provider import (
                GitHubProvider,
                ReleaseInfo,
                _releases_from_json,
            )

            aux_controller = AuxMetadataController.get_or_create_cached_instance(
                self.settings_controller.settings.aux_db_path
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

            path_to_uuid = self.metadata_manager.mod_metadata_dir_mapper
            local_metadata = self.metadata_manager.internal_local_metadata
            update_highlight = QBrush(QColor(255, 200, 50, 60))

            for mod in mod_data:
                mod_name: str = mod["owner_repo"]
                uuid = path_to_uuid.get(mod["mod_path"])
                if uuid and uuid in local_metadata:
                    meta = local_metadata[uuid]
                    mod_name = meta.get("name", mod_name)

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
            from app.controllers.metadata_db_controller import AuxMetadataController
            from app.models.metadata.metadata_db import Base
            from app.utils.github.models import GitHubModEntry

            aux_controller = AuxMetadataController.get_or_create_cached_instance(
                self.settings_controller.settings.aux_db_path
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

    def _on_check_updates(self) -> None:
        """Trigger update check for all GitHub mods, then refresh the table."""
        if self._update_worker is not None and self._update_worker.isRunning():
            return

        try:
            from sqlalchemy import create_engine
            from sqlalchemy.orm import sessionmaker as sa_sessionmaker

            from app.controllers.metadata_db_controller import AuxMetadataController
            from app.models.metadata.metadata_db import Base
            from app.utils.app_info import AppInfo
            from app.utils.github.models import CacheBase, GitHubModEntry
            from app.utils.github.provider import GitHubProvider
            from app.utils.github.worker import GitHubUpdateCheckWorker

            aux_controller = AuxMetadataController.get_or_create_cached_instance(
                self.settings_controller.settings.aux_db_path
            )
            Base.metadata.create_all(aux_controller.engine)

            with aux_controller.Session() as session:
                if session.query(GitHubModEntry).count() == 0:
                    return

            cache_db = AppInfo().app_storage_folder / "github_release_cache.db"
            cache_engine = create_engine(f"sqlite+pysqlite:///{cache_db}")
            CacheBase.metadata.create_all(cache_engine)
            cache_session = sa_sessionmaker(bind=cache_engine)()

            settings = self.settings_controller.settings
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

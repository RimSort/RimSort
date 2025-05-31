from pathlib import Path
from typing import List, Optional

from loguru import logger
from PySide6.QtCore import QObject, QThreadPool, Slot
from PySide6.QtWidgets import QInputDialog

from app.controllers.settings_controller import SettingsController
from app.utils import git_utils
from app.utils.app_info import AppInfo
from app.utils.event_bus import EventBus
from app.utils.git_worker import (
    GitBatchUpdateResults,
    GitBatchUpdateWorker,
    GitCheckResults,
    GitCheckUpdatesWorker,
    GitCloneWorker,
)
from app.views.dialogue import (
    BinaryChoiceDialog,
    InformationBox,
    show_dialogue_conditional,
)
from app.views.main_content_panel import MainContent


class MainContentController(QObject):
    """Controller with concurrent checking/updating and improved structure."""

    def __init__(
        self, view: MainContent, settings_controller: SettingsController
    ) -> None:
        super().__init__()
        self.view = view
        self.settings_controller = settings_controller
        self._git_clone_worker: Optional[GitCloneWorker] = None

        # Thread pool for concurrent tasks
        self.thread_pool = QThreadPool.globalInstance()

        # Map download signals to (base_path, url_getter)
        self.download_signals = {
            EventBus().do_download_community_rules_db_from_github: (
                AppInfo().databases_folder,
                lambda: self.settings_controller.settings.external_community_rules_repo,
            ),
            EventBus().do_download_steam_workshop_db_from_github: (
                AppInfo().databases_folder,
                lambda: self.settings_controller.settings.external_steam_metadata_repo,
            ),
            EventBus().do_download_use_this_instead_db_from_github: (
                AppInfo().databases_folder,
                lambda: self.settings_controller.settings.external_use_this_instead_repo_path,
            ),
            EventBus().do_download_no_version_warning_db_from_github: (
                AppInfo().databases_folder,
                lambda: self.settings_controller.settings.external_no_version_warning_repo_path,
            ),
        }

        self._connect_signals()

    def _connect_signals(self) -> None:
        # Bind install mod signal
        EventBus().do_add_git_mod.connect(self._do_git_install_mod)

        # Bind update check signals
        update_targets = [
            self.view.mods_panel.active_mods_list.update_git_mods_signal,
            self.view.mods_panel.inactive_mods_list.update_git_mods_signal,
        ]
        for signal in update_targets:
            signal.connect(self._on_check_updates_requested)

        # Bind download signals
        for event_signal, (base_path_obj, url_getter) in self.download_signals.items():
            event_signal.connect(
                lambda url_getter=url_getter,
                base_path_obj=base_path_obj: self._do_git_clone(
                    base_path=str(base_path_obj),
                    repo_url=url_getter(),
                )
            )

    @Slot(list)
    def _on_check_updates_requested(self, repos_paths: List[Path]) -> None:
        """Schedule concurrent update checks for given repositories."""
        if not repos_paths:
            InformationBox(
                title=self.tr("No Repositories"),
                text=self.tr("No repositories provided for update check."),
                information=self.tr("Please select at least one repository to check."),
            ).exec()
            return

        logger.debug(
            f"Scheduling concurrent check for {len(repos_paths)} repositories."
        )
        worker = GitCheckUpdatesWorker(repos_paths)
        worker.signals.finished.connect(self._handle_check_updates_results)
        self.thread_pool.start(worker)

    @Slot(object)
    def _handle_check_updates_results(self, results: GitCheckResults) -> None:
        """Process results from GitCheckUpdatesWorker."""
        # Handle invalid paths
        for invalid_path in results.invalid_paths:
            InformationBox(
                title=self.tr("Invalid git repository"),
                text=self.tr("Could not find a valid git repository."),
                information=str(invalid_path),
            ).exec()

        updates = results.updates
        logger.debug(f"Found {len(updates)} repositories with updates.")

        if results.errors:
            msg = "\n".join(f"{path}: {err}" for path, err in results.errors.items())
            InformationBox(
                title=self.tr("Errors during update check"),
                text=self.tr("Some repositories encountered errors."),
                information=self.tr(
                    "Errors occurred while checking for updates:\n{errors}"
                ).format(errors=msg),
            ).exec()
            return

        if not updates:
            InformationBox(
                title=self.tr("No updates found"),
                text=self.tr("All repositories are up to date."),
                information=self.tr("No new commits were found on remote branches."),
            ).exec()
            return

        # Build details for user
        details_msg = ""
        for repo_path, messages in updates.items():
            details_msg += f"{repo_path}\n"
            for msg in messages:
                details_msg += f"\t{msg}\n"

        binary_diag = BinaryChoiceDialog(
            title=self.tr("Git Updates Found"),
            text=self.tr("{len} repositories have updates available.").format(
                len=len(updates)
            ),
            information=self.tr("Would you like to update them now?"),
            details=details_msg,
            positive_text=self.tr("Update All"),
            negative_text=self.tr("Cancel"),
        )

        if binary_diag.exec_is_positive():
            self._on_update_repos(list(updates.keys()))
        else:
            logger.debug("User declined batch update.")

    def _on_update_repos(self, repos_paths: List[Path]) -> None:
        """Schedule concurrent batch pull for multiple repositories."""
        logger.debug(
            f"Scheduling concurrent update for {len(repos_paths)} repositories."
        )
        worker = GitBatchUpdateWorker(repos_paths)
        worker.signals.finished.connect(self._handle_batch_update_results)
        self.thread_pool.start(worker)

    @Slot(object)
    def _handle_batch_update_results(self, results: GitBatchUpdateResults) -> None:
        """Process results from GitBatchUpdateWorker."""
        successful = results.successful
        failed = results.failed
        total = len(successful) + len(failed)

        if not failed:
            InformationBox(
                title=self.tr("Updates Completed"),
                text=self.tr("All repositories updated successfully!"),
                information=self.tr("{count} repositories were updated.").format(
                    count=len(successful)
                ),
                details="\n".join([Path(p).name for p in successful]),
            ).exec()
        elif not successful:
            details_msg = ""
            for repo_path, err in failed:
                details_msg += f"{Path(repo_path).name}: {err}\n"

            InformationBox(
                title=self.tr("Update Failed"),
                text=self.tr("All pull operations failed."),
                information=self.tr(
                    "{count} repositories could not be updated."
                ).format(count=len(failed)),
                details=details_msg,
            ).exec()
        else:
            details_msg = self.tr("Successful updates:\n")
            for p in successful:
                details_msg += f"  ✓ {Path(p).name}\n"
            details_msg += f"\n{self.tr('Failed updates:')}\n"
            for repo_path, err in failed:
                details_msg += f"  ✗ {Path(repo_path).name}: {err}\n"

            InformationBox(
                title=self.tr("Partial Updates Completed"),
                text=self.tr("Some repositories updated successfully."),
                information=self.tr(
                    "{success} succeeded, {failed} failed out of {total}."
                ).format(success=len(successful), failed=len(failed), total=total),
                details=details_msg,
            ).exec()

    @Slot(str, str)
    def _do_git_clone(self, base_path: str, repo_url: str) -> None:
        """Handle clone request: if exists, prompt overwrite or pull, else start clone."""
        repo_folder = git_utils.git_get_repo_name(repo_url)
        full_repo_path = Path(base_path) / repo_folder

        if full_repo_path.exists():
            answer = show_dialogue_conditional(
                title=self.tr("Existing repository found"),
                text=self.tr("An existing local folder was found."),
                information=self.tr(
                    "{repo_folder}\n\n"
                    + "Choose an action:\n"
                    + "1) Clone new (overwrite)\n"
                    + "2) Pull updates"
                ).format(repo_folder=full_repo_path.name),
                button_text_override=[self.tr("Clone new"), self.tr("Pull updates")],
                details=str(full_repo_path),
            )
            if answer == self.tr("Clone new"):
                self._start_git_clone_worker(repo_url, str(full_repo_path), force=True)
            elif answer == self.tr("Pull updates"):
                self._on_update_repos([full_repo_path])
            else:
                logger.debug("User cancelled clone operation.")
        else:
            self._start_git_clone_worker(repo_url, str(full_repo_path), force=False)

    def _start_git_clone_worker(
        self, repo_url: str, base_path: str, force: bool
    ) -> None:
        """Initialize and start GitCloneWorker."""
        if self._git_clone_worker is not None:
            try:
                self._git_clone_worker.finished.disconnect()
                self._git_clone_worker.progress.disconnect()
                self._git_clone_worker.error.disconnect()
                self._git_clone_worker.quit()
                self._git_clone_worker.wait()
            except Exception:
                pass
            self._git_clone_worker = None

        self._git_clone_worker = GitCloneWorker(
            repo_url=repo_url,
            repo_path=base_path,
            force=force,
            notify_errors=False,
        )
        self._git_clone_worker.finished.connect(self._on_git_clone_finished)
        self._git_clone_worker.progress.connect(self._on_git_clone_progress)
        self._git_clone_worker.error.connect(self._on_git_clone_error)
        logger.info(f"Starting git clone worker for: {repo_url}")
        self._git_clone_worker.start()

    @Slot(str)
    def _on_git_clone_progress(self, message: str) -> None:
        logger.debug(f"Git clone progress: {message}")

    @Slot(bool, str, str)
    def _on_git_clone_finished(self, success: bool, message: str, path: str) -> None:
        logger.info(
            f"Git clone finished: success={success}, message={message}, path={path}"
        )
        if success:
            InformationBox(
                title=self.tr("Clone Successful"),
                text=self.tr("Repository cloned successfully!"),
                information=self.tr("Cloned to: {path}").format(path=path),
            ).exec()
        if self._git_clone_worker:
            try:
                self._git_clone_worker.finished.disconnect()
                self._git_clone_worker.progress.disconnect()
                self._git_clone_worker.error.disconnect()
            except Exception:
                pass
            self._git_clone_worker = None

    @Slot(str)
    def _on_git_clone_error(self, error_message: str) -> None:
        logger.error(f"Git clone error: {error_message}")
        InformationBox(
            title=self.tr("Clone Error"),
            text=self.tr("Error during clone operation"),
            information=error_message,
        ).exec()

    @Slot()
    def _do_git_install_mod(self) -> None:
        """Prompt user for repo URL and trigger clone."""
        args, ok = QInputDialog().getText(
            self.view.mods_panel,
            self.tr("Enter git repo"),
            self.tr("Enter a git repository URL to clone:"),
        )
        if ok and args:
            self._do_git_clone(
                base_path=str(
                    self.settings_controller.settings.instances[
                        self.settings_controller.settings.current_instance
                    ].local_folder
                ),
                repo_url=args,
            )
        else:
            logger.debug("Cancelled git install mod.")

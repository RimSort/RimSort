from pathlib import Path
from typing import Optional

from loguru import logger
from PySide6.QtCore import QObject, Slot
from PySide6.QtWidgets import QInputDialog

from app.controllers.settings_controller import SettingsController
from app.utils import git_utils
from app.utils.app_info import AppInfo
from app.utils.event_bus import EventBus
from app.utils.git_worker import GitCloneWorker
from app.views.dialogue import (
    BinaryChoiceDialog,
    InformationBox,
    show_dialogue_conditional,
)
from app.views.main_content_panel import MainContent


class MainContentController(QObject):
    def __init__(
        self, view: MainContent, settings_controller: SettingsController
    ) -> None:
        super().__init__()

        self.view = view
        self.settings_controller = settings_controller
        self._git_clone_worker: Optional[GitCloneWorker] = (
            None  # Track active git clone worker
        )

        # Connect signals to slots
        self._connect_signals()

    def _connect_signals(self) -> None:
        EventBus().do_add_git_mod.connect(self._do_git_install_mod)
        self.view.mods_panel.active_mods_list.update_git_mods_signal.connect(
            self._do_git_check_updates
        )
        self.view.mods_panel.inactive_mods_list.update_git_mods_signal.connect(
            self._do_git_check_updates
        )
        EventBus().do_download_community_rules_db_from_github.connect(
            lambda: self._do_git_clone(
                base_path=str(AppInfo().databases_folder),
                repo_url=self.settings_controller.settings.external_community_rules_repo,
            )
        )
        EventBus().do_download_steam_workshop_db_from_github.connect(
            lambda: self._do_git_clone(
                base_path=str(AppInfo().databases_folder),
                repo_url=self.settings_controller.settings.external_steam_metadata_repo,
            )
        )
        EventBus().do_download_use_this_instead_db_from_github.connect(
            lambda: self._do_git_clone(
                base_path=str(AppInfo().databases_folder),
                repo_url=self.settings_controller.settings.external_use_this_instead_repo_path,
            )
        )
        EventBus().do_download_no_version_warning_db_from_github.connect(
            lambda: self._do_git_clone(
                base_path=str(AppInfo().databases_folder),
                repo_url=self.settings_controller.settings.external_no_version_warning_repo_path,
            )
        )
        pass

    @Slot(object)
    def _do_git_check_updates(self, repos_paths: list[Path]) -> None:
        """Check for updates in the git repositories in the list.
        Displays a dialogue with the list of repositories with updates, and prompts the user to update them.

        :param repos_paths: The list of paths to the git repositories to check for updates.
        :type repos_paths: list[Path]
        """
        logger.debug(f"Checking for updates in {len(repos_paths)} repositories.")
        updates: dict[Path, git_utils.pygit2.Walker] = {}
        for repo_path in repos_paths:
            repo = git_utils.git_discover(repo_path)
            if repo is None:
                logger.warning(f"Could not find valid git repository in {repo_path}")
                InformationBox(
                    title=self.tr("Invalid git repository"),
                    text=self.tr(
                        "Could not find a valid git repository in the selected folder."
                    ),
                    information=(
                        self.tr(
                            "Please make sure the selected folder contains a valid git repository."
                        )
                    ),
                    details=str(repo_path),
                ).exec()

                continue

            walker = git_utils.git_check_updates(repo)
            repo.free()
            if walker is not None:
                updates[repo_path] = walker

        logger.debug(f"Found {len(updates)} repositories with updates.")
        if len(updates) == 0:
            InformationBox(
                title=self.tr("No updates found"),
                text=self.tr("No updates were found in the selected repositories."),
                information=(
                    self.tr(
                        "All repositories are up to date with their respective remote branches."
                    )
                ),
            ).exec()
            return

        details_msg = ""
        for repo_path, walker in updates.items():
            details_msg += f"{repo_path}\n"
            for commit in walker:
                details_msg += f"\t{commit.message}\n"

        binary_diag = BinaryChoiceDialog(
            title=self.tr("Git Updates Found"),
            text=self.tr("{len} repositories have updates available.").format(
                len=len(updates)
            ),
            information=self.tr("Would you like to update (pull) them now?"),
            details=details_msg,
            positive_text="Update All",
            negative_text="Cancel",
        )

        if binary_diag.exec_is_positive():
            self._do_git_updates(list(updates.keys()))
        else:
            logger.debug("User declined git update operation.")    @Slot(object)
    def _do_git_updates(self, repos_paths: list[Path]) -> None:
        """Update the git repositories in the list."""
        logger.debug(f"Updating {len(repos_paths)} repositories.")
        
        successful_updates = []
        failed_updates = []
        
        for i, repo_path in enumerate(repos_paths, 1):
            logger.info(f"Updating repository {i}/{len(repos_paths)}: {repo_path.name}")
            
            repo = git_utils.git_discover(repo_path)
            if repo is None:
                logger.warning(f"Could not find valid git repository in {repo_path}")
                failed_updates.append((repo_path, self.tr("Invalid git repository")))
                continue

            try:
                git_utils.git_pull(repo)
                logger.info(f"Successfully updated repository at {repo_path}")
                successful_updates.append(repo_path)
            except Exception as e:
                error_msg = str(e)
                logger.error(f"Failed to update repository at {repo_path}: {error_msg}")
                failed_updates.append((repo_path, error_msg))
            finally:
                repo.free()

        # Show completion notification
        self._show_update_completion_notification(successful_updates, failed_updates)
        logger.debug("Git update operation completed.")
    
    def _show_update_completion_notification(self, successful_updates: list[Path], failed_updates: list[tuple[Path, str]]) -> None:
        """Show notification about the update operation results."""
        total_repos = len(successful_updates) + len(failed_updates)
        
        if len(failed_updates) == 0:
            # All updates successful
            InformationBox(
                title=self.tr("Updates Completed"),
                text=self.tr("All repositories updated successfully!"),
                information=self.tr("{count} repositories were updated successfully.").format(
                    count=len(successful_updates)
                ),
                details="\n".join([str(repo.name) for repo in successful_updates]),
            ).exec()
        elif len(successful_updates) == 0:
            # All updates failed
            details_msg = ""
            for repo_path, error in failed_updates:
                details_msg += f"{repo_path.name}: {error}\n"
            
            InformationBox(
                title=self.tr("Update Failed"),
                text=self.tr("Failed to update repositories"),
                information=self.tr("All {count} repositories failed to update.").format(
                    count=len(failed_updates)
                ),
                details=details_msg,
            ).exec()
        else:
            # Mixed results
            details_msg = self.tr("Successful updates:\n")
            for repo in successful_updates:
                details_msg += f"  ✓ {repo.name}\n"
            
            details_msg += f"\n{self.tr('Failed updates:')}\n"
            for repo_path, error in failed_updates:
                details_msg += f"  ✗ {repo_path.name}: {error}\n"
            
            InformationBox(
                title=self.tr("Updates Partially Completed"),
                text=self.tr("Some repositories updated successfully"),
                information=self.tr("{success} successful, {failed} failed out of {total} repositories.").format(
                    success=len(successful_updates),
                    failed=len(failed_updates),
                    total=total_repos
                ),
                details=details_msg,
            ).exec()

    @Slot(str, str)
    def _do_git_clone(self, base_path: str, repo_url: str) -> None:
        """
        Checks validity of configured git repo, as well as if it exists
        Handles possible existing repo, and prompts (re)download of repo
        Otherwise it just clones the repo and notifies user

        :param base_path: The path to the local mods folder
        :type base_path: str
        :param repo_url: The URL of the git repository to
        :type repo_url: str
        :return: None
        """

        repo_folder = git_utils.git_get_repo_name(repo_url)
        full_repo_path = Path(base_path) / repo_folder

        if full_repo_path.exists():
            answer = show_dialogue_conditional(
                title=self.tr("Existing repository found"),
                text=self.tr(
                    "An existing local folder that potentially matches this repository was found!"
                ),
                information=(
                    self.tr(
                        "{repo_folder}\n\n"
                        + "How would you like to continue?\n"
                        + "\n1) Clone new repository (Deletes existing and replaces)"
                        + "\n2) Update existing repository (Pull from tracked remote)"
                    ).format(repo_folder=full_repo_path.name)
                ),
                button_text_override=[
                    self.tr("Clone new"),
                    self.tr("Update existing"),
                ],
                details=str(full_repo_path),
            )
            if answer == self.tr("Clone new"):
                self._start_git_clone_worker(repo_url, base_path, force=True)
                return
            elif answer == self.tr("Update existing"):
                self._do_git_updates([full_repo_path])
                return
            else:
                logger.debug("User cancelled git clone operation.")
                return
        else:
            self._start_git_clone_worker(repo_url, str(full_repo_path), force=False)
            return

    def _do_git_push(self, repo_path: Path) -> None:
        """Push changes to the remote repository."""
        raise NotImplementedError

    @Slot()
    def _do_git_install_mod(self) -> None:
        """Install a mod from a remote git repository."""

        args, ok = QInputDialog().getText(
            self.view.mods_panel,
            self.tr("Enter git repo"),
            self.tr("Enter a git repository URL (http/https) to clone to local mods:"),
        )
        if ok:
            self._do_git_clone(
                base_path=self.settings_controller.settings.instances[
                    self.settings_controller.settings.current_instance
                ].local_folder,
                repo_url=args,
            )

        else:
            logger.debug("Cancelling git install mod operation.")

    def _start_git_clone_worker(
        self, repo_url: str, base_path: str, force: bool = False
    ) -> None:
        """Start the git clone worker thread"""
        # Clean up any existing worker
        if self._git_clone_worker is not None:
            self._git_clone_worker.finished.disconnect()
            self._git_clone_worker.progress.disconnect()
            self._git_clone_worker.error.disconnect()
            self._git_clone_worker.quit()
            self._git_clone_worker.wait()
            self._git_clone_worker = None

        # Create and configure the worker
        self._git_clone_worker = GitCloneWorker(
            repo_url=repo_url,
            repo_path=base_path,
            force=force,
            notify_errors=False,  # We handle errors through signals
        )

        # Connect signals
        self._git_clone_worker.finished.connect(self._on_git_clone_finished)
        self._git_clone_worker.progress.connect(self._on_git_clone_progress)
        self._git_clone_worker.error.connect(self._on_git_clone_error)

        # Start the worker
        logger.info(f"Starting git clone worker for: {repo_url}")
        self._git_clone_worker.start()

    def _on_git_clone_progress(self, message: str) -> None:
        """Handle progress updates from git clone worker"""
        logger.debug(f"Git clone progress: {message}")
        # You could emit a signal here to update UI progress indicator if needed

    def _on_git_clone_finished(self, success: bool, message: str, path: str) -> None:
        """Handle completion of git clone operation"""
        logger.info(
            f"Git clone finished: success={success}, message={message}, path={path}"
        )

        if success:
            InformationBox(
                title=self.tr("Clone Successful"),
                text=self.tr("Repository cloned successfully!"),
                information=self.tr("The repository has been cloned to: {path}").format(
                    path=path
                ),
            ).exec()
        else:
            # Error was already logged by worker, just show user notification
            InformationBox(
                title=self.tr("Clone Failed"),
                text=self.tr("Failed to clone repository"),
                information=message,
            ).exec()

        # Clean up worker
        if self._git_clone_worker is not None:
            self._git_clone_worker.finished.disconnect()
            self._git_clone_worker.progress.disconnect()
            self._git_clone_worker.error.disconnect()
            self._git_clone_worker = None

    def _on_git_clone_error(self, error_message: str) -> None:
        """Handle errors from git clone worker"""
        logger.error(f"Git clone error: {error_message}")
        InformationBox(
            title=self.tr("Clone Error"),
            text=self.tr("An error occurred during clone operation"),
            information=error_message,
        ).exec()

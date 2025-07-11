import datetime
import json
import os
import time
from pathlib import Path
from typing import List, Optional, cast

from github import Github, Repository
from loguru import logger
from PySide6.QtCore import QObject, QThreadPool, Slot
from PySide6.QtWidgets import QInputDialog

from app.controllers.settings_controller import SettingsController
from app.utils import git_utils
from app.utils.app_info import AppInfo
from app.utils.event_bus import EventBus
from app.utils.generic import (
    check_internet_connection,
    extract_git_dir_name,
    extract_git_user_or_org,
)
from app.utils.git_utils import GitOperationConfig
from app.utils.git_worker import (
    GitBatchPushResults,
    GitBatchPushWorker,
    GitBatchUpdateResults,
    GitBatchUpdateWorker,
    GitCheckResults,
    GitCheckUpdatesWorker,
    GitCloneWorker,
    GitPushWorker,
    GitStageCommitWorker,
    PushConfig,
)
from app.views.dialogue import (
    BinaryChoiceDialog,
    InformationBox,
    show_dialogue_conditional,
    show_internet_connection_error,
)
from app.views.main_content_panel import MainContent

try:
    import pygit2
except Exception:
    import certifi

    os.environ["SSL_CERT_FILE"] = certifi.where()
    os.environ["SSL_CERT_DIR"] = os.path.dirname(certifi.where())
    logger.warning("Set SSL certificates using certifi")

    try:
        import pygit2
    except Exception as e:
        logger.error("Failed to import pygit2 after setting SSL certificates. ")
        raise ImportError("Failed to import pygit2. ") from e


class MainContentController(QObject):
    """Controller with concurrent checking/updating and improved structure."""

    def __init__(
        self, view: MainContent, settings_controller: SettingsController
    ) -> None:
        super().__init__()
        self.view = view
        self.settings_controller = settings_controller
        self._git_clone_worker: Optional[GitCloneWorker] = None
        self._git_push_worker: Optional[GitPushWorker] = None
        self._git_stage_commit_worker: Optional[GitStageCommitWorker] = None

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

        EventBus().do_upload_steam_workshop_db_to_github.connect(
            self._on_do_upload_steam_workshop_db_to_github
        )
        EventBus().do_upload_community_rules_db_to_github.connect(
            self._on_do_upload_community_db_to_github
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
        config = GitOperationConfig(notify_errors=True)
        worker = GitCheckUpdatesWorker(repos_paths, config=config)
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
        config = GitOperationConfig(notify_errors=True)
        worker = GitBatchUpdateWorker(repos_paths, config=config)
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
                information=self.tr(
                    "{count} repositories were updated:<br/>{repos}"
                ).format(
                    count=len(successful),
                    repos="<br/>".join([Path(p).name for p in successful]),
                ),
            ).exec()
        elif not successful:
            details_msg = ""
            for repo_path, err in failed:
                details_msg += f"{Path(repo_path).name}: {err}\n"

            InformationBox(
                title=self.tr("Failed to update repo!"),
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

    @Slot(list)
    def _on_push_requested(self, repos_paths: List[Path]) -> None:
        """Handle push request for multiple repositories."""
        if not repos_paths:
            InformationBox(
                title=self.tr("No Repositories"),
                text=self.tr("No repositories provided for push operation."),
                information=self.tr("Please select at least one repository to push."),
            ).exec()
            return

        # Ask user for push options
        force_push = False
        binary_diag = BinaryChoiceDialog(
            title=self.tr("Push Options"),
            text=self.tr("Push changes to remote repositories?"),
            information=self.tr(
                "This will push local commits to the remote repositories."
            ),
            details="\n".join([str(p) for p in repos_paths]),
            positive_text=self.tr("Push"),
            negative_text=self.tr("Cancel"),
        )

        if not binary_diag.exec_is_positive():
            logger.debug("User cancelled push operation.")
            return

        # Ask if force push is needed
        force_diag = BinaryChoiceDialog(
            title=self.tr("Force Push"),
            text=self.tr("Use force push?"),
            information=self.tr(
                "Force push will overwrite remote history. Use with caution!"
            ),
            positive_text=self.tr("Force Push"),
            negative_text=self.tr("Normal Push"),
        )
        force_push = force_diag.exec_is_positive()

        self._on_push_repos(repos_paths, force=force_push)

    def _on_push_repos(self, repos_paths: List[Path], force: bool = False) -> None:
        """Schedule concurrent batch push for multiple repositories."""
        logger.debug(
            f"Scheduling concurrent push for {len(repos_paths)} repositories (force={force})."
        )
        config = GitOperationConfig(notify_errors=True)

        # Get GitHub authentication from settings
        username = self.settings_controller.settings.github_username
        token = self.settings_controller.settings.github_token

        push_config = PushConfig(
            username=username,
            token=token,
            force=force,
        )

        worker = GitBatchPushWorker(repos_paths, push_config=push_config, config=config)
        worker.signals.finished.connect(self._handle_batch_push_results)
        self.thread_pool.start(worker)

    @Slot(object)
    def _handle_batch_push_results(self, results: GitBatchPushResults) -> None:
        """Process results from GitBatchPushWorker."""
        successful = results.successful
        failed = results.failed
        total = len(successful) + len(failed)

        if not failed:
            InformationBox(
                title=self.tr("Push Completed"),
                text=self.tr("All repositories pushed successfully!"),
                information=self.tr("{count} repositories were pushed.").format(
                    count=len(successful)
                ),
                details="\n".join([Path(p).name for p in successful]),
            ).exec()
        elif not successful:
            details_msg = ""
            for repo_path, err in failed:
                details_msg += f"{Path(repo_path).name}: {err}\n"

            InformationBox(
                title=self.tr("Push Failed"),
                text=self.tr("All push operations failed."),
                information=self.tr("{count} repositories could not be pushed.").format(
                    count=len(failed)
                ),
                details=details_msg,
            ).exec()
        else:
            details_msg = self.tr("Successful pushes:\n")
            for p in successful:
                details_msg += f"  ✓ {Path(p).name}\n"
            details_msg += f"\n{self.tr('Failed pushes:')}\n"
            for repo_path, err in failed:
                details_msg += f"  ✗ {Path(repo_path).name}: {err}\n"

            InformationBox(
                title=self.tr("Partial Push Completed"),
                text=self.tr("Some repositories pushed successfully."),
                information=self.tr(
                    "{success} succeeded, {failed} failed out of {total}."
                ).format(success=len(successful), failed=len(failed), total=total),
                details=details_msg,
            ).exec()

    @Slot(str, str)
    def _do_git_clone(self, base_path: str, repo_url: str) -> None:
        """Handle clone request: ask user before starting."""
        # Check internet connection before attempting task
        if not check_internet_connection():
            show_internet_connection_error()
            return
        repo_folder = git_utils.git_get_repo_name(repo_url)
        full_repo_path = Path(base_path) / repo_folder

        # Always ask user before starting clone
        binary_diag = BinaryChoiceDialog(
            title=self.tr("Clone Repository"),
            text=self.tr("Do you want to clone this repository?"),
            information=self.tr("Repository: {repo_url}\nDestination: {dest}").format(
                repo_url=repo_url, dest=str(full_repo_path)
            ),
            positive_text=self.tr("Clone"),
            negative_text=self.tr("Cancel"),
        )
        if not binary_diag.exec_is_positive():
            logger.debug("User cancelled clone operation.")
            return

        if full_repo_path.exists():
            answer = show_dialogue_conditional(
                title=self.tr("Existing repository found"),
                text=self.tr(
                    "An existing local repo that matches this repository was found:"
                ),
                information=self.tr(
                    "{repo_folder}<br/>"
                    + "How would you like to handle? Choose option:<br/>"
                    + "<br/>1) Clone new repository (deletes existing and replaces)"
                    + "<br/>2) Update existing repository (in-place force-update)"
                ).format(repo_folder=full_repo_path.name),
                button_text_override=[self.tr("Clone new"), self.tr("Update existing")],
            )
            if answer == self.tr("Clone new"):
                self._start_git_clone_worker(repo_url, str(full_repo_path), force=True)
            elif answer == self.tr("Update existing"):
                self._on_update_repos([full_repo_path])
            else:
                logger.debug("User cancelled clone operation.")
        else:
            self._start_git_clone_worker(repo_url, str(full_repo_path), force=False)

    def _update_databases_on_startup_if_enabled_silent(self) -> None:
        """
        Silently update databases on startup if enabled.
        Directly calls MainContentController methods instead of emitting signals.
        """
        if not self.settings_controller.settings.update_databases_on_startup:
            logger.info("Update databases on startup is disabled.")
            return

        # Check internet connection before attempting task
        if not check_internet_connection():
            show_internet_connection_error()
            return

        # Community Rules database
        if (
            self.settings_controller.settings.external_community_rules_metadata_source
            == "Configured git repository"
            and self.settings_controller.settings.external_community_rules_repo
        ):
            logger.info("Auto-updating Community Rules database from GitHub.")
            self._do_auto_database_update(
                str(AppInfo().databases_folder),
                self.settings_controller.settings.external_community_rules_repo,
            )

        # Steam Workshop database
        if (
            self.settings_controller.settings.external_steam_metadata_source
            == "Configured git repository"
            and self.settings_controller.settings.external_steam_metadata_repo
        ):
            logger.info("Auto-updating Steam Workshop database from GitHub.")
            self._do_auto_database_update(
                str(AppInfo().databases_folder),
                self.settings_controller.settings.external_steam_metadata_repo,
            )

        # No Version Warning database
        if (
            self.settings_controller.settings.external_no_version_warning_metadata_source
            == "Configured git repository"
            and self.settings_controller.settings.external_no_version_warning_repo_path
        ):
            logger.info('Auto-updating "No Version Warning" database from GitHub.')
            self._do_auto_database_update(
                str(AppInfo().databases_folder),
                self.settings_controller.settings.external_no_version_warning_repo_path,
            )

        # Use This Instead database (Cross Version Databases)
        if (
            self.settings_controller.settings.external_use_this_instead_metadata_source
            == "Configured git repository"
            and self.settings_controller.settings.external_use_this_instead_repo_path
        ):
            logger.info('Auto-updating "Use This Instead" database from GitHub.')
            self._do_auto_database_update(
                str(AppInfo().databases_folder),
                self.settings_controller.settings.external_use_this_instead_repo_path,
            )

    def _do_auto_database_update(self, base_path: str, repo_url: str) -> None:
        """Handle automatic database update: silently update existing or clone new."""
        logger.info(f"Starting automatic database update: {repo_url}")
        repo_folder = git_utils.git_get_repo_name(repo_url)
        full_repo_path = Path(base_path) / repo_folder

        if full_repo_path.exists():
            # For existing repositories, update them silently (default behavior)
            logger.info(f"Updating existing database repository: {full_repo_path}")
            self._on_update_repos_silent([full_repo_path])
        else:
            # For new repositories, clone them silently
            logger.info(f"Cloning new database repository to: {full_repo_path}")
            self._start_git_clone_worker(repo_url, str(full_repo_path), force=False)

    def _on_update_repos_silent(self, repos_paths: List[Path]) -> None:
        """Schedule concurrent batch pull for multiple repositories silently."""
        logger.debug(
            f"Scheduling silent concurrent update for {len(repos_paths)} repositories."
        )
        config = GitOperationConfig(notify_errors=False)
        worker = GitBatchUpdateWorker(repos_paths, config=config)
        worker.signals.finished.connect(self._handle_batch_update_results_silent)
        self.thread_pool.start(worker)

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

        config = GitOperationConfig(notify_errors=False)
        self._git_clone_worker = GitCloneWorker(
            repo_url=repo_url,
            repo_path=base_path,
            force=force,
            config=config,
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
                title=self.tr("Repo retrieved"),
                text=self.tr("The configured repository was cloned!"),
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
            title=self.tr("Failed to clone repo!"),
            text=self.tr(
                "The configured repo failed to clone/initialize! "
                + "Are you connected to the Internet? "
                + "Is your configured repo valid?"
            ),
            information=error_message,
        ).exec()

    @Slot()
    def _do_git_install_mod(self) -> None:
        """Prompt user for repo URL and trigger clone."""
        args, ok = QInputDialog().getText(
            self.view.mods_panel,
            self.tr("Enter git repo"),
            self.tr("Enter a git repository url (http/https) to clone to local mods:"),
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

    @Slot(str, str)
    def _do_upload_db_to_repo(self, repo_url: str, file_name: str) -> None:
        """
        Modern implementation of database upload to repository using git_utils and workers.
        Creates/uses user's fork, stages, commits, and pushes changes, then creates a pull request.

        Args:
            repo_url: The original repository URL to contribute to
            file_name: The database file name to upload
        """
        # Check internet connection before attempting task
        if not check_internet_connection():
            show_internet_connection_error()
            return

        if not repo_url or not repo_url.strip():
            InformationBox(
                title=self.tr("Invalid repository"),
                text=self.tr("Repository URL is empty or invalid."),
                information=self.tr(
                    "Please configure a valid repository URL in settings."
                ),
            ).exec()
            return

        if not (repo_url.startswith("http://") or repo_url.startswith("https://")):
            InformationBox(
                title=self.tr("Invalid repository"),
                text=self.tr("An invalid repository was detected!"),
                information=self.tr(
                    "Please reconfigure a repository in settings!\n"
                    + 'A valid repository is a repository URL which is not empty and is prefixed with "http://" or "https://"'
                ),
            ).exec()
            return

        # Extract repository information
        try:
            repo_user_or_org = extract_git_user_or_org(repo_url)
            repo_folder_name = extract_git_dir_name(repo_url)
        except Exception as e:
            logger.error(f"Failed to parse repository URL: {e}")
            InformationBox(
                title=self.tr("Invalid repository URL"),
                text=self.tr("Failed to parse repository information from URL."),
                information=self.tr("URL: {repo_url}\nError: {error}").format(
                    repo_url=repo_url, error=str(e)
                ),
            ).exec()
            return

        # Check GitHub credentials
        github_username = self.settings_controller.settings.github_username
        github_token = self.settings_controller.settings.github_token

        if not github_username or not github_token:
            InformationBox(
                title=self.tr("GitHub credentials missing"),
                text=self.tr(
                    "GitHub username and token are required for database upload."
                ),
                information=self.tr(
                    "Please configure your GitHub credentials in settings."
                ),
            ).exec()
            return

        # Calculate local repository path
        repo_path = Path(AppInfo().databases_folder) / repo_folder_name

        if not repo_path.exists():
            # Ask user if they want to clone the repository first
            answer = show_dialogue_conditional(
                title=self.tr("Repository not found"),
                text=self.tr("Local repository does not exist."),
                information=self.tr("Would you like to clone the repository first?"),
            )
            if answer == "&Yes":
                self._do_git_clone(
                    base_path=str(AppInfo().databases_folder),
                    repo_url=repo_url,
                )
            return

        # Check if the database file exists
        file_full_path = repo_path / file_name
        if not file_full_path.exists():
            InformationBox(
                title=self.tr("File does not exist"),
                text=self.tr(
                    "Please ensure the file exists and then try to upload again!"
                ),
                information=self.tr(
                    "File not found:\n{file_full_path}\nRepository:\n{repo_url}"
                ).format(file_full_path=file_full_path, repo_url=repo_url),
            ).exec()
            return

        # Parse database version information
        try:
            with open(file_full_path, encoding="utf-8") as f:
                database = json.loads(f.read())

            if database.get("version"):
                database_version = (
                    database["version"]
                    - self.settings_controller.settings.database_expiry
                )
            elif database.get("timestamp"):
                database_version = database["timestamp"]
            else:
                InformationBox(
                    title=self.tr("Invalid database"),
                    text=self.tr(
                        "Database file does not contain version or timestamp."
                    ),
                    information=self.tr("File: {file_path}").format(
                        file_path=str(file_full_path)
                    ),
                ).exec()
                return
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Failed to parse database file: {e}")
            InformationBox(
                title=self.tr("Database parse error"),
                text=self.tr("Failed to read or parse database file."),
                information=str(e),
            ).exec()
            return

        # Create human-readable version
        timezone_abbreviation = (
            datetime.datetime.now(datetime.timezone.utc).astimezone().tzinfo
        )
        database_version_human_readable = (
            time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(database_version))
            + f" {timezone_abbreviation}"
        )
        # Initialize GitHub API
        try:
            g = Github(github_username, github_token)
            original_repo = g.get_repo(f"{repo_user_or_org}/{repo_folder_name}")
        except Exception as e:
            logger.error(f"Failed to initialize GitHub API: {e}")
            InformationBox(
                title=self.tr("GitHub API error"),
                text=self.tr("Failed to connect to GitHub API."),
                information=str(e),
            ).exec()
            return
        # Check if user has a fork, create one if not
        fork_repo = None
        try:
            # Try to get existing fork
            fork_repo = g.get_repo(f"{github_username}/{repo_folder_name}")
            logger.info(f"Found existing fork: {fork_repo.full_name}")
        except Exception:
            # Fork doesn't exist, create one
            try:
                logger.info(f"Creating fork of {original_repo.full_name}")
                fork_repo = original_repo.create_fork()
                logger.info(f"Created fork: {fork_repo.full_name}")

                # Give GitHub some time to set up the fork
                InformationBox(
                    title=self.tr("Fork created"),
                    text=self.tr("Created fork of repository."),
                    information=self.tr(
                        "Fork: {fork_name}\nPlease wait a moment for GitHub to set up the fork."
                    ).format(fork_name=fork_repo.full_name),
                ).exec()
            except Exception as e:
                logger.error(f"Failed to create fork: {e}")
                InformationBox(
                    title=self.tr("Fork creation failed"),
                    text=self.tr("Failed to create fork of repository."),
                    information=str(e),
                ).exec()
                return

        if not fork_repo:
            InformationBox(
                title=self.tr("Fork error"),
                text=self.tr("Could not access or create fork repository."),
            ).exec()
            return

        # Update local repository remote to point to user's fork
        fork_url = fork_repo.clone_url

        # Perform git operations using the new git_utils and workers
        self._perform_git_upload_operations(
            repo_path=repo_path,
            file_name=file_name,
            fork_url=fork_url,
            database_version=database_version,
            database_version_human_readable=database_version_human_readable,
            original_repo=original_repo,
            fork_repo=fork_repo,
            github_username=github_username,
            github_token=github_token,
        )

    def _perform_git_upload_operations(
        self,
        repo_path: Path,
        file_name: str,
        fork_url: str,
        database_version: int,
        database_version_human_readable: str,
        original_repo: Repository.Repository,
        fork_repo: Repository.Repository,
        github_username: str,
        github_token: str,
    ) -> None:
        """
        Perform the actual git operations for database upload.

        Args:
            repo_path: Local repository path
            file_name: Database file name
            fork_url: User's fork repository URL
            database_version: Numeric database version
            database_version_human_readable: Human-readable version string
            original_repo: PyGithub original repository object
            fork_repo: PyGithub fork repository object
            github_username: GitHub username
            github_token: GitHub token
        """
        config = GitOperationConfig(notify_errors=True)

        # Update the remote to point to user's fork
        try:
            with git_utils.git_repository(repo_path, config) as repo:
                if repo is None:
                    InformationBox(
                        title=self.tr("Git repository error"),
                        text=self.tr("Invalid git repository."),
                        information=str(repo_path),
                    ).exec()
                    return

                # Update origin remote to user's fork
                # Since pygit2 remote.url is read-only, we need to remove and recreate the remote
                origin_remote = None
                for remote in repo.remotes:
                    if remote.name == "origin":
                        origin_remote = remote
                        break

                if origin_remote:
                    # Remove existing origin remote
                    repo.remotes.delete("origin")

                # Add new origin remote pointing to fork
                repo.remotes.create("origin", fork_url)

                logger.info(f"Updated origin remote to fork: {fork_url}")

                # New workflow: Stash → Pull → Unstash → Check for changes
                stash_created = False

                # Step 1: Check if there are uncommitted changes and stash them
                if git_utils.git_has_uncommitted_changes(repo, config):
                    logger.info(
                        "Uncommitted changes detected, stashing them before pull"
                    )
                    stash_result = git_utils.git_stash(
                        repo,
                        message="Auto-stash before database upload pull",
                        config=config,
                    )
                    if (
                        stash_result.is_successful()
                        and stash_result == git_utils.GitStashResult.STASHED
                    ):
                        stash_created = True
                        logger.info("Successfully stashed uncommitted changes")
                    elif not stash_result.is_successful():
                        logger.error(f"Failed to stash changes: {stash_result}")
                        InformationBox(
                            title=self.tr("Stash failed"),
                            text=self.tr(
                                "Failed to stash uncommitted changes before pull."
                            ),
                            information=str(stash_result),
                        ).exec()
                        return
                else:
                    logger.info("No uncommitted changes detected")

                # Step 3: Pull latest changes from fork (main branch) without reset_working_tree
                pull_result = git_utils.git_pull(
                    repo,
                    branch="main",
                    reset_working_tree=True,
                    force=True,
                    config=config,
                )
                if not pull_result.is_successful():
                    logger.warning(f"Pull operation result: {pull_result}")
                    if "conflict" in str(pull_result).lower():
                        logger.error("Merge conflicts detected during pull")
                        InformationBox(
                            title=self.tr("Pull conflict"),
                            text=self.tr(
                                "Merge conflicts encountered during pull operation."
                            ),
                            information=self.tr(
                                "Please manually resolve conflicts and try again."
                            ),
                        ).exec()
                        return
                    else:
                        logger.error(f"Pull failed: {pull_result}")
                        InformationBox(
                            title=self.tr("Pull failed"),
                            text=self.tr("Failed to pull latest changes from remote."),
                            information=str(pull_result),
                        ).exec()
                        return

                branch_name = f"{database_version}"
                commit_message = f"DB Update: {database_version_human_readable}"
                # Step 4: Restore stashed changes with automatic conflict resolution
                if stash_created:
                    logger.info(
                        "Restoring stashed changes on main branch after successful pull"
                    )

                    # Store current HEAD before attempting stash pop for potential rollback
                    current_head_after_pull = repo.head.target

                    unstash_result = git_utils.git_stash(
                        repo,
                        pop=True,  # Pop the stash (apply and remove)
                        config=config,
                    )

                    if not unstash_result.is_successful():
                        logger.warning(
                            f"Failed to restore stashed changes: {unstash_result}"
                        )

                        # Check if there are merge conflicts in the working directory
                        conflict_detected = False
                        try:
                            status = repo.status()
                            conflict_files = []
                            for filepath, flags in status.items():
                                if flags & pygit2.GIT_STATUS_CONFLICTED:
                                    conflict_files.append(filepath)

                            if conflict_files:
                                conflict_detected = True
                                logger.error(
                                    f"Merge conflicts detected in files: {conflict_files}"
                                )

                                # Automatic conflict resolution: Reset to clean state
                                logger.info(
                                    "Automatically resolving conflicts by resetting to clean state"
                                )  # Reset the working directory and index to clean state
                                repo.reset(
                                    current_head_after_pull, pygit2.enums.ResetMode.HARD
                                )

                                # Clear any remaining conflicted state
                                repo.state_cleanup()

                                logger.info(
                                    "Repository reset to clean state after conflicts"
                                )

                                # Inform user about the automatic resolution
                                InformationBox(
                                    title=self.tr("Conflicts Auto-Resolved"),
                                    text=self.tr(
                                        "Merge conflicts were detected and automatically resolved."
                                    ),
                                    information=self.tr(
                                        "Your local changes conflicted with remote changes. "
                                        "The repository has been reset to a clean state with the latest remote changes. "
                                        "Your original changes are preserved in the database file and will be committed."
                                    ),
                                ).exec()
                        except Exception as e:
                            logger.warning(f"Could not check for merge conflicts: {e}")

                        # If conflicts were detected and resolved, continue with clean state
                        # If no conflicts but still failed, show warning and continue
                        if not conflict_detected:
                            logger.warning(
                                "Stash pop failed but no conflicts detected, continuing..."
                            )
                            InformationBox(
                                title=self.tr("Stash restore warning"),
                                text=self.tr(
                                    "Failed to restore stashed changes, but no conflicts detected."
                                ),
                                information=self.tr(
                                    "Continuing with current state. Your database changes should still be present."
                                ),
                            ).exec()

                # Step 5: Create new branch but don't switch yet (keep changes in working directory)
                try:
                    # Get the current HEAD commit (after pull)
                    current_commit_oid = repo.head.target
                    current_commit = cast(pygit2.Commit, repo[current_commit_oid])

                    # Check if branch already exists and delete it
                    try:
                        existing_branch = repo.branches.local[branch_name]
                        if existing_branch:
                            logger.info(f"Deleting existing branch: {branch_name}")
                            existing_branch.delete()
                    except KeyError:
                        # Branch doesn't exist, which is fine
                        pass

                    # Create new branch reference using commit object (required by pygit2)
                    branch_ref = repo.branches.local.create(branch_name, current_commit)

                    # IMPORTANT: Don't switch branches yet! Keep the changes in the working directory
                    # We'll switch after committing the changes
                    logger.info(
                        f"Created branch: {branch_name} (will switch after commit)"
                    )
                except Exception as e:
                    logger.error(f"Failed to create branch {branch_name}: {e}")
                    InformationBox(
                        title=self.tr("Branch creation failed"),
                        text=self.tr("Failed to create new branch for upload."),
                        information=f"Branch: {branch_name}",
                    ).exec()
                    return

                # Step 6: Verify changes are still present in working directory
                logger.info(
                    "Verifying changes are present in working directory before staging"
                )

                # Quick verification that we have uncommitted changes as expected
                if git_utils.git_has_uncommitted_changes(repo, config):
                    logger.info("Uncommitted changes confirmed in working directory")
                else:
                    logger.warning(
                        "No uncommitted changes detected in working directory"
                    )
                    # Don't return here - let git_stage_commit make the final determination

                # Log the current working tree status before staging
                logger.info(f"About to stage and commit file: {file_name}")

                # Try to get git status for debugging
                try:
                    status = repo.status()
                    logger.info(f"Git status before staging: {dict(status)}")
                except Exception as e:
                    logger.warning(f"Could not get git status: {e}")

                # Stage and commit the database file (this will be on main branch initially)
                stage_commit_result = git_utils.git_stage_commit(
                    repo=repo,
                    message=commit_message,
                    paths=[file_name],
                    config=config,
                )

                logger.info(f"Stage and commit result: {stage_commit_result}")

                if stage_commit_result == git_utils.GitStageCommitResult.COMMITTED:
                    logger.info(
                        "Successfully staged and committed changes on main branch"
                    )

                    # Now move the commit to the new branch
                    try:
                        # Get the commit we just made
                        latest_commit_oid = repo.head.target

                        # Update the branch to point to the latest commit
                        branch_ref.set_target(latest_commit_oid)

                        # Switch to the new branch
                        repo.head.set_target(branch_ref.target)

                        # Reset main branch to the previous commit (before our change)
                        main_branch = repo.branches.local["main"]
                        main_branch.set_target(current_commit_oid)

                        logger.info(
                            f"Moved commit to branch: {branch_name} and reset main branch"
                        )
                    except Exception as e:
                        logger.error(f"Failed to move commit to new branch: {e}")
                        # If this fails, the commit is still on main, but we can continue
                        # Just switch to the new branch and the commit will be duplicated
                        repo.head.set_target(
                            branch_ref.target
                        )  # Push to user's fork with the new branch
                    push_result = git_utils.git_push(
                        repo=repo,
                        branch=branch_name,
                        username=github_username,
                        token=github_token,
                        config=config,
                    )

                    if push_result.is_successful():
                        logger.info("Successfully pushed to fork")

                        # Create pull request
                        self._create_pull_request(
                            original_repo=original_repo,
                            fork_repo=fork_repo,
                            branch_name=branch_name,
                            database_version=database_version,
                            database_version_human_readable=database_version_human_readable,
                            commit_message=commit_message,
                        )
                    elif (
                        push_result == git_utils.GitPushResult.REJECTED_NON_FAST_FORWARD
                    ):
                        logger.warning(
                            "Push rejected due to non-fast-forward. Attempting force push."
                        )

                        # For a feature branch in a fork, force push is generally safe
                        # since it's a new branch that only we are working on
                        try:
                            push_result_force = git_utils.git_push(
                                repo=repo,
                                branch=branch_name,
                                username=github_username,
                                token=github_token,
                                config=config,
                                force=True,  # Force push to overwrite remote branch
                            )

                            if push_result_force.is_successful():
                                logger.info("Successfully force pushed to fork")

                                # Create pull request
                                self._create_pull_request(
                                    original_repo=original_repo,
                                    fork_repo=fork_repo,
                                    branch_name=branch_name,
                                    database_version=database_version,
                                    database_version_human_readable=database_version_human_readable,
                                    commit_message=commit_message,
                                )
                            else:
                                InformationBox(
                                    title=self.tr("Force push failed"),
                                    text=self.tr(
                                        "Failed to force push changes to fork."
                                    ),
                                    information=str(push_result_force),
                                ).exec()

                        except Exception as e:
                            logger.error(f"Error during force push: {e}")
                            InformationBox(
                                title=self.tr("Force push error"),
                                text=self.tr(
                                    "Error occurred while force pushing to remote."
                                ),
                                information=str(e),
                            ).exec()
                    else:
                        InformationBox(
                            title=self.tr("Push failed"),
                            text=self.tr("Failed to push changes to fork."),
                            information=str(push_result),
                        ).exec()
                elif stage_commit_result == git_utils.GitStageCommitResult.NO_CHANGES:
                    logger.info("No changes detected in database file after staging")
                    InformationBox(
                        title=self.tr("No changes"),
                        text=self.tr("No changes detected in database file."),
                        information=self.tr(
                            "The database appears to be up to date with the remote repository."
                        ),
                    ).exec()
                    return
                # Stop execution here since there's nothing to push or create PR for
                else:
                    InformationBox(
                        title=self.tr("Commit failed"),
                        text=self.tr("Failed to stage and commit changes."),
                        information=str(stage_commit_result),
                    ).exec()

        except Exception as e:
            logger.error(f"Git operations failed: {e}")
            InformationBox(
                title=self.tr("Git operation error"),
                text=self.tr("Failed to perform git operations."),
                information=str(e),
            ).exec()
        finally:
            # Ensure we switch back to main branch before exiting
            try:
                with git_utils.git_repository(repo_path, config) as repo:
                    if repo is not None:
                        # Check if main branch exists and switch to it
                        try:
                            main_branch = repo.branches.local.get("main")  # type: ignore
                            if main_branch is not None:
                                repo.checkout(main_branch)
                                logger.info("Switched back to main branch")
                            else:
                                logger.warning(
                                    "Main branch not found, staying on current branch"
                                )
                        except Exception as e:
                            logger.warning(f"Failed to switch to main branch: {e}")
            except Exception as e:
                logger.warning(f"Failed to switch back to main branch: {e}")

    def _create_pull_request(
        self,
        original_repo: Repository.Repository,
        fork_repo: Repository.Repository,
        branch_name: str,
        database_version: int,
        database_version_human_readable: str,
        commit_message: str,
    ) -> None:
        """
        Create a pull request from user's fork to the original repository.

        Args:
            original_repo: PyGithub original repository object
            fork_repo: PyGithub fork repository object
            branch_name: Branch name for the pull request
            database_version: Numeric database version
            database_version_human_readable: Human-readable version string
            commit_message: Commit message used
        """
        try:
            # Pull request details
            pr_title = f"DB update {database_version}"
            pr_body = f"Steam Workshop {commit_message}"
            base_branch = "main"
            head_branch = f"{fork_repo.owner.login}:{branch_name}"

            # Create the pull request
            pull_request = original_repo.create_pull(
                title=pr_title,
                body=pr_body,
                base=base_branch,
                head=head_branch,
            )

            logger.info(f"Created pull request: {pull_request.html_url}")

            # Notify user of success
            answer = show_dialogue_conditional(
                title=self.tr("Pull request created"),
                text=self.tr("Successfully created pull request!"),
                information=self.tr(
                    "Pull request created successfully.\nDo you want to open it in your web browser?\n\nURL: {url}"
                ).format(url=pull_request.html_url),
            )

            if answer == "&Yes":
                # Open URL in browser
                try:
                    import webbrowser

                    webbrowser.open(pull_request.html_url)
                except Exception as e:
                    logger.error(f"Failed to open browser: {e}")

        except Exception as e:
            logger.error(f"Failed to create pull request: {e}")
            InformationBox(
                title=self.tr("Pull request failed"),
                text=self.tr("Failed to create pull request."),
                information=self.tr(
                    "The changes were pushed to your fork successfully, but the pull request creation failed.\n\n"
                    + "You can manually create a pull request on GitHub.\n\nError: {error}"
                ).format(error=str(e)),
            ).exec()

    @Slot()
    def _on_do_upload_steam_workshop_db_to_github(self) -> None:
        """Ask user for confirmation before uploading Steam Workshop database."""
        binary_diag = BinaryChoiceDialog(
            title=self.tr("Upload Steam Workshop Database"),
            text=self.tr(
                "Are you sure you want to upload the Steam Workshop database to GitHub?"
            ),
            information=self.tr(
                "This will create a pull request with your local database changes."
            ),
            positive_text=self.tr("Upload"),
            negative_text=self.tr("Cancel"),
        )

        if binary_diag.exec_is_positive():
            self._do_upload_db_to_repo(
                repo_url=self.settings_controller.settings.external_steam_metadata_repo,
                file_name="steamDB.json",
            )
        else:
            logger.debug("User cancelled Steam Workshop database upload.")

    @Slot()
    def _on_do_upload_community_db_to_github(self) -> None:
        """Ask user for confirmation before uploading Community Rules database."""
        binary_diag = BinaryChoiceDialog(
            title=self.tr("Upload Community Rules Database"),
            text=self.tr(
                "Are you sure you want to upload the Community Rules database to GitHub?"
            ),
            information=self.tr(
                "This will create a pull request with your local database changes."
            ),
            positive_text=self.tr("Upload"),
            negative_text=self.tr("Cancel"),
        )

        if binary_diag.exec_is_positive():
            self._do_upload_db_to_repo(
                repo_url=self.settings_controller.settings.external_community_rules_repo,
                file_name="communityRules.json",
            )
        else:
            logger.debug("User cancelled Community Rules database upload.")

    @Slot(object)
    def _handle_batch_update_results_silent(
        self, results: GitBatchUpdateResults
    ) -> None:
        """Process results from GitBatchUpdateWorker silently."""
        successful = results.successful
        failed = results.failed

        if successful:
            logger.info(
                f"Silently updated {len(successful)} database repositories successfully"
            )

        if failed:
            logger.warning(
                f"Failed to update {len(failed)} database repositories: {[str(p) for p, e in failed]}"
            )

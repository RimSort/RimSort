from pathlib import Path

from loguru import logger
from PySide6.QtCore import QObject, Slot
from PySide6.QtWidgets import QInputDialog

from app.controllers.settings_controller import SettingsController
from app.utils import git_utils
from app.utils.app_info import AppInfo
from app.utils.event_bus import EventBus
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
            logger.debug("User declined git update operation.")

    @Slot(object)
    def _do_git_updates(self, repos_paths: list[Path]) -> None:
        """Update the git repositories in the list."""
        logger.debug(f"Updating {len(repos_paths)} repositories.")
        for repo_path in repos_paths:
            repo = git_utils.git_discover(repo_path)
            if repo is None:
                logger.warning(f"Could not find valid git repository in {repo_path}")
                continue

            try:
                git_utils.git_pull(repo)
                logger.info(f"Successfully updated repository at {repo_path}")
            except Exception as e:
                logger.error(f"Failed to update repository at {repo_path}: {e}")
            finally:
                repo.free()

        logger.debug("Git update operation completed.")

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
                repo, result = git_utils.git_clone(repo_url, base_path, force=True)
                if repo is not None:
                    git_utils.git_cleanup(repo)
                    if result == git_utils.GitCloneResult.CLONED:
                        InformationBox(
                            title=self.tr("Clone Successful"),
                            text=self.tr("Repository cloned successfully!"),
                            information=self.tr(
                                "The repository has been cloned to: {path}"
                            ).format(path=str(full_repo_path)),
                        ).exec()
                return
            elif answer == self.tr("Update existing"):
                self._do_git_updates([full_repo_path])
                return
            else:
                logger.debug("User cancelled git clone operation.")
                return
        else:
            repo, result = git_utils.git_clone(repo_url, full_repo_path)
            if repo is not None:
                git_utils.git_cleanup(repo)
                if result == git_utils.GitCloneResult.CLONED:
                    InformationBox(
                        title=self.tr("Clone Successful"),
                        text=self.tr("Repository cloned successfully!"),
                        information=self.tr(
                            "The repository has been cloned to: {path}"
                        ).format(path=str(full_repo_path)),
                    ).exec()
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

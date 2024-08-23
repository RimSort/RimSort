from pathlib import Path

from loguru import logger
from PySide6.QtCore import QObject, Slot
from PySide6.QtWidgets import QInputDialog

from app.controllers.settings_controller import SettingsController
from app.utils import git_utils
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
        pass

    @Slot(list[Path])
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
                    title="Invalid git repository",
                    text="Could not find a valid git repository in the selected folder.",
                    information=(
                        "Please make sure the selected folder contains a valid git repository."
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
                title="No updates found",
                text="No updates were found in the selected repositories.",
                information=(
                    "All repositories are up to date with their respective remote branches."
                ),
            ).exec()
            return

        details_msg = ""
        for repo_path, walker in updates.items():
            details_msg += f"{repo_path}\n"
            for commit in walker:
                details_msg += f"\t{commit.message}\n"

        binary_diag = BinaryChoiceDialog(
            title="Git Updates Found",
            text=f"{len(updates)} repositories have updates available.",
            information="Would you like to update (pull) them now?",
            details=details_msg,
            positive_text="Update All",
            negative_text="Cancel",
        )

        if binary_diag.exec_is_positive():
            self._do_git_updates(list(updates.keys()))
        else:
            logger.debug("User declined git update operation.")

    @Slot(list[Path])
    def _do_git_updates(self, repos_paths: list[Path]) -> None:
        """Update the git repositories in the list."""

        raise NotImplementedError

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
                title="Existing repository found",
                text="An existing local folder that potentially matches this repository was found!",
                information=(
                    f"{repo_folder}\n\n"
                    + "How would you like to continue?\n"
                    + "\n1) Clone new repository (Deletes existing and replaces)"
                    + "\n2) Update existing repository (Pull from tracked remote)"
                ),
                button_text_override=[
                    "Clone new",
                    "Update existing",
                ],
                details=str(full_repo_path),
            )
            if answer == "Clone new":
                repo, _ = git_utils.git_clone(repo_url, base_path, force=True)
                if repo is not None:
                    git_utils.git_cleanup(repo)
                return
            elif answer == "Update existing":
                raise NotImplementedError
                self._do_git_updates([full_repo_path])
                return
            else:
                logger.debug("User cancelled git clone operation.")
                return
        else:
            repo, _ = git_utils.git_clone(repo_url, base_path)
            if repo is not None:
                git_utils.git_cleanup(repo)
            return

    @Slot()
    def _do_git_install_mod(self) -> None:
        """Install a mod from a remote git repository."""

        args, ok = QInputDialog().getText(
            title="Enter git repo",
            label="Enter a git repository url (http/https) to clone to local mods:",
            parent=self.view.mods_panel,
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

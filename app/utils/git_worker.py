"""Git worker thread for background git operations."""

from pathlib import Path
from typing import Optional

from loguru import logger
from PySide6.QtCore import QThread, Signal

from app.utils import git_utils
from app.utils.git_utils import GitCloneResult


class GitCloneWorker(QThread):
    """Worker thread for git clone operations"""

    # Signals
    finished = Signal(bool, str, str)  # success, message, path
    progress = Signal(str)  # status message
    error = Signal(str)  # error message

    def __init__(
        self,
        repo_url: str,
        repo_path: str | Path,
        checkout_branch: Optional[str] = None,
        depth: int = 1,
        force: bool = False,
        notify_errors: bool = False,  # We'll handle errors through signals
    ):
        """
        Initialize git clone worker

        :param repo_url: The URL of the repository to clone
        :param repo_path: The path to clone the repository to
        :param checkout_branch: The branch to checkout if any
        :param depth: The clone depth
        :param force: Whether to force the clone operation
        :param notify_errors: Whether to show error dialogs (disabled for threading)
        """
        super().__init__()
        self.repo_url = repo_url
        self.repo_path = repo_path
        self.checkout_branch = checkout_branch
        self.depth = depth
        self.force = force
        self.notify_errors = notify_errors

    def run(self) -> None:
        """Execute the git clone operation in background"""
        try:
            logger.info(
                f"Starting git clone in thread: {self.repo_url} to {self.repo_path}"
            )

            # Emit progress update
            self.progress.emit(f"Cloning repository: {self.repo_url}")

            # Perform the clone operation
            repo, result = git_utils.git_clone(
                repo_url=self.repo_url,
                repo_path=self.repo_path,
                checkout_branch=self.checkout_branch,
                depth=self.depth,
                force=self.force,
                notify_errors=self.notify_errors,
            )

            # Determine final path
            repo_folder = git_utils.git_get_repo_name(self.repo_url)
            if isinstance(self.repo_path, str):
                final_path = str(Path(self.repo_path) / repo_folder)
            else:
                final_path = str(self.repo_path / repo_folder)

            # Clean up repository object if successful
            if repo is not None:
                git_utils.git_cleanup(repo)

            # Emit results based on clone result
            if result == GitCloneResult.CLONED:
                success_msg = f"Repository cloned successfully to: {final_path}"
                logger.info(success_msg)
                self.finished.emit(True, success_msg, final_path)
            else:
                error_msg = f"Clone failed: {result}"
                logger.error(error_msg)
                self.finished.emit(False, error_msg, final_path)

        except Exception as e:
            error_msg = f"Unexpected error during clone: {str(e)}"
            logger.error(error_msg)
            self.error.emit(error_msg)
            self.finished.emit(False, error_msg, "")

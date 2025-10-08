import os
from platform import system
from re import compile, search
from typing import Any, Optional, Sequence

import psutil
from loguru import logger
from PySide6.QtCore import QProcess, Qt, Signal
from PySide6.QtGui import QCloseEvent, QFont, QIcon, QKeyEvent, QTextCursor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.utils.app_info import AppInfo
from app.utils.steam.webapi.wrapper import (
    ISteamRemoteStorage_GetPublishedFileDetails,
)
from app.views.dialogue import (
    BinaryChoiceDialog,
    show_dialogue_conditional,
    show_dialogue_file,
    show_warning,
)


class RunnerPanel(QWidget):
    """
    A generic, read-only panel that can be used to display output from something.
    It also has a built-in QProcess functionality.
    """

    closing_signal = Signal()
    steamcmd_downloader_signal = Signal(list)

    def __init__(
        self,
        todds_dry_run_support: bool = False,
        steamcmd_download_tracking: Optional[list[str]] = None,
        steam_db: Optional[dict[str, Any]] = None,
    ):
        """
        Initialize the RunnerPanel widget.

        Args:
            todds_dry_run_support: Whether to support TODDS dry run mode
            steamcmd_download_tracking: List of Steam Workshop IDs to track
            steam_db: Dictionary of Steam mod information
        """
        super().__init__()
        logger.debug("Initializing RunnerPanel")

        # Initialize instance variables
        self.ansi_escape = compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
        self.system = system()
        self.installEventFilter(self)
        self.previous_line = ""
        self.steamcmd_download_tracking = steamcmd_download_tracking or []
        self.steam_db = steam_db or {}
        self.todds_dry_run_support = todds_dry_run_support

        # Process-related variables
        self.process = QProcess()
        self.process_killed = False
        self.process_last_output = ""
        self.process_last_command = ""
        self.process_last_args: Sequence[str] = []
        self.steamcmd_current_pfid: Optional[str] = None
        self.login_error = False
        self.redownloading = False

        # Set up UI components
        self._setup_text_display()
        self._setup_buttons()
        self._setup_progress_bar()
        self._setup_layouts()

        # Clear the display
        self._do_clear_runner()

        # Set the window size
        self.resize(900, 600)

    def _setup_text_display(self) -> None:
        """Set up the text display area."""
        self.text = QPlainTextEdit()
        self.text.verticalScrollBar().setValue(self.text.verticalScrollBar().maximum())
        self.text.setReadOnly(True)
        self.text.setObjectName("RunnerPanelText")

        # Set font based on platform
        font_mapping = {
            "Darwin": "Monaco",
            "Linux": "DejaVu Sans Mono",
            "Windows": "Cascadia Code",
        }
        font_name = font_mapping.get(self.system)
        if font_name:
            self.text.setFont(QFont(font_name))

    def _setup_buttons(self) -> None:
        """Set up the control buttons."""
        # Set object name for styling
        self.setObjectName("RunnerPanel")

        # Clear button
        self.clear_runner_icon = QIcon(
            str(AppInfo().theme_data_folder / "default-icons" / "clear.png")
        )
        self.clear_runner_button = QToolButton()
        self.clear_runner_button.setIcon(self.clear_runner_icon)
        self.clear_runner_button.clicked.connect(self._do_clear_runner)
        self.clear_runner_button.setToolTip(
            self.tr("Clear the text currently displayed by the runner")
        )

        # Restart button
        self.restart_process_icon = QIcon(
            str(AppInfo().theme_data_folder / "default-icons" / "restart_process.png")
        )
        self.restart_process_button = QToolButton()
        self.restart_process_button.setIcon(self.restart_process_icon)
        self.restart_process_button.clicked.connect(self._do_restart_process)
        self.restart_process_button.setToolTip(
            self.tr("Re-run the process last used by the runner")
        )
        self.restart_process_button.hide()  # Hidden until execute() is called

        # Kill button
        self.kill_process_icon = QIcon(
            str(AppInfo().theme_data_folder / "default-icons" / "kill_process.png")
        )
        self.kill_process_button = QToolButton()
        self.kill_process_button.setIcon(self.kill_process_icon)
        self.kill_process_button.clicked.connect(self._do_kill_process)
        self.kill_process_button.setToolTip(
            self.tr("Kill a process currently being executed by the runner")
        )
        self.kill_process_button.hide()  # Hidden until execute() is called

        # Save output button
        self.save_runner_icon = QIcon(
            str(AppInfo().theme_data_folder / "default-icons" / "save_output.png")
        )
        self.save_runner_output_button = QToolButton()
        self.save_runner_output_button.setIcon(self.save_runner_icon)
        self.save_runner_output_button.clicked.connect(self._do_save_runner_output)
        self.save_runner_output_button.setToolTip(
            self.tr("Save the current output to a file")
        )

    def _setup_progress_bar(self) -> None:
        """Set up the progress bar."""
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.hide()
        self.progress_bar.setObjectName("runner")

    def _setup_layouts(self) -> None:
        """Set up the widget layouts."""
        # Create layouts
        self.main_layout = QHBoxLayout()
        self.runner_layout = QVBoxLayout()
        self.actions_bar_layout = QVBoxLayout()

        # Add widgets to layouts
        self.runner_layout.addWidget(self.progress_bar)
        self.runner_layout.addWidget(self.text)

        self.actions_bar_layout.addWidget(self.clear_runner_button)
        self.actions_bar_layout.addWidget(self.restart_process_button)
        self.actions_bar_layout.addWidget(self.kill_process_button)
        self.actions_bar_layout.addWidget(self.save_runner_output_button)

        # Combine layouts
        self.main_layout.addLayout(self.runner_layout)
        self.main_layout.addLayout(self.actions_bar_layout)

        # Set the main layout
        self.setLayout(self.main_layout)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.closing_signal.emit()
        self._do_kill_process()
        event.accept()
        self.destroy()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close()

    def _do_clear_runner(self) -> None:
        self.text.clear()

    def _do_kill_process(self) -> None:
        """Safely terminate the running process and all its child processes."""
        if not self.process or self.process.state() != QProcess.ProcessState.Running:
            return

        try:
            # Get the parent process ID
            pid = self.process.processId()
            parent_process = psutil.Process(pid)

            # First terminate all child processes
            for child in parent_process.children(recursive=True):
                try:
                    child.terminate()
                except psutil.NoSuchProcess:
                    # Process might have already terminated
                    pass

            # Then terminate the parent process
            try:
                parent_process.terminate()
            except psutil.NoSuchProcess:
                # Process might have already terminated
                pass

            # Wait for the process to finish
            self.process.waitForFinished(3000)  # Wait up to 3 seconds

            # If process is still running, kill it forcefully
            if self.process.state() == QProcess.ProcessState.Running:
                logger.warning("Process did not terminate gracefully, forcing kill")
                self.process.kill()

            self.process_killed = True
            logger.debug(f"Process {pid} terminated successfully")

        except Exception as e:
            logger.error(f"Error killing process: {e}")
            # Try direct kill as fallback
            self.process.kill()

    def _do_restart_process(self) -> None:
        if self.process_last_command != "":
            self.message("\nRestarting last used process...\n")
            self.execute(self.process_last_command, self.process_last_args)

    def _do_save_runner_output(self) -> None:
        """
        Save the current output text to a user-specified file.

        Prompts the user for a file location and saves the current
        contents of the text display to that file.
        """
        # Check if there's any text to save
        if not self.text.toPlainText().strip():
            logger.info("No text to save")
            return

        try:
            # Open file dialog to get save location
            logger.info("Opening file dialog to specify output file")
            file_path = show_dialogue_file(
                mode="save",
                caption=self.tr("Save Runner Output"),
                _dir=os.path.expanduser("~"),
                _filter=self.tr("Text files (*.txt)"),
            )

            # If user canceled, exit
            if not file_path:
                logger.info("File save canceled by user")
                return

            logger.info(f"Saving output to: {file_path}")

            # Save the text content to the file
            try:
                with open(file_path, "w", encoding="utf-8") as outfile:
                    outfile.write(self.text.toPlainText())
                logger.info("Output successfully saved")
            except IOError as e:
                logger.error(f"Error writing to file: {e}")

        except Exception as e:
            logger.error(f"Unexpected error in save operation: {e}")

    def change_progress_bar_color(self, state: str) -> None:
        self.progress_bar.setObjectName(state)
        self.progress_bar.style().unpolish(self.progress_bar)
        self.progress_bar.style().polish(self.progress_bar)

    def execute(
        self,
        command: str,
        args: Sequence[str],
        progress_bar: Optional[int] = None,
    ) -> None:
        """
        Execute the given command in a new terminal-like GUI

        Args:
            command: Path to the executable
            args: Arguments for the executable
            progress_bar: Value for the progress bar, None to hide progress bar
        """
        logger.info("RunnerPanel subprocess initiating...")
        # Store command info for potential restart
        self.process_last_command = command
        self.process_last_args = args

        # Show control buttons
        self.restart_process_button.show()
        self.kill_process_button.show()

        # Set up process
        self.process = QProcess(self)
        self.process.setProgram(command)
        self.process.setArguments(args)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardError.connect(self.handle_output)
        self.process.readyReadStandardOutput.connect(self.handle_output)
        self.process.finished.connect(self.finished)

        # Configure progress bar if needed
        if progress_bar is not None:
            self.progress_bar.show()
            self.progress_bar.setValue(0)
            if progress_bar > 0:
                if "steamcmd" in command:
                    self.progress_bar.setRange(0, progress_bar)
                    self.progress_bar.setFormat("%v/%m")

        # Display command being executed (unless in dry run mode)
        if not self.todds_dry_run_support:
            self.message(f"\nExecuting command:\n{command} {' '.join(args)}\n\n")

        # Start the process
        self.process.start()

    def handle_output(self) -> None:
        data = self.process.readAll()
        stdout = self.ansi_escape.sub("", bytes(data.data()).decode("utf8"))
        if self._is_process_running("steamcmd"):
            for line in stdout.splitlines():
                self.message(line)
        else:
            self.message(stdout)

    def message(self, line: str) -> None:
        """
        Process and display a message in the output panel.

        This method handles special formatting and progress tracking for different
        types of processes (steamcmd, todds, query).

        Args:
            line: The text line to process and display
        """
        # Default behavior is to append the line
        overwrite = False

        # Log the message with appropriate context
        if self.process and self.process.state() == QProcess.ProcessState.Running:
            program_name = self.process.program().split("/")[-1]
            logger.debug(f"[{program_name}]\n{line}")
        else:
            logger.debug(f"{line}")

        # Process specific handlers
        if self._is_process_running("steamcmd"):
            overwrite = self._handle_steamcmd_output(line)
        elif self._is_process_running("todds"):
            overwrite = self._handle_todds_output(line)

        # Handle query progress output (applies to any process)
        query_overwrite = self._handle_query_output(line)
        overwrite = overwrite or query_overwrite

        # Display the line (either by overwriting the last line or appending)
        if overwrite:
            self._overwrite_last_line(line.strip())
        else:
            self.text.appendPlainText(line)

        # Store the line for potential future reference
        self.previous_line = line

    def _is_process_running(self, program_name: str) -> bool:
        """Check if a specific process is currently running."""
        if not self.process:
            return False
        if self.process.state() != QProcess.ProcessState.Running:
            return False
        return program_name in self.process.program()

    def _handle_steamcmd_output(self, line: str) -> bool:
        """
        Process steamcmd-specific output.

        Returns:
            bool: True if the line should overwrite the previous line
        """
        overwrite = False

        # Track current download item
        if "Downloading item " in line:
            match = search(r"Downloading item (\d+)...", line)
            if match:
                self.steamcmd_current_pfid = match.group(1)

        # Determine if this line should overwrite the previous one
        if any(
            pattern in line
            for pattern in [
                "] Downloading update (",
                "] Installing update",
                "] Extracting package",
            ]
        ):
            overwrite = True

        # Format specific lines for better readability
        if "workshop_download_item" in line:
            line = line.replace("workshop_download_item", "\n\nworkshop_download_item")
        elif ") quit" in line:
            line = line.replace(") quit", ")\n\nquit")

        # Handle download success and errors
        if (
            f"Success. Downloaded item {self.steamcmd_current_pfid}" in line
            and self.steamcmd_current_pfid in self.steamcmd_download_tracking
        ):
            # Remove the current PFID from tracking if it was successfully downloaded
            self.steamcmd_download_tracking.remove(self.steamcmd_current_pfid)
            self.progress_bar.setValue(self.progress_bar.value() + 1)
        elif "ERROR! Download item " in line:
            # Track failed downloads
            match = search(r"ERROR! Download item (\d+)", line)
            if match:
                pfid = match.group(1)
                if pfid not in self.steamcmd_download_tracking:
                    self.steamcmd_download_tracking.append(pfid)
        elif "ERROR! Not logged on." in line:
            # Handle login error specifically
            self.login_error = True

        return overwrite

    def _handle_todds_output(self, line: str) -> bool:
        """
        Process todds-specific output.

        Returns:
            bool: True if the line should overwrite the previous line
        """
        match = search(r"Progress: (\d+)/(\d+)", line)
        if match:
            self.progress_bar.setRange(0, int(match.group(2)))
            self.progress_bar.setValue(int(match.group(1)))
            return True
        return False

    def _handle_query_output(self, line: str) -> bool:
        """
        Process query-specific output.

        Returns:
            bool: True if the line should overwrite the previous line
        """
        match = search(
            r"IPublishedFileService/(QueryFiles|GetDetails) (page|chunk) \[(\d+)\/(\d+)\]",
            line,
        )
        if match:
            operation, pagination, start, end = match.groups()
            self.progress_bar.setRange(0, int(end))
            self.progress_bar.setValue(int(start))
            return True
        return False

    def _overwrite_last_line(self, text: str) -> None:
        """Replace the last line in the text display with the given text."""
        cursor = self.text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.movePosition(
            QTextCursor.MoveOperation.StartOfLine,
            QTextCursor.MoveMode.KeepAnchor,
        )
        cursor.removeSelectedText()
        cursor.insertText(text)

    def finished(self) -> None:
        """
        Handle process completion, including success/failure reporting and cleanup.
        """
        # Skip detailed output in dry run mode
        if not self.todds_dry_run_support:
            # Show completion status
            status_message = (
                "Subprocess killed!" if self.process_killed else "Subprocess completed."
            )
            self.message(status_message)
            self.process_killed = False  # Reset the kill flag

            # Handle process-specific completion tasks
            if "SteamCMD" in self.windowTitle():
                self._handle_steamcmd_completion()
            elif "todds" in self.windowTitle():
                self._handle_todds_completion()

        # Always clean up the process
        if not self.redownloading:
            self.process.terminate()
            self.process_complete()

    def _handle_steamcmd_completion(self) -> None:
        """Handle SteamCMD-specific completion tasks."""
        # Check if there are any failed downloads to report
        if len(self.steamcmd_download_tracking) == 0:
            self.change_progress_bar_color("success")
            return

        # Check and Handle login error
        if self.login_error:
            self.change_progress_bar_color("error")
            show_warning(
                title=self.tr("SteamCMD Downloader Login error"),
                text=self.tr(
                    "SteamCMD reported a login error. Please ensure you are connected to internet and steamcmd is not blocked by your firewall."
                ),
            )

        # Handle failed downloads
        self.change_progress_bar_color("failure")

        # Resolve mod names for failed downloads
        pfids_to_name = self._resolve_mod_names()

        # Compile details of failed mods for the report
        details = "\n".join(
            f"{pfids_to_name.get(pfid, f'Mod name not found (ID: {pfid})')}"
            for pfid in self.steamcmd_download_tracking
        )
        # Prompt user for action on failed mods
        answer = show_dialogue_conditional(
            title=self.tr("SteamCMD downloader"),
            text=self.tr(
                "SteamCMD failed to download mod(s)! Would you like to retry download of the mods that failed?\n\n"
                "Click 'Show Details' to see a list of mods that failed."
            ),
            details=details,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.redownloading = True
            self.steamcmd_downloader_signal.emit(self.steamcmd_download_tracking)
            self.close()

        else:
            self.redownloading = False
            logger.debug("User declined re-download of failed mods.")

    def _resolve_mod_names(self) -> dict[str, str]:
        """
        Resolve mod names for failed downloads from local DB or Steam API.

        Returns:
            Dictionary mapping mod IDs to mod names
        """
        pfids_to_name = {}
        failed_mods_no_names = []

        # First try to resolve from local database
        if self.steam_db:
            for failed_mod_pfid in self.steamcmd_download_tracking:
                mod_info = self.steam_db.get(failed_mod_pfid)
                if mod_info:
                    mod_name = mod_info.get("steamName") or mod_info.get("name")
                    if mod_name:
                        pfids_to_name[failed_mod_pfid] = mod_name
                    else:
                        failed_mods_no_names.append(failed_mod_pfid)
                else:
                    failed_mods_no_names.append(failed_mod_pfid)

        # For mods not found in local DB, try Steam API
        if failed_mods_no_names:
            try:
                mod_details_lookup = ISteamRemoteStorage_GetPublishedFileDetails(
                    failed_mods_no_names
                )
                if mod_details_lookup:
                    for mod_metadata in mod_details_lookup:
                        mod_title = mod_metadata.get("title")
                        if mod_title:
                            pfids_to_name[mod_metadata["publishedfileid"]] = mod_title
            except Exception as e:
                logger.error(f"Error fetching mod details from Steam API: {e}")

        return pfids_to_name

    def _handle_todds_completion(self) -> None:
        """Handle TODDS-specific completion tasks."""
        self.change_progress_bar_color("success")

    def process_complete(self) -> None:
        diag = BinaryChoiceDialog(
            title=self.tr("Process Complete"),
            text=self.tr("Process complete, you can close the window."),
            positive_text=self.tr("Close Window"),
            negative_text=self.tr("Ok"),
        )
        if diag.exec_is_positive():
            self.close()

import os
from platform import system
from re import compile

import psutil
from PySide6.QtCore import Qt, QEvent, QProcess, Signal
from PySide6.QtGui import QFont, QIcon, QTextCursor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QPlainTextEdit,
    QToolButton,
    QWidget,
    QVBoxLayout,
    QProgressBar,
)
from loguru import logger

from app.models.dialogue import show_dialogue_file, show_dialogue_conditional
from app.utils.app_info import AppInfo
from app.utils.steam.webapi.wrapper import (
    ISteamRemoteStorage_GetPublishedFileDetails,
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
        todds_dry_run_support=False,
        steamcmd_download_tracking=None,
        steam_db=None,
    ):
        super().__init__()

        logger.debug("Initializing RunnerPanel")
        self.ansi_escape = compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
        self.system = system()
        self.installEventFilter(self)

        # Support for tracking SteamCMD download progress
        self.previous_line = ""
        self.steamcmd_download_tracking = steamcmd_download_tracking
        self.steam_db = steam_db

        # The "runner"
        self.text = QPlainTextEdit(readOnly=True)
        self.text.verticalScrollBar().setValue(self.text.verticalScrollBar().maximum())
        # Font cfg by platform
        if self.system == "Darwin":
            self.text.setFont(QFont("Monaco"))
        elif self.system == "Linux":
            self.text.setFont(QFont("DejaVu Sans Mono"))
        elif self.system == "Windows":
            self.text.setFont(QFont("Cascadia Code"))

        # A runner can have a process executed and display it's output
        self.process = QProcess()
        self.process_killed = False
        self.process_last_output = ""
        self.process_last_command = ""
        self.process_last_args = []
        self.todds_dry_run_support = todds_dry_run_support

        # SET STYLESHEET
        self.text.setObjectName("RunnerPaneltext")
        self.setObjectName("RunnerPanel")

        # CREATE WIDGETS
        # Clear btn
        self.clear_runner_icon = QIcon(
            str(AppInfo().theme_data_folder / "default-icons" / "clear.png")
        )
        self.clear_runner_button = QToolButton()
        self.clear_runner_button.setIcon(self.clear_runner_icon)
        self.clear_runner_button.clicked.connect(self._do_clear_runner)
        self.clear_runner_button.setToolTip(
            "Clear the text currently displayed by the runner"
        )
        # Restart btn
        self.restart_process_icon = QIcon(
            str(AppInfo().theme_data_folder / "default-icons" / "restart_process.png")
        )
        self.restart_process_button = QToolButton()
        self.restart_process_button.setIcon(self.restart_process_icon)
        self.restart_process_button.clicked.connect(self._do_restart_process)
        self.restart_process_button.setToolTip(
            "Re-run the process last used by the runner"
        )
        self.restart_process_button.hide()  # Hide this by default - it will be enabled if self.execute()
        # Kill btn
        self.kill_process_icon = QIcon(
            str(AppInfo().theme_data_folder / "default-icons" / "kill_process.png")
        )
        self.kill_process_button = QToolButton()
        self.kill_process_button.setIcon(self.kill_process_icon)
        self.kill_process_button.clicked.connect(self._do_kill_process)
        self.kill_process_button.setToolTip(
            "Kill a process currently being executed by the runner"
        )
        self.kill_process_button.hide()  # Hide this by default - it will be enabled if self.execute()
        # Save process output btn
        self.save_runner_icon = QIcon(
            str(AppInfo().theme_data_folder / "default-icons" / "save_output.png")
        )
        self.save_runner_output_button = QToolButton()
        self.save_runner_output_button.setIcon(self.save_runner_icon)
        self.save_runner_output_button.clicked.connect(self._do_save_runner_output)
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.hide()
        self.progress_bar.setObjectName("default")
        # CREATE LAYOUTS
        self.main_layout = QHBoxLayout()
        self.runner_layout = QVBoxLayout()
        self.actions_bar_layout = QVBoxLayout()
        # ADD WIDGETS TO LAYOUTS
        self.runner_layout.addWidget(self.progress_bar)
        self.runner_layout.addWidget(self.text)
        self.actions_bar_layout.addWidget(self.clear_runner_button)
        self.actions_bar_layout.addWidget(self.restart_process_button)
        self.actions_bar_layout.addWidget(self.kill_process_button)
        self.actions_bar_layout.addWidget(self.save_runner_output_button)
        # ADD LAYOUTS TO LAYOUTS
        self.main_layout.addLayout(self.runner_layout)
        self.main_layout.addLayout(self.actions_bar_layout)
        # WINDOW
        self.setLayout(self.main_layout)
        self.resize(800, 600)

        self._do_clear_runner()

    def closeEvent(self, event):
        self.closing_signal.emit()
        self._do_kill_process()
        event.accept()
        self.destroy()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress and event.key() == Qt.Key_Escape:
            self.close()
            return True

        return super().eventFilter(obj, event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()

    def _do_clear_runner(self):
        self.text.clear()

    def _do_kill_process(self):
        if self.process and self.process.state() == QProcess.Running:
            # Terminate the main process and its child processes
            parent_process = psutil.Process(self.process.processId())
            children = parent_process.children(recursive=True)
            for child in children:
                child.terminate()
            parent_process.terminate()
            self.process.waitForFinished()
            self.process_killed = True

    def _do_restart_process(self):
        if self.process_last_command != "":
            self.message("\nRestarting last used process...\n")
            self.execute(self.process_last_command, self.process_last_args)

    def _do_save_runner_output(self):
        """
        Export the current list of active mods to a user-designated
        file. The current list does not need to have been saved.
        """
        if self.text != "":
            logger.info("Opening file dialog to specify output file")
            file_path = show_dialogue_file(
                mode="save",
                caption="Save runner output",
                _dir=os.path.expanduser("~"),
                _filter="text files (*.txt)",
            )
            logger.info(f"Selected path: {file_path}")
            if file_path:
                logger.info(
                    "Exporting current runner output to the designated txt file"
                )
                with open(file_path, "w", encoding="utf-8") as outfile:
                    logger.info("Writing to file")
                    outfile.write(self.text.toPlainText())

    def change_progress_bar_color(self, state: str):
        self.progress_bar.setObjectName(state)
        self.progress_bar.style().unpolish(self.progress_bar)
        self.progress_bar.style().polish(self.progress_bar)

    def execute(self, command: str, args: list, progress_bar=None, additional=None):
        """ "
        Execute the given command in a new terminal like gui

        command:str, path to .exe
        args:list, argument for .exe
        progress_bar:Optional int, value for the progress bar, -1 to not set value
        additional:Optional, data to parse to the runner
        """
        logger.info("RunnerPanel subprocess initiating...")
        self.restart_process_button.show()
        self.kill_process_button.show()
        self.process_last_command = command
        self.process_last_args = args
        self.process = QProcess(self)
        self.process.setProgram(command)
        self.process.setArguments(args)
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardError.connect(self.handle_output)
        self.process.readyReadStandardOutput.connect(self.handle_output)
        self.process.finished.connect(self.finished)
        if progress_bar:
            self.progress_bar.show()
            self.progress_bar.setValue(0)
            if progress_bar > 0:
                if "steamcmd" in command:
                    self.progress_bar.setRange(0, progress_bar)
                    self.progress_bar.setFormat("%v/%m")
        if not self.todds_dry_run_support:
            self.message(f"\nExecuting command:\n{command} {args}\n\n")
        self.process.start()

    def handle_output(self):
        data = self.process.readAll()
        stdout = self.ansi_escape.sub("", bytes(data).decode("utf8"))
        self.message(stdout)

    def message(self, line: str):
        overwrite = False
        if self.process and self.process.state() == QProcess.Running:
            logger.debug(f"{self.process.program()} {line}")
        else:
            logger.debug(f"{line}")

        # Hardcoded steamcmd progress output support
        if (  # -------STEAM-------
            self.process
            and self.process.state() == QProcess.Running
            and "steamcmd" in self.process.program()
        ):
            if "Downloading item " in line:
                pfid = line.split("Downloading item ")[1].replace("...", "").strip()
                pfid = str(pfid[: pfid.index(" ")])
            # Overwrite when SteamCMD client is doing updates
            if (
                ("] Downloading update (" in line)
                or ("] Installing update" in line)
                or ("] Extracting package" in line)
            ):
                overwrite = True
            # Properly format lines
            if "workshop_download_item" in line:
                line = line.replace(
                    "workshop_download_item", "\n\nworkshop_download_item"
                )
            elif ") quit" in line:
                line = line.replace(") quit", ")\n\nquit")
            # Progress bar output support
            if "Success. Downloaded item " in line:
                self.steamcmd_download_tracking.remove(pfid)
                self.progress_bar.setValue(self.progress_bar.value() + 1)
            elif "ERROR! Download item " in line:
                self.change_progress_bar_color("warn")
                self.progress_bar.setValue(self.progress_bar.value() + 1)
            elif "ERROR! Not logged on." in line:
                self.change_progress_bar_color("critical")
                self.progress_bar.setValue(self.progress_bar.value() + 1)
            # -------STEAM-------

        # Hardcoded todds progress output support
        elif (  # -------TODDS-------
            self.process
            and self.process.state() == QProcess.Running
            and "todds" in self.process.program()
        ):
            if line[1:10] == "Progress:":
                self.progress_bar.setValue(
                    int(line[line.index(":") + 1 : line.index("/")])
                )
            if "Progress: 1/" in line:
                self.progress_bar.setRange(0, int(line.split("Progress: 1/")[1]))
            if "Progress: " in line:
                overwrite = True
            # -------TODDS-------

        # Hardcoded query progress output support
        # -------QUERY-------
        elif (
            "IPublishedFileService/QueryFiles page" in line
            or "IPublishedFileService/GetDetails chunk" in line
        ):
            if int(line[line.index("[") + 1 : line.index("/", 22)]) == 0:
                self.progress_bar.setRange(
                    0, int(line[line.index("/", 22) + 1 : line.index("]")])
                )
            self.progress_bar.setValue(
                int(line[line.index("[") + 1 : line.index("/", 22)])
            )
            overwrite = True
        # -------QUERY-------

        # Overwrite support - set the overwrite bool to overwrite the last line instead of appending
        if overwrite:
            cursor = self.text.textCursor()
            cursor.movePosition(QTextCursor.End)
            cursor.movePosition(QTextCursor.StartOfLine, QTextCursor.KeepAnchor)
            cursor.removeSelectedText()
            cursor.insertText(line.strip())
        else:
            self.text.appendPlainText(line)
        self.previous_line = line

    def finished(self):
        # If todds dry run, we explicitly filter the output
        if not self.todds_dry_run_support:
            # If the process was killed, adjust the message to reflect
            if self.process_killed:
                self.message("Subprocess killed!")
                self.process_killed = False
            else:  # Otherwise, alert the user the process was completed
                self.message("Subprocess completed.")
                # -------STEAM-------
                if "steamcmd" in self.process.program():
                    # If we have mods that did not successfully download
                    if self.steamcmd_download_tracking is not None:
                        if len(self.steamcmd_download_tracking) > 0:
                            self.change_progress_bar_color("emergency")
                            # Try to get the names of our mods
                            pfids_to_name = {}
                            failed_mods_no_names = []
                            # Use Steam DB as initial source
                            if self.steam_db and len(self.steam_db.keys()) > 0:
                                for failed_mod_pfid in self.steamcmd_download_tracking:
                                    if failed_mod_pfid in self.steam_db.keys():
                                        if self.steam_db[failed_mod_pfid].get(
                                            "steamName"
                                        ):
                                            pfids_to_name[failed_mod_pfid] = (
                                                self.steam_db[failed_mod_pfid][
                                                    "steamName"
                                                ]
                                            )
                                        elif self.steam_db[failed_mod_pfid].get("name"):
                                            pfids_to_name[failed_mod_pfid] = (
                                                self.steam_db[failed_mod_pfid]["name"]
                                            )
                                        else:
                                            failed_mods_no_names.append(failed_mod_pfid)
                            # If we didn't return all names from Steam DB, try to look them up using WebAPI
                            if len(failed_mods_no_names) > 0:
                                failed_mods_name_lookup = (
                                    ISteamRemoteStorage_GetPublishedFileDetails(
                                        self.steamcmd_download_tracking
                                    )
                                )
                                if failed_mods_name_lookup != None:
                                    for mod_metadata in failed_mods_name_lookup:
                                        if (
                                            mod_metadata["publishedfileid"]
                                            not in pfids_to_name
                                        ):
                                            if mod_metadata.get("title"):
                                                pfids_to_name[
                                                    mod_metadata["publishedfileid"]
                                                ] = mod_metadata["title"]
                            # Build our report
                            details = ""
                            for failed_mod_pfid in self.steamcmd_download_tracking:
                                if failed_mod_pfid in pfids_to_name:
                                    details = (
                                        details
                                        + f"{pfids_to_name[failed_mod_pfid]} - {failed_mod_pfid}\n"
                                    )
                                else:
                                    details = (
                                        details
                                        + f"*Mod name not found!* - {failed_mod_pfid}\n"
                                    )
                            # Prompt user to redownload mods
                            if (
                                show_dialogue_conditional(
                                    title="SteamCMD downloader",
                                    text='SteamCMD failed to download mod(s)! Would you like to retry download of the mods that failed?\n\nClick "Show Details" to see a list of mods that failed.',
                                    details=details,
                                )
                                == "&Yes"
                            ):
                                self.steamcmd_downloader_signal.emit(
                                    self.steamcmd_download_tracking
                                )
                            else:  # Otherwise do nothing
                                logger.debug(
                                    "User declined re-download of failed mods."
                                )
                        else:
                            self.change_progress_bar_color("success")
                # -------STEAM-------
                # -------TODDS-------
                if "todds" in self.process.program():
                    self.change_progress_bar_color("success")
                # -------TODDS-------
        # Cleanup process
        self.process = None

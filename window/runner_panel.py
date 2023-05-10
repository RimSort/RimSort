from functools import partial
from logger_tt import logger
import os
from pathlib import Path
from platform import system
from re import compile

from PySide6.QtCore import QProcess
from PySide6.QtGui import QFont, QIcon, QTextCursor
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QPlainTextEdit,
    QToolButton,
    QWidget,
    QVBoxLayout,
    QProgressBar,
)

from model.dialogue import show_warning
from util.steam.webapi.wrapper import (
    ISteamRemoteStorage_GetPublishedFileDetails as get_mod_data,
)


class RunnerPanel(QWidget):
    """
    A generic, read-only panel that can be used to display output from something.
    It also has a built-in QProcess functionality.
    """

    def __init__(self, todds_dry_run_support=False):
        super().__init__()
        logger.info("Initializing RunnerPanel")
        self.ansi_escape = compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
        self.system = system()
        self.warningmod = []
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
        self.process_last_command = ""
        self.process_last_args = []
        self.todds_dry_run_support = todds_dry_run_support

        # SET STYLESHEET TO CONFORM WITH GLOBAL CFG
        self.setObjectName("RunnerPanel")
        self.setStyleSheet(  # Add style sheet for styling layouts and widgets
            Path(os.path.join(os.path.dirname(__file__), "../data/style.qss"))
            .resolve()
            .read_text()
        )

        # CREATE WIDGETS
        # Clear btn
        self.clear_runner_icon = QIcon(
            os.path.join(os.path.dirname(__file__), "../data/clear_runner.png")
        )
        self.clear_runner_button = QToolButton()
        self.clear_runner_button.setIcon(self.clear_runner_icon)
        self.clear_runner_button.clicked.connect(self._do_clear_runner)
        self.clear_runner_button.setToolTip(
            "Clear the text currently displayed by the runner"
        )
        # Restart btn
        self.restart_process_icon = QIcon(
            os.path.join(os.path.dirname(__file__), "../data/restart_process.png")
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
            os.path.join(os.path.dirname(__file__), "../data/kill_process.png")
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
            os.path.join(os.path.dirname(__file__), "../data/save_runner_output.png")
        )
        self.save_runner_output_button = QToolButton()
        self.save_runner_output_button.setIcon(self.save_runner_icon)
        self.save_runner_output_button.clicked.connect(self._do_save_runner_output)
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.hide()
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
        self._do_kill_process()
        event.accept()

    def _do_clear_runner(self):
        self.text.clear()
        if not self.todds_dry_run_support:
            self.message("ヽ༼ ຈل͜ຈ༼ ▀̿̿Ĺ̯̿̿▀̿ ̿༽Ɵ͆ل͜Ɵ͆ ༽ﾉ")

    def _do_kill_process(self):
        self.process_killed = True
        if self.process != None:
            self.process.kill()

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
            file_path = QFileDialog.getSaveFileName(
                caption="Save runner output",
                dir=os.path.expanduser("~"),
                filter="text files (*.txt)",
            )
            logger.info(f"Selected path: {file_path[0]}")
            if file_path[0]:
                logger.info(
                    "Exporting current runner output to the designated txt file"
                )
                with open(file_path[0], "w") as outfile:
                    logger.info("Writing to file")
                    outfile.write(self.text.toPlainText())

    def execute(self, command: str, args: list, show_bar=False, additional=None):
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
        if show_bar:
            self.progress_bar.show()
            if "steamcmd" in command:
                self.progress_bar.setRange(0, additional)
        if not self.todds_dry_run_support:
            self.message(f"\nExecuting command:\n{command} {args}\n\n")
        self.process.start()

    def handle_output(self):
        data = self.process.readAll()
        stdout = self.ansi_escape.sub("", bytes(data).decode("utf8"))
        self.message(stdout)

    def message(self, line: str):
        overwrite = False
        logger.debug(f"{self.process.program()}: {line}")
        # Hardcoded steamcmd progress output support
        if (  # -------STEAM-------
            self.process.state() == QProcess.Running
            and "steamcmd" in self.process.program()
        ):
            if (
                ("] Downloading update (" in line)
                or ("] Installing update" in line)
                or ("] Extracting package" in line)
            ):
                overwrite = True
            elif "Success. Downloaded item " in line:
                self.progress_bar.setValue(self.progress_bar.value() + 1)
            elif "ERROR! Download item " in line:
                self.progress_bar.setValue(self.progress_bar.value() + 1)
                tempdata = line.split("ERROR! Download item ")[1]
                self.warningmod = self.warningmod + [
                    tempdata[: tempdata.index("f") - 1]
                ]  # f for failed
            # -------STEAM-------

            # -------TODDS-------
        # Hardcoded todds progress output support
        elif (
            self.process.state() == QProcess.Running
            and "todds" in self.process.program()
        ):
            if "Progress: " in line:
                overwrite = True
            elif (
                self.todds_dry_run_support  # TODO: REMOVE THIS
                # Hardcoded todds --dry-run support - we don't want the total time output until jose fixes
                and ("Total time: " in line)
            ):
                return
            # -------TODDS-------

        if overwrite:
            cursor = self.text.textCursor()
            cursor.movePosition(QTextCursor.End)
            cursor.movePosition(QTextCursor.StartOfLine, QTextCursor.KeepAnchor)
            cursor.removeSelectedText()
            cursor.insertText(line.strip())
        else:
            self.text.appendPlainText(line)

    def finished(self):
        if not self.todds_dry_run_support:
            if self.process_killed:
                self.message("Subprocess killed!")
                self.process_killed = False
            else:
                self.message("Subprocess completed.")
                if "steamcmd" in self.process.program():
                    if self.warningmod != []:
                        tempdata = ""
                        for i in get_mod_data(self.warningmod)["response"][
                            "publishedfiledetails"
                        ]:
                            tempdata = tempdata + i["title"] + "\n"
                        show_warning(
                            title="WARNING steamcmd",
                            text="Warning! some mod has failed to download.",
                            information='Click "Show Details" to see the full report.',
                            details=tempdata,
                        )

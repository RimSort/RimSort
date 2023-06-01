from functools import partial
from tempfile import gettempdir

from logger_tt import logger
import os
from pathlib import Path
from platform import system
from re import compile

from PySide6.QtCore import Qt, QEvent, QProcess
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

from model.dialogue import show_warning, show_dialogue_conditional
from util.steam.webapi.wrapper import ISteamRemoteStorage_GetPublishedFileDetails


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
        self.installEventFilter(self)

        self.steamcmd_failed_mods = []  # Store failed mod ids
        self.previousline = ""
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
        if not self.todds_dry_run_support:
            self.message("ヽ༼ ຈل͜ຈ༼ ▀̿̿Ĺ̯̿̿▀̿ ̿༽Ɵ͆ل͜Ɵ͆ ༽ﾉ")

    def _do_kill_process(self):
        if self.process and self.process.state() == QProcess.Running:
            self.process.kill()
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

    def execute(self, command: str, args: list, progress_bar=None, additional=None):
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
            if "steamcmd" in command:
                self.progress_bar.setValue(0)
                self.progress_bar.setRange(0, additional)
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
            if (
                ("] Downloading update (" in line)
                or ("] Installing update" in line)
                or ("] Extracting package" in line)
            ):
                overwrite = True
            elif "Success. Downloaded item " in line:
                self.progress_bar.setValue(self.progress_bar.value() + 1)
            elif "ERROR!" in line:
                self._BAR_change_color("yellow")
                self.progress_bar.setValue(self.progress_bar.value() + 1)
                tempdata = self.previousline.split("workshop_download_item 294100")[1]
                self.steamcmd_failed_mods = self.steamcmd_failed_mods + [
                    tempdata[: tempdata.index("\n")]
                ]
            # -------STEAM-------

        # Hardcoded todds progress output support
        elif (  # -------TODDS-------
            self.process
            and self.process.state() == QProcess.Running
            and "todds" in self.process.program()
        ):
            if "Progress: " in line:
                overwrite = True
            elif (
                self.todds_dry_run_support  # TODO: REMOVE THIS
                # Hardcoded todds --dry-run support - we don't want the total time output until jose fixes
                and ("Total time: " in line)
            ):
                self.previousline = line
                return
            # -------TODDS-------

        # Hardcoded query progress output support
        # -------QUERY-------
        elif "IPublishedFileService/QueryFiles page" in line:
            overwrite = True
        elif "IPublishedFileService/GetDetails chunk" in line:
            overwrite = True
        # -------QUERY-------

        if overwrite:
            cursor = self.text.textCursor()
            cursor.movePosition(QTextCursor.End)
            cursor.movePosition(QTextCursor.StartOfLine, QTextCursor.KeepAnchor)
            cursor.removeSelectedText()
            cursor.insertText(line.strip())
        else:
            self.text.appendPlainText(line)
        self.previousline = line

    def finished(self):
        if not self.todds_dry_run_support:
            if self.process_killed:
                self.message("Subprocess killed!")
                self.process_killed = False
            else:
                self.message("Subprocess completed.")
                if "steamcmd" in self.process.program():
                    if self.steamcmd_failed_mods != []:
                        self._BAR_change_color("red")
                        tempdata = "Failed to connect"  # Default value
                        GetPublishedFileDetails = (
                            ISteamRemoteStorage_GetPublishedFileDetails(
                                self.steamcmd_failed_mods
                            )
                        )
                        if GetPublishedFileDetails != None:
                            tempdata = ""
                            for i in GetPublishedFileDetails["response"][
                                "publishedfiledetails"
                            ]:
                                tempdata = tempdata + i["title"] + "\n"
                        if tempdata == "Failed to connect":
                            show_warning(
                                title="SteamCMD downloader",
                                text="SteamCMD failed to download mod(s)! Please try to download these mods again!",
                                information='Click "Show Details" to see the full report.',
                                details=tempdata,
                            )
                        else:
                            if (
                                show_dialogue_conditional(
                                    title="SteamCMD downloader",
                                    text="SteamCMD failed to download mod(s)! Retry ?",
                                    information='Click "Show Details" to see the full report.',
                                    details=tempdata,
                                )
                                == "&Yes"
                            ):
                                with open(
                                    os.path.join(
                                        gettempdir(), "steamcmd_download_mods.txt"
                                    ),
                                    "r",
                                ) as re:
                                    steamcmd_mods_path = re.readline().split(
                                        "force_install_dir"
                                    )[1][1:]
                                    print(steamcmd_mods_path)
                                    script = [
                                        f"force_install_dir {steamcmd_mods_path}",
                                        "login anonymous",
                                    ]
                                    re.close()

                                for i in self.steamcmd_failed_mods:
                                    script.append(f"workshop_download_item 294100 {i}")
                                script.extend(["quit\n"])
                                with open(
                                    os.path.join(
                                        gettempdir(), "steamcmd_download_mods.txt"
                                    ),
                                    "w",
                                ) as wr:
                                    wr.write("\n".join(script))

                                self.execute(
                                    self.process_last_command,
                                    self.process_last_args,
                                    True,
                                    len(self.steamcmd_failed_mods),
                                )
                            else:
                                self.close()
                    else:
                        self._BAR_change_color("green")

    def _BAR_change_color(self, color: str):
        default = """
                    QProgressBar {
                        text-align: center;
                    }
                """
        color = "background: {};".format(color)
        self.progress_bar.setStyleSheet(
            default
            + """
                    QProgressBar::chunk {
                        0000_TOREPLACE
                    }
                    """.replace(
                "0000_TOREPLACE", color
            )
        )

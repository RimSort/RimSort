from logger_tt import logger

from PySide6.QtCore import QProcess
from PySide6.QtWidgets import (
    QPlainTextEdit,
    QWidget,
    QVBoxLayout,
)


class RunnerPanel(QWidget):
    """
    A generic, read-only panel that can be used to display output from something.
    It also has a built-in QProcess functionality.
    """

    def __init__(self):
        super().__init__()
        logger.info("Initializing RunnerPanel")
        self.text = QPlainTextEdit(readOnly=True)
        self.text.verticalScrollBar().setValue(self.text.verticalScrollBar().maximum())

        self.process = QProcess = None

        self.layout = QVBoxLayout()
        self.layout.addWidget(self.text)
        self.setLayout(self.layout)
        self.resize(800, 600)

        self.message("ヽ༼ ຈل͜ຈ༼ ▀̿̿Ĺ̯̿̿▀̿ ̿༽Ɵ͆ل͜Ɵ͆ ༽ﾉ")

    def closeEvent(self, event):
        if self.process is not None:
            self.process.kill()
        event.accept()

    def execute(self, command: str, args: list):
        logger.info("RunnerPanel subprocess initiating...")
        self.process = QProcess(self)
        self.process.setProgram(command)
        self.process.setArguments(args)
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardError.connect(self.handle_output)
        self.process.readyReadStandardOutput.connect(self.handle_output)
        self.process.finished.connect(self.finished)
        self.message(f"\nExecuting command:\n{command} {args}")
        self.process.start()

    def handle_output(self):
        data = self.process.readAllStandardOutput()
        stdout = bytes(data).decode("utf8")
        self.message(stdout)

    def message(self, line: str):
        logger.info(line)
        self.text.appendPlainText(line)

    def finished(self):
        self.message("Subprocess completed.")

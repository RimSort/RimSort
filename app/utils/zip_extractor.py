import os
import shutil
import time
from zipfile import ZipFile

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QProgressBar, QPushButton, QVBoxLayout, QWidget


class ZipExtractThread(QThread):
    progress = Signal(int)
    finished = Signal(bool, str)

    def __init__(
        self,
        zip_path: str,
        target_path: str,
        overwrite_all: bool = True,
        delete: bool = False,
    ):
        super().__init__()
        self.zip_path = zip_path
        self.target_path = target_path
        self.overwrite_all = overwrite_all
        self.delete = delete
        self._should_abort = False

    def run(self) -> None:
        start = time.perf_counter()

        with ZipFile(self.zip_path) as zipobj:
            file_list = zipobj.infolist()
            total_files = len(file_list)
            update_interval = max(1, total_files // 100)

            for i, zip_info in enumerate(file_list):
                if self._should_abort:
                    self.finished.emit(False, "Operation aborted")
                    return
                filename = zip_info.filename
                dst = os.path.join(self.target_path, filename)
                os.makedirs(os.path.dirname(dst), exist_ok=True)

                if zip_info.is_dir():
                    os.makedirs(dst, exist_ok=True)
                else:
                    if os.path.exists(dst) and not self.overwrite_all:
                        continue

                    with zipobj.open(zip_info) as src, open(dst, "wb") as out_file:
                        shutil.copyfileobj(src, out_file)

                if i % update_interval == 0 or i == total_files - 1:
                    self.progress.emit(int((i + 1) / total_files * 100))

        end = time.perf_counter()
        elapsed = end - start
        self.finished.emit(
            True,
            f"{self.zip_path} → {self.target_path}\nTime elapsed: {elapsed:.2f} seconds",
        )
        if self.delete:
            os.remove(self.zip_path)

    def stop(self) -> None:
        self._should_abort = True


class ExtractionProgressWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Extracting Zip")
        self.resize(350, 120)

        self.progressBar = QProgressBar()
        self.progressBar.setMinimum(0)
        self.progressBar.setMaximum(100)
        self.progressBar.setValue(0)
        self.progressBar.setVisible(True)

        self.cancel_button = QPushButton("Cancel")

        layout = QVBoxLayout()
        layout.addWidget(self.progressBar)
        self.setLayout(layout)
        layout.addWidget(self.cancel_button)

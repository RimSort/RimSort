import json
import sys

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QApplication

from app.utils.app_info import AppInfo
from app.utils.constants import DEFAULT_USER_RULES
from app.views.main_window import MainWindow


class AppController(QObject):
    def __init__(self):
        super().__init__()

        self.app = QApplication(sys.argv)

        self.app.setStyle("Fusion")

        self.app.setStyleSheet(  # Add style sheet for styling layouts and widgets
            (
                (AppInfo().application_folder / "themes" / "RimPy" / "style.qss")
            ).read_text()
        )

        # One-time initialization of userRules.json
        user_rules_path = AppInfo().databases_folder / "userRules.json"
        if not user_rules_path.exists():
            initial_rules_db = DEFAULT_USER_RULES
            with open(user_rules_path, "w", encoding="utf-8") as output:
                json.dump(initial_rules_db, output, indent=4)

        # Instantiate and show the main window
        self.main_window = MainWindow()
        self.main_window.show()
        self.main_window.initialize_content()

    def run(self) -> int:
        self.main_window.show()
        return self.app.exec()

    def shutdown_watchdog(self) -> None:
        self.main_window.shutdown_watchdog()

    def quit(self) -> None:
        self.app.quit()

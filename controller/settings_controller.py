from PySide6.QtCore import QObject

from model.settings import Settings


class SettingsController(QObject):
    def __init__(self, model: Settings) -> None:
        super().__init__()

        self.settings = model
        self.settings.load()
